from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from ..decorators import business_required
from ..payments import get_provider


@business_required
def pago_retorno(request, metodo):
    """Customer lands here after a gateway checkout. Per spec: NEVER activate a subscription
    just because the customer returned here — real activation only happens via a verified
    webhook (payments/base.py:handle_webhook_event). This is a status/waiting page only."""
    return render(request, 'cotizador_app/pago_retorno.html', {'metodo': metodo})


@csrf_exempt
def pago_webhook(request, metodo):
    try:
        provider = get_provider(metodo)
    except ValueError:
        return JsonResponse({'error': 'unknown provider'}, status=404)

    try:
        event = provider.verify_webhook(request)
    except PermissionDenied:
        return JsonResponse({'error': 'invalid signature'}, status=403)
    except NotImplementedError:
        return JsonResponse({'error': 'not configured'}, status=501)

    provider.handle_webhook_event(event)
    return JsonResponse({'status': 'ok'})
