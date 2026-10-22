import os


# Please don't change following settings unless you know what you are doing
STATIC_ROOT = '/data/static'

MEDIA_ROOT = os.path.join(STATIC_ROOT, 'media')

# SECURITY WARNING: keep the secret key used in production secret!
# Or just write your own secret-key here instead of using a env-variable
SECRET_KEY = "secret_key_place_holder"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False
TEMPLATE_DEBUG = DEBUG

# SECURITY WARNING: use your actual domain name in production!
# The ALLOWED_HOSTS environment variable (comma separated), if set, wins.
ALLOWED_HOSTS = ['*']

# Database
# https://docs.djangoproject.com/en/1.10/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': '/data/production.db',
    }
}

# Allow users to register by themselves
ALLOW_NEW_REGISTRATIONS = True

# Delete image files once you remove your pin
IMAGE_AUTO_DELETE = True

# thumbnail size control
IMAGE_SIZES = {
    'thumbnail': {'size': [240, 0]},
    'standard': {'size': [600, 0]},
    'square': {'crop': True, 'size': [125, 125]},
}

# Whether people can view pins without login
PUBLIC = True

# Accept HTTP Basic auth (username and password) on the API. API clients
# should use a token instead, see docs/src/api.md.
ALLOW_BASIC_AUTH = False

# Allow pinning images from private/LAN addresses (e.g. http://192.168.1.10/).
# Only enable this if you trust every account holder: it lets them make the
# server fetch from internal services.
ALLOW_PRIVATE_URL_FETCH = False

# Largest image, in bytes, downloaded when pinning by URL
MAX_FETCH_BYTES = 50 * 1024 * 1024

# Plugins to load, see docs/src/plugin-system.md
ENABLED_PLUGINS = [
    # 'pinry_plugins.batteries.plugin_example.Plugin',
]
