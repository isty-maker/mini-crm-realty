from django import template


register = template.Library()


@register.filter
def price_display(value):
    if value is None:
        return "—"
    return f"{value:,.2f}".removesuffix(".00").replace(",", " ").replace(".", ",")
