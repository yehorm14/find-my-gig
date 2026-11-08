"""
Main URL Configuration for the find_my_gig project.
Routes traffic to the primary 'gigs' application.
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    # Admin Panel
    path('admin/', admin.site.urls),
    
    # Delegate all primary routing and authentication to the 'gigs' app
    path('', include('gigs.urls')),
]

# Uploaded media (profile pictures). Served by Django in development, or in
# production when SERVE_MEDIA=true (demo deployments only, see settings.py).
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
