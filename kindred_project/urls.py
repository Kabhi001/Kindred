"""
URL configuration for kindred_project project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('matcher.urls', namespace='matcher')),
]

urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / 'static')
