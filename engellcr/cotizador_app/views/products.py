from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator

from ..decorators import business_required
from ..forms import ProductForm
from ..models import Product


@business_required
def producto_lista(request):
    qs = Product.objects.filter(business=request.business)
    q = request.GET.get('q', '')
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))
    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'cotizador_app/producto_lista.html', {'page_obj': page, 'q': q})


@business_required
def producto_buscar_ajax(request):
    """Backs the searchable product picker on the quotation form's item rows."""
    q = request.GET.get('q', '').strip()
    qs = Product.objects.filter(business=request.business, is_active=True)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q) | Q(description__icontains=q))
    results = [
        {'id': p.id, 'text': p.name, 'price': str(p.unit_price), 'tax': str(p.tax_pct)}
        for p in qs.order_by('name')[:20]
    ]
    return JsonResponse(results, safe=False)


@business_required
def producto_crear_ajax(request):
    """Quick-create used by the "+ Nuevo producto" modal on the quotation form's item rows."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido.'}, status=405)
    form = ProductForm(request.POST)
    if form.is_valid():
        product = form.save(commit=False)
        product.business = request.business
        product.is_active = True  # not exposed in the quick-add modal — new products default active
        product.save()
        return JsonResponse({'id': product.id, 'text': product.name,
                              'price': str(product.unit_price), 'tax': str(product.tax_pct)})
    return JsonResponse({'errors': form.errors.get_json_data()}, status=400)


@business_required
def producto_crear(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.business = request.business
            product.save()
            messages.success(request, 'Producto/servicio creado.')
            return redirect('cotizador_app:producto_lista')
    else:
        form = ProductForm()
    return render(request, 'cotizador_app/producto_form.html', {'form': form, 'titulo': 'Nuevo Producto/Servicio'})


@business_required
def producto_editar(request, pk):
    product = get_object_or_404(Product, pk=pk, business=request.business)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, 'Producto/servicio actualizado.')
            return redirect('cotizador_app:producto_lista')
    else:
        form = ProductForm(instance=product)
    return render(request, 'cotizador_app/producto_form.html', {'form': form, 'titulo': 'Editar Producto/Servicio'})


@business_required
def producto_archivar(request, pk):
    """Archives (deactivates) rather than deletes — products may be referenced by past quotations."""
    product = get_object_or_404(Product, pk=pk, business=request.business)
    if request.method == 'POST':
        product.is_active = False
        product.save(update_fields=['is_active'])
        messages.success(request, 'Producto/servicio archivado.')
        return redirect('cotizador_app:producto_lista')
    return render(request, 'cotizador_app/confirmar_eliminar.html', {'objeto': product, 'titulo': 'Archivar Producto/Servicio'})
