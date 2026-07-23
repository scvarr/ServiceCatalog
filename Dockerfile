FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app
COPY requirements.txt ./
RUN umask 022 \
    && python -m pip install --no-cache-dir --upgrade -r requirements.txt \
    && chmod -R a+rX /usr/local/lib/python3.13/site-packages \
    && python -c "import django, gunicorn; print(f'Django {django.get_version()} installed')"
COPY . .
RUN python -c "import django; print(f'Django {django.get_version()} available after source copy')"
RUN chmod +x /app/entrypoint.sh && chown -R app:app /app

RUN setpriv --reuid=app --regid=app --init-groups python -c "import django; print(f'Django {django.get_version()} available to the runtime user')"
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
