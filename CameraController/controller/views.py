# CameraController/controller/views.py

import os
import json
import requests
from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseServerError, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt

# Base URLs (injected via docker-compose env)
API = os.getenv('CAMERA_API_URL', '/api')                    # for client‐side URLs (proxy)
CAMERA_SERVICE_URL = os.getenv('CAMERA_SERVICE_URL', 'http://pi-cam-camera:8000')  # for server‐side calls

def index(request):
    """
    Renders the main dashboard with the live stream and control forms.
    """
    return render(request, 'controller/index.html', {
        'stream_url': f"{API}/stream",
        'settings': ['brightness', 'contrast', 'saturation', 'hue', 'gain', 'exposure'],
    })

def set_setting(request, setting):
    """
    POST form submits here to adjust a camera setting via the FastAPI service.
    """
    if request.method == 'POST':
        value = request.POST.get('value')
        try:
            resp = requests.post(
                f"{CAMERA_SERVICE_URL}/settings/{setting}",
                params={'value': value},
                timeout=5
            )
            resp.raise_for_status()
        except Exception as e:
            return HttpResponseServerError(f"Error setting {setting}: {e}")
    return redirect('index')

def restart(request):
    """
    Triggers a camera restart on the FastAPI service.
    """
    if request.method == 'POST':
        try:
            resp = requests.post(f"{CAMERA_SERVICE_URL}/restart", timeout=5)
            resp.raise_for_status()
        except Exception as e:
            return HttpResponseServerError(f"Error restarting camera: {e}")
    return redirect('index')

def health(request):
    """
    Returns JSON health status from the FastAPI service.
    """
    try:
        resp = requests.get(f"{CAMERA_SERVICE_URL}/health", timeout=5)
        data = resp.json()
        return JsonResponse(data, status=resp.status_code)
    except Exception:
        return JsonResponse({'status': 'error', 'camera_open': False}, status=503)

@csrf_exempt
def camera_event(request):
    """
    Receives POSTs from the camera service (e.g. restart events, alerts).
    Payload example: {"event":"restarted","timestamp":"2025-04-28T21:00:00Z"}
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("POST only")
    try:
        payload = json.loads(request.body)
        # TODO: persist payload to DB or trigger notifications
        # e.g., Event.objects.create(type=payload['event'], data=payload)
        return JsonResponse({'status': 'received'})
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")
