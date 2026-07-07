from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404

from ..decorators import role_required
from ..models import (Role, UserRole, Business, BusinessNote, SubscriptionPlan, Subscription,
                       Payment, PaymentEvent, SinpePaymentReceipt, AuditLog, Quotation)
from ..payments.sinpe import approve_receipt, reject_receipt


@role_required(Role.ADMIN, Role.SUPPORT)
def staff_dashboard(request):
    context = {
        'total_negocios': Business.objects.filter(is_deleted=False).count(),
        'suscripciones_activas': Subscription.objects.filter(status=Subscription.ACTIVE).count(),
        'sinpe_pendientes': SinpePaymentReceipt.objects.filter(status=SinpePaymentReceipt.PENDING_REVIEW).count(),
        'pagos_pendientes': Payment.objects.filter(status=Payment.PENDING).count(),
    }
    return render(request, 'cotizador_app/staff_dashboard.html', context)


@role_required(Role.ADMIN, Role.SUPPORT)
def staff_usuarios(request):
    q = request.GET.get('q', '')
    qs = User.objects.select_related('business', 'cotizador_profile').prefetch_related('cotizador_roles__role')
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(business__name__icontains=q))
    paginator = Paginator(qs.order_by('-date_joined'), 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'cotizador_app/staff_usuarios.html', {'page_obj': page, 'q': q})


@role_required(Role.ADMIN, Role.SUPPORT)
def staff_negocios(request):
    q = request.GET.get('q', '')
    qs = Business.objects.select_related('owner').filter(is_deleted=False)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(owner__email__icontains=q) | Q(legal_id__icontains=q))
    paginator = Paginator(qs.order_by('-created_at'), 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'cotizador_app/staff_negocios.html', {'page_obj': page, 'q': q})


@role_required(Role.ADMIN, Role.SUPPORT)
def staff_negocio_detalle(request, pk):
    business = get_object_or_404(Business, pk=pk)
    if request.method == 'POST' and request.POST.get('action') == 'nota':
        from ..decorators import user_has_role
        if not user_has_role(request.user, Role.ADMIN):
            messages.error(request, 'Solo un administrador puede agregar notas.')
        else:
            text = request.POST.get('text', '').strip()
            if text:
                BusinessNote.objects.create(business=business, author=request.user, text=text)
                messages.success(request, 'Nota agregada.')
        return redirect('cotizador_app:staff_negocio_detalle', pk=pk)

    context = {
        'business': business,
        'subscriptions': business.subscriptions.select_related('plan').order_by('-created_at')[:10],
        'payments': business.payments.select_related('plan').order_by('-created_at')[:10],
        'quotations_count': Quotation.objects.filter(business=business).count(),
        'notes': business.notes.select_related('author')[:20],
    }
    return render(request, 'cotizador_app/staff_negocio_detalle.html', context)


@role_required(Role.ADMIN)
def staff_planes(request):
    if request.method == 'POST':
        plan = get_object_or_404(SubscriptionPlan, pk=request.POST.get('plan_id'))
        plan.price_crc = request.POST.get('price_crc') or plan.price_crc
        limit = request.POST.get('monthly_quote_limit', '').strip()
        plan.monthly_quote_limit = int(limit) if limit else None
        plan.is_active = bool(request.POST.get('is_active'))
        plan.save()
        messages.success(request, f'Plan {plan.name} actualizado.')
        return redirect('cotizador_app:staff_planes')
    return render(request, 'cotizador_app/staff_planes.html', {'planes': SubscriptionPlan.objects.all()})


@role_required(Role.ADMIN, Role.SUPPORT)
def staff_suscripciones(request):
    q = request.GET.get('q', '')
    status = request.GET.get('status', '')
    qs = Subscription.objects.select_related('business', 'plan').order_by('-created_at')
    if q:
        qs = qs.filter(business__name__icontains=q)
    if status:
        qs = qs.filter(status=status)
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'cotizador_app/staff_suscripciones.html', {
        'page_obj': page, 'q': q, 'status': status, 'estados': Subscription.STATUS_CHOICES,
    })


@role_required(Role.ADMIN)
def staff_suscripcion_editar(request, pk):
    sub = get_object_or_404(Subscription, pk=pk)
    if request.method == 'POST':
        sub.status = request.POST.get('status', sub.status)
        override = request.POST.get('quota_override', '').strip()
        sub.quota_override = int(override) if override else None
        sub.save()
        AuditLog.objects.create(
            actor=request.user, business=sub.business, action='subscription_overridden',
            target_repr=str(sub), metadata={'status': sub.status, 'quota_override': sub.quota_override},
        )
        messages.success(request, 'Suscripción actualizada.')
    return redirect('cotizador_app:staff_suscripciones')


@role_required(Role.ADMIN, Role.SUPPORT)
def staff_pagos(request):
    q = request.GET.get('q', '')
    qs = Payment.objects.select_related('business', 'plan').order_by('-created_at')
    if q:
        qs = qs.filter(Q(internal_reference__icontains=q) | Q(external_reference__icontains=q)
                        | Q(business__name__icontains=q))
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'cotizador_app/staff_pagos.html', {'page_obj': page, 'q': q})


@role_required(Role.ADMIN, Role.SUPPORT)
def staff_pago_detalle(request, pk):
    payment = get_object_or_404(Payment.objects.select_related('business', 'plan'), pk=pk)
    events = payment.events.order_by('-received_at')
    return render(request, 'cotizador_app/staff_pago_detalle.html', {'payment': payment, 'events': events})


@role_required(Role.ADMIN, Role.SUPPORT)
def staff_sinpe_cola(request):
    qs = SinpePaymentReceipt.objects.select_related('business', 'payment', 'payment__plan') \
        .filter(status=SinpePaymentReceipt.PENDING_REVIEW).order_by('created_at')
    return render(request, 'cotizador_app/staff_sinpe_cola.html', {'recibos': qs})


@role_required(Role.ADMIN, Role.SUPPORT)
def staff_sinpe_revisar(request, pk):
    from ..decorators import user_has_role
    receipt = get_object_or_404(SinpePaymentReceipt.objects.select_related('business', 'payment', 'payment__plan'), pk=pk)
    is_admin = user_has_role(request.user, Role.ADMIN)

    if request.method == 'POST':
        if not is_admin:
            messages.error(request, 'Solo un administrador puede aprobar o rechazar pagos.')
            return redirect('cotizador_app:staff_sinpe_revisar', pk=pk)
        action = request.POST.get('action')
        if action == 'aprobar':
            approve_receipt(receipt, request.user)
            _notify_sinpe_decision(receipt, approved=True)
            messages.success(request, 'Pago aprobado y suscripción activada.')
        elif action == 'rechazar':
            reason = request.POST.get('reason', '').strip()
            if not reason:
                messages.error(request, 'Debés indicar un motivo de rechazo.')
                return redirect('cotizador_app:staff_sinpe_revisar', pk=pk)
            reject_receipt(receipt, request.user, reason)
            _notify_sinpe_decision(receipt, approved=False, reason=reason)
            messages.success(request, 'Pago rechazado.')
        return redirect('cotizador_app:staff_sinpe_cola')

    from ..storage_sinpe import get_signed_url
    receipt_url = get_signed_url(receipt.cloudinary_public_id, receipt.resource_type)
    return render(request, 'cotizador_app/staff_sinpe_revisar.html', {
        'receipt': receipt, 'is_admin': is_admin, 'receipt_url': receipt_url,
    })


def _notify_sinpe_decision(receipt, approved, reason=''):
    from ..emailing import send_transactional_email
    owner_email = receipt.business.owner.email
    if not owner_email:
        return
    if approved:
        send_transactional_email(
            to_email=owner_email, subject='Tu pago fue aprobado — Cotización Express CR',
            template_name='sinpe_aprobado.html', context={'receipt': receipt},
            category='sinpe_approved', business=receipt.business,
        )
    else:
        send_transactional_email(
            to_email=owner_email, subject='Tu pago fue rechazado — Cotización Express CR',
            template_name='sinpe_rechazado.html', context={'receipt': receipt, 'reason': reason},
            category='sinpe_rejected', business=receipt.business,
        )


@role_required(Role.ADMIN, Role.SUPPORT)
def staff_auditoria(request):
    qs = AuditLog.objects.select_related('actor', 'business').order_by('-created_at')
    action = request.GET.get('action', '')
    if action:
        qs = qs.filter(action=action)
    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get('page'))
    acciones = AuditLog.objects.values_list('action', flat=True).distinct()
    return render(request, 'cotizador_app/staff_auditoria.html', {'page_obj': page, 'action': action, 'acciones': acciones})


@role_required(Role.ADMIN, Role.SUPPORT)
def staff_ayuda(request):
    return render(request, 'cotizador_app/staff_ayuda.html')
