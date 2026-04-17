from django.utils.deprecation import MiddlewareMixin

from .models import SiteVisitCounter


class PublicVisitCounterMiddleware(MiddlewareMixin):
    session_key = 'public_site_visit_counted'

    def process_response(self, request, response):
        if request.method != 'GET':
            return response
        if response.status_code >= 400:
            return response
        if request.path.startswith('/admin-panel/') or request.path.startswith('/admin-login/') or request.path.startswith('/logout/'):
            return response
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return response
        if getattr(request, 'session', None) is None:
            return response
        if request.session.get(self.session_key):
            return response

        SiteVisitCounter.increment()
        request.session[self.session_key] = True
        return response
