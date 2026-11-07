from django.urls import path

from . import views

app_name = "reportes"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("reportes/", views.ReportesView.as_view(), name="reportes"),
    path("exportar/", views.ExportarMesView.as_view(), name="exportar_mes"),
    path("exportar/backup/", views.ExportarBackupView.as_view(), name="exportar_backup"),
]
