import logging

from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.urls import reverse

from .models import EmailLog

logger = logging.getLogger(__name__)

VERIFICATION_SALT = 'cotizador_app.email_verification'
VERIFICATION_MAX_AGE = 60 * 60 * 48  # 48 horas


def make_verification_token(user_id):
    return signing.dumps({'uid': user_id}, salt=VERIFICATION_SALT)


def read_verification_token(token):
    """Returns the user_id, or None if invalid/expired."""
    try:
        data = signing.loads(token, salt=VERIFICATION_SALT, max_age=VERIFICATION_MAX_AGE)
    except signing.BadSignature:
        return None
    return data.get('uid')


def send_transactional_email(to_email, subject, template_name, context, category, business=None, attachments=None):
    """Renders an HTML template and sends it. Never raises — email failures must not break the
    calling flow (e.g. a SINPE approval should still succeed even if SMTP is down). Always logs.
    `attachments` is an optional list of (filename, content_bytes, mimetype) tuples."""
    status = EmailLog.SENT
    error_message = ''
    try:
        html_body = render_to_string(f'cotizador_app/emails/{template_name}', context)
        msg = EmailMultiAlternatives(subject=subject, body=html_body, to=[to_email])
        msg.attach_alternative(html_body, 'text/html')
        for filename, content, mimetype in (attachments or []):
            msg.attach(filename, content, mimetype)
        msg.send(fail_silently=False)
    except Exception as exc:
        status = EmailLog.FAILED
        error_message = str(exc)[:2000]
        logger.warning('Fallo al enviar correo (%s) a %s: %s', category, to_email, error_message)

    EmailLog.objects.create(
        business=business, to_email=to_email, subject=subject,
        category=category, status=status, error_message=error_message,
    )
    return status == EmailLog.SENT


def send_verification_email(request, user, business=None):
    """Sent once at registration (and on 'reenviar correo'): combines the welcome message
    with the verification link — a new user used to get two separate emails, which read
    as redundant/spammy. One message covering both is clearer."""
    token = make_verification_token(user.id)
    verify_url = request.build_absolute_uri(reverse('cotizador_app:verificar_correo', args=[token]))
    send_transactional_email(
        to_email=user.email, subject='Bienvenido a Cotización Express — Verificá tu correo',
        template_name='verifica_correo.html',
        context={'user': user, 'business': business, 'verify_url': verify_url},
        category='email_verification', business=business,
    )
    profile = user.cotizador_profile
    profile.email_verification_sent_at = timezone.now()
    profile.save(update_fields=['email_verification_sent_at'])
