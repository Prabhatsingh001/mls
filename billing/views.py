import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from auditapp.models import AuditLog
from auditapp.tasks import record_audit_log_tasks
from auditapp.utils import _log_details
from authentication.decorators import role_required
from authentication.models import User

from .models import Invoice, Payment, RazorpayOrder
from .razorpay import (
    create_razorpay_order,
    get_payment_checkout_data,
    verify_payment_signature,
    verify_webhook_signature,
)
from .tasks import send_invoice_email_task, generate_payment_confirmation_pdf_task

logger = logging.getLogger(__name__)


# ============== Customer Views ==============


@login_required()
@role_required([User.Role.CUSTOMER])
def customer_invoices_list(request):
    """List all invoices for the logged-in customer."""
    invoices = (
        Invoice.objects.filter(customer=request.user)
        .select_related("project__job_request__service")
        .order_by("-created_at")
    )

    paginator = Paginator(invoices, 10)
    page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "billing/customer/invoices_list.html",
        {"invoices": page},
    )


@login_required()
@role_required([User.Role.CUSTOMER])
def customer_invoice_detail(request, invoice_id):
    """View invoice details with payment option."""
    invoice = get_object_or_404(
        Invoice.objects.select_related(
            "project__job_request__service__category",
            "project__technician",
        ).prefetch_related("line_items", "payments"),
        pk=invoice_id,
        customer=request.user,
    )

    # Check if there's an active Razorpay order
    active_order = invoice.razorpay_orders.filter(  # type: ignore
        status=RazorpayOrder.Status.CREATED
    ).first()

    checkout_data = None
    if active_order and invoice.amount_due > 0:
        checkout_data = get_payment_checkout_data(invoice, active_order)

    return render(
        request,
        "billing/customer/invoice_detail.html",
        {
            "invoice": invoice,
            "checkout_data": json.dumps(checkout_data) if checkout_data else None,
            "razorpay_key": settings.RAZORPAY_KEY_ID,
        },
    )


@login_required()
@role_required([User.Role.CUSTOMER, User.Role.ADMIN])
def customer_download_invoice_pdf(request, invoice_id):
    """Download invoice PDF."""
    if request.user.role == User.Role.CUSTOMER:
        invoice = get_object_or_404(
            Invoice,
            pk=invoice_id,
            customer=request.user,
        )
    else:
        invoice = get_object_or_404(Invoice, pk=invoice_id)

    if not invoice.pdf_file:
        raise Http404("PDF not available yet. Please try again later.")

    return FileResponse(
        invoice.pdf_file.open("rb"),
        as_attachment=True,
        filename=f"{invoice.invoice_number}.pdf",
    )


@login_required()
@role_required([User.Role.CUSTOMER])
@require_POST
def initiate_payment(request, invoice_id):
    """Create Razorpay order and return checkout data."""
    invoice = get_object_or_404(
        Invoice,
        pk=invoice_id,
        customer=request.user,
    )

    if invoice.status == Invoice.Status.PAID:
        return JsonResponse({"error": "Invoice already paid"}, status=400)

    if invoice.amount_due <= 0:
        return JsonResponse({"error": "No amount due"}, status=400)

    try:
        # Create new Razorpay order
        razorpay_order = create_razorpay_order(invoice)
        checkout_data = get_payment_checkout_data(invoice, razorpay_order)

        return JsonResponse(
            {
                "success": True,
                "checkout_data": checkout_data,
            }
        )
    except Exception as e:
        logger.error(f"Failed to create Razorpay order: {e}")
        return JsonResponse(
            {"error": "Failed to initiate payment. Please try again."},
            status=500,
        )


@login_required()
@role_required([User.Role.CUSTOMER])
@require_POST
def payment_callback(request):
    """Handle Razorpay payment callback (client-side)."""
    try:
        data = json.loads(request.body)
        razorpay_order_id = data.get("razorpay_order_id")
        razorpay_payment_id = data.get("razorpay_payment_id")
        razorpay_signature = data.get("razorpay_signature")

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return JsonResponse({"error": "Missing payment data"}, status=400)

        # Verify signature
        if not verify_payment_signature(
            razorpay_order_id, razorpay_payment_id, razorpay_signature
        ):
            return JsonResponse({"error": "Invalid payment signature"}, status=400)

        # Find the order
        razorpay_order = RazorpayOrder.objects.get(
            order_id=razorpay_order_id
        )

        # Ensure customer owns this invoice
        if razorpay_order.invoice.customer != request.user:
            return JsonResponse({"error": "Unauthorized"}, status=403)

        return JsonResponse(
            {
                "success": True,
                "message": "Payment recieved, confirming...",
                "redirect_url": f"/billing/invoice/{razorpay_order.invoice.pk}/",
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Payment callback error: {e}")
        return JsonResponse(
            {"error": "Payment verification failed"},
            status=500,
        )


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """Handle Razorpay server-to-server webhook."""
    signature = request.headers.get("X-Razorpay-Signature")

    if not signature:
        return JsonResponse({"error": "Missing signature"}, status=400)

    if not verify_webhook_signature(request.body, signature):
        return JsonResponse({"error": "Invalid signature"}, status=400)

    try:
        payload = json.loads(request.body)
        event = payload.get("event")

        if event == "payment.captured":
            payment_entity = payload["payload"]["payment"]["entity"]
            razorpay_order_id = payment_entity.get("order_id")
            razorpay_payment_id = payment_entity.get("id")
            amount_paise = payment_entity.get("amount")

            from decimal import Decimal

            amount = Decimal(amount_paise) / 100

            with transaction.atomic():
                razorpay_order = (
                    RazorpayOrder.objects.select_for_update()
                    .filter(order_id=razorpay_order_id)
                    .first()
                )

                if not razorpay_order:
                    logger.warning(
                        f"Razorpay order not found for ID: {razorpay_order_id}"
                    )
                    return JsonResponse(
                        {"status": "ok"}
                    )  # Acknowledge to prevent retries

                if (
                    razorpay_order
                    and razorpay_order.status != RazorpayOrder.Status.PAID
                ):
                    razorpay_order.status = RazorpayOrder.Status.PAID
                    razorpay_order.save(update_fields=["status"])

                    payment, created = Payment.objects.get_or_create(
                        razorpay_payment_id=razorpay_payment_id,
                        defaults={
                            "invoice": razorpay_order.invoice,
                            "amount": amount,
                            "method": Payment.Method.RAZORPAY,
                            "razorpay_order_id": razorpay_order.pk,  # this is a FK to RazorpayOrder, not the ID string
                            "status": Payment.Status.COMPLETED,
                            "payment_date": timezone.now(),
                        },
                    )

                    if created:
                        payment.invoice.status = Invoice.Status.PAID
                        payment.invoice.amount_paid = amount
                        payment.invoice.amount_due = payment.invoice.amount_due - amount
                        payment.invoice.save(update_fields=["status", "amount_paid", "amount_due"])
                        transaction.on_commit(
                            lambda: generate_payment_confirmation_pdf_task.delay(
                                payment.invoice.pk
                            )  # type: ignore
                        )

        elif event == "payment.failed":
            payment_entity = payload["payload"]["payment"]["entity"]
            razorpay_order_id = payment_entity.get("order_id")

            RazorpayOrder.objects.filter(order_id=razorpay_order_id).update(
                status=RazorpayOrder.Status.FAILED
            )

        return JsonResponse({"status": "ok"})

    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return JsonResponse({"error": "Processing failed"}, status=500)


# ============== Admin Views ==============


@login_required()
@role_required([User.Role.ADMIN])
def admin_invoices_list(request):
    """Admin view to list all invoices with filters."""
    invoices = Invoice.objects.select_related(
        "customer",
        "project__job_request__service",
    ).order_by("-created_at")

    # Filters
    status_filter = request.GET.get("status")
    if status_filter and status_filter in Invoice.Status.values:
        invoices = invoices.filter(status=status_filter)

    customer_id = request.GET.get("customer")
    if customer_id:
        invoices = invoices.filter(customer_id=customer_id)

    search = request.GET.get("search", "").strip()
    if search:
        invoices = invoices.filter(invoice_number__icontains=search) | invoices.filter(
            customer_name__icontains=search
        )

    paginator = Paginator(invoices, 20)
    page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "billing/admin/invoices_list.html",
        {
            "invoices": page,
            "statuses": Invoice.Status.choices,
            "current_status": status_filter,
            "search": search,
        },
    )


@login_required()
@role_required([User.Role.ADMIN])
def admin_invoice_detail(request, invoice_id):
    """Admin view of invoice with payment recording capability."""
    invoice = get_object_or_404(
        Invoice.objects.select_related(
            "project__job_request__service__category",
            "project__technician",
            "customer",
        ).prefetch_related("line_items", "payments__recorded_by"),
        pk=invoice_id,
    )

    return render(
        request,
        "billing/admin/invoice_detail.html",
        {
            "invoice": invoice,
            "payment_methods": Payment.Method.choices,
        },
    )


@login_required()
@role_required([User.Role.ADMIN])
@require_POST
def admin_record_payment(request, invoice_id):
    """Record a manual payment against an invoice."""
    invoice = get_object_or_404(Invoice, pk=invoice_id)

    amount = request.POST.get("amount", "").strip()
    method = request.POST.get("method", "")
    transaction_id = request.POST.get("transaction_id", "").strip()
    notes = request.POST.get("notes", "").strip()

    if not amount or not method:
        messages.error(request, "Amount and payment method are required.")
        return redirect("billing:admin-invoice-detail", invoice_id=invoice_id)

    try:
        from decimal import Decimal

        amount_decimal = Decimal(amount)

        if amount_decimal <= 0:
            messages.error(request, "Amount must be greater than zero.")
            return redirect("billing:admin-invoice-detail", invoice_id=invoice_id)

        payment = Payment.objects.create(
            invoice=invoice,
            amount=amount_decimal,
            method=method,
            status=Payment.Status.COMPLETED,
            transaction_id=transaction_id,
            recorded_by=request.user,
            notes=notes,
            payment_date=timezone.now(),
        )

        # Audit log
        log_details = _log_details(
            request,
            category=AuditLog.Category.BUSINESS,
            action="payment_recorded",
            description=f"Payment of Rs. {amount} recorded for {invoice.invoice_number}",
            target=invoice,
            metadata={
                "payment_id": payment.pk,
                "amount": str(amount),
                "method": method,
            },
        )
        transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore

        # Send confirmation email
        transaction.on_commit(
            lambda: generate_payment_confirmation_pdf_task.delay(payment.invoice.pk)  # type: ignore
        )

        messages.success(request, f"Payment of Rs. {amount} recorded successfully.")

    except ValueError:
        messages.error(request, "Invalid amount format.")
    except Exception as e:
        logger.error(f"Failed to record payment: {e}")
        messages.error(request, f"Failed to record payment: {e}")

    return redirect("billing:admin-invoice-detail", invoice_id=invoice_id)


@login_required()
@role_required([User.Role.ADMIN])
@require_POST
def admin_resend_invoice(request, invoice_id):
    """Resend invoice email to customer."""
    invoice = get_object_or_404(Invoice, pk=invoice_id)
    send_invoice_email_task.delay(invoice.pk)  # type: ignore

    messages.success(
        request,
        f"Invoice {invoice.invoice_number} will be resent to {invoice.customer_email}.",
    )
    return redirect("billing:admin-invoice-detail", invoice_id=invoice_id)


@login_required()
@role_required([User.Role.ADMIN])
@require_POST
def admin_regenerate_pdf(request, invoice_id):
    """Regenerate invoice PDF."""
    from .tasks import generate_invoice_pdf_task

    invoice = get_object_or_404(Invoice, pk=invoice_id)
    invoice.pdf_file.close()  # Close the file if it's open
    invoice.pdf_file.delete(save=True)  # Delete old PDF
    transaction.on_commit(lambda: generate_invoice_pdf_task.delay(invoice.pk))  # type: ignore

    messages.success(
        request,
        f"PDF for {invoice.invoice_number} is being regenerated.",
    )
    return redirect("billing:admin-invoice-detail", invoice_id=invoice_id)


@login_required()
@role_required([User.Role.ADMIN])
@require_POST
def admin_cancel_invoice(request, invoice_id):
    """Cancel an invoice."""
    invoice = get_object_or_404(Invoice, pk=invoice_id)

    if invoice.status == Invoice.Status.PAID:
        messages.error(request, "Cannot cancel a paid invoice.")
        return redirect("billing:admin-invoice-detail", invoice_id=invoice_id)

    invoice.status = Invoice.Status.CANCELLED
    invoice.save(update_fields=["status"])

    # Audit log
    log_details = _log_details(
        request,
        category=AuditLog.Category.BUSINESS,
        action="invoice_cancelled",
        description=f"Invoice {invoice.invoice_number} cancelled",
        target=invoice,
    )
    transaction.on_commit(lambda: record_audit_log_tasks.delay(log_details))  # type: ignore

    messages.success(request, f"Invoice {invoice.invoice_number} has been cancelled.")
    return redirect("billing:admin-invoice-detail", invoice_id=invoice_id)
