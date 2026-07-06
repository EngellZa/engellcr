from django.contrib import messages
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator

from ..decorators import business_required
from ..forms import ClientForm
from ..models import Client


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
