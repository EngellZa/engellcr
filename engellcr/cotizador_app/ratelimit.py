"""Minimal rate-limiting decorator built on the cache module — no new dependency.
Works identically whether CACHES is LocMemCache (dev, no Redis) or RedisCache (prod)."""
from functools import wraps

from django.http import HttpResponse

from .cache import cx_get, cx_set, cx_incr, rate_limit_key
from .decorators import get_client_ip


def _find_request(args):
    for a in args:
        if hasattr(a, 'META') and hasattr(a, 'method'):
            return a
    return None


def rate_limit(scope, limit, window_seconds, key_kind='ip'):
    """key_kind='ip' limits per client IP (for anonymous endpoints like login/register);
    key_kind='user' limits per authenticated user (for endpoints that require login)."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            request = _find_request(args)
            if request is None:
                return view_func(*args, **kwargs)

            if key_kind == 'user' and request.user.is_authenticated:
                identifier = f'user:{request.user.id}'
            else:
                identifier = f'ip:{get_client_ip(request)}'
            key = rate_limit_key(scope, identifier)

            count = cx_get(key, 0)
            if count >= limit:
                return HttpResponse('Demasiados intentos. Intentá de nuevo más tarde.', status=429)
            if count == 0:
                cx_set(key, 1, timeout=window_seconds)
            else:
                cx_incr(key, timeout=window_seconds)
            return view_func(*args, **kwargs)
        return wrapped
    return decorator
