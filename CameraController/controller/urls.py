# CameraController/controller/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('login/',  views.login_view,  name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Main dashboard (requires login)
    path('',               views.index,          name='index'),
    path('set/<str:setting>/', views.set_setting, name='set_setting'),
    path('restart/',       views.restart,        name='restart'),
    path('switch/<int:idx>/', views.switch_camera, name='switch_camera'),

    # Public health endpoint
    path('health/',        views.health,         name='health'),

    # Protected camera events webhook
    path('camera-event/',  views.camera_event,   name='camera_event'),
]
