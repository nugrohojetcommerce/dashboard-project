class UserActivityMiddleware:
    """
    Middleware that records authenticated user activities.
    Stores username, requested URL, client IP address, and timestamp in the database.
    Designed with minimum overhead and failsafe error handling.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Skip logging for static assets, media files, debug toolbar, and favicons
        path = request.path
        if (
            path.startswith('/static/')
            or path.startswith('/media/')
            or path.startswith('/__debug__/')
            or path == '/favicon.ico'
        ):
            return response

        try:
            # We record after get_response so that if the user just logged in on this request,
            # request.user is authenticated and available.
            if hasattr(request, 'user') and request.user.is_authenticated:
                from .models import UserActivityLog

                username = request.user.username
                ip = self.get_client_ip(request)
                url = request.get_full_path()

                UserActivityLog.objects.create(
                    username=username,
                    url=url,
                    ip_address=ip,
                )
        except Exception:
            # Silently pass on logging errors so application functionality is never interrupted
            pass

        return response

    @staticmethod
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # When behind reverse proxies (Nginx/Cloudflare), first IP in list is client IP
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

