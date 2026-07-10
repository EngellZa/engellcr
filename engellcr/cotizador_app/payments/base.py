from dataclasses import dataclass, field


@dataclass
class WebhookResult:
    external_event_id: str
    payment_reference: str  # matches Payment.internal_reference
    status: str              # normalized: 'completed' | 'failed'
    raw_payload: dict = field(default_factory=dict)


class PaymentProvider:
    """Common interface for redirect/webhook-based gateways (Tilopay, PayPal).
    SINPE Móvil is manual (upload + admin review) and deliberately does NOT
    implement this interface — see payments/sinpe.py."""
    code = None

    def create_pending_payment(self, business, plan):
        """Creates a Payment(status=pending) row before redirecting the customer."""
        from ..models import Payment
        return Payment.objects.create(
            business=business, plan=plan, provider=self.code,
            amount=plan.price_crc, currency='CRC', status=Payment.PENDING,
        )

    def get_redirect_url(self, payment):
        """Returns the hosted-checkout/payment-link URL the customer is redirected to.
        Real implementations must NOT invent API endpoints — until real credentials/API
        details are available, this returns a clearly-labeled placeholder."""
        raise NotImplementedError

    def confirm_return(self, request):
        """Optional hook run when the customer lands back on pago_retorno. Some gateways
        (PayPal's Orders API) need an explicit capture call at this point to actually collect
        the funds — but per the spec, this must NEVER activate the subscription itself; that
        only ever happens via a verified webhook event in handle_webhook_event. Default is a
        no-op for gateways (like Tilopay) that don't need this step."""
        pass

    def verify_webhook(self, request):
        """Validates the webhook signature/secret and returns a WebhookResult.
        Must raise PermissionDenied on an invalid/missing signature."""
        raise NotImplementedError

    def handle_webhook_event(self, event: WebhookResult):
        """Idempotent webhook processing shared by all gateway providers: records the event
        (unique on provider+external_event_id — a duplicate delivery is a no-op), and only
        activates the subscription if the event reports a completed payment."""
        from django.db import IntegrityError, transaction
        from ..models import Payment, PaymentEvent
        from ..services import activate_subscription

        try:
            with transaction.atomic():
                payment_event = PaymentEvent.objects.create(
                    provider=self.code, event_type=event.status,
                    external_event_id=event.external_event_id, raw_payload=event.raw_payload,
                )
        except IntegrityError:
            return  # already processed this exact event — safe no-op

        payment = Payment.objects.filter(internal_reference=event.payment_reference).first()
        if payment is None:
            return
        payment_event.payment = payment
        payment_event.processed = True
        payment_event.save(update_fields=['payment', 'processed'])

        if event.status == 'completed' and payment.status != Payment.APPROVED:
            activate_subscription(payment)
        elif event.status == 'failed':
            payment.status = Payment.FAILED
            payment.save(update_fields=['status'])
