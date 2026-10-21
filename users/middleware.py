from django.conf import settings
from django.http import HttpResponseForbidden
from django.utils.deprecation import MiddlewareMixin


class Public(MiddlewareMixin):

    acceptable_paths = (
        "/api/v2/profile/",
        "/admin/login/",
    )

    def process_request(self, request):
        if settings.PUBLIC is False and not request.user.is_authenticated:
            if not any(
                request.path.startswith(path) for path in self.acceptable_paths
            ):
                return HttpResponseForbidden()
