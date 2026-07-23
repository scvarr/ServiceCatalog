# Service Catalog

Внутренний каталог услуг, экземпляров и договорного состава. Приложение написано на Django и запускается вместе с PostgreSQL в Docker Compose.

## Быстрый старт

1. Скопируйте `.env.example` в `.env` и замените `DJANGO_SECRET_KEY` и `POSTGRES_PASSWORD`.
2. Запустите приложение: `docker compose up --build`.
3. Создайте локального администратора: `docker compose exec web python manage.py createsuperuser`.
4. Откройте `http://localhost:8380/admin/`.

Миграции и группы `Readers`, `Editors`, `ContractEditors`, `Administrators` применяются автоматически при старте `web`.

## Разработка и проверки

Запуск с bind mount и Django development server:

```text
docker compose -f compose.yaml -f compose.dev.yaml up --build
```

Проверки внутри контейнера:

```text
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py test
```

## Развёртывание

После `git pull` подготовьте production `.env`, затем выполните `docker compose up --build -d`. PostgreSQL хранит данные в именованном volume `postgres_data`; обычный перезапуск контейнеров не удаляет их.

Compose создаёт именованную сеть `servicecatalog_net` (`172.30.0.0/24`): приложение получает адрес `172.30.0.10`, PostgreSQL — `172.30.0.11`. Внешний порт задаётся `HOST_PORT` и по умолчанию равен `8380`.

Для Nginx Proxy Manager на том же Docker-хосте подключите его контейнер к сети `servicecatalog_net` и укажите upstream `http://172.30.0.10:8000`. Внешний порт `8380` можно использовать для локальной диагностики; GUI на сервере для работы приложения не нужен.
# ServiceCatalog
