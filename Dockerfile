FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.settings.prod
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# El CSS de Tailwind ya está compilado en static/css/app.css.
RUN SECRET_KEY=solo-para-collectstatic-solo-para-collectstatic-123456 python manage.py collectstatic --noinput

RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 3"]
