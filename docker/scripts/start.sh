#!/bin/bash
# -----------------------------------------------------------------------------
# docker-pinry start script
#
# Collects static files, applies migrations, deletes unused images, then
# runs nginx and gunicorn.
# Stops at the first error, e.g. a missing SECRET_KEY or ALLOWED_HOSTS.
# -----------------------------------------------------------------------------
set -e

cd /pinry

python manage.py collectstatic --noinput
python manage.py migrate --noinput
# Delete images no pin has used for a day, such as abandoned uploads.
python manage.py prune_images --delete

# The data volume may come from the host with other owners.
chown -R www-data:www-data /data

/usr/sbin/nginx

exec ./docker/scripts/_start_gunicorn.sh
