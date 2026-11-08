"""
Main URL Configuration for the find_my_gig project.
Routes traffic to the primary 'gigs' application.
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

urlpatterns = [
    # Admin Panel
    path('admin/', admin.site.urls),
    
    # Delegate all primary routing and authentication to the 'gigs' app
    path('', include('gigs.urls')),
]

# Uploaded media (profile pictures) is served by Django only in development.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
