#!/bin/sh
set -e

echo "==> Waiting for the database..."
python wait_for_db.py

echo "==> Applying database migrations..."
python manage.py migrate --noinput

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

# Optional convenience: create a superuser when credentials are provided
# via DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_PASSWORD (+ optional EMAIL).
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "==> Ensuring superuser '$DJANGO_SUPERUSER_USERNAME'..."
  python manage.py createsuperuser --noinput || echo "    (superuser already exists)"
fi

if [ "$(echo "$DEBUG" | tr '[:upper:]' '[:lower:]')" = "true" ]; then
  echo "==> Starting Django development server on 0.0.0.0:8000 ..."
  exec python manage.py runserver 0.0.0.0:8000
else
  echo "==> Starting gunicorn on 0.0.0.0:8000 ..."
  exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout 60 \
    --access-logfile -
fi
