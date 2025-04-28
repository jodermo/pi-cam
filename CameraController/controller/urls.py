# CameraController/controller/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Main dashboard
    path('', views.index, name='index'),
    # Adjust a camera setting
    path('set/<str:setting>/', views.set_setting, name='set_setting'),
    # Restart the camera service
    path('restart/', views.restart, name='restart'),
    # Health check endpoint
    path('health/', views.health, name='health'),
    # Receive events/webhooks from the camera service
    path('camera-event/', views.camera_event, name='camera_event'),
]
