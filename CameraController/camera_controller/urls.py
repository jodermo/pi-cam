# CameraController/camera_controller/urls.py

from django.urls import path, include
from controller import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', include('controller.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
