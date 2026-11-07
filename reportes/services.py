"""Agregados para el dashboard, reportes, alertas y exportación. Todos los montos en ARS."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth

from core.fechas import rango_mes, sumar_meses_a_mes
from core.models import TipoMovimiento
from finanzas.models import Categoria, Transaccion

CERO = Decimal("0")
UMBRAL_AVISO = Decimal("80")


def _del_mes(usuario, mes: date):
    inicio, fin = rango_mes(mes)
    return Transaccion.objects.de(usuario).filter(fecha__gte=inicio, fecha__lt=fin)


def _suma(queryset, **filtro) -> Decimal:
    return queryset.filter(**filtro).aggregate(total=Sum("monto_ars"))["total"] or CERO


def variacion(actual: Decimal, anterior: Decimal) -> Decimal | None:
    """Variación % respecto del mes anterior. None si el anterior es 0 (se muestra 'nuevo' o '—')."""
    if not anterior:
        return None
    return (actual - anterior) / anterior * 100


def resumen_mes(usuario, mes: date) -> dict:
    movimientos = _del_mes(usuario, mes)
    totales = movimientos.aggregate(
        ingresos=Sum("monto_ars", filter=Q(tipo=TipoMovimiento.INGRESO)),
        gastos=Sum("monto_ars", filter=Q(tipo=TipoMovimiento.GASTO)),
    )
    ingresos, gastos = totales["ingresos"] or CERO, totales["gastos"] or CERO
    return {"ingresos": ingresos, "gastos": gastos, "saldo": ingresos - gastos}


def gastos_por_categoria(usuario, mes: date) -> dict[str, Decimal]:
    """{nombre de categoría: total gastado en ARS}, de mayor a menor."""
    filas = (
        _del_mes(usuario, mes)
        .filter(tipo=TipoMovimiento.GASTO)
        .values("categoria__nombre")
        .annotate(total=Sum("monto_ars"))
        .order_by("-total")
    )
    return {f["categoria__nombre"]: f["total"] for f in filas}


@dataclass
class ConsumoCategoria:
    categoria: Categoria
    gastado: Decimal

    @property
    def porcentaje(self) -> Decimal | None:
        if not self.categoria.tope_mensual:
            return None
        return self.gastado / self.categoria.tope_mensual * 100

    @property
    def nivel(self) -> str | None:
        """'roja' si superó el tope, 'amarilla' desde el 80 % (incluido el 100 % justo)."""
        if self.porcentaje is None:
            return None
        if self.gastado > self.categoria.tope_mensual:
            return "roja"
        if self.porcentaje >= UMBRAL_AVISO:
            return "amarilla"
        return None


def consumo_por_categoria(usuario, mes: date) -> list[ConsumoCategoria]:
    gastado = gastos_por_categoria(usuario, mes)
    return [ConsumoCategoria(c, gastado.get(c.nombre, CERO)) for c in Categoria.objects.de(usuario)]


def alertas_presupuesto(usuario, mes: date) -> list[ConsumoCategoria]:
    """Categorías con tope que llegaron al 80 % en el mes filtrado, la más comprometida primero."""
    alertas = [c for c in consumo_por_categoria(usuario, mes) if c.nivel]
    return sorted(alertas, key=lambda c: c.porcentaje, reverse=True)


def comparar_con_mes_anterior(usuario, mes: date) -> dict:
    actual = gastos_por_categoria(usuario, mes)
    anterior = gastos_por_categoria(usuario, sumar_meses_a_mes(mes, -1))
    nombres = sorted(set(actual) | set(anterior), key=lambda n: actual.get(n, CERO), reverse=True)
    filas = [
        {
            "categoria": n,
            "actual": actual.get(n, CERO),
            "anterior": anterior.get(n, CERO),
            "variacion": variacion(actual.get(n, CERO), anterior.get(n, CERO)),
        }
        for n in nombres
    ]
    total_actual, total_anterior = sum(actual.values(), CERO), sum(anterior.values(), CERO)
    return {
        "filas": filas,
        "total": {
            "actual": total_actual,
            "anterior": total_anterior,
            "variacion": variacion(total_actual, total_anterior),
        },
    }


def ultimos_meses(usuario, mes: date, n: int = 6) -> list[dict]:
    """Ingresos, gastos y variación de gastos de los últimos n meses hasta `mes`, en una consulta."""
    desde = sumar_meses_a_mes(mes, -n)  # un mes extra para la variación del primero
    _, hasta = rango_mes(mes)
    filas = (
        Transaccion.objects.de(usuario)
        .filter(fecha__gte=desde, fecha__lt=hasta)
        .annotate(mes=TruncMonth("fecha"))
        .values("mes")
        .annotate(
            ingresos=Sum("monto_ars", filter=Q(tipo=TipoMovimiento.INGRESO)),
            gastos=Sum("monto_ars", filter=Q(tipo=TipoMovimiento.GASTO)),
        )
    )
    por_mes = {f["mes"]: f for f in filas}
    resultado = []
    for i in range(n - 1, -1, -1):
        m = sumar_meses_a_mes(mes, -i)
        fila, previa = por_mes.get(m, {}), por_mes.get(sumar_meses_a_mes(m, -1), {})
        ingresos, gastos = fila.get("ingresos") or CERO, fila.get("gastos") or CERO
        resultado.append(
            {
                "mes": m,
                "ingresos": ingresos,
                "gastos": gastos,
                "variacion": variacion(gastos, previa.get("gastos") or CERO),
                "es_actual": m == mes,
            }
        )
    return resultado


def datos_graficos(usuario, mes: date) -> dict:
    """Datos para Chart.js, serializados con json_script en el template."""
    por_categoria = gastos_por_categoria(usuario, mes)
    resumen = resumen_mes(usuario, mes)
    return {
        "categorias": {"etiquetas": list(por_categoria), "valores": [float(v) for v in por_categoria.values()]},
        "balance": {"ingresos": float(resumen["ingresos"]), "gastos": float(resumen["gastos"])},
    }


# --- CSV ---

ENCABEZADO_CSV = [
    "Fecha", "Tipo", "Categoría", "Cuenta", "Descripción", "Moneda", "Monto", "Tipo de cambio", "Monto ARS",
]  # fmt: skip
BOM = "﻿"


def _numero_csv(valor) -> str:
    """Coma decimal para Excel en español."""
    if valor is None:
        return ""
    return f"{Decimal(valor):.2f}".replace(".", ",")


def _campo_csv(valor) -> str:
    texto = "" if valor is None else str(valor)
    if any(c in texto for c in ';"\r\n'):
        return '"' + texto.replace('"', '""') + '"'
    return texto


def exportar_csv(usuario, mes: date | None = None) -> Iterator[str]:
    """Líneas del CSV (con BOM y ';'). Sin mes = backup completo. Pensado para StreamingHttpResponse."""
    movimientos = Transaccion.objects.de(usuario).select_related("categoria", "cuenta").order_by("fecha", "pk")
    if mes:
        inicio, fin = rango_mes(mes)
        movimientos = movimientos.filter(fecha__gte=inicio, fecha__lt=fin)
    yield BOM + ";".join(ENCABEZADO_CSV) + "\r\n"
    for t in movimientos.iterator(chunk_size=500):
        fila = [
            t.fecha.isoformat(), t.tipo, t.categoria.nombre, t.cuenta.nombre, t.descripcion, t.moneda,
            _numero_csv(t.monto), _numero_csv(t.tipo_cambio), _numero_csv(t.monto_ars),
        ]  # fmt: skip
        yield ";".join(_campo_csv(v) for v in fila) + "\r\n"
