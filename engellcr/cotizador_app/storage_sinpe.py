"""SINPE receipts must be private — uploaded via the raw Cloudinary SDK with
type='authenticated' (NOT the default public MediaCloudinaryStorage used elsewhere),
and only ever served through a signed, short-lived URL generated on demand."""
import time

import cloudinary
import cloudinary.uploader
import cloudinary.utils
from django.conf import settings


def _configure():
    """cloudinary.uploader calls need the global cloudinary config set explicitly —
    django-cloudinary-storage only does this lazily inside its own Storage class,
    which we bypass here since receipts need type='authenticated' (private) uploads."""
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
        api_key=settings.CLOUDINARY_STORAGE['API_KEY'],
        api_secret=settings.CLOUDINARY_STORAGE['API_SECRET'],
        secure=True,
    )


def upload_receipt(file, business_id, resource_type):
    if not settings.CLOUDINARY_CLOUD_NAME:
        raise RuntimeError('Cloudinary no está configurado — no se pueden subir comprobantes SINPE.')
    _configure()
    result = cloudinary.uploader.upload(
        file, type='authenticated', resource_type=resource_type,
        folder=f'cotizador/sinpe/{business_id}/',
    )
    return result['public_id']


def get_signed_url(public_id, resource_type, expires_in=300):
    _configure()
    url, _ = cloudinary.utils.cloudinary_url(
        public_id, type='authenticated', resource_type=resource_type,
        sign_url=True, expires_at=int(time.time()) + expires_in,
    )
    return url
