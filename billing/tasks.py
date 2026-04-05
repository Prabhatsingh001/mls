"""
Asynchronous Celery tasks for billing operations.

This module handles invoice creation, PDF generation, and email notifications
as background tasks using Celery.
"""

from celery import shared_task
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.shortcuts import get_object_or_404
from weasyprint import HTML
import markdown


@shared_task()
def create_invoice_task(project_id):
    """
    Create an invoice for a completed project asynchronously.

    Args:
        project_id: ID of the project to create invoice for
    """
    from .services import create_invoice_for_project

    invoice = create_invoice_for_project(project_id)

    if invoice:
        # Queue PDF generation
        generate_amount_due_receipt_pdf_task(invoice.pk) # type: ignore

    return invoice.pk if invoice else None


@shared_task(bind=True, max_retries=3)
def generate_invoice_pdf_task(self, invoice_id, pdf_name="payment_pending"):
    from .models import Invoice, CompanyConfig

    try:
        invoice = (
            Invoice.objects.select_related(
                "project__job_request__service__category",
                "customer",
            )
            .prefetch_related("line_items")
            .get(pk=invoice_id)
        )

        company_config = CompanyConfig.objects.first()

        # Skip if already exists
        if invoice.pdf_file:
            return invoice_id

        # Markdown → HTML
        terms_md = invoice.terms
        if isinstance(terms_md, tuple):
            terms_md = terms_md[0]

        terms_html = markdown.markdown(
            terms_md,
            extensions=["extra", "sane_lists", "nl2br", "smarty"],
        )

        # Render template
        html_content = render_to_string(
            "billing/pdf/invoice.html",
            {
                "invoice": invoice,
                "company_name": company_config.company_name if company_config else "MLS - Micro Labor Services",
                "company_address": company_config.company_address
                if company_config
                else "Default Address",
                "company_phone": company_config.company_phone
                if company_config
                else "+91 XXXXX XXXXX",
                "company_email": company_config.company_email
                if company_config
                else settings.EMAIL_HOST_USER,
                "company_gstin": company_config.gst_number
                if company_config
                else "GSTIN",
                "terms_html": terms_html,
            },
        )

        # 🔥 WeasyPrint PDF generation
        pdf_bytes = HTML(
            string=html_content,
            base_url=settings.BASE_DIR,  # IMPORTANT for static/media files
        ).write_pdf(
            stylesheets=None  # optional CSS files
        )

        # Save PDF
        filename = f"{invoice.invoice_number}-{pdf_name}.pdf"
        invoice.pdf_file.save(filename, ContentFile(pdf_bytes), save=False) # type: ignore
        invoice.save(update_fields=["pdf_file"])

        return invoice_id

    except Exception as e:
        print(f"Error generating PDF for invoice {invoice_id}: {e}")
        raise self.retry(exc=e, countdown=5)


@shared_task()
def generate_amount_due_receipt_pdf_task(invoice_id):
    """
    Generate amount due receipt PDF for an invoice asynchronously.

    Args:
        invoice_id: ID of the invoice to generate receipt for
    """
    generate_invoice_pdf_task(invoice_id, pdf_name="amount_due_receipt") # type: ignore
    send_invoice_email_task(invoice_id) # type: ignore


@shared_task()
def generate_payment_confirmation_pdf_task(invoice_id):
    """
    Generate payment confirmation PDF for an invoice asynchronously.

    Args:
        invoice_id: ID of the invoice to generate payment confirmation for
    """
    from .models import Invoice,Payment
    try:
        invoice = Invoice.objects.get(pk=invoice_id)
        if invoice.pdf_file:
            invoice.pdf_file.close()  # Close existing PDF file if open
            invoice.pdf_file.delete()  # Delete existing PDF file
            invoice.save(update_fields=["pdf_file"])  # Clear the pdf_file field
        generate_invoice_pdf_task(invoice_id, pdf_name="payment_confirmation") # type: ignore
        payment = get_object_or_404(Payment, invoice_id=invoice_id)
        send_payment_confirmation_email_task(payment.pk) # type: ignore
    except Invoice.DoesNotExist:
        print(f"Invoice with ID {invoice_id} does not exist.")
    except Exception as e:
        print(f"Error generating payment confirmation PDF for invoice {invoice_id}: {e}")
        raise



@shared_task()
def send_invoice_email_task(invoice_id):
    """
    Send invoice email to customer with PDF attachment.

    Args:
        invoice_id: ID of the invoice to send
    """
    from notification.models import Notification
    from notification.services import notify_user

    from .models import Invoice, CompanyConfig

    company_config = CompanyConfig.objects.first()
    invoice = Invoice.objects.select_related(
        "customer",
        "project__job_request__service",
    ).get(pk=invoice_id)

    subject = f"Invoice {invoice.invoice_number} - MLS"

    view_url = (
        f"{settings.PROTOCOL}://{settings.SITE_DOMAIN}/billing/invoice/{invoice.pk}/"
    )

    html_content = render_to_string(
        "billing/emails/invoice_email.html",
        {
            "invoice": invoice,
            "view_url": view_url,
            "company_name": company_config.company_name if company_config else "MLS - Micro Labor Services", # type: ignore
        },
    )

    text_content = f"""
Dear {invoice.customer_name},

Your invoice {invoice.invoice_number} for Rs. {invoice.total_amount} is ready.

Service: {invoice.project.job_request.service.title}
Amount Due: Rs. {invoice.amount_due}
Due Date: {invoice.due_date.strftime("%B %d, %Y")}

View your invoice online: {view_url}

Thank you for choosing MLS!

Best regards,
MLS - Micro Labor Services
    """

    email = EmailMultiAlternatives(
        subject,
        text_content.strip(),
        settings.EMAIL_HOST_USER,
        [invoice.customer_email],
    )
    email.attach_alternative(html_content, "text/html")

    # Attach PDF if available
    if invoice.pdf_file:
        invoice.pdf_file.seek(0)
        email.attach(
            f"{invoice.invoice_number}-amount-due-receipt.pdf",
            invoice.pdf_file.read(),
            "application/pdf",
        )
        invoice.pdf_file.close()

    email.send(fail_silently=True)

    # Create in-app notification
    notify_user(
        user=invoice.customer,
        type=Notification.Type.PAYMENT_RECEIVED,
        title="Invoice Ready",
        message=f"Your invoice {invoice.invoice_number} for Rs. {invoice.total_amount} is ready for payment.",
        obj=invoice.project,
    )

    return invoice_id


@shared_task()
def send_payment_confirmation_email_task(payment_id):
    """
    Send payment confirmation email to customer.

    Args:
        payment_id: ID of the payment to confirm
    """
    from notification.models import Notification
    from notification.services import notify_user

    from .models import Payment

    payment = Payment.objects.select_related(
        "invoice__customer",
        "invoice__project__job_request__service",
    ).get(pk=payment_id)

    invoice = payment.invoice
    subject = f"Payment Received - {invoice.invoice_number}"

    html_content = render_to_string(
        "billing/emails/payment_confirmation.html",
        {
            "payment": payment,
            "invoice": invoice,
            "company_name": "MLS - Micro Labor Services",
        },
    )

    text_content = f"""
Dear {invoice.customer_name},

We have received your payment of Rs. {payment.amount} for invoice {invoice.invoice_number}.

Payment Method: {payment.method}
Transaction ID: {payment.transaction_id or payment.razorpay_payment_id or "N/A"}
Date: {payment.payment_date.strftime("%B %d, %Y at %I:%M %p")}

{"Invoice Status: Fully Paid" if invoice.is_paid else f"Remaining Balance: Rs. {invoice.amount_due}"}

Thank you for your payment!

Best regards,
MLS - Micro Labor Services
    """

    email = EmailMultiAlternatives(
        subject,
        text_content.strip(),
        settings.EMAIL_HOST_USER,
        [invoice.customer_email],
    )
    email.attach_alternative(html_content, "text/html")
    # Attach PDF if available
    if invoice.pdf_file:
        invoice.pdf_file.seek(0)
        email.attach(
            f"{invoice.invoice_number}-amount-paid.pdf",
            invoice.pdf_file.read(),
            "application/pdf",
        )
        invoice.pdf_file.close()
    email.send(fail_silently=True)

    # Create in-app notification
    notify_user(
        user=invoice.customer,
        type=Notification.Type.PAYMENT_RECEIVED,
        title="Payment Received",
        message=f"Your payment of Rs. {payment.amount} for invoice {invoice.invoice_number} has been received.",
        obj=invoice.project,
    )

    return payment_id
