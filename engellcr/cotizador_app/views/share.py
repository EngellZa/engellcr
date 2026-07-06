from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from ..models import QuotationShareLink, Quotation
from ..ratelimit import rate_limit
from ..cache import cx_get, cx_set, cx_delete, public_quote_key


def _get_valid_link_or_404(token):
    link = get_object_or_404(
        QuotationShareLink.objects.select_related('quotation', 'quotation__client', 'quotation__business'),
        token=token,
    )
    if not link.is_valid:
        return None
    return link


def _build_quote_snapshot(quotation):
    """Plain-dict snapshot of everything the public page displays — safe to cache (no
    internal IDs, no session/messages data) and cheap to rebuild from the ORM objects
    already loaded by _get_valid_link_or_404's select_related."""
    return {
        'quote_number': quotation.quote_number,
        'status': quotation.status,
        'status_display': quotation.get_status_display(),
        'valid_until': quotation.valid_until,
        'notes': quotation.notes,
        'terms': quotation.terms,
        'simbolo': quotation.simbolo,
        'subtotal': quotation.subtotal,
        'discount_total': quotation.discount_total,
        'tax_total': quotation.tax_total,
        'total': quotation.total,
        'business_name': quotation.business.name,
        'business_color': quotation.business.color_primary,
        'business_logo_url': quotation.business.logo.url if quotation.business.logo else '',
        'client_name': quotation.client.name,
        'items': [
            {
                'description': i.description, 'quantity': i.quantity,
                'unit_price': i.unit_price, 'line_total': i.line_total,
            }
            for i in quotation.items.all()
        ],
    }


def _invalidate_quote_cache(token):
    cx_delete(public_quote_key(token))


@rate_limit('public_quote_view', limit=60, window_seconds=300, key_kind='ip')
def public_quote_view(request, token):
    link = _get_valid_link_or_404(token)
    if link is None:
        return render(request, 'cotizador_app/public_quote_unavailable.html', status=404)

    link.view_count += 1
    link.last_viewed_at = timezone.now()
    link.save(update_fields=['view_count', 'last_viewed_at'])

    cache_key = public_quote_key(token)
    quote = cx_get(cache_key)
    if quote is None:
        quote = _build_quote_snapshot(link.quotation)
        cx_set(cache_key, quote, timeout=60)  # safe, non-sensitive display data only

    return render(request, 'cotizador_app/public_quote.html', {'quote': quote, 'link': link})


@rate_limit('public_quote_approve', limit=10, window_seconds=300, key_kind='ip')
def public_quote_approve(request, token):
    link = _get_valid_link_or_404(token)
    if link is None or request.method != 'POST':
        return render(request, 'cotizador_app/public_quote_unavailable.html', status=404)
    link.approved_at = timezone.now()
    link.save(update_fields=['approved_at'])
    link.quotation.status = Quotation.STATUS_APPROVED
    link.quotation.save(update_fields=['status'])
    _invalidate_quote_cache(token)  # status changed — cached snapshot is now stale
    messages.success(request, 'Cotización aprobada. ¡Gracias!')
    return redirect('public_quote_view', token=token)


@rate_limit('public_quote_reject', limit=10, window_seconds=300, key_kind='ip')
def public_quote_reject(request, token):
    link = _get_valid_link_or_404(token)
    if link is None or request.method != 'POST':
        return render(request, 'cotizador_app/public_quote_unavailable.html', status=404)
    link.rejected_at = timezone.now()
    link.rejection_reason = request.POST.get('reason', '')[:255]
    link.save(update_fields=['rejected_at', 'rejection_reason'])
    link.quotation.status = Quotation.STATUS_REJECTED
    link.quotation.save(update_fields=['status'])
    _invalidate_quote_cache(token)  # status changed — cached snapshot is now stale
    messages.success(request, 'Marcaste la cotización como rechazada.')
    return redirect('public_quote_view', token=token)
