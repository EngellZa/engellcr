from django.contrib import messages
from django.shortcuts import render, redirect

from ..cache import cx_get, cx_set, plan_list_key, dashboard_summary_key
from ..decorators import business_required, cotizador_login_required, get_current_business
from ..forms import BusinessForm
from ..models import Quotation


@cotizador_login_required
def perfil_negocio(request):
    """Doubles as onboarding (first save) and profile editing (subsequent saves)."""
    profile = getattr(request.user, 'cotizador_profile', None)
    if profile is None or not profile.email_verified:
        return redirect('cotizador_app:verificacion_pendiente')

    business = get_current_business(request)
    if request.method == 'POST':
        form = BusinessForm(request.POST, request.FILES, instance=business)
        if form.is_valid():
            business = form.save(commit=False)
            business.owner = request.user
            business.save()
            messages.success(request, 'Perfil de negocio actualizado.')
            return redirect('cotizador_app:dashboard')
    else:
        form = BusinessForm(instance=business)
    return render(request, 'cotizador_app/perfil_negocio.html', {'form': form, 'business': business})


@business_required
def dashboard(request):
    business = request.business
    quotations = Quotation.objects.filter(business=business)

    summary_key = dashboard_summary_key(business.id)
    summary = cx_get(summary_key)
    if summary is None:
        summary = {
            'total_cotizaciones': quotations.count(),
            'borradores': quotations.filter(status=Quotation.STATUS_DRAFT).count(),
            'enviadas': quotations.filter(status=Quotation.STATUS_SENT).count(),
            'aprobadas': quotations.filter(status=Quotation.STATUS_APPROVED).count(),
            'pendientes': quotations.filter(status__in=[Quotation.STATUS_SENT]).count(),
        }
        cx_set(summary_key, summary, timeout=60)  # short TTL — counts change as quotations are created

    context = {
        'business': business,
        'subscription': business.current_subscription,
        'usage': business.current_usage,
        'ultimas_cotizaciones': quotations.select_related('client')[:8],
        **summary,
    }
    return render(request, 'cotizador_app/dashboard.html', context)


def landing(request):
    from ..models import SubscriptionPlan
    plans = cx_get(plan_list_key())
    if plans is None:
        plans = list(SubscriptionPlan.objects.filter(is_active=True))
        cx_set(plan_list_key(), plans, timeout=1800)  # 30 min — pricing rarely changes
    return render(request, 'cotizador_app/landing.html', {'plans': plans})
