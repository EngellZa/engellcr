from django import template

register = template.Library()


@register.filter
def moneda(value, simbolo='₡'):
    try:
        return f'{simbolo}{float(value):,.2f}'
    except (TypeError, ValueError):
        return value
