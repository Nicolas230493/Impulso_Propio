from django.db import models
from django.db.models import Q

from core.models import Moneda, TipoMovimiento, UserOwnedModel
from core.moneda import convertir_a_ars


class Cuenta(UserOwnedModel):
    class Tipo(models.TextChoices):
        EFECTIVO = "efectivo", "Efectivo"
        TARJETA = "tarjeta", "Tarjeta"
        TRANSFERENCIA = "transferencia", "Transferencia"

    nombre = models.CharField(max_length=80)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    moneda = models.CharField(max_length=3, choices=Moneda.choices, default=Moneda.ARS)
    saldo_inicial = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["creado"]
        constraints = [models.UniqueConstraint(fields=["usuario", "nombre"], name="cuenta_unica")]

    def __str__(self):
        return f"{self.nombre} (USD)" if self.moneda == Moneda.USD else self.nombre


class Categoria(UserOwnedModel):
    nombre = models.CharField(max_length=60)
    tope_mensual = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(fields=["usuario", "nombre"], name="categoria_unica"),
            models.CheckConstraint(
                condition=Q(tope_mensual__isnull=True) | Q(tope_mensual__gt=0), name="categoria_tope_positivo"
            ),
        ]

    def __str__(self):
        return self.nombre


class Recurrente(UserOwnedModel):
    tipo = models.CharField(max_length=7, choices=TipoMovimiento.choices)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    moneda = models.CharField(max_length=3, choices=Moneda.choices, default=Moneda.ARS)
    # Respaldo si el usuario todavía no tiene un último tipo de cambio cargado.
    tipo_cambio = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    cuenta = models.ForeignKey(Cuenta, on_delete=models.PROTECT)
    descripcion = models.CharField(max_length=200, blank=True)
    dia_del_mes = models.PositiveSmallIntegerField()
    ultimo_generado = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["dia_del_mes", "creado"]
        constraints = [
            models.CheckConstraint(condition=Q(monto__gt=0), name="recurrente_monto_positivo"),
            models.CheckConstraint(condition=Q(dia_del_mes__gte=1, dia_del_mes__lte=31), name="recurrente_dia_valido"),
        ]

    def __str__(self):
        return self.descripcion or self.categoria.nombre


class Transaccion(UserOwnedModel):
    tipo = models.CharField(max_length=7, choices=TipoMovimiento.choices)
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    moneda = models.CharField(max_length=3, choices=Moneda.choices, default=Moneda.ARS)
    tipo_cambio = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    monto_ars = models.DecimalField(max_digits=16, decimal_places=2, editable=False)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    cuenta = models.ForeignKey(Cuenta, on_delete=models.PROTECT)
    fecha = models.DateField(db_index=True)
    descripcion = models.CharField(max_length=200, blank=True)
    grupo_id = models.UUIDField(null=True, blank=True, db_index=True)
    cuota = models.PositiveSmallIntegerField(null=True, blank=True)
    cuotas = models.PositiveSmallIntegerField(null=True, blank=True)
    recurrente = models.ForeignKey(Recurrente, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-fecha", "-creado"]
        indexes = [models.Index(fields=["usuario", "fecha"])]
        constraints = [
            models.UniqueConstraint(fields=["recurrente", "fecha"], name="recurrente_una_vez_por_fecha"),
            models.CheckConstraint(condition=Q(monto__gt=0), name="transaccion_monto_positivo"),
        ]

    def __str__(self):
        return f"{self.fecha} {self.tipo} {self.monto} {self.moneda}"

    @property
    def es_ingreso(self):
        return self.tipo == TipoMovimiento.INGRESO

    def save(self, *args, **kwargs):
        self.monto_ars = convertir_a_ars(self.monto, self.moneda, self.tipo_cambio)
        super().save(*args, **kwargs)
