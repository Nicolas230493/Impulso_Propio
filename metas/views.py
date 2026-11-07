from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from django.views.generic.detail import SingleObjectMixin

from core.mixins import FormConUsuarioMixin, UsuarioQuerysetMixin, es_htmx, respuesta_vacia

from . import services
from .forms import AporteForm, MetaForm
from .models import MetaAhorro

LISTA = reverse_lazy("metas:lista")


class MetaListView(UsuarioQuerysetMixin, ListView):
    model = MetaAhorro
    template_name = "metas/lista.html"
    context_object_name = "metas"

    def get_context_data(self, **kwargs):
        return super().get_context_data(form_aporte=AporteForm(), **kwargs)


class MetaCreateView(LoginRequiredMixin, FormConUsuarioMixin, CreateView):
    model = MetaAhorro
    form_class = MetaForm
    template_name = "metas/form.html"
    success_url = LISTA

    def form_valid(self, form):
        form.instance.usuario = self.request.user
        messages.success(self.request, "Meta guardada.")
        return super().form_valid(form)


class MetaUpdateView(UsuarioQuerysetMixin, FormConUsuarioMixin, UpdateView):
    model = MetaAhorro
    form_class = MetaForm
    template_name = "metas/form.html"
    success_url = LISTA

    def form_valid(self, form):
        messages.success(self.request, "Meta actualizada.")
        return super().form_valid(form)


class MetaDeleteView(UsuarioQuerysetMixin, DeleteView):
    model = MetaAhorro
    template_name = "metas/borrar.html"
    success_url = LISTA

    def form_valid(self, form):
        self.object.delete()
        if es_htmx(self.request):
            return respuesta_vacia()
        messages.success(self.request, "Meta eliminada.")
        return redirect(self.success_url)


class MetaAportarView(UsuarioQuerysetMixin, SingleObjectMixin, View):
    model = MetaAhorro

    def post(self, request, *args, **kwargs):
        meta = self.get_object()
        form = AporteForm(request.POST)
        if form.is_valid():
            try:
                meta = services.aportar(meta, form.cleaned_data["monto"])
                form = AporteForm()
            except ValidationError as error:
                form.add_error("monto", error.messages)
        if es_htmx(request):
            return render(request, "parciales/meta_tarjeta.html", {"meta": meta, "form_aporte": form})
        if form.errors:
            messages.error(request, "El aporte tiene que ser mayor a cero.")
        return redirect(LISTA)
