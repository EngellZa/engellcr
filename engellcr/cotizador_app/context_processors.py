from decouple import config


def site_settings(request):
    return {
        'WHATSAPP_CONTACT_NUMBER': config('WHATSAPP_CONTACT_NUMBER', default=''),
        'SINPE_MOBILE_NUMBER': config('SINPE_MOBILE_NUMBER', default=''),
        'SINPE_ACCOUNT_HOLDER': config('SINPE_ACCOUNT_HOLDER', default=''),
    }
