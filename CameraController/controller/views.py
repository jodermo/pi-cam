# CameraController/controller/views.py

import os
import json
import logging
import threading
import time
import tempfile
import base64
import requests
import subprocess
from datetime import datetime
import zipfile
from django.shortcuts import render, redirect
from django.http import (
    JsonResponse,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseServerError,
    FileResponse, 
    Http404
)
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods, require_POST
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

    return render(request, 'controller/camera.html', {
        'stream_url': STREAM_PATH,
        'settings_fields': settings_list,
        'db_settings': db_settings,
        'camera_list'    : camera_list if len(camera_list) > 1 else None,
        'active_index': active_index,
        'is_recording': is_recording,
        'last_video_url': last_video_url,
    })



@login_required
@require_POST
def set_setting(request, setting):
    if setting not in SETTINGS_FIELDS + ['auto_exposure']:
        return JsonResponse({'error': 'Invalid setting'}, status=400)

    # parse & save to your DB as before
    raw = request.POST.get('value')
    val = raw.lower() in ['on','true','1'] if setting=='auto_exposure' else int(raw)
    obj, _ = CameraSettings.objects.get_or_create(pk=1)
    if setting=='exposure':
        obj.manual_exposure = val
    elif setting=='auto_exposure':
        obj.auto_exposure = val
    else:
        setattr(obj, setting, val)
    obj.save()

    svc      = CAMERA_SERVICE_BASE.rstrip('/')
    api_root = API_PREFIX.rstrip('/')
    try:
        resp = requests.post(
            f"{svc}{api_root}/settings/{setting}",
            json={'value': val},       # ← send JSON, not query params
            headers={'Content-Type':'application/json'},
            timeout=2,
        )
        resp.raise_for_status()
        camera_data = resp.json()
    except Exception as e:
        return JsonResponse({
            'error': 'Saved locally but failed to apply on camera',
            'detail': str(e)
        }, status=502)

    return JsonResponse({
        'status':  'ok',
        'setting': setting,
        'value':   val,
        'camera':  camera_data
    })

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
@require_POST
def restart(request):
    svc      = CAMERA_SERVICE_BASE.rstrip('/')
    api_root = API_PREFIX.rstrip('/')
    try:
        resp = requests.post(f"{svc}{api_root}/restart", timeout=2)
        resp.raise_for_status()
        camera_data = resp.json()
    except Exception as e:
        return JsonResponse({
            'error': 'Failed to restart camera service',
            'detail': str(e)
        }, status=502)

    return JsonResponse(camera_data)


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
def media_browser(request):
    base_url = settings.MEDIA_URL.rstrip('/')
    photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
    videos_dir = os.path.join(settings.MEDIA_ROOT, 'videos')
    tl_folder = AppConfigSettings.objects.get_or_create(pk=1)[0].timelapse_folder or 'timelapse'
    tl_dir = os.path.join(settings.MEDIA_ROOT, tl_folder)

    def list_urls(dirpath, exts, subpath):
        if not os.path.isdir(dirpath):
            return []
        return [
            {'filename': fn, 'url': f"{base_url}/{subpath}/{fn}"}
            for fn in sorted(os.listdir(dirpath), reverse=True)
            if fn.lower().endswith(exts)
        ]

    photos    = list_urls(photos_dir, ('.jpg','.jpeg','.png'), 'photos')
    videos    = list_urls(videos_dir, ('.mp4',),               'videos')
    timelapse = list_urls(tl_dir,    ('.jpg','.jpeg','.png'), tl_folder)

    return render(request, 'controller/media_browser.html', {
        'photos':    photos,
        'videos':    videos,
        'timelapses': timelapse,
    })

@login_required
@csrf_exempt
@require_http_methods(["GET","DELETE"])
def photos_api(request):
    photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
    if not os.path.isdir(photos_dir):
        return JsonResponse([], safe=False) if request.method=="GET" else JsonResponse({'deleted':0})
    files = sorted(
        [f for f in os.listdir(photos_dir) if f.lower().endswith(('.jpg','.jpeg','.png'))],
        reverse=True
    )
    if request.method == "DELETE":
        count=0
        for fn in files:
            try:
                os.remove(os.path.join(photos_dir, fn)); count+=1
            except: pass
        return JsonResponse({'deleted': count})
    # GET:
    data = [{'filename':f,'url':settings.MEDIA_URL.rstrip('/')+'/photos/'+f} for f in files]
    return JsonResponse(data, safe=False)


@login_required
@csrf_exempt
@require_http_methods(["GET","DELETE"])
def video_api(request):
    vids_dir = os.path.join(settings.MEDIA_ROOT, 'videos')
    if not os.path.isdir(vids_dir):
        return JsonResponse([], safe=False) if request.method=="GET" else JsonResponse({'deleted':0})
    files = sorted([f for f in os.listdir(vids_dir) if f.lower().endswith('.mp4')], reverse=True)
    if request.method=="DELETE":
        count=0
        for fn in files:
            try:
                os.remove(os.path.join(vids_dir,fn)); count+=1
            except: pass
        return JsonResponse({'deleted': count})
    data = [{'filename':f,'url':settings.MEDIA_URL.rstrip('/')+'/videos/'+f} for f in files]
    return JsonResponse(data, safe=False)


@login_required
@csrf_exempt
@require_http_methods(["GET","DELETE"])
def timelapse_api(request):
    config, _ = AppConfigSettings.objects.get_or_create(pk=1)
    folder = config.timelapse_folder or 'timelapse'
    tl_dir = os.path.join(settings.MEDIA_ROOT, folder)

    if not os.path.isdir(tl_dir):
        return JsonResponse(
            [] if request.method=="GET" else {'deleted': 0},
            safe=False
        )

    files = sorted(
        [f for f in os.listdir(tl_dir) if f.lower().endswith(('.jpg','.jpeg','.png'))],
        reverse=True
    )

    if request.method == "DELETE":
        count = 0
        for fn in files:
            try:
                os.remove(os.path.join(tl_dir, fn))
                count += 1
            except:
                pass
        return JsonResponse({'deleted': count})

    base = settings.MEDIA_URL.rstrip('/')
    data = [{
        'filename': f,
        'url': f"{base}/{folder}/{f}"
    } for f in files]

    return JsonResponse(data, safe=False)



@login_required
@csrf_exempt
def delete_photo(request, filename):
    """Delete a single snapshot file."""
    if request.method != 'DELETE':
        return HttpResponseBadRequest('DELETE only')
    photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
    path = os.path.join(photos_dir, filename)
    if not os.path.isfile(path):
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        os.remove(path)
        return JsonResponse({'status': 'deleted', 'filename': filename})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@csrf_exempt
def delete_video(request, filename):
    """Delete a single recording."""
    if request.method != 'DELETE':
        return HttpResponseBadRequest('DELETE only')
    vids_dir = os.path.join(settings.MEDIA_ROOT, 'videos')
    path = os.path.join(vids_dir, filename)
    if not os.path.isfile(path):
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        os.remove(path)
        return JsonResponse({'status': 'deleted', 'filename': filename})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@csrf_exempt
def delete_timelapse(request, filename):
    """Delete a single timelapse frame."""
    if request.method != 'DELETE':
        return HttpResponseBadRequest('DELETE only')
    config, _ = AppConfigSettings.objects.get_or_create(pk=1)
    folder = config.timelapse_folder or 'timelapse'
    tl_dir = os.path.join(settings.MEDIA_ROOT, folder)
    path = os.path.join(tl_dir, filename)
    if not os.path.isfile(path):
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        os.remove(path)
        return JsonResponse({'status': 'deleted', 'filename': filename})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def download_timelapse(request):
    # 1. Load timelapse folder and speed settings
    config, _ = AppConfigSettings.objects.get_or_create(pk=1)
    folder = config.timelapse_folder or 'timelapse_frames'
    
    # ms/frame from POST, fallback to interval (min) or 500ms
    try:
        speed_ms = int(request.POST.get(
            'speed_ms',
            (config.timelapse_interval_minutes * 60 * 1000) if config.timelapse_interval_minutes else 500
        ))
    except (ValueError, TypeError):
        speed_ms = 500
    fps = max(1, int(1000 / speed_ms))

    # 2. Locate frames
    frame_dir = os.path.join(settings.MEDIA_ROOT, folder)
    if not os.path.isdir(frame_dir):
        raise Http404(f"Timelapse folder '{folder}' not found.")
    frames = sorted(
        os.path.join(frame_dir, f)
        for f in os.listdir(frame_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    )
    if not frames:
        raise Http404("No timelapse frames found.")

    # 3. Create temp output and list file
    tmp = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
    tmp_path = tmp.name
    tmp.close()
    list_txt = tmp_path + '.txt'
    with open(list_txt, 'w') as f:
        for frame in frames:
            f.write(f"file '{frame}'\n")

    # 4. Try generating with concat demuxer
    concat_cmd = [
        'ffmpeg', '-f', 'concat', '-safe', '0', '-i', list_txt,
        '-r', str(fps), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', tmp_path
    ]
    try:
        subprocess.run(
            concat_cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg concat failed: {e.stderr}")
        # fallback to image2 glob input
        pattern = os.path.join(frame_dir, '*.jpg')
        glob_cmd = [
            'ffmpeg', '-y', '-framerate', str(fps),
            '-pattern_type', 'glob', '-i', pattern,
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', tmp_path
        ]
        try:
            subprocess.run(
                glob_cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )
        except subprocess.CalledProcessError as e2:
            logger.error(f"FFmpeg glob failed: {e2.stderr}")
            os.remove(tmp_path)
            os.remove(list_txt)
            raise Http404("Failed to generate timelapse video.")
    finally:
        # remove the list file
        if os.path.exists(list_txt):
            os.remove(list_txt)

    # 5. Stream file
    response = FileResponse(
        open(tmp_path, 'rb'),
        as_attachment=True,
        filename='timelapse.mp4'
    )
    response['X-Accel-Buffering'] = 'no'
    return response



# Shared helper
def _build_zip_response(filenames, base_dir, subdir, archive_name):
    # Create a temp zip file
    tmp = tempfile.NamedTemporaryFile(suffix='.zip', delete=False)
    tmp_path = tmp.name
    tmp.close()

    # Write the selected files into the zip under subdir/
    with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fname in filenames:
            src = os.path.join(base_dir, fname)
            if os.path.isfile(src):
                zf.write(src, arcname=os.path.join(subdir, fname))

    # Stream the zip back
    response = FileResponse(
        open(tmp_path, 'rb'),
        as_attachment=True,
        filename=archive_name
    )
    response['X-Accel-Buffering'] = 'no'
    return response


@login_required
@require_POST
def download_selected_photos(request):
    photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
    filenames = request.POST.getlist('filenames')
    if not filenames:
        return HttpResponseBadRequest('No photos selected')
    return _build_zip_response(filenames, photos_dir, 'photos', 'selected_photos.zip')


@login_required
@require_POST
def download_all_photos(request):
    photos_dir = os.path.join(settings.MEDIA_ROOT, 'photos')
    filenames = [
        f for f in os.listdir(photos_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ]
    if not filenames:
        return HttpResponseBadRequest('No photos available')
    return _build_zip_response(filenames, photos_dir, 'photos', 'all_photos.zip')


@login_required
@require_POST
def download_selected_videos(request):
    vids_dir = os.path.join(settings.MEDIA_ROOT, 'videos')
    filenames = request.POST.getlist('filenames')
    if not filenames:
        return HttpResponseBadRequest('No videos selected')
    return _build_zip_response(filenames, vids_dir, 'videos', 'selected_videos.zip')


@login_required
@require_POST
def download_all_videos(request):
    vids_dir = os.path.join(settings.MEDIA_ROOT, 'videos')
    filenames = [
        f for f in os.listdir(vids_dir)
        if f.lower().endswith('.mp4')
    ]
    if not filenames:
        return HttpResponseBadRequest('No videos available')
    return _build_zip_response(filenames, vids_dir, 'videos', 'all_videos.zip')


@login_required
@require_POST
def download_selected_timelapse(request):
    from .models import AppConfigSettings
    config, _ = AppConfigSettings.objects.get_or_create(pk=1)
    folder = config.timelapse_folder or 'timelapse'
    tl_dir = os.path.join(settings.MEDIA_ROOT, folder)

    filenames = request.POST.getlist('filenames')
    if not filenames:
        return HttpResponseBadRequest('No timelapse frames selected')
    return _build_zip_response(filenames, tl_dir, folder, 'selected_timelapse.zip')


@login_required
@require_POST
def download_all_timelapse(request):
    from .models import AppConfigSettings
    config, _ = AppConfigSettings.objects.get_or_create(pk=1)
    folder = config.timelapse_folder or 'timelapse'
    tl_dir = os.path.join(settings.MEDIA_ROOT, folder)

    filenames = [
        f for f in os.listdir(tl_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    ]
    if not filenames:
        return HttpResponseBadRequest('No timelapse frames available')
    return _build_zip_response(filenames, tl_dir, folder, 'all_timelapse.zip')