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

    # Photos
    path('api/photos/', views.photos_api, name='api_photo_list'),
    path('api/photos/<str:filename>/', views.delete_photo, name='api_delete_photo'),
    path('download/photos/selected/', views.download_selected_photos, name='download_selected_photos'),
    path('download/photos/all/',      views.download_all_photos,      name='download_all_photos'),

    # Videos
    path('api/videos/', views.video_api, name='api_video_list'),
    path('api/videos/<str:filename>/', views.delete_video, name='api_delete_video'),
    path('download/videos/selected/', views.download_selected_videos, name='download_selected_videos'),
    path('download/videos/all/',      views.download_all_videos,      name='download_all_videos'),

    # Timelapse
    path('api/timelapse/', views.timelapse_api, name='api_timelapse_list'),
    path('api/timelapse/<str:filename>/', views.delete_timelapse, name='api_delete_timelapse'),
    path('timelapse/download/', views.download_timelapse, name='download_timelapse'),
    path('download/timelapse/selected/', views.download_selected_timelapse, name='download_selected_timelapse'),
    path('download/timelapse/all/',      views.download_all_timelapse,      name='download_all_timelapse'),
    path('timelapse-gallery/', views.timelapse_gallery, name='timelapse_gallery'),

    # Media Brwoser
    path('media-browser/', views.media_browser, name='media_browser'),

]
