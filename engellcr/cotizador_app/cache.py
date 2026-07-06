"""Thin wrapper around Django's cache framework.

Works with zero Redis configured (falls back to LocMemCache — see config/settings.py).
Keys are always deterministic/reconstructable from their inputs — never rely on prefix or
pattern-based invalidation, since LocMemCache can't scan keys the way Redis can.
"""
from django.core.cache import cache


def cx_get(key, default=None):
    try:
        return cache.get(key, default)
    except Exception:
        return default


def cx_set(key, value, timeout=None):
    try:
        cache.set(key, value, timeout=timeout)
    except Exception:
        pass


def cx_delete(key):
    try:
        cache.delete(key)
    except Exception:
        pass


def cx_incr(key, timeout=None):
    """Atomic-ish counter: returns the new count. Falls back to get/set if incr isn't supported."""
    try:
        return cache.incr(key)
    except ValueError:
        cx_set(key, 1, timeout=timeout)
        return 1
    except Exception:
        current = cx_get(key, 0)
        cx_set(key, current + 1, timeout=timeout)
        return current + 1


# ── Deterministic key builders ──────────────────────────────────────────────

def plan_list_key():
    return 'cx:plans:list'


def public_quote_key(token):
    return f'cx:quote:{token}'


def dashboard_summary_key(business_id):
    return f'cx:dash:{business_id}'


def rate_limit_key(scope, identifier):
    return f'cx:rl:{scope}:{identifier}'


def invalidate_dashboard_cache(business_id):
    cx_delete(dashboard_summary_key(business_id))
