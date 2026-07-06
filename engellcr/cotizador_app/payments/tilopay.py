from django.conf import settings
from django.core.exceptions import PermissionDenied

from .base import PaymentProvider, WebhookResult


class TilopayProvider(PaymentProvider):
    code = 'tilopay'

    def get_redirect_url(self, payment):
        if not settings.TILOPAY_API_KEY:
            # Not configured yet — architecture is ready, credentials aren't. See TILOPAY_* in .env.example.
            return None
        # TODO: real API call — create a Tilopay hosted-checkout session using
        # settings.TILOPAY_API_KEY / TILOPAY_API_SECRET / TILOPAY_MERCHANT_ID and
        # settings.TILOPAY_RETURN_URL / TILOPAY_CANCEL_URL, then return the checkout URL
        # Tilopay responds with. Do not invent the endpoint/payload shape here.
        raise NotImplementedError('Integración real de Tilopay pendiente de credenciales.')

    def verify_webhook(self, request):
        secret = settings.TILOPAY_WEBHOOK_SECRET
        signature = request.headers.get('X-Tilopay-Signature', '')
        if not secret or signature != secret:
            raise PermissionDenied('Firma de webhook de Tilopay inválida.')
        # TODO: replace with Tilopay's real signature verification once documented/available.
        import json
        payload = json.loads(request.body or '{}')
        return WebhookResult(
            external_event_id=str(payload.get('event_id', '')),
            payment_reference=str(payload.get('reference', '')),
            status='completed' if payload.get('status') == 'approved' else 'failed',
            raw_payload=payload,
        )
