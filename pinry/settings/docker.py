import logging

from django.core.exceptions import ImproperlyConfigured

from .base import *


def _env_list(name):
    return [
        item.strip() for item in os.environ[name].split(',') if item.strip()
    ]


def _env_flag(name):
    return os.environ.get(name, '').strip().lower() in ('1', 'true', 'yes', 'on')


# SECURITY WARNING: keep the secret key used in production secret!
# Set it in the environment or in local_settings.py; there is no default.
SECRET_KEY = os.environ.get('SECRET_KEY', '')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# SECURITY WARNING: use your actual domain name in production!
# Set ALLOWED_HOSTS in the environment, e.g. "pins.example.com,192.168.1.10".
ALLOWED_HOSTS = ['*']

# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'postgres',
        'USER': 'postgres',
        'HOST': 'db',
        'PORT': 5432,
    }
}

USE_X_FORWARDED_HOST = True

# Set HTTPS=true when Pinry is served over HTTPS by a reverse proxy that sets
# X-Forwarded-Proto. Cookies are then only sent over HTTPS.
if _env_flag('HTTPS'):
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# HSTS makes browsers refuse plain HTTP for this many seconds. Only set it
# once HTTPS works, since browsers remember it.
SECURE_HSTS_SECONDS = int(os.environ.get('HSTS_SECONDS', '0'))

REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES'] = [
    'rest_framework.renderers.JSONRenderer',
]

# should not ignore import error in production, local_settings is required
from .local_settings import *

# Environment variables win over local_settings.py, so existing installs
# (whose local_settings.py sets ALLOWED_HOSTS = ['*']) can be locked down
# without editing it.
if 'ALLOWED_HOSTS' in os.environ:
    ALLOWED_HOSTS = _env_list('ALLOWED_HOSTS')
# Django 2.2 format: host names without a scheme, e.g. "pins.example.com".
if 'CSRF_TRUSTED_ORIGINS' in os.environ:
    CSRF_TRUSTED_ORIGINS = _env_list('CSRF_TRUSTED_ORIGINS')

if SECRET_KEY in ('', 'PLEASE_REPLACE_ME', 'secret_key_place_holder'):
    raise ImproperlyConfigured(
        "SECRET_KEY is not set. Set it in the environment or in "
        "local_settings.py."
    )

if ALLOWED_HOSTS == ['*']:
    logging.warning(
        "ALLOWED_HOSTS is ['*'], so any Host header is accepted. Set the "
        "ALLOWED_HOSTS environment variable to your domain names."
    )
