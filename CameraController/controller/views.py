# CameraController/controller/views.py

import os
import json
import requests

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponseServerError, HttpResponseBadRequest
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt, csrf_protect


API = os.getenv('CAMERA_API_URL', '/api')
CAMERA_SERVICE_URL = os.getenv('CAMERA_SERVICE_URL', 'http://pi-cam-camera:8000')


@csrf_protect
def login_view(request):
    """
    Render login form and authenticate users.
    """
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('index')
        else:
            return render(request, 'controller/login.html', {
                'error': 'Invalid username or password'
            })
    return render(request, 'controller/login.html')


@login_required
def logout_view(request):
    """
    Log the user out and redirect to login.
    """
    logout(request)
    return redirect('login')


@login_required
def index(request):
    """
    Renders the main dashboard; requires login.
    """
    try:
        resp = requests.get(f"{CAMERA_SERVICE_URL}/cameras", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        camera_list  = data.get('sources', [])
        active_index = data.get('active_idx', 0)
    except requests.RequestException:
        camera_list, active_index = [], None

    return render(request, 'controller/index.html', {
        'stream_url':   f"{API}/stream",
        'settings':     ['brightness','contrast','saturation','hue','gain','exposure'],
        'camera_list':  camera_list,
        'active_index': active_index,
    })


@login_required
def set_setting(request, setting):
    """
    POST to adjust a camera setting via FastAPI (requires login).
    """
    if request.method == 'POST':
        value = request.POST.get('value')
        try:
            r = requests.post(
                f"{CAMERA_SERVICE_URL}/settings/{setting}",
                params={'value': value}, timeout=5
            )
            r.raise_for_status()
        except requests.RequestException as e:
            return HttpResponseServerError(f"Error setting {setting}: {e}")
    return redirect('index')


@login_required
def restart(request):
    """
    POST to restart the camera service via FastAPI (requires login).
    """
    if request.method == 'POST':
        try:
            r = requests.post(f"{CAMERA_SERVICE_URL}/restart", timeout=5)
            r.raise_for_status()
        except requests.RequestException as e:
            return HttpResponseServerError(f"Error restarting camera: {e}")
    return redirect('index')


@login_required
def switch_camera(request, idx):
    """
    POST here to switch to camera index `idx` (requires login).
    """
    if request.method == 'POST':
        try:
            r = requests.post(f"{CAMERA_SERVICE_URL}/switch/{idx}", timeout=5)
            r.raise_for_status()
        except requests.RequestException as e:
            return HttpResponseServerError(f"Error switching to camera {idx}: {e}")
    return redirect('index')


def health(request):
    """
    Public JSON health status from the FastAPI service.
    """
    try:
        r = requests.get(f"{CAMERA_SERVICE_URL}/health", timeout=5)
        return JsonResponse(r.json(), status=r.status_code)
    except requests.RequestException:
        return JsonResponse({'status':'error','camera_open':False}, status=503)


@login_required
@csrf_exempt
def camera_event(request):
    """
    Receives POSTs from the camera service (requires login).
    """
    if request.method != 'POST':
        return HttpResponseBadRequest("POST only")
    try:
        payload = json.loads(request.body)
        # TODO: persist payload to DB or trigger notifications
        return JsonResponse({'status': 'received'})
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")
