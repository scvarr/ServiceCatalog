FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade -r requirements.txt \
    && python -c "import django, gunicorn; print(f'Django {django.get_version()} installed')"
COPY . .
RUN python -c "import django; print(f'Django {django.get_version()} available after source copy')"
RUN chmod +x /app/entrypoint.sh && chown -R app:app /app

USER app
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
