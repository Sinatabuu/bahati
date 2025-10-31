import threading
from django.utils.deprecation import MiddlewareMixin

_user_local = threading.local()

def get_current_user():
    return getattr(_user_local, "user", None)

class CurrentUserMiddleware(MiddlewareMixin):
    def process_request(self, request):
        _user_local.user = getattr(request, "user", None)
    def process_response(self, request, response):
        _user_local.user = None
        return response
