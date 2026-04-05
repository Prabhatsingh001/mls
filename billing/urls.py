from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    # Customer URLs
    path(
        "invoices/", 
        views.customer_invoices_list, 
        name="customer-invoices"
    ),
    path(
        "invoice/<int:invoice_id>/",
        views.customer_invoice_detail,
        name="customer-invoice-detail",
    ),
    path(
        "invoice/<int:invoice_id>/download/",
        views.customer_download_invoice_pdf,
        name="customer-download-pdf",
    ),
    path(
        "invoice/<int:invoice_id>/pay/",
        views.initiate_payment,
        name="initiate-payment",
    ),
    path(
        "payment/callback/", 
        views.payment_callback, 
        name="payment-callback"
    ),
    path(
        "payment/webhook/", 
        views.razorpay_webhook, 
        name="razorpay-webhook"
    ),
    # Admin URLs
    path(
        "admin/invoices/", 
        views.admin_invoices_list, 
        name="admin-invoices"
    ),
    path(
        "admin/invoice/<int:invoice_id>/",
        views.admin_invoice_detail,
        name="admin-invoice-detail",
    ),
    path(
        "admin/invoice/<int:invoice_id>/record-payment/",
        views.admin_record_payment,
        name="admin-record-payment",
    ),
    path(
        "admin/invoice/<int:invoice_id>/resend/",
        views.admin_resend_invoice,
        name="admin-resend-invoice",
    ),
    path(
        "admin/invoice/<int:invoice_id>/regenerate-pdf/",
        views.admin_regenerate_pdf,
        name="admin-regenerate-pdf",
    ),
    path(
        "admin/invoice/<int:invoice_id>/cancel/",
        views.admin_cancel_invoice,
        name="admin-cancel-invoice",
    ),
]
