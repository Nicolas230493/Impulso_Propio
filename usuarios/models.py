from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _crear(self, email, password, **extra):
        if not email:
            raise ValueError("El email es obligatorio.")
        usuario = self.model(email=self.normalize_email(email).lower(), **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._crear(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self._crear(email, password, **extra)


class Usuario(AbstractUser):
    """Login por email. Guarda las preferencias que antes vivían en localStorage."""

    username = None
    email = models.EmailField("email", unique=True)
    ultimo_tipo_cambio = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    ultima_cuenta = models.ForeignKey(
        "finanzas.Cuenta", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UsuarioManager()

    def __str__(self):
        return self.email
