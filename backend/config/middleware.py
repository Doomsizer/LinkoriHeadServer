from django.conf import settings


class SubdomainRoutingMiddleware:
    """
    Переключает urlconf на шлюз подписок при обращении к SUB_GATEWAY_HOST
    (sub.linkori.org), изолируя админку и основное API на linkori.org.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":", 1)[0].lower()
        if host == settings.SUB_GATEWAY_HOST:
            request.urlconf = settings.SUB_GATEWAY_URLCONF
        return self.get_response(request)
