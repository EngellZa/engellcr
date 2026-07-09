from django.contrib import messages
from django.db.models import Q, Count, Sum
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.urls import reverse

from ..decorators import business_required
from ..forms import ClientForm
from ..models import Client, Quotation, QuotationItem


@business_required
def cliente_lista(request):
    qs = Client.objects.filter(business=request.business, is_deleted=False)
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(company_name__icontains=q) | Q(email__icontains=q))
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'cotizador_app/cliente_lista.html', {'page_obj': page, 'q': q})


@business_required
def cliente_detalle(request, pk):
    client = get_object_or_404(Client, pk=pk, business=request.business, is_deleted=False)
    quotations = Quotation.objects.filter(business=request.business, client=client).order_by('-created_at')

    # "Related items to buy" — everything previously quoted to this client, grouped so
    # frequently-repeated items surface first (useful context when quoting them again).
    items_history = (
        QuotationItem.objects.filter(quotation__business=request.business, quotation__client=client)
        .values('description')
        .annotate(veces=Count('id'), cantidad_total=Sum('quantity'))
        .order_by('-veces', 'description')
    )

    return render(request, 'cotizador_app/cliente_detalle.html', {
        'client': client,
        'quotations': quotations[:20],
        'total_cotizaciones': quotations.count(),
        'items_history': items_history[:15],
        'nueva_cotizacion_url': f"{reverse('cotizador_app:cotizacion_crear')}?cliente={client.pk}",
    })


@business_required
def cliente_buscar_ajax(request):
    """Backs the searchable client picker on the quotation form — remote search across
    every client field, so the rendered <select> never has to hold the full client list."""
    q = request.GET.get('q', '').strip()
    qs = Client.objects.filter(business=request.business, is_deleted=False)
    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(company_name__icontains=q) | Q(email__icontains=q) |
            Q(phone__icontains=q) | Q(identification__icontains=q)
        )
    results = [
        {'id': c.id, 'text': f'{c.name} — {c.company_name}' if c.company_name else c.name}
        for c in qs.order_by('name')[:20]
    ]
    return JsonResponse(results, safe=False)


@business_required
def cliente_crear_ajax(request):
    """Quick-create used by the "+ Nuevo cliente" modal on the quotation form, so a
    missing client doesn't force the user to abandon the quotation they're building."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido.'}, status=405)
    form = ClientForm(request.POST)
    if form.is_valid():
        client = form.save(commit=False)
        client.business = request.business
        client.is_active = True  # not exposed in the quick-add modal — new clients default active
        client.save()
        return JsonResponse({'id': client.id, 'text': str(client)})
    return JsonResponse({'errors': form.errors.get_json_data()}, status=400)


@business_required
def cliente_crear(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.business = request.business
            client.save()
            messages.success(request, 'Cliente creado.')
            return redirect('cotizador_app:cliente_lista')
    else:
        form = ClientForm()
    return render(request, 'cotizador_app/cliente_form.html', {'form': form, 'titulo': 'Nuevo Cliente'})


@business_required
def cliente_editar(request, pk):
    client = get_object_or_404(Client, pk=pk, business=request.business, is_deleted=False)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, 'Cliente actualizado.')
            return redirect('cotizador_app:cliente_lista')
    else:
        form = ClientForm(instance=client)
    return render(request, 'cotizador_app/cliente_form.html', {'form': form, 'titulo': 'Editar Cliente'})


@business_required
def cliente_eliminar(request, pk):
    client = get_object_or_404(Client, pk=pk, business=request.business, is_deleted=False)
    if request.method == 'POST':
        client.is_deleted = True
        client.is_active = False
        client.save(update_fields=['is_deleted', 'is_active'])
        messages.success(request, 'Cliente eliminado.')
        return redirect('cotizador_app:cliente_lista')
    return render(request, 'cotizador_app/confirmar_eliminar.html', {'objeto': client, 'titulo': 'Eliminar Cliente'})
