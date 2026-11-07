from decimal import Decimal

from django import forms

from core.forms import EstiloMixin, FechaInput

from .models import MetaAhorro


class MetaForm(EstiloMixin, forms.ModelForm):
    class Meta:
        model = MetaAhorro
        fields = ["titulo", "monto_objetivo", "monto_actual", "fecha_limite", "por_que"]
        labels = {"titulo": "Título", "fecha_limite": "Fecha límite", "por_que": "El porqué / motivación"}
        widgets = {"fecha_limite": FechaInput, "por_que": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)

    def clean_monto_objetivo(self):
        monto = self.cleaned_data["monto_objetivo"]
        if monto <= 0:
            raise forms.ValidationError("El objetivo tiene que ser mayor a cero.")
        return monto


class AporteForm(EstiloMixin, forms.Form):
    monto = forms.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0.01"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["monto"].widget.attrs.update(placeholder="Aporte", step="0.01")
