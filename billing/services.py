from decimal import Decimal

from django.utils import timezone

from .models import Invoice, InvoiceLineItem


def create_invoice_for_project(project_id):
    """
    Create a complete invoice from a completed project.
    This function handles all the business logic for invoice creation.
    """
    from services.models import Project

    project = (
        Project.objects.select_related(
            "job_request__customer",
            "job_request__service",
        )
        .prefetch_related(
            "project_items",
            "extra_materials",
        )
        .get(pk=project_id)
    )

    # Check if invoice already exists
    if hasattr(project, "invoice"):
        return project.invoice # type: ignore

    customer = project.job_request.customer
    service = project.job_request.service

    # Create the invoice with immediate due date
    today = timezone.now().date()
    invoice = Invoice.objects.create(
        project=project,
        customer=customer,
        customer_name=customer.full_name,
        customer_email=customer.email,
        customer_phone=customer.phone_number or "",
        billing_address=project.job_request.site_address,
        due_date=today,  # Immediate payment
        terms="Payment is due immediately upon project completion.",
    )

    display_order = 0

    # Add service base price as first line item
    InvoiceLineItem.objects.create(
        invoice=invoice,
        item_type=InvoiceLineItem.ItemType.SERVICE,
        description=f"Service: {service.title}",
        quantity=Decimal("1"),
        unit_price=service.base_price,
        line_total=service.base_price,
        display_order=display_order,
    )
    display_order += 1

    # Add project items (materials, tasks, tools)
    for item in project.project_items.all(): # type: ignore
        item_type = InvoiceLineItem.ItemType.MATERIAL
        if item.item_type == "Task":
            item_type = InvoiceLineItem.ItemType.LABOR

        unit_price = item.unit_cost + (item.extra_cost or Decimal("0"))
        line_total = unit_price * item.quantity

        InvoiceLineItem.objects.create(
            invoice=invoice,
            item_type=item_type,
            description=item.item_name,
            quantity=Decimal(str(item.quantity)),
            unit_price=unit_price,
            line_total=line_total,
            project_item=item,
            display_order=display_order,
        )
        display_order += 1

    # Add extra materials added during project execution
    for extra in project.extra_materials.all(): # type: ignore
        if extra.unit_cost is None:
            continue

        line_total = extra.unit_cost * extra.quantity

        InvoiceLineItem.objects.create(
            invoice=invoice,
            item_type=InvoiceLineItem.ItemType.EXTRA,
            description=f"Extra: {extra.material_name}",
            quantity=Decimal(str(extra.quantity)),
            unit_price=extra.unit_cost,
            line_total=line_total,
            extra_material=extra,
            display_order=display_order,
        )
        display_order += 1

    # Recalculate totals
    invoice.calculate_totals()
    invoice.status = Invoice.Status.SENT
    invoice.save()

    return invoice
