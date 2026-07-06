from .base import PaymentProvider, WebhookResult


def get_provider(code):
    if code == 'tilopay':
        from .tilopay import TilopayProvider
        return TilopayProvider()
    if code == 'paypal':
        from .paypal import PaypalProvider
        return PaypalProvider()
    raise ValueError(f'Proveedor de pago desconocido: {code}')
