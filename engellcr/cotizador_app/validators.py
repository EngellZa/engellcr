from django.core.exceptions import ValidationError

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}


def validate_receipt_file(uploaded_file):
    """Server-side validation for SINPE receipt uploads: size, then real content sniffing
    (magic bytes / Pillow decode) — never trust the filename extension or claimed content-type alone.
    Returns (mime_type, resource_type) on success; raises ValidationError otherwise."""
    if uploaded_file.size > MAX_UPLOAD_SIZE:
        raise ValidationError('El archivo supera el tamaño máximo permitido (5 MB).')

    uploaded_file.seek(0)
    head = uploaded_file.read(8)
    uploaded_file.seek(0)

    if head.startswith(b'%PDF-'):
        uploaded_file.seek(0)
        return 'application/pdf', 'raw'

    from PIL import Image
    try:
        img = Image.open(uploaded_file)
        img.verify()
    except Exception:
        raise ValidationError('El archivo debe ser una imagen (JPG, PNG, WEBP) o un PDF válido.')
    finally:
        uploaded_file.seek(0)

    # verify() leaves the file unusable for a second open — re-open to read the format safely
    img2 = Image.open(uploaded_file)
    fmt = img2.format
    uploaded_file.seek(0)
    if fmt not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError('Formato de imagen no permitido. Usá JPG, PNG o WEBP.')

    mime_map = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'WEBP': 'image/webp'}
    return mime_map[fmt], 'image'
