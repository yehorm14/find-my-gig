"""
Read-only portfolio demo mode (DEMO_MODE=true, off by default).

Everything is enforced server-side:
- ReadOnlyDemoMiddleware rejects every non-safe HTTP method for every visitor
  (anonymous, demo or real accounts, admin included), except starting a demo
  session and signing out. Nothing a visitor does can write to the shared
  database, so one visitor cannot change what another sees.
- demo_start signs a visitor in as one fixed seeded account (musician or band)
  and flags the session. It exists only when DEMO_MODE is on.
"""
from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import Resolver404, resolve
from django.views.decorators.http import require_POST

SAFE_METHODS = ('GET', 'HEAD', 'OPTIONS')
DEMO_ACCOUNTS = {'musician': 'musician_1', 'band': 'band_user_1'}
DEMO_SESSION_KEY = 'is_demo_session'
READ_ONLY_MESSAGE = (
    'This is a read-only demo: changes are not saved. '
    'Run the project locally to try editing.'
)


class ReadOnlyDemoMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEMO_MODE and request.method not in SAFE_METHODS:
            if not _is_allowed_write(request):
                return self.reject(request)
        return self.get_response(request)

    @staticmethod
    def reject(request):
        wants_json = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or 'application/json' in request.headers.get('Content-Type', '')
            or 'application/json' in request.headers.get('Accept', '')
        )
        if wants_json:
            return JsonResponse(
                {'success': False, 'error': 'demo_read_only', 'message': READ_ONLY_MESSAGE},
                status=403,
            )
        return render(request, 'gigs/demo_read_only.html', {'message': READ_ONLY_MESSAGE}, status=403)


def _is_allowed_write(request):
    match = getattr(request, 'resolver_match', None) or resolve_or_none(request.path_info)
    return bool(match) and match.view_name in ('gigs:demo_start', 'gigs:logout')


def resolve_or_none(path):
    try:
        return resolve(path)
    except Resolver404:
        return None


@require_POST
def demo_start(request, role):
    if not settings.DEMO_MODE or role not in DEMO_ACCOUNTS:
        raise Http404
    try:
        user = User.objects.get(username=DEMO_ACCOUNTS[role])
    except User.DoesNotExist:
        raise Http404('Demo data has not been seeded.')
    logout(request)  # drop any previous session first
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session[DEMO_SESSION_KEY] = True
    return redirect('gigs:dashboard')


def demo_context(request):
    return {'demo_mode': settings.DEMO_MODE, 'demo_message': READ_ONLY_MESSAGE}
