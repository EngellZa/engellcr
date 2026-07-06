import hashlib
import json
from io import BytesIO

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone


def compute_content_hash(quotation):
    """Hashes everything a client would see in the PDF. Deliberately excludes `status` —
    approving/rejecting a quote shouldn't force a PDF rebuild."""
    business = quotation.business
    payload = {
        'business': {
            'name': business.name, 'legal_id': business.legal_id, 'email': business.email,
            'phone': business.phone, 'address': business.address,
            'color_primary': business.color_primary, 'footer_note': business.footer_note,
            'logo': business.logo.name if business.logo else '',
        },
        'client': {
            'name': quotation.client.name, 'company_name': quotation.client.company_name,
            'email': quotation.client.email, 'phone': quotation.client.phone,
            'address': quotation.client.address,
        },
        'quote_number': quotation.quote_number,
        'issue_date': str(quotation.issue_date),
        'valid_until': str(quotation.valid_until),
        'currency': quotation.currency,
        'notes': quotation.notes,
        'terms': quotation.terms,
        'subtotal': str(quotation.subtotal),
        'discount_total': str(quotation.discount_total),
        'tax_total': str(quotation.tax_total),
        'total': str(quotation.total),
        'items': [
            {
                'description': i.description, 'quantity': str(i.quantity),
                'unit_price': str(i.unit_price), 'discount_pct': str(i.discount_pct),
                'tax_pct': str(i.tax_pct), 'line_total': str(i.line_total),
            }
            for i in quotation.items.all().order_by('sort_order', 'id')
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def get_or_generate_pdf(quotation):
    """Returns the quotation's PDF file field, regenerating only if the content hash changed."""
    current_hash = compute_content_hash(quotation)
    if quotation.pdf_file and quotation.pdf_content_hash == current_hash:
        return quotation.pdf_file

    from weasyprint import HTML  # imported lazily so a missing system lib never breaks app startup

    html = render_to_string('cotizador_app/cotizacion_pdf.html', {'quotation': quotation})
    buffer = BytesIO()
    HTML(string=html).write_pdf(target=buffer)
    quotation.pdf_file.save(f'{quotation.quote_number}.pdf', ContentFile(buffer.getvalue()), save=False)
    quotation.pdf_content_hash = current_hash
    quotation.pdf_generated_at = timezone.now()
    quotation.save(update_fields=['pdf_file', 'pdf_content_hash', 'pdf_generated_at'])
    return quotation.pdf_file
