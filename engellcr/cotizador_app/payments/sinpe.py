"""SINPE Móvil is a manual payment method (upload + admin review) — it has no redirect
and no webhook, so it deliberately does not implement the PaymentProvider interface
used by Tilopay/PayPal. All three payment paths converge on services.activate_subscription()."""
from django.db import transaction
from django.utils import timezone

from ..models import Payment, SinpePaymentReceipt, AuditLog
from ..services import activate_subscription


def create_pending_sinpe_payment(business, plan):
    return Payment.objects.create(
        business=business, plan=plan, provider=Payment.SINPE,
        amount=plan.price_crc, currency='CRC', status=Payment.PENDING,
    )


def submit_receipt(payment, *, cloudinary_public_id, resource_type, mime_type, file_size,
                    reference_number, payment_date, note=''):
    receipt = SinpePaymentReceipt.objects.create(
        payment=payment, business=payment.business,
        cloudinary_public_id=cloudinary_public_id, resource_type=resource_type,
        mime_type=mime_type, file_size=file_size,
        reference_number=reference_number, payment_date=payment_date, note=note,
    )
    payment.status = Payment.PROCESSING
    payment.save(update_fields=['status'])
    return receipt


@transaction.atomic
def approve_receipt(receipt, staff_user):
    receipt.status = SinpePaymentReceipt.APPROVED
    receipt.reviewed_by = staff_user
    receipt.reviewed_at = timezone.now()
    receipt.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

    subscription = activate_subscription(receipt.payment, actor=staff_user)

    AuditLog.objects.create(
        actor=staff_user, business=receipt.business, action='sinpe_approved',
        target_repr=str(receipt), metadata={'receipt_id': receipt.id, 'payment_id': receipt.payment_id},
    )
    return subscription


@transaction.atomic
def reject_receipt(receipt, staff_user, reason):
    receipt.status = SinpePaymentReceipt.REJECTED
    receipt.reviewed_by = staff_user
    receipt.reviewed_at = timezone.now()
    receipt.rejection_reason = reason
    receipt.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason'])

    receipt.payment.status = Payment.REJECTED
    receipt.payment.save(update_fields=['status'])

    AuditLog.objects.create(
        actor=staff_user, business=receipt.business, action='sinpe_rejected',
        target_repr=str(receipt), metadata={'receipt_id': receipt.id, 'reason': reason},
    )
