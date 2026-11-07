"""Fechas por mes. Los meses se representan como `date` en el día 1 o como texto 'AAAA-MM'."""

import calendar
from datetime import date

from django.utils import timezone


def hoy() -> date:
    return timezone.localdate()


def primer_dia(fecha: date) -> date:
    return fecha.replace(day=1)


def sumar_meses_a_mes(mes: date, n: int) -> date:
    """Mes (día 1) desplazado n meses; n puede ser negativo."""
    indice = mes.year * 12 + (mes.month - 1) + n
    return date(indice // 12, indice % 12 + 1, 1)


def fecha_en_mes(mes: date, dia: int) -> date:
    """Día `dia` del mes, recortado al último día (31 en febrero -> 28/29)."""
    ultimo = calendar.monthrange(mes.year, mes.month)[1]
    return date(mes.year, mes.month, min(dia, ultimo))


def sumar_meses(fecha: date, n: int) -> date:
    return fecha_en_mes(sumar_meses_a_mes(primer_dia(fecha), n), fecha.day)


def rango_mes(mes: date) -> tuple[date, date]:
    """(primer día, primer día del mes siguiente) para filtrar con fecha__gte / fecha__lt."""
    inicio = primer_dia(mes)
    return inicio, sumar_meses_a_mes(inicio, 1)


def mes_a_texto(mes: date) -> str:
    return f"{mes.year:04d}-{mes.month:02d}"


def parsear_mes(texto: str | None) -> date:
    """'AAAA-MM' -> date del día 1. Vacío o inválido -> mes actual."""
    try:
        anio, mes = (int(p) for p in (texto or "").split("-"))
        return date(anio, mes, 1)
    except ValueError:
        return primer_dia(hoy())


def mes_de_request(request) -> date:
    return parsear_mes(request.GET.get("mes"))
