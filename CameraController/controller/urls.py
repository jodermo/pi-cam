# CameraController/controller/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('login/',  views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Main dashboard (requires login)
    path('', views.index, name='index'),
    path('set/<str:setting>/', views.set_setting, name='set_setting'),
    path('restart/',views.restart, name='restart'),
    path('switch/<int:idx>/', views.switch_camera, name='switch_camera'),

    # Capture photo and recording endpoints
    path('capture/', views.capture_photo, name='capture_photo'),
    path('record/start/', views.start_recording, name='start_recording'),
    path('record/stop/', views.stop_recording, name='stop_recording'),
    path('camera-frame/', views.camera_frame, name='camera_frame'),

    # Public health endpoint
    path('health/', views.health, name='health'),

    # Protected camera events webhook
    path('camera-event/', views.camera_event, name='camera_event'),
    path('api/snapshot/', views.capture_photo, name='api_snapshot'),

    # Photos
    path('api/photos/', views.photos_api, name='api_media_list'),
    path('api/photos/<str:filename>/', views.delete_photo, name='api_delete_photo'),
    path('api/photos/delete-all/', views.delete_all_photos, name='api_delete_all_photos'),

    # Videos
    path('api/videos/', views.video_api, name='api_video_list'),
    path('api/videos/<str:filename>/', views.delete_video, name='api_delete_video'),
    path('api/videos/delete-all/', views.delete_all_videos, name='api_delete_all_videos'),

    # Timelapse
    path('api/timelapse/', views.timelapse_api, name='api_timelapse_list'),
    path('api/timelapse/<str:filename>/', views.delete_timelapse, name='api_delete_timelapse'),
    path('api/timelapse/delete-all/',  views.delete_all_timelapse, name='api_delete_all_timelapse'),

    path('timelapse-gallery/', views.timelapse_gallery, name='timelapse_gallery'),
    path('media-browser/', views.media_browser, name='media_browser'),
    path('app-settings/', views.app_settings, name='app_settings'),

]
