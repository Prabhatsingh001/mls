from django.contrib import admin
from django.utils.html import format_html

from .models import CompanyConfig, Invoice, InvoiceLineItem, Payment, RazorpayOrder


class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 0
    fields = ("item_type", "description", "quantity", "unit_price", "line_total")
    readonly_fields = ("line_total",)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = (
        "amount",
        "method",
        "status",
        "transaction_id",
        "payment_date",
        "recorded_by",
    )
    readonly_fields = ("recorded_by",)


class RazorpayOrderInline(admin.TabularInline):
    model = RazorpayOrder
    extra = 0
    fields = ("order_id", "amount", "currency", "status", "created_at")
    readonly_fields = ("order_id", "amount", "currency", "status", "created_at")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_number",
        "customer_name",
        "project_link",
        "total_amount",
        "amount_paid",
        "status_badge",
        "issue_date",
        "due_date",
    )
    list_filter = ("status", "issue_date", "due_date")
    search_fields = ("invoice_number", "customer_name", "customer_email")
    readonly_fields = (
        "invoice_number",
        "subtotal",
        "tax_amount",
        "total_amount",
        "amount_paid",
        "amount_due",
        "created_at",
        "updated_at",
    )
    inlines = [InvoiceLineItemInline, PaymentInline, RazorpayOrderInline]
    date_hierarchy = "issue_date"

    fieldsets = (
        (
            "Invoice Info",
            {
                "fields": (
                    "invoice_number",
                    "project",
                    "status",
                    "due_date",
                    "paid_date",
                )
            },
        ),
        (
            "Customer Details",
            {
                "fields": (
                    "customer",
                    "customer_name",
                    "customer_email",
                    "customer_phone",
                    "billing_address",
                )
            },
        ),
        (
            "Financial",
            {
                "fields": (
                    "subtotal",
                    "discount_amount",
                    "discount_description",
                    "tax_rate",
                    "tax_amount",
                    "total_amount",
                    "amount_paid",
                    "amount_due",
                )
            },
        ),
        ("Documents", {"fields": ("pdf_file",)}),
        ("Notes", {"fields": ("notes", "terms")}),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def project_link(self, obj):
        return format_html(
            '<a href="/admin/services/project/{}/change/">PRJ-{}</a>',
            obj.project.pk,
            obj.project.pk,
        )

    project_link.short_description = "Project" # type: ignore

    def status_badge(self, obj):
        colors = {
            "DRAFT": "#6b7280",
            "SENT": "#3b82f6",
            "PAID": "#10b981",
            "PARTIAL": "#f59e0b",
            "OVERDUE": "#ef4444",
            "CANCELLED": "#6b7280",
            "REFUNDED": "#8b5cf6",
        }
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:4px; font-size:11px;">{}</span>',
            colors.get(obj.status, "#6b7280"),
            obj.get_status_display(),
        )

    status_badge.short_description = "Status" # type: ignore


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "invoice",
        "amount",
        "method",
        "status_badge",
        "transaction_id",
        "payment_date",
        "recorded_by",
    )
    list_filter = ("method", "status", "payment_date")
    search_fields = (
        "invoice__invoice_number",
        "transaction_id",
        "razorpay_payment_id",
    )
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "payment_date"

    fieldsets = (
        ("Payment Info", {"fields": ("invoice", "amount", "method", "status")}),
        (
            "Transaction Details",
            {"fields": ("transaction_id", "reference_number")},
        ),
        (
            "Razorpay Details",
            {
                "fields": (
                    "razorpay_order_id",
                    "razorpay_payment_id",
                    "razorpay_signature",
                ),
                "classes": ("collapse",),
            },
        ),
        ("Recording", {"fields": ("recorded_by", "payment_date", "notes")}),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def status_badge(self, obj):
        colors = {
            "PENDING": "#f59e0b",
            "COMPLETED": "#10b981",
            "FAILED": "#ef4444",
            "REFUNDED": "#8b5cf6",
        }
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:4px; font-size:11px;">{}</span>',
            colors.get(obj.status, "#6b7280"),
            obj.get_status_display(),
        )

    status_badge.short_description = "Status" # type: ignore


@admin.register(RazorpayOrder)
class RazorpayOrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_id",
        "invoice",
        "amount",
        "currency",
        "status_badge",
        "created_at",
    )
    list_filter = ("status", "currency", "created_at")
    search_fields = ("order_id", "invoice__invoice_number")
    readonly_fields = ("created_at",)

    def status_badge(self, obj):
        colors = {
            "CREATED": "#3b82f6",
            "PAID": "#10b981",
            "FAILED": "#ef4444",
            "EXPIRED": "#6b7280",
        }
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; '
            'border-radius:4px; font-size:11px;">{}</span>',
            colors.get(obj.status, "#6b7280"),
            obj.get_status_display(),
        )

    status_badge.short_description = "Status" # type: ignore

@admin.register(CompanyConfig)
class CompanyConfigAdmin(admin.ModelAdmin):
    list_display = ("company_name", "pan_number", "company_email", "company_phone")