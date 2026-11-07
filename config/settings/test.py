from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "clave-solo-para-tests"
# Por defecto SQLite en memoria; TEST_DATABASE_URL permite correr la suite contra PostgreSQL.
DATABASES = {"default": env.db("TEST_DATABASE_URL", default="sqlite://:memory:")}  # noqa: F405
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher", "usuarios.hashers.SupabaseBcryptHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
