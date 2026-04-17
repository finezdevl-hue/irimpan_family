from .views import live_stream_context


def navigation_context(request):
    return live_stream_context(request)
