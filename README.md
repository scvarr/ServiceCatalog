# Service Catalog

Внутренний каталог услуг, экземпляров и договорного состава. Приложение написано на Django и запускается вместе с PostgreSQL в Docker Compose.

## Быстрый старт

1. Скопируйте `.env.example` в `.env` и замените `DJANGO_SECRET_KEY` и `POSTGRES_PASSWORD`.
2. Запустите приложение: `docker compose up --build`.
3. Создайте локального администратора: `docker compose exec web python manage.py createsuperuser`.
4. Откройте `http://localhost:8380/admin/`.

Миграции и группы `Readers`, `Editors`, `ContractEditors`, `Administrators` применяются автоматически при старте `web`.

Для доступа по DNS-имени добавьте его без порта в `DJANGO_ALLOWED_HOSTS`, например: `DJANGO_ALLOWED_HOSTS=ims01-ladm1.atomflot.ru,localhost,127.0.0.1`. На production-сервере установите `DJANGO_DEBUG=false`.

Если приложение находится за HTTPS reverse proxy (например, Nginx Proxy Manager), добавьте полный origin в `DJANGO_CSRF_TRUSTED_ORIGINS`, например: `DJANGO_CSRF_TRUSTED_ORIGINS=https://svc.atomflot.ru`. В production Django принимает `X-Forwarded-Proto` от proxy и выставляет secure-флаги cookie.

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

## Идентификаторы каталога

Тип экземпляра создаётся только по наименованию. Системные коды услуг (`SVC-000001`) и экземпляров (`INS-000001`) формируются автоматически после первого сохранения; код экземпляра используется как стабильный ключ CSV-импорта.

## Точечная синхронизация GLPI

Интеграция по умолчанию отключена (`GLPI_ENABLED=false`). Для сервера задайте в `.env` `GLPI_ENABLED=true`, URL GLPI, OAuth client ID/secret, пользователя, пароль, версию `v2.3`, таймаут и при необходимости путь к CA bundle. TLS-проверка включена по умолчанию (`GLPI_TLS_VERIFY=true`); её можно явно отключить только для согласованного внутреннего контура (`GLPI_TLS_VERIFY=false`).

В Django Admin откройте экземпляр и добавьте внешнюю ссылку: система `GLPI`, тип `Computer`, внешний ID `2713`. Затем используйте кнопку «Обновить данные из GLPI» на карточке экземпляра или выполните:

```text
docker compose exec web python manage.py sync_glpi_instance INS-000001
```

Синхронизация обновляет только отдельный snapshot GLPI и не изменяет имя, тип, примечание, системный код или участие экземпляра в услугах.

## Развёртывание

После `git pull` подготовьте production `.env`, затем выполните `docker compose up --build -d`. PostgreSQL хранит данные в именованном volume `postgres_data`; обычный перезапуск контейнеров не удаляет их.

Compose создаёт именованную сеть `servicecatalog_net` (`172.30.0.0/24`): приложение получает адрес `WEB_CONTAINER_IP` (по умолчанию `172.30.0.10`), PostgreSQL — `DB_CONTAINER_IP` (по умолчанию `172.30.0.11`). Внешний порт задаётся `HOST_PORT` и по умолчанию равен `8380`.

Внутренний Docker DNS не требуется: `web` подключается к PostgreSQL по `DB_CONTAINER_IP`. При изменении подсети укажите в `.env` согласованные значения `DB_CONTAINER_IP`, `WEB_CONTAINER_IP` и `POSTGRES_HOST` (последнее оставьте равным `DB_CONTAINER_IP`).

Для Nginx Proxy Manager на том же Docker-хосте подключите его контейнер к сети `servicecatalog_net` и укажите upstream `http://172.30.0.10:8000`. Внешний порт `8380` можно использовать для локальной диагностики; GUI на сервере для работы приложения не нужен.

Статические файлы, включая стили Django Admin, раздаёт WhiteNoise внутри контейнера `web`; отдельный reverse proxy для них не требуется.

## Массовая синхронизация GLPI

Локальный кэш GLPI заполняется из API и отображается на странице «Кэш GLPI». При пустом корректном API-ответе для процессоров используется read-only MySQL fallback; ошибки API не подменяются данными БД.

Для ручного запуска используйте кнопку на странице кэша либо команду:

```text
docker compose exec web python manage.py sync_glpi_cache
```

Для cron/systemd допускается `--fail-on-partial`; `--no-linked-instances` обновляет только кэш. Параметры страницы API, числа worker-потоков и SQL-блоков задаются `GLPI_API_PAGE_SIZE`, `GLPI_COMPONENT_WORKERS`, `GLPI_DB_BATCH_SIZE`.
