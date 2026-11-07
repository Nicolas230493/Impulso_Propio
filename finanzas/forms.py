from decimal import Decimal

from django import forms

from core.fechas import hoy
from core.forms import EstiloMixin, FechaInput
from core.models import Moneda, TipoMovimiento

from .models import Categoria, Cuenta
from .services import MAX_CUOTAS, DatosMovimiento


def datos_cuentas(usuario) -> dict:
    """Tipo y moneda de cada cuenta, para que el form muestre cuotas / tipo de cambio sin pedir al servidor."""
    return {str(c.pk): {"tipo": c.tipo, "moneda": c.moneda} for c in Cuenta.objects.de(usuario)}


class MovimientoForm(EstiloMixin, forms.Form):
    tipo = forms.ChoiceField(choices=TipoMovimiento.choices, widget=forms.RadioSelect, initial=TipoMovimiento.GASTO)
    monto = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))
    categoria = forms.ModelChoiceField(queryset=Categoria.objects.none(), empty_label="Categoría")
    cuenta = forms.ModelChoiceField(queryset=Cuenta.objects.none(), empty_label=None)
    fecha = forms.DateField(widget=FechaInput)
    moneda = forms.ChoiceField(choices=Moneda.choices, initial=Moneda.ARS)
    tipo_cambio = forms.DecimalField(
        max_digits=12, decimal_places=4, min_value=Decimal("0.0001"), required=False, label="Tipo de cambio"
    )
    cuotas = forms.IntegerField(min_value=1, max_value=MAX_CUOTAS, initial=1)
    repetir = forms.BooleanField(required=False, label="Repetir todos los meses")
    descripcion = forms.CharField(max_length=200, required=False, label="Descripción")

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario
        self.fields["categoria"].queryset = Categoria.objects.de(usuario)
        self.fields["cuenta"].queryset = Cuenta.objects.de(usuario)
        self.fields["monto"].widget.attrs.update(placeholder="Monto", step="0.01", autofocus=True)
        self.fields["tipo_cambio"].widget.attrs.update(placeholder="Tipo de cambio", step="0.0001")
        self.fields["descripcion"].widget.attrs.update(placeholder="Descripción (opcional)")
        if not self.is_bound and "fecha" not in self.initial:
            self._precargar()

    def _precargar(self):
        """Carga rápida: hoy, última cuenta usada y último tipo de cambio."""
        self.initial.setdefault("fecha", hoy())
        cuenta = self.usuario.ultima_cuenta
        if cuenta and cuenta.usuario_id == self.usuario.pk:
            self.initial.setdefault("cuenta", cuenta.pk)
            self.initial.setdefault("moneda", cuenta.moneda)
        if self.usuario.ultimo_tipo_cambio:
            self.initial.setdefault("tipo_cambio", self.usuario.ultimo_tipo_cambio)

    def clean(self):
        datos = super().clean()
        cuenta, moneda = datos.get("cuenta"), datos.get("moneda")
        if not cuenta or not moneda:
            return datos
        # Los campos ocultos en pantalla igual viajan en el POST: se normalizan acá.
        necesita_tc = moneda == Moneda.USD or moneda != cuenta.moneda
        if not necesita_tc:
            datos["tipo_cambio"] = None
        elif not datos.get("tipo_cambio"):
            self.add_error("tipo_cambio", "Cargá el tipo de cambio para este movimiento.")
        admite_cuotas = datos.get("tipo") == TipoMovimiento.GASTO and cuenta.tipo == Cuenta.Tipo.TARJETA
        if "cuotas" in self.fields and not admite_cuotas:
            datos["cuotas"] = 1
        if datos.get("repetir") and (datos.get("cuotas") or 1) > 1:
            self.add_error("repetir", "Un movimiento no puede ser en cuotas y recurrente a la vez.")
        return datos

    def datos(self) -> DatosMovimiento:
        d = self.cleaned_data
        return DatosMovimiento(
            tipo=d["tipo"],
            monto=d["monto"],
            categoria=d["categoria"],
            cuenta=d["cuenta"],
            fecha=d["fecha"],
            moneda=d["moneda"],
            tipo_cambio=d.get("tipo_cambio"),
            descripcion=d.get("descripcion", ""),
            cuotas=d.get("cuotas") or 1,
            repetir=d.get("repetir", False),
        )


class EditarMovimientoForm(MovimientoForm):
    """En la edición no se cambian cuotas ni recurrencia: se edita esta fila."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields["cuotas"]
        del self.fields["repetir"]

    @staticmethod
    def inicial_desde(tx):
        return {
            "tipo": tx.tipo,
            "monto": tx.monto,
            "categoria": tx.categoria_id,
            "cuenta": tx.cuenta_id,
            "fecha": tx.fecha,
            "moneda": tx.moneda,
            "tipo_cambio": tx.tipo_cambio,
            "descripcion": tx.descripcion,
        }


class _NombreUnicoMixin:
    """La restricción usuario+nombre no la valida el ModelForm porque `usuario` no está en el form."""

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario = usuario

    def clean_nombre(self):
        nombre = self.cleaned_data["nombre"].strip()
        repetido = self._meta.model.objects.de(self.usuario).filter(nombre__iexact=nombre)
        if self.instance.pk:
            repetido = repetido.exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError("Ya tenés una con ese nombre.")
        return nombre


class CuentaForm(_NombreUnicoMixin, EstiloMixin, forms.ModelForm):
    class Meta:
        model = Cuenta
        fields = ["nombre", "tipo", "moneda", "saldo_inicial"]

    def clean_moneda(self):
        moneda = self.cleaned_data["moneda"]
        if self.instance.pk and moneda != self.instance.moneda and self.instance.transaccion_set.exists():
            raise forms.ValidationError("No se puede cambiar la moneda de una cuenta con movimientos.")
        return moneda


class CategoriaForm(_NombreUnicoMixin, EstiloMixin, forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ["nombre", "tope_mensual"]
        labels = {"tope_mensual": "Tope mensual (opcional, en ARS)"}


class ReasignarForm(EstiloMixin, forms.Form):
    destino = forms.ModelChoiceField(queryset=None, label="Pasar los movimientos a")

    def __init__(self, *args, objeto, **kwargs):
        super().__init__(*args, **kwargs)
        opciones = type(objeto).objects.de(objeto.usuario).exclude(pk=objeto.pk)
        if isinstance(objeto, Cuenta):
            opciones = opciones.filter(moneda=objeto.moneda)
        self.fields["destino"].queryset = opciones
