# CameraController/controller/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('login/',       views.login_view,      name='login'),
    path('logout/',      views.logout_view,     name='logout'),

    # Main dashboard (requires login)
    path('',             views.index,           name='index'),
    path('set/<str:setting>/', views.set_setting, name='set_setting'),
    path('restart/',     views.restart,         name='restart'),
    path('switch/<int:idx>/', views.switch_camera, name='switch_camera'),

    # Capture photo and recording endpoints
    path('capture/',      views.capture_photo,   name='capture_photo'),
    path('record/start/', views.start_recording, name='start_recording'),
    path('record/stop/',  views.stop_recording,  name='stop_recording'),
    path('camera-frame/', views.camera_frame, name='camera_frame'),

    # Public health endpoint
    path('health/',       views.health,          name='health'),

    # Protected camera events webhook
    path('camera-event/', views.camera_event,    name='camera_event'),

    path('api/timelapse/', views.timelapse_list_api, name='api_timelapse_list'),
    path('api/media/',    views.media_list_api, name='api_media_list'),

    path('timelapse-gallery/', views.timelapse_gallery, name='timelapse_gallery'),
    path('media-browser/', views.media_browser, name='media_browser'),
    path('app-settings/', views.app_settings, name='app_settings'),

]
