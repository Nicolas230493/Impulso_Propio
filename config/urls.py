from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("usuarios.urls")),
    path("", include("reportes.urls")),
    path("", include("finanzas.urls")),
    path("metas/", include("metas.urls")),
]
