from django.conf import settings
from django.core.exceptions import PermissionDenied

from .base import PaymentProvider, WebhookResult


class PaypalProvider(PaymentProvider):
    code = 'paypal'

    def create_pending_payment(self, business, plan):
        """PayPal doesn't settle in colones (CRC) — charge in USD instead of the
        CRC default from PaymentProvider.create_pending_payment."""
        from ..models import Payment
        return Payment.objects.create(
            business=business, plan=plan, provider=self.code,
            amount=plan.price_usd, currency='USD', status=Payment.PENDING,
        )

    def get_redirect_url(self, payment):
        if not settings.PAYPAL_CLIENT_ID:
            # Not configured yet — architecture is ready, credentials aren't. See PAYPAL_* in .env.example.
            return None
        # TODO: real API call — create a PayPal order server-side (never expose PAYPAL_CLIENT_SECRET
        # to the frontend) using settings.PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET / PAYPAL_MODE and
        # settings.PAYPAL_RETURN_URL / PAYPAL_CANCEL_URL, then return PayPal's approval URL.
        # Do not invent the endpoint/payload shape here.
        raise NotImplementedError('Integración real de PayPal pendiente de credenciales.')

    def verify_webhook(self, request):
        webhook_id = settings.PAYPAL_WEBHOOK_ID
        if not webhook_id:
            raise PermissionDenied('PayPal no está configurado.')
        # TODO: replace with PayPal's real webhook signature verification
        # (POST to /v1/notifications/verify-webhook-signature) once credentials are available.
        import json
        payload = json.loads(request.body or '{}')
        event_type = payload.get('event_type', '')
        resource = payload.get('resource', {})
        return WebhookResult(
            external_event_id=str(payload.get('id', '')),
            payment_reference=str(resource.get('custom_id', '')),
            status='completed' if event_type == 'CHECKOUT.ORDER.APPROVED' else 'failed',
            raw_payload=payload,
        )
