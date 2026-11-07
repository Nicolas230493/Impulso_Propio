from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import StreamingHttpResponse
from django.views import View
from django.views.generic import TemplateView

from core.fechas import hoy, mes_a_texto
from core.mixins import MesMixin
from finanzas.forms import MovimientoForm, datos_cuentas
from finanzas.services import generar_recurrentes_pendientes

from . import services


class DashboardView(MesMixin, LoginRequiredMixin, TemplateView):
    template_name = "reportes/dashboard.html"

    def get_context_data(self, **kwargs):
        usuario = self.request.user
        # Además del login y el cron: si la sesión quedó abierta, que el mes esté al día.
        generar_recurrentes_pendientes(usuario)
        return super().get_context_data(
            resumen=services.resumen_mes(usuario, self.mes),
            alertas=services.alertas_presupuesto(usuario, self.mes),
            graficos=services.datos_graficos(usuario, self.mes),
            form=MovimientoForm(usuario=usuario),
            cuentas_json=datos_cuentas(usuario),
            **kwargs,
        )


class ReportesView(MesMixin, LoginRequiredMixin, TemplateView):
    template_name = "reportes/reportes.html"

    def get_context_data(self, **kwargs):
        usuario = self.request.user
        return super().get_context_data(
            comparacion=services.comparar_con_mes_anterior(usuario, self.mes),
            meses=services.ultimos_meses(usuario, self.mes),
            graficos=services.datos_graficos(usuario, self.mes),
            **kwargs,
        )


def _csv(lineas, nombre):
    respuesta = StreamingHttpResponse(lineas, content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


class ExportarMesView(MesMixin, LoginRequiredMixin, View):
    def get(self, request):
        return _csv(services.exportar_csv(request.user, self.mes), f"movimientos-{mes_a_texto(self.mes)}.csv")


class ExportarBackupView(LoginRequiredMixin, View):
    def get(self, request):
        return _csv(services.exportar_csv(request.user), f"movimientos-backup-{hoy().isoformat()}.csv")
