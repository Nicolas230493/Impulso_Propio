from django import forms


class EstiloMixin:
    """Aplica la clase .input de Tailwind a los campos de texto, número, fecha y select."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if not isinstance(campo.widget, forms.RadioSelect | forms.CheckboxInput):
                campo.widget.attrs.setdefault("class", "input")


class FechaInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None):
        super().__init__(attrs, format="%Y-%m-%d")


def agregar_errores(form, error):
    """Vuelca un ValidationError de un servicio en el formulario."""
    if hasattr(error, "error_dict"):
        for campo, errores in error.error_dict.items():
            form.add_error(campo if campo in form.fields else None, errores)
    else:
        form.add_error(None, error)
