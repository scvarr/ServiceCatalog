#!/bin/sh
set -eu

if [ "$(id -u)" = "0" ]; then
    # Some hardened Docker hosts create /etc/hosts with restrictive ACLs.
    # The application itself still runs as the unprivileged app user below.
    chmod a+r /etc/hosts 2>/dev/null || true
    exec setpriv --reuid=app --regid=app --init-groups "$0" "$@"
fi

python manage.py migrate --noinput
python manage.py setup_roles
python manage.py collectstatic --noinput
exec "$@"
