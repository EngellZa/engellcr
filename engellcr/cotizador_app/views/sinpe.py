from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect, get_object_or_404

from ..decorators import business_required
from ..forms import SinpeReceiptForm
from ..models import Payment, SinpePaymentReceipt
from ..payments.sinpe import submit_receipt
from ..ratelimit import rate_limit
from ..storage_sinpe import upload_receipt, get_signed_url


@business_required
def sinpe_subir_comprobante(request, payment_id):
    payment = get_object_or_404(Payment, pk=payment_id, business=request.business, provider=Payment.SINPE)
    if hasattr(payment, 'sinpe_receipt'):
        messages.info(request, 'Ya subiste un comprobante para este pago. Esperá la revisión del equipo.')
        return redirect('cotizador_app:pagos_lista')

    return _handle_upload(request, payment)


@rate_limit('sinpe_upload', limit=5, window_seconds=3600, key_kind='user')
def _handle_upload(request, payment):
    if request.method == 'POST':
        form = SinpeReceiptForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data['comprobante']
            public_id = upload_receipt(file, payment.business_id, form.cleaned_data['resource_type'])
            submit_receipt(
                payment,
                cloudinary_public_id=public_id, resource_type=form.cleaned_data['resource_type'],
                mime_type=form.cleaned_data['mime_type'], file_size=file.size,
                reference_number=form.cleaned_data['reference_number'],
                payment_date=form.cleaned_data['payment_date'], note=form.cleaned_data['note'],
            )
            messages.success(request, 'Comprobante recibido. Un administrador lo revisará pronto.')
            return redirect('cotizador_app:pagos_lista')
    else:
        form = SinpeReceiptForm()
    return render(request, 'cotizador_app/pago_sinpe_form.html', {'form': form, 'payment': payment})


@business_required
def ver_recibo(request, receipt_id):
    """Authenticated view — only the owning business or staff can see a SINPE receipt.
    Never a stored public URL; generates a short-lived signed Cloudinary URL on demand."""
    receipt = get_object_or_404(SinpePaymentReceipt, pk=receipt_id)
    from ..decorators import user_has_role
    from ..models import Role
    if receipt.business_id != request.business.id and not user_has_role(request.user, Role.ADMIN, Role.SUPPORT):
        raise PermissionDenied
    url = get_signed_url(receipt.cloudinary_public_id, receipt.resource_type)
    return redirect(url)
