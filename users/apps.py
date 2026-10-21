from __future__ import unicode_literals

from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = 'users'

    def ready(self):
        # Registers the user_login_failed receiver for the login throttle.
        from users.auth import throttling  # noqa: F401
