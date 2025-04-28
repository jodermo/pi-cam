# CameraController/camera_controller/urls.py

from django.urls import path, include

urlpatterns = [
    # All routes for the camera controller app
    path('', include('controller.urls')),
]
