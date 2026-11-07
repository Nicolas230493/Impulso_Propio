from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


def _formatear(valor, decimales=2) -> str:
    try:
        numero = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        return ""
    texto = f"{abs(numero):,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-{texto}" if numero < 0 else texto


@register.filter
def dinero(valor, moneda="ARS"):
    """1234.5 -> '$ 1.234,50'; con 'USD' -> 'US$ 1.234,50'."""
    if valor is None or valor == "":
        return ""
    simbolo = "US$" if moneda == "USD" else "$"
    return f"{simbolo} {_formatear(valor)}"


@register.filter
def ars(valor):
    return dinero(valor, "ARS")


@register.filter
def numero(valor, decimales=2):
    return _formatear(valor, int(decimales))


@register.filter
def porcentaje(valor):
    """Variación con signo: 12.3 -> '+12 %'."""
    if valor is None:
        return ""
    numero = Decimal(valor)
    signo = "+" if numero > 0 else ""
    return f"{signo}{_formatear(numero, 0)} %"


@register.simple_tag(takes_context=True)
def con_mes(context, url):
    """Agrega ?mes=AAAA-MM a una URL para conservar el filtro al navegar."""
    separador = "&" if "?" in url else "?"
    return f"{url}{separador}mes={context.get('mes', '')}"
