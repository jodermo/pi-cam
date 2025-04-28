# CameraController/camera_controller/urls.py

from django.urls import path, include
from controller import views

urlpatterns = [
    path('', include('controller.urls')),
]
