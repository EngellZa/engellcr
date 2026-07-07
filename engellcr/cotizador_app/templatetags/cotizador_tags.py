from django import template

register = template.Library()


@register.filter
def moneda(value, simbolo='₡'):
    try:
        return f'{simbolo}{float(value):,.2f}'
    except (TypeError, ValueError):
        return value


@register.filter
def numero(value, decimales=2):
    """Formats a number with comma-thousands/period-decimal, bypassing Django's
    locale-aware formatting (which would otherwise flip to comma-decimal for es-cr)."""
    try:
        return f'{float(value):,.{int(decimales)}f}'
    except (TypeError, ValueError):
        return value
