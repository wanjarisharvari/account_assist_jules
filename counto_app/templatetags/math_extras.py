from django import template

register = template.Library()

@register.filter(name='subtract')
def subtract(value, arg):
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        try:
            return value - arg
        except (TypeError, ValueError):
            return ''
