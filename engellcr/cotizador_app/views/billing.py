from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404

from ..decorators import business_required
from ..models import SubscriptionPlan, Payment
from ..payments import get_provider
from ..payments.sinpe import create_pending_sinpe_payment
from ..ratelimit import rate_limit


@business_required
def plan_actual(request):
    context = {
        'subscription': request.business.current_subscription,
        'usage': request.business.current_usage,
        'planes': SubscriptionPlan.objects.filter(is_active=True),
    }
    return render(request, 'cotizador_app/plan.html', context)


@business_required
def plan_mejorar(request):
    planes = SubscriptionPlan.objects.filter(is_active=True).exclude(code=SubscriptionPlan.FREE_TRIAL)
    return render(request, 'cotizador_app/mejorar_plan.html', {'planes': planes})


@business_required
@rate_limit('pago_iniciar', limit=10, window_seconds=3600, key_kind='user')
def pago_iniciar(request, plan_id, metodo):
    plan = get_object_or_404(SubscriptionPlan, pk=plan_id, is_active=True)

    if metodo == Payment.SINPE:
        payment = create_pending_sinpe_payment(request.business, plan)
        return redirect('cotizador_app:sinpe_subir_comprobante', payment_id=payment.id)

    if metodo in (Payment.TILOPAY, Payment.PAYPAL):
        provider = get_provider(metodo)
        payment = provider.create_pending_payment(request.business, plan)
        redirect_url = provider.get_redirect_url(payment)
        if redirect_url:
            return redirect(redirect_url)
        # Not configured yet — show a clear "coming soon" placeholder instead of a broken redirect.
        return render(request, 'cotizador_app/pago_gateway_pendiente.html', {
            'payment': payment, 'metodo': metodo,
        })

    messages.error(request, 'Método de pago no reconocido.')
    return redirect('cotizador_app:plan_mejorar')


@business_required
def pagos_lista(request):
    qs = Payment.objects.filter(business=request.business).select_related('plan')
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'cotizador_app/pagos_lista.html', {'page_obj': page})
