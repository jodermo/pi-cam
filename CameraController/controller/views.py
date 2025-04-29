# CameraController/controller/views.py

import os
import json
import logging
import threading
import time
import tempfile
import base64
import requests
from datetime import datetime

from django.shortcuts import render, redirect
from django.http import (
    JsonResponse,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseServerError
)
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.conf import settings
from django import forms

import cv2
from .models import CameraSettings, AppConfigSettings
from .stream_recorder import StreamRecorder

logger = logging.getLogger(__name__)

API_PREFIX          = os.getenv('CAMERA_API_URL', '/api')
STREAM_PATH         = f"{API_PREFIX}/stream"

CAMERA_SERVICE_BASE = os.getenv('CAMERA_SERVICE_URL', 'http://pi-cam-camera:8000')
INTERNAL_STREAM_URL = f"{CAMERA_SERVICE_BASE.rstrip('/')}/api/stream"

# Properties to expose in UI
SETTINGS_FIELDS = [
    'brightness', 'contrast', 'saturation', 'hue', 'gain', 'exposure'
]

# Recording state
_recording_thread = None
_recording_path = None

class StreamRecorder(threading.Thread):
    """Background thread to record MJPEG stream to MP4 file."""
    def __init__(self, stream_url, output_path, fps=20.0):
        super().__init__()
        self.stream_url = stream_url
        self.output_path = output_path
        self.stop_event = threading.Event()
        self.fps = fps

    def run(self):
        cap = cv2.VideoCapture(self.stream_url)
        if not cap.isOpened():
            logger.error(f"Cannot open stream: {self.stream_url}")
            return
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(self.output_path, fourcc, self.fps, (width, height))
        while not self.stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue
            writer.write(frame)
        writer.release()
        cap.release()
        logger.info(f"Saved recording to {self.output_path}")



class AppSettingsForm(forms.ModelForm):
    class Meta:
        model = AppConfigSettings
        fields = [
            'enable_timelapse',
            'timelapse_interval_minutes',
            'timelapse_folder',
            'capture_resolution_width',
            'capture_resolution_height',
        ]
        widgets = {
            'timelapse_interval_minutes': forms.NumberInput(attrs={'min': 1}),
            'capture_resolution_width': forms.NumberInput(attrs={'min': 1}),
            'capture_resolution_height': forms.NumberInput(attrs={'min': 1}),
        }


@csrf_protect
def login_view(request):
    if request.method == 'POST':
        user = authenticate(
            request,
            username=request.POST.get('username'),
            password=request.POST.get('password')
        )
        if user:
            login(request, user)
            return redirect('index')
        return render(request, 'controller/login.html', {'error': 'Invalid credentials'})
    return render(request, 'controller/login.html')

@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def index(request):
    settings_obj, _ = CameraSettings.objects.get_or_create(pk=1)
    db_settings = {
        'brightness': settings_obj.brightness,
        'contrast': settings_obj.contrast,
        'saturation': settings_obj.saturation,
        'hue': settings_obj.hue,
        'gain': settings_obj.gain,
        'exposure': settings_obj.manual_exposure,
        'auto_exposure': settings_obj.auto_exposure,
    }

    camera_list = ["/dev/video0"]
    active_index = 0

    settings_list = []
    for key in ['brightness', 'contrast', 'saturation', 'hue', 'gain', 'exposure']:
        settings_list.append({'name': key, 'value': db_settings[key]})

    is_recording = _recording_thread is not None and _recording_thread.is_alive()
    last_video_url = None

    if _recording_path and not is_recording:
        rel = os.path.relpath(_recording_path, getattr(settings, 'MEDIA_ROOT', ''))
        rel = rel.replace('\\', '/')
        last_video_url = settings.MEDIA_URL.rstrip('/') + '/' + rel

    return render(request, 'controller/index.html', {
        'stream_url': STREAM_PATH,
        'settings_fields': settings_list,
        'db_settings': db_settings,
        'camera_list': camera_list,
        'active_index': active_index,
        'is_recording': is_recording,
        'last_video_url': last_video_url,
    })




@login_required
def set_setting(request, setting):
    if request.method != 'POST' or setting not in SETTINGS_FIELDS + ['auto_exposure']:
        return JsonResponse({'error': 'Invalid setting or method'}, status=400)

    raw = request.POST.get('value')
    if raw is None:
        return JsonResponse({'error': 'Missing value'}, status=400)

    if setting == 'auto_exposure':
        val = raw.lower() in ['on', 'true', '1']
    else:
        try:
            val = int(raw)
        except (ValueError, TypeError):
            return HttpResponseBadRequest('Bad value')

    settings_obj, _ = CameraSettings.objects.get_or_create(pk=1)
    if setting == 'exposure':
        settings_obj.manual_exposure = val
    elif setting == 'auto_exposure':
        settings_obj.auto_exposure = val
    else:
        setattr(settings_obj, setting, val)
    settings_obj.save()

    return JsonResponse({'status': 'ok', 'setting': setting, 'value': val})

@login_required
def capture_photo(request):
    """
    Capture one fresh frame from the camera MJPEG stream (internal URL),
    persist it under MEDIA_ROOT/photos/, and return it as a JPEG download.
    """
    # 1) Open the MJPEG stream from the internal camera service
    cap = cv2.VideoCapture(INTERNAL_STREAM_URL)
    if not cap.isOpened():
        return JsonResponse(
            {'error': f'Cannot open stream at {INTERNAL_STREAM_URL}'},
            status=503
        )

    # 2) Flush stale/buffered frames so we get a current image
    for _ in range(5):
        cap.read()

    # 3) Read the next (fresh) frame
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return JsonResponse({'error': 'Could not read frame from stream'}, status=500)

    # 4) Ensure the photos directory exists
    photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
    try:
        os.makedirs(photos_dir, exist_ok=True)
    except Exception as e:
        return JsonResponse(
            {'error': f'Failed to create photos directory: {e}'},
            status=500
        )

    # 5) Build a UTC-timestamped filename and save to disk
    fname = datetime.utcnow().strftime('photo_%Y%m%d_%H%M%S.jpg')
    fpath = os.path.join(photos_dir, fname)
    if not cv2.imwrite(fpath, frame):
        return JsonResponse({'error': 'Failed to write photo to disk'}, status=500)

    # 6) Encode the same frame into memory for immediate response
    ret, buf = cv2.imencode('.jpg', frame)
    if not ret:
        return JsonResponse({'error': 'Failed to encode JPEG'}, status=500)

    # 7) Send the JPEG back as a file download
    response = HttpResponse(buf.tobytes(), content_type='image/jpeg')
    response['Content-Disposition'] = f'attachment; filename="{fname}"'
    return response


@login_required
def start_recording(request):
    global _recording_thread, _recording_path
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')

    if _recording_thread and _recording_thread.is_alive():
        return JsonResponse({'error': 'Already recording'}, status=400)

    # ensure the videos folder exists
    videos_dir = os.path.join(settings.MEDIA_ROOT, 'videos')
    os.makedirs(videos_dir, exist_ok=True)

    # timestamped filename
    fname = datetime.utcnow().strftime('stream_%Y%m%d_%H%M%S.mp4')
    _recording_path = os.path.join(videos_dir, fname)

    _recording_thread = StreamRecorder(INTERNAL_STREAM_URL, _recording_path)
    _recording_thread.start()
    return JsonResponse({'status': 'started'})



@login_required
def stop_recording(request):
    global _recording_thread, _recording_path
    if request.method != 'POST':
        return HttpResponseBadRequest('POST only')
    if not _recording_thread or not _recording_thread.is_alive():
        return HttpResponseServerError('Not recording')

    _recording_thread.stop_event.set()
    _recording_thread.join()

    # build URL under /media/videos
    rel = os.path.relpath(_recording_path, getattr(settings, 'MEDIA_ROOT', ''))
    rel = rel.replace('\\', '/')
    url = settings.MEDIA_URL.rstrip('/') + '/' + rel
    return JsonResponse({'status': 'stopped', 'url': url})



@login_required
def camera_frame(request):
    cap = cv2.VideoCapture(INTERNAL_STREAM_URL)
    if not cap.isOpened():
        return JsonResponse({'error': 'stream unavailable'}, status=503)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return JsonResponse({'error': 'capture failed'}, status=500)

    ret, buf = cv2.imencode('.jpg', frame)
    if not ret:
        return JsonResponse({'error': 'encode failed'}, status=500)

    b64 = base64.b64encode(buf.tobytes()).decode('utf-8')
    return JsonResponse({'frame': b64})


@login_required
def switch_camera(request, idx):
    if request.method!='POST': return HttpResponseBadRequest('POST only')
    try: idx=int(idx)
    except: return HttpResponseBadRequest('Bad index')
    # TODO: persist or inform service
    return JsonResponse({'status':'switched','active_idx':idx})

@login_required
def restart(request):
    return JsonResponse({'status':'restarted'})



@csrf_exempt
def health(request):
    try:
        url = f"{CAMERA_SERVICE_BASE.rstrip('/')}/health"
        response = requests.get(url, timeout=2)

        try:
            camera_data = response.json()
        except ValueError:
            camera_data = None  # Antwort war kein JSON

        if response.status_code == 200 and camera_data:
            return JsonResponse(camera_data)

        # Fehlerhafte Antwort, versuche JSON zu extrahieren
        try:
            error_data = response.json()
        except ValueError:
            error_data = {'raw_body': response.text}

        return JsonResponse({
            'error': 'Camera service unhealthy',
            'http_status': response.status_code,
            'response_body': error_data,
        }, status=503)

    except requests.ConnectionError as e:
        return JsonResponse({
            'error': 'Connection error to camera service',
            'details': str(e),
        }, status=503)

    except requests.Timeout as e:
        return JsonResponse({
            'error': 'Timeout when connecting to camera service',
            'details': str(e),
        }, status=503)

    except Exception as e:
        return JsonResponse({
            'error': 'Unexpected error contacting camera service',
            'details': str(e),
        }, status=503)


@login_required
@csrf_exempt
def camera_event(request):
    if request.method!='POST': return HttpResponseBadRequest('POST only')
    try: payload=json.loads(request.body)
    except: return HttpResponseBadRequest('Invalid JSON')
    # TODO: handle payload
    return JsonResponse({'status':'received'})




@login_required
def timelapse_gallery(request):
    """Display list of timelapse images and handle settings form."""

    # Correct: load AppConfigSettings
    config, _ = AppConfigSettings.objects.get_or_create(pk=1)

    if request.method == 'POST':
        form = AppSettingsForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            return redirect('timelapse_gallery')
    else:
        form = AppSettingsForm(instance=config)

    timelapse_dir = os.path.join(settings.MEDIA_ROOT, config.timelapse_folder)
    if not os.path.exists(timelapse_dir):
        images = []
    else:
        images = sorted([
            f for f in os.listdir(timelapse_dir)
            if f.lower().endswith(('.jpg', '.jpeg', '.png'))
        ], reverse=True)

    images_urls = [
        settings.MEDIA_URL.rstrip('/') + f'/{config.timelapse_folder}/{img}'
        for img in images
    ]

    return render(request, 'controller/timelapse_gallery.html', {
        'images': images_urls,
        'form': form
    })


@login_required
def app_settings(request):
    """View to update global AppConfigSettings parameters."""

    config, _ = AppConfigSettings.objects.get_or_create(pk=1)

    if request.method == 'POST':
        form = AppSettingsForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            return redirect('app_settings')
    else:
        form = AppSettingsForm(instance=config)

    return render(request, 'controller/app_settings.html', {
        'form': form,
    })


@login_required
def media_browser(request):
    photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
    files = sorted(os.listdir(photos_dir), reverse=True)
    images = [
        settings.MEDIA_URL.rstrip('/') + '/photos/' + fn
        for fn in files
        if fn.lower().endswith(('.jpg','jpeg','png'))
    ]
    return render(request, 'controller/media_browser.html', {'images': images})


@login_required
def media_list_api(request):
    photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
    if not os.path.isdir(photos_dir):
        return JsonResponse([], safe=False)

    files = sorted(
        [f for f in os.listdir(photos_dir) if f.lower().endswith(('.jpg','.jpeg','.png'))],
        reverse=True
    )

    data = [
        {
            'filename': f,
            'url': settings.MEDIA_URL.rstrip('/') + '/photos/' + f
        }
        for f in files
    ]
    return JsonResponse(data, safe=False)


@login_required
def timelapse_list_api(request):
    config, _ = AppConfigSettings.objects.get_or_create(pk=1)
    folder = config.timelapse_folder or 'timelapse'
    timelapse_dir = os.path.join(settings.MEDIA_ROOT, folder)
    if not os.path.isdir(timelapse_dir):
        return JsonResponse([], safe=False)

    files = sorted(
        [f for f in os.listdir(timelapse_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))],
        reverse=True
    )

    data = [
        {
            'filename': f,
            'url': settings.MEDIA_URL.rstrip('/') + '/' + folder + '/' + f
        }
        for f in files
    ]
    return JsonResponse(data, safe=False)

