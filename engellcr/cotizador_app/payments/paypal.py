import logging

import requests
from django.conf import settings
from django.core.exceptions import PermissionDenied

from .base import PaymentProvider, WebhookResult

logger = logging.getLogger(__name__)


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

    def _api_base(self):
        return 'https://api-m.sandbox.paypal.com' if settings.PAYPAL_MODE == 'sandbox' else 'https://api-m.paypal.com'

    def _get_access_token(self):
        resp = requests.post(
            f'{self._api_base()}/v1/oauth2/token',
            auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
            data={'grant_type': 'client_credentials'},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()['access_token']

    def get_redirect_url(self, payment):
        if not settings.PAYPAL_CLIENT_ID:
            # Not configured yet — architecture is ready, credentials aren't. See PAYPAL_* in .env.example.
            return None

        access_token = self._get_access_token()
        resp = requests.post(
            f'{self._api_base()}/v2/checkout/orders',
            headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
            json={
                'intent': 'CAPTURE',
                'purchase_units': [{
                    'custom_id': payment.internal_reference,
                    'description': f'Cotización Express — {payment.plan.name}',
                    'amount': {'currency_code': payment.currency, 'value': str(payment.amount)},
                }],
                'application_context': {
                    'brand_name': 'Cotización Express',
                    'user_action': 'PAY_NOW',
                    'return_url': settings.PAYPAL_RETURN_URL,
                    'cancel_url': settings.PAYPAL_CANCEL_URL,
                },
            },
            timeout=15,
        )
        resp.raise_for_status()
        order = resp.json()

        payment.external_reference = order['id']
        payment.save(update_fields=['external_reference'])

        approve_link = next((link['href'] for link in order['links'] if link['rel'] == 'approve'), None)
        return approve_link

    def confirm_return(self, request):
        """The customer approved on PayPal's site and landed back on pago_retorno with
        ?token=<order_id>. Capturing here just collects the funds — it deliberately does NOT
        activate the subscription (that only happens from the verified PAYMENT.CAPTURE.COMPLETED
        webhook below, via handle_webhook_event)."""
        order_id = request.GET.get('token')
        if not order_id:
            return
        from ..models import Payment
        payment = Payment.objects.filter(provider=self.code, external_reference=order_id, status=Payment.PENDING).first()
        if payment is None:
            return
        try:
            access_token = self._get_access_token()
            resp = requests.post(
                f'{self._api_base()}/v2/checkout/orders/{order_id}/capture',
                headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
                timeout=15,
            )
            if resp.ok:
                payment.status = Payment.PROCESSING
                payment.save(update_fields=['status'])
            else:
                logger.warning('PayPal capture failed for order %s: %s', order_id, resp.text[:500])
        except requests.RequestException:
            logger.exception('PayPal capture request failed for order %s', order_id)

    def verify_webhook(self, request):
        webhook_id = settings.PAYPAL_WEBHOOK_ID
        if not webhook_id:
            raise PermissionDenied('PayPal no está configurado.')

        import json
        payload = json.loads(request.body or '{}')
        headers = request.headers
        required = ('Paypal-Auth-Algo', 'Paypal-Cert-Url', 'Paypal-Transmission-Id',
                    'Paypal-Transmission-Sig', 'Paypal-Transmission-Time')
        if not all(h in headers for h in required):
            raise PermissionDenied('Faltan encabezados de verificación de PayPal.')

        access_token = self._get_access_token()
        resp = requests.post(
            f'{self._api_base()}/v1/notifications/verify-webhook-signature',
            headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
            json={
                'auth_algo': headers['Paypal-Auth-Algo'],
                'cert_url': headers['Paypal-Cert-Url'],
                'transmission_id': headers['Paypal-Transmission-Id'],
                'transmission_sig': headers['Paypal-Transmission-Sig'],
                'transmission_time': headers['Paypal-Transmission-Time'],
                'webhook_id': webhook_id,
                'webhook_event': payload,
            },
            timeout=15,
        )
        resp.raise_for_status()
        if resp.json().get('verification_status') != 'SUCCESS':
            raise PermissionDenied('Firma de webhook de PayPal inválida.')

        event_type = payload.get('event_type', '')
        resource = payload.get('resource', {})
        # Only these two are actionable for handle_webhook_event ('completed' activates the
        # subscription, 'failed' marks the payment failed). Anything else — notably
        # CHECKOUT.ORDER.APPROVED, which fires before the funds are actually captured and would
        # wrongly mark the payment failed if it fell into the else branch — is left as the raw
        # event_type, which matches neither branch and is safely a no-op (still recorded as a
        # PaymentEvent for the audit trail, just without side effects).
        if event_type == 'PAYMENT.CAPTURE.COMPLETED':
            status = 'completed'
        elif event_type in ('PAYMENT.CAPTURE.DENIED', 'CHECKOUT.ORDER.VOIDED'):
            status = 'failed'
        else:
            status = event_type
        # PAYMENT.CAPTURE.COMPLETED's resource is the capture itself, whose custom_id/invoice_id
        # comes from the purchase_unit — CHECKOUT.ORDER.APPROVED's resource is the order itself.
        payment_reference = str(resource.get('custom_id') or resource.get('invoice_id') or '')
        return WebhookResult(
            external_event_id=str(payload.get('id', '')),
            payment_reference=payment_reference,
            status=status,
            raw_payload=payload,
        )
