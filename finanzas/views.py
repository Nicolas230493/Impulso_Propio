from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import CreateView, DeleteView, FormView, ListView, UpdateView
from django.views.generic.detail import SingleObjectMixin

from core.fechas import mes_a_texto, rango_mes
from core.forms import agregar_errores
from core.mixins import FormConUsuarioMixin, MesMixin, UsuarioQuerysetMixin, es_htmx, respuesta_vacia

from . import services
from .forms import CategoriaForm, CuentaForm, EditarMovimientoForm, MovimientoForm, ReasignarForm, datos_cuentas
from .models import Categoria, Cuenta, Recurrente, Transaccion


def _destino_seguro(request, por_defecto):
    destino = request.POST.get("next") or request.GET.get("next")
    if destino and url_has_allowed_host_and_scheme(destino, {request.get_host()}, request.is_secure()):
        return destino
    return por_defecto


def _lista_del_mes(fecha):
    return f"{reverse('finanzas:movimientos')}?mes={mes_a_texto(fecha)}"


# --- Movimientos ---


class MovimientoListView(MesMixin, UsuarioQuerysetMixin, ListView):
    model = Transaccion
    template_name = "finanzas/movimientos.html"
    context_object_name = "movimientos"

    def get_queryset(self):
        inicio, fin = rango_mes(self.mes)
        return super().get_queryset().filter(fecha__gte=inicio, fecha__lt=fin).select_related("categoria", "cuenta")


class _FormMovimientoMixin:
    template_name = "finanzas/movimiento_form.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(cuentas_json=datos_cuentas(self.request.user), **kwargs)


class MovimientoCreateView(LoginRequiredMixin, _FormMovimientoMixin, FormConUsuarioMixin, FormView):
    form_class = MovimientoForm

    def form_valid(self, form):
        datos = form.datos()
        try:
            filas = services.crear_movimiento(self.request.user, datos)
        except ValidationError as error:
            agregar_errores(form, error)
            return self.form_invalid(form)
        if len(filas) > 1:
            messages.success(self.request, f"Gasto cargado en {len(filas)} cuotas.")
        elif datos.repetir:
            messages.success(self.request, "Movimiento guardado. Se va a repetir todos los meses.")
        else:
            messages.success(self.request, "Movimiento guardado.")
        return redirect(_destino_seguro(self.request, _lista_del_mes(datos.fecha)))


class MovimientoUpdateView(
    UsuarioQuerysetMixin, _FormMovimientoMixin, FormConUsuarioMixin, SingleObjectMixin, FormView
):
    model = Transaccion
    form_class = EditarMovimientoForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.object = self.get_object()
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        return EditarMovimientoForm.inicial_desde(self.object)

    def form_valid(self, form):
        try:
            services.actualizar_movimiento(self.object, form.datos())
        except ValidationError as error:
            agregar_errores(form, error)
            return self.form_invalid(form)
        messages.success(self.request, "Movimiento actualizado.")
        return redirect(_destino_seguro(self.request, _lista_del_mes(self.object.fecha)))


class MovimientoDeleteView(UsuarioQuerysetMixin, DeleteView):
    model = Transaccion
    template_name = "finanzas/movimiento_borrar.html"

    def form_valid(self, form):
        fecha = self.object.fecha
        borrados = services.borrar_movimiento(self.object, todo_el_grupo=self.request.POST.get("todo_el_grupo") == "1")
        if es_htmx(self.request):
            return respuesta_vacia()
        messages.success(self.request, "Movimiento eliminado." if borrados == 1 else f"{borrados} cuotas eliminadas.")
        return redirect(_destino_seguro(self.request, _lista_del_mes(fecha)))


# --- Cuentas y categorías ---


class CuentaListView(UsuarioQuerysetMixin, ListView):
    model = Cuenta
    template_name = "finanzas/cuentas.html"

    def get_context_data(self, **kwargs):
        contexto = super().get_context_data(**kwargs)
        contexto["cuentas"] = [(c, services.saldo_a_hoy(c)) for c in contexto["object_list"]]
        contexto["form"] = CuentaForm(usuario=self.request.user)
        return contexto


class CategoriaListView(MesMixin, UsuarioQuerysetMixin, ListView):
    model = Categoria
    template_name = "finanzas/categorias.html"

    def get_context_data(self, **kwargs):
        from reportes.services import consumo_por_categoria

        contexto = super().get_context_data(**kwargs)
        contexto["categorias"] = consumo_por_categoria(self.request.user, self.mes)
        contexto["form"] = CategoriaForm(usuario=self.request.user)
        return contexto


class _CrearConUsuario(LoginRequiredMixin, FormConUsuarioMixin, CreateView):
    template_name = "finanzas/form_simple.html"
    titulo = ""

    def form_valid(self, form):
        form.instance.usuario = self.request.user
        messages.success(self.request, f"{self.titulo} guardada.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        return super().get_context_data(titulo=f"Nueva {self.titulo.lower()}", volver=self.success_url, **kwargs)


class _EditarConUsuario(UsuarioQuerysetMixin, FormConUsuarioMixin, UpdateView):
    template_name = "finanzas/form_simple.html"
    titulo = ""

    def form_valid(self, form):
        messages.success(self.request, f"{self.titulo} actualizada.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        return super().get_context_data(titulo=f"Editar {self.titulo.lower()}", volver=self.success_url, **kwargs)


class CuentaCreateView(_CrearConUsuario):
    model, form_class, titulo = Cuenta, CuentaForm, "Cuenta"
    success_url = reverse_lazy("finanzas:cuentas")


class CuentaUpdateView(_EditarConUsuario):
    model, form_class, titulo = Cuenta, CuentaForm, "Cuenta"
    success_url = reverse_lazy("finanzas:cuentas")


class CategoriaCreateView(_CrearConUsuario):
    model, form_class, titulo = Categoria, CategoriaForm, "Categoría"
    success_url = reverse_lazy("finanzas:categorias")


class CategoriaUpdateView(_EditarConUsuario):
    model, form_class, titulo = Categoria, CategoriaForm, "Categoría"
    success_url = reverse_lazy("finanzas:categorias")


class _BorrarConReasignar(UsuarioQuerysetMixin, SingleObjectMixin, View):
    """Borrar una cuenta o categoría usada: pide a cuál pasar sus movimientos."""

    template_name = "finanzas/borrar_con_reasignar.html"
    success_url = None

    def _render(self, form):
        usos = services.cantidad_de_usos(self.object)
        return render(self.request, self.template_name, {"objeto": self.object, "usos": usos, "form": form})

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return self._render(ReasignarForm(objeto=self.object))

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = ReasignarForm(request.POST, objeto=self.object)
        necesita_destino = services.cantidad_de_usos(self.object) > 0
        if necesita_destino and not form.is_valid():
            return self._render(form)
        try:
            services.reasignar_y_borrar(self.object, form.cleaned_data.get("destino") if necesita_destino else None)
        except ValidationError as error:
            agregar_errores(form, error)
            return self._render(form)
        messages.success(request, f"“{self.object.nombre}” eliminada.")
        return redirect(self.success_url)


class CuentaDeleteView(_BorrarConReasignar):
    model = Cuenta
    success_url = reverse_lazy("finanzas:cuentas")


class CategoriaDeleteView(_BorrarConReasignar):
    model = Categoria
    success_url = reverse_lazy("finanzas:categorias")


# --- Recurrentes ---


class RecurrenteListView(UsuarioQuerysetMixin, ListView):
    model = Recurrente
    template_name = "finanzas/recurrentes.html"
    context_object_name = "recurrentes"

    def get_queryset(self):
        return super().get_queryset().select_related("categoria", "cuenta").order_by("-activo", "dia_del_mes")


class RecurrenteDetenerView(UsuarioQuerysetMixin, SingleObjectMixin, View):
    model = Recurrente

    def post(self, request, *args, **kwargs):
        recurrente = self.get_object()
        services.detener_recurrente(recurrente)
        if es_htmx(request):
            return render(request, "parciales/recurrente_fila.html", {"r": recurrente})
        messages.success(request, "Listo, ya no se repite. Los movimientos generados se conservan.")
        return redirect("finanzas:recurrentes")
