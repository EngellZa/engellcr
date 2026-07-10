from datetime import date, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from ..cache import invalidate_dashboard_cache, cx_delete, public_quote_key
from ..decorators import business_required
from ..emailing import send_transactional_email
from ..forms import QuotationForm, QuotationItemFormSet
from ..models import AuditLog, Quotation, QuotationShareLink
from ..pdf import get_or_generate_pdf
from ..ratelimit import rate_limit
from ..services import next_quote_number, recalculate_totals, check_and_increment_usage, get_current_usage


@business_required
def cotizacion_lista(request):
    qs = Quotation.objects.filter(business=request.business).select_related('client')
    status = request.GET.get('status', '')
    q = request.GET.get('q', '')
    if status:
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(Q(quote_number__icontains=q) | Q(client__name__icontains=q))
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'cotizador_app/cotizacion_lista.html', {
        'page_obj': page, 'status': status, 'q': q, 'estados': Quotation.STATUS_CHOICES,
    })


@business_required
def cotizacion_auditoria(request):
    """Every quotation ever created/duplicated/deleted for this business — a durable
    record independent of whether the quotation itself still exists, so a discrepancy
    between plan usage and the current quotation count can always be explained."""
    qs = AuditLog.objects.filter(
        business=request.business,
        action__in=['quotation_created', 'quotation_duplicated', 'quotation_deleted'],
    ).select_related('actor')
    paginator = Paginator(qs, 30)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'cotizador_app/cotizacion_auditoria.html', {'page_obj': page})


def _save_items_and_totals(quotation, formset):
    items = formset.save(commit=False)
    for item in items:
        item.quotation = quotation
        item.line_total = (item.quantity * item.unit_price
                            - (item.quantity * item.unit_price * item.discount_pct / 100))
        item.save()
    for obj in formset.deleted_objects:
        obj.delete()
    recalculate_totals(quotation)


@business_required
def cotizacion_crear(request):
    usage = get_current_usage(request.business)
    if usage.is_blocked:
        messages.error(request, 'Alcanzaste el límite de cotizaciones de tu plan. Mejorá tu plan para seguir cotizando.')
        return redirect('cotizador_app:plan_actual')

    if request.method == 'POST':
        form = QuotationForm(request.POST, business=request.business)
        formset = QuotationItemFormSet(request.POST, instance=Quotation(), prefix='items',
                                        form_kwargs={'business': request.business})
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                if not check_and_increment_usage(request.business):
                    messages.error(request, 'Alcanzaste el límite de cotizaciones de tu plan.')
                    return redirect('cotizador_app:plan_actual')
                quotation = form.save(commit=False)
                quotation.business = request.business
                quotation.created_by = request.user
                quotation.quote_number = next_quote_number(request.business.id)
                quotation.save()
                formset.instance = quotation
                _save_items_and_totals(quotation, formset)
                AuditLog.objects.create(
                    actor=request.user, business=request.business, action='quotation_created',
                    target_repr=quotation.quote_number,
                    metadata={'client': str(quotation.client), 'total': str(quotation.total)},
                )
            invalidate_dashboard_cache(request.business.id)
            messages.success(request, f'Cotización {quotation.quote_number} creada.')
            return redirect('cotizador_app:cotizacion_detalle', pk=quotation.pk)
    else:
        today = date.today()
        initial = {
            'issue_date': today, 'valid_until': today + timedelta(days=3),
            'currency': request.business.currency,
            'notes': 'Gracias por su interés en nuestros productos y servicios.',
            'terms': 'Esta cotización es válida hasta la fecha de vencimiento indicada. Precios sujetos a cambios sin previo aviso.',
        }
        cliente_id = request.GET.get('cliente')
        if cliente_id and cliente_id.isdigit():
            initial['client'] = cliente_id
        form = QuotationForm(business=request.business, initial=initial)
        formset = QuotationItemFormSet(instance=Quotation(), prefix='items',
                                        form_kwargs={'business': request.business})
    return render(request, 'cotizador_app/cotizacion_form.html', {
        'form': form, 'formset': formset, 'titulo': 'Nueva Cotización',
    })


@business_required
def cotizacion_editar(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk, business=request.business)
    if not quotation.is_editable:
        messages.error(request, 'Solo se pueden editar cotizaciones en borrador.')
        return redirect('cotizador_app:cotizacion_detalle', pk=pk)

    if request.method == 'POST':
        form = QuotationForm(request.POST, instance=quotation, business=request.business)
        formset = QuotationItemFormSet(request.POST, instance=quotation, prefix='items',
                                        form_kwargs={'business': request.business})
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                quotation = form.save()
                _save_items_and_totals(quotation, formset)
            if hasattr(quotation, 'share_link'):
                cx_delete(public_quote_key(quotation.share_link.token))
            messages.success(request, 'Cotización actualizada.')
            return redirect('cotizador_app:cotizacion_detalle', pk=quotation.pk)
    else:
        form = QuotationForm(instance=quotation, business=request.business)
        formset = QuotationItemFormSet(instance=quotation, prefix='items',
                                        form_kwargs={'business': request.business})
    return render(request, 'cotizador_app/cotizacion_form.html', {
        'form': form, 'formset': formset, 'titulo': f'Editar {quotation.quote_number}', 'quotation': quotation,
    })


@business_required
def cotizacion_eliminar(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk, business=request.business)
    if not quotation.is_editable:
        messages.error(request, 'Solo se pueden eliminar cotizaciones en borrador. Una cotización enviada no se puede borrar.')
        return redirect('cotizador_app:cotizacion_detalle', pk=pk)

    if request.method == 'POST':
        with transaction.atomic():
            AuditLog.objects.create(
                actor=request.user, business=request.business, action='quotation_deleted',
                target_repr=quotation.quote_number,
                metadata={
                    'client': str(quotation.client), 'total': str(quotation.total),
                    'created_at': quotation.created_at.isoformat(),
                    'created_by': str(quotation.created_by) if quotation.created_by else '',
                },
            )
            quotation.delete()
        invalidate_dashboard_cache(request.business.id)
        messages.success(request, 'Cotización eliminada.')
        return redirect('cotizador_app:cotizacion_lista')
    return render(request, 'cotizador_app/confirmar_eliminar.html', {
        'objeto': quotation, 'titulo': f'Eliminar {quotation.quote_number}',
    })


@business_required
def cotizacion_detalle(request, pk):
    quotation = get_object_or_404(
        Quotation.objects.select_related('client').prefetch_related('items'),
        pk=pk, business=request.business,
    )
    share_link = QuotationShareLink.objects.filter(quotation=quotation).first()
    share_url = ''
    whatsapp_text = ''
    if share_link and share_link.is_valid:
        share_url = request.build_absolute_uri(reverse('public_quote_view', args=[share_link.token]))
        whatsapp_text = (f'Hola {quotation.client.name}, te comparto la cotización '
                          f'{quotation.quote_number} de {request.business.name}: {share_url}')
    return render(request, 'cotizador_app/cotizacion_detalle.html', {
        'quotation': quotation, 'share_link': share_link, 'share_url': share_url,
        'whatsapp_text': whatsapp_text,
    })


@business_required
def cotizacion_duplicar(request, pk):
    original = get_object_or_404(Quotation.objects.prefetch_related('items'), pk=pk, business=request.business)
    usage = get_current_usage(request.business)
    if usage.is_blocked:
        messages.error(request, 'Alcanzaste el límite de cotizaciones de tu plan.')
        return redirect('cotizador_app:plan_actual')

    with transaction.atomic():
        if not check_and_increment_usage(request.business):
            messages.error(request, 'Alcanzaste el límite de cotizaciones de tu plan.')
            return redirect('cotizador_app:plan_actual')
        new = Quotation.objects.create(
            business=request.business, client=original.client,
            quote_number=next_quote_number(request.business.id),
            status=Quotation.STATUS_DRAFT, issue_date=original.issue_date,
            valid_until=original.valid_until, currency=original.currency,
            notes=original.notes, terms=original.terms, created_by=request.user,
        )
        for item in original.items.all():
            item.pk = None
            item.quotation = new
            item.save()
        recalculate_totals(new)
        AuditLog.objects.create(
            actor=request.user, business=request.business, action='quotation_duplicated',
            target_repr=new.quote_number,
            metadata={'client': str(new.client), 'total': str(new.total), 'source': original.quote_number},
        )
    invalidate_dashboard_cache(request.business.id)
    messages.success(request, f'Cotización duplicada como {new.quote_number}. Podés cambiar el cliente y los datos antes de guardar.')
    return redirect('cotizador_app:cotizacion_editar', pk=new.pk)


@business_required
def cotizacion_pdf(request, pk):
    quotation = get_object_or_404(Quotation.objects.prefetch_related('items'), pk=pk, business=request.business)
    pdf_file = get_or_generate_pdf(quotation)
    return FileResponse(pdf_file.open('rb'), as_attachment=True,
                         filename=f'{quotation.quote_number}.pdf', content_type='application/pdf')


@business_required
def cotizacion_orden_compra(request, pk):
    """Never a stored public URL — generates a short-lived signed Cloudinary URL on demand,
    same private-file pattern as SINPE receipts."""
    quotation = get_object_or_404(Quotation, pk=pk, business=request.business)
    share_link = get_object_or_404(QuotationShareLink, quotation=quotation)
    if not share_link.has_purchase_order:
        raise Http404
    from ..storage_sinpe import get_signed_url
    url = get_signed_url(share_link.purchase_order_public_id, share_link.purchase_order_resource_type)
    return redirect(url)


@business_required
@rate_limit('cotizacion_enviar', limit=20, window_seconds=3600, key_kind='user')
def cotizacion_enviar(request, pk):
    quotation = get_object_or_404(Quotation.objects.select_related('client'), pk=pk, business=request.business)
    if not quotation.client.email:
        messages.error(request, 'El cliente no tiene correo registrado.')
        return redirect('cotizador_app:cotizacion_detalle', pk=pk)

    pdf_file = get_or_generate_pdf(quotation)
    pdf_file.open('rb')
    pdf_bytes = pdf_file.read()
    pdf_file.close()
    share_link, _ = QuotationShareLink.objects.get_or_create(quotation=quotation)
    share_url = request.build_absolute_uri(reverse('public_quote_view', args=[share_link.token]))

    sent = send_transactional_email(
        to_email=quotation.client.email,
        subject=f'Cotización {quotation.quote_number} — {request.business.name}',
        template_name='cotizacion_compartida.html',
        context={'quotation': quotation, 'business': request.business, 'share_url': share_url},
        category='quotation_share', business=request.business,
        attachments=[(f'{quotation.quote_number}.pdf', pdf_bytes, 'application/pdf')],
    )
    if sent and quotation.status == Quotation.STATUS_DRAFT:
        quotation.status = Quotation.STATUS_SENT
        quotation.save(update_fields=['status'])
        invalidate_dashboard_cache(request.business.id)
    if sent:
        messages.success(request, 'Cotización enviada por correo.')
    else:
        messages.warning(request, 'No se pudo enviar el correo (revisá la configuración de SMTP).')
    return redirect('cotizador_app:cotizacion_detalle', pk=pk)


@business_required
def cotizacion_compartir(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk, business=request.business)
    share_link, _ = QuotationShareLink.objects.get_or_create(quotation=quotation)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'rotar':
            share_link.rotate()
            messages.success(request, 'Se generó un nuevo enlace público. El anterior ya no funciona.')
        elif action == 'revocar':
            share_link.is_revoked = True
            share_link.save(update_fields=['is_revoked'])
            messages.success(request, 'Enlace público revocado.')
        elif action == 'activar':
            share_link.is_revoked = False
            share_link.save(update_fields=['is_revoked'])
            messages.success(request, 'Enlace público reactivado.')
        if quotation.status == Quotation.STATUS_DRAFT:
            quotation.status = Quotation.STATUS_SENT
            quotation.save(update_fields=['status'])
            invalidate_dashboard_cache(request.business.id)
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            share_url = request.build_absolute_uri(reverse('public_quote_view', args=[share_link.token]))
            whatsapp_text = (f'Hola {quotation.client.name}, te comparto la cotización '
                              f'{quotation.quote_number} de {request.business.name}: {share_url}')
            return JsonResponse({'share_url': share_url, 'whatsapp_text': whatsapp_text})
    return redirect('cotizador_app:cotizacion_detalle', pk=pk)
