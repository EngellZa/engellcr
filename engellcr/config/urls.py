from django.contrib import admin
from django.urls import path, include

from . import views as core_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', core_views.health, name='health'),
    path('q/', include('cotizador_app.share_urls')),
    path('', include('cotizador_app.urls')),
]
