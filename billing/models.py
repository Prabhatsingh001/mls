from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum
from django.conf import settings


class Invoice(models.Model):
    """Invoice generated for completed projects."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SENT = "SENT", "Sent"
        PAID = "PAID", "Paid"
        PARTIALLY_PAID = "PARTIAL", "Partially Paid"
        OVERDUE = "OVERDUE", "Overdue"
        CANCELLED = "CANCELLED", "Cancelled"
        REFUNDED = "REFUNDED", "Refunded"

    invoice_number = models.CharField(max_length=20, unique=True, editable=False)

    # One-to-one relationship with Project ensures each project has at most one invoice, and invoice is directly linked to its project
    project = models.OneToOneField(
        "services.Project", on_delete=models.PROTECT,related_name="invoice")
    
    # customer details are denormalized for historical accuracy, as customer info may change over time
    customer = models.ForeignKey(
        "authentication.User",on_delete=models.PROTECT,related_name="invoices")
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=15, blank=True)
    billing_address = models.TextField(blank=True)

    # financial fields
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("18.00"),help_text="GST percentage")
    tax_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount_description = models.CharField(max_length=255, blank=True)
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"))
    amount_paid = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"))
    amount_due = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.DRAFT)
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    paid_date = models.DateField(null=True, blank=True)

    pdf_file = models.FileField(upload_to="invoices/pdf/%Y/%m/", null=True, blank=True)

    notes = models.TextField(
        blank=True, help_text="Internal notes (not shown on invoice)"
    )
    terms = models.TextField(blank=True, help_text="Payment terms shown on invoice")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["invoice_number"]),
        ]

    def __str__(self):
        return f"{self.invoice_number} - {self.customer_name}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self._generate_invoice_number()
        super().save(*args, **kwargs)

    def _generate_invoice_number(self):
        """Generate unique invoice number: INV-YYYY-NNNNN"""
        year = timezone.now().year
        #TODO optimize this by caching last invoice number per year, to avoid hitting DB every time
        # also avoid race condition by using select_for_update in transaction when creating new invoice
        last_invoice = (
            Invoice.objects.filter(invoice_number__startswith=f"INV-{year}-")
            .order_by("-invoice_number")
            .first()
        )

        if last_invoice:
            last_num = int(last_invoice.invoice_number.split("-")[-1])
            new_num = last_num + 1
        else:
            new_num = 1

        return f"INV-{year}-{new_num:05d}"

    def calculate_totals(self):
        """Recalculate all totals from line items."""
        self.subtotal = self.line_items.aggregate(total=Sum("line_total"))[ # type: ignore
            "total"
        ] or Decimal("0.00")
        self.tax_amount = (self.subtotal - self.discount_amount) * (
            self.tax_rate / Decimal("100")
        )
        self.total_amount = self.subtotal - self.discount_amount + self.tax_amount
        self.amount_due = self.total_amount - self.amount_paid

    @property
    def is_paid(self):
        return self.status == self.Status.PAID

    @property
    def is_overdue(self):
        return (
            self.status
            not in [self.Status.PAID, self.Status.CANCELLED, self.Status.REFUNDED]
            and self.due_date < timezone.now().date()
        )


class InvoiceLineItem(models.Model):
    """Individual line items on an invoice."""

    class ItemType(models.TextChoices):
        SERVICE = "SERVICE", "Service"
        MATERIAL = "MATERIAL", "Material"
        LABOR = "LABOR", "Labor"
        EXTRA = "EXTRA", "Extra Material"
        OTHER = "OTHER", "Other"

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="line_items")
    item_type = models.CharField(max_length=20, choices=ItemType.choices)
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("1.00")
    )
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    display_order = models.PositiveIntegerField(default=0)

    project_item = models.ForeignKey(
        "services.ProjectItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_line_items",
    )
    extra_material = models.ForeignKey(
        "services.ProjectExtraMaterial",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_line_items",
    )

    class Meta:
        ordering = ["display_order", "id"]

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} - Rs. {self.line_total}"


class Payment(models.Model):
    """Track payments against invoices."""

    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        UPI = "UPI", "UPI"
        CARD = "CARD", "Credit/Debit Card"
        BANK_TRANSFER = "BANK", "Bank Transfer"
        CHEQUE = "CHEQUE", "Cheque"
        RAZORPAY = "RAZORPAY", "Razorpay"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payments",
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.PENDING
    )

    transaction_id = models.CharField(max_length=100, blank=True)
    reference_number = models.CharField(max_length=100, blank=True)
    razorpay_payment_id = models.CharField(
        max_length=100, unique=True, null=True, blank=True
    )
    razorpay_signature = models.CharField(max_length=255, blank=True)

    recorded_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
    )
    razorpay_order = models.ForeignKey(
        "RazorpayOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )
    notes = models.TextField(blank=True)
    payment_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-payment_date"]
        indexes = [
            models.Index(fields=["invoice", "-payment_date"]),
            models.Index(fields=["status", "-payment_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["razorpay_payment_id"],
                name="unique_razorpay_payment"
            )
        ]

    def __str__(self):
        return f"Payment of Rs. {self.amount} for {self.invoice.invoice_number}"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)

        if is_new and self.status == Payment.Status.COMPLETED:
            self._update_invoice_payment_status()

    def _update_invoice_payment_status(self):
        from decimal import Decimal

        with transaction.atomic():
            invoice = Invoice.objects.select_for_update().get(pk=self.invoice.pk)

            total_paid = invoice.payments.filter( # type: ignore
                status=Payment.Status.COMPLETED
            ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

            invoice.amount_paid = total_paid
            invoice.amount_due = invoice.total_amount - total_paid

            if total_paid >= invoice.total_amount:
                invoice.status = Invoice.Status.PAID
                invoice.paid_date = self.payment_date.date()
            elif total_paid > 0:
                invoice.status = Invoice.Status.PARTIALLY_PAID

            invoice.save(update_fields=["amount_paid", "amount_due", "status", "paid_date"])


class RazorpayOrder(models.Model):
    """Track Razorpay payment orders."""

    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"
        EXPIRED = "EXPIRED", "Expired"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="razorpay_orders",
    )
    order_id = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="INR")
    status = models.CharField(
        max_length=15, choices=Status.choices, default=Status.CREATED
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order_id"])
        ]

    def __str__(self):
        return f"Razorpay Order {self.order_id} for {self.invoice.invoice_number}"


class CompanyConfig(models.Model):
    """Singleton model to store company-wide billing settings."""
    # future fields for company details, tax info, etc. can be added here
    gst_number = models.CharField(max_length=20, default="29XXXXX1234X1Z5", help_text="GSTIN number for tax purposes")
    pan_number = models.CharField(max_length=10, default="ABCDE1234F", help_text="PAN number for tax purposes")
    company_name = models.CharField(max_length=255, default="MLS - Micro Labor Services")
    company_address = models.TextField(default="123 Main Street, Bengaluru, Karnataka, India")
    company_email = models.EmailField(default=settings.EMAIL_HOST_USER)
    company_phone = models.CharField(max_length=15, default="+91-9876543210")
    terms_and_conditions = models.TextField(blank=True, default="Payment is due immediately upon project completion.", help_text="Default terms and conditions for invoices")

    class Meta:
        verbose_name = "Company Configuration"

    def __str__(self):
        return "Company Configuration"

    def save(self, *args, **kwargs):
        if not self.pk and CompanyConfig.objects.exists():
            raise ValueError("Only one CompanyConfig instance allowed.")
        super().save(*args, **kwargs)