from django import template

register = template.Library()

@register.filter
def format_view_count(value):
    """
    Format view count with K (thousands) and M (millions) suffixes
    Example: 1234567 -> 1.2 млн.
    """
    value = float(value)
    if value >= 1000000:
        return f"{value/1000000:.1f} млн."
    elif value >= 1000:
        return f"{value/1000:.1f} тыс."
    return str(int(value)) 