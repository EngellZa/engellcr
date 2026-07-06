from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

from .models import Business


def cotizador_login_required(view_func):
    return login_required(view_func, login_url='cotizador_app:login')


def get_current_business(request):
    """Returns the Business owned by request.user, or None."""
    return Business.objects.filter(owner=request.user, is_deleted=False).first()


def business_required(view_func):
    """Requires a logged-in user who owns a Business and has verified their email."""
    @wraps(view_func)
    @cotizador_login_required
    def wrapped(request, *args, **kwargs):
        profile = getattr(request.user, 'cotizador_profile', None)
        if profile is None or not profile.email_verified:
            return redirect('cotizador_app:verificacion_pendiente')
        business = get_current_business(request)
        if business is None:
            return redirect('cotizador_app:perfil_negocio')
        request.business = business
        return view_func(request, *args, **kwargs)
    return wrapped


def user_has_role(user, *codes):
    if not user.is_authenticated:
        return False
    return user.cotizador_roles.filter(role__code__in=codes).exists()


def role_required(*codes):
    """Restricts a view to users holding one of the given role codes (checked via UserRole, not is_staff)."""
    def decorator(view_func):
        @wraps(view_func)
        @cotizador_login_required
        def wrapped(request, *args, **kwargs):
            if not user_has_role(request.user, *codes):
                raise PermissionDenied('No tenés permiso para acceder a esta sección.')
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def get_client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')
