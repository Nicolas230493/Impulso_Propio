from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView

from .forms import RegistroForm


class RegistroView(FormView):
    template_name = "registration/registro.html"
    form_class = RegistroForm
    success_url = reverse_lazy("reportes:dashboard")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        usuario = form.save()  # la señal post_save crea categorías y cuentas iniciales
        login(self.request, usuario, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(self.request, "¡Cuenta creada! Ya podés cargar tus movimientos.")
        return super().form_valid(form)
