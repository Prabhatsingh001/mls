"""
Razorpay payment gateway integration.

This module provides functions for creating Razorpay orders and verifying
payment signatures.
"""

import razorpay
from django.conf import settings

from .models import Invoice, RazorpayOrder


def get_razorpay_client():
    """Get configured Razorpay client."""
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def create_razorpay_order(invoice: Invoice) -> RazorpayOrder:
    """
    Create a Razorpay order for the given invoice.

    Args:
        invoice: Invoice to create order for

    Returns:
        RazorpayOrder instance
    """
    client = get_razorpay_client()

    # Amount in paise (Razorpay expects smallest currency unit)
    amount_paise = int(invoice.amount_due * 100)

    order_data = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": invoice.invoice_number,
        "notes": {
            "invoice_id": str(invoice.pk),
            "customer_email": invoice.customer_email,
        },
    }

    razorpay_order = client.order.create(data=order_data) # type: ignore

    # Save order to database
    order = RazorpayOrder.objects.create(
        invoice=invoice,
        order_id=razorpay_order["id"],
        amount=invoice.amount_due,
        currency="INR",
        status=RazorpayOrder.Status.CREATED,
    )

    return order


def verify_payment_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """
    Verify Razorpay payment signature.

    Args:
        razorpay_order_id: Razorpay order ID
        razorpay_payment_id: Razorpay payment ID
        razorpay_signature: Razorpay signature

    Returns:
        True if signature is valid, False otherwise
    """
    client = get_razorpay_client()

    try:
        client.utility.verify_payment_signature( # type: ignore
            {
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            }
        )
        return True
    except razorpay.errors.SignatureVerificationError: # type: ignore
        return False


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    """
    Verify Razorpay webhook signature.

    Args:
        body: Raw request body bytes
        signature: X-Razorpay-Signature header value

    Returns:
        True if signature is valid, False otherwise
    """
    client = get_razorpay_client()

    try:
        client.utility.verify_webhook_signature( # type: ignore
            body.decode("utf-8"),
            signature,
            settings.RAZORPAY_WEBHOOK_SECRET,
        )
        return True
    except razorpay.errors.SignatureVerificationError: # type: ignore
        return False


def get_payment_checkout_data(invoice: Invoice, razorpay_order: RazorpayOrder) -> dict:
    """
    Get data needed for Razorpay checkout.

    Args:
        invoice: Invoice being paid
        razorpay_order: Razorpay order for the invoice

    Returns:
        Dictionary with checkout data
    """
    return {
        "key": settings.RAZORPAY_KEY_ID,
        "amount": int(razorpay_order.amount * 100),
        "currency": razorpay_order.currency,
        "name": "MLS - Micro Labor Services",
        "description": f"Payment for {invoice.invoice_number}",
        "order_id": razorpay_order.order_id,
        "prefill": {
            "name": invoice.customer_name,
            "email": invoice.customer_email,
            "contact": invoice.customer_phone,
        },
        "notes": {
            "invoice_id": str(invoice.pk),
            "invoice_number": invoice.invoice_number,
        },
        "theme": {
            "color": "#1f2937",
        },
    }
