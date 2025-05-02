#!/usr/bin/env python3
"""
FastAPI-based USB camera & audio service with dynamic settings, on-the-fly apply,
MJPEG video streaming, and Ogg/Opus audio streaming.
Enhanced with dynamic device detection and parallel audio streaming.
"""
import os
import cv2
import threading
import logging
import time
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# ----------------------------------------------------------------------------
# Load environment and configure logging
# ----------------------------------------------------------------------------
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("camera_service")

# Configure uvicorn access logger to suppress specific paths
uvicorn_access_logger = logging.getLogger("uvicorn.access")

class StreamAccessFilter(logging.Filter):
    def filter(self, record):
        # Check if the log message contains audio stream paths
        message = str(record.getMessage()) if hasattr(record, 'getMessage') else str(record)
        if 'GET /api/stream/audio' in message or 'GET /stream/audio' in message:
            return False  # Do not log this message
        return True  # Log other messages

# Apply the filter to the access logger
uvicorn_access_logger.addFilter(StreamAccessFilter())

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
API_PREFIX         = os.getenv("CAMERA_API_URL", "/api").rstrip("/")
STREAM_PORT        = int(os.getenv("STREAM_PORT", "8000"))
RECONNECT_DELAY    = float(os.getenv("RECONNECT_DELAY", "1.0"))
FALLBACK_PATH      = os.getenv("FALLBACK_IMAGE", "")
DEVICE_CACHE_PATH  = os.getenv("DEVICE_CACHE_PATH", "/tmp/camera_devices.json")
DEVICE_CACHE_TTL   = int(os.getenv("DEVICE_CACHE_TTL", "3600"))  # seconds

# OpenCV property mapping
CAMERA_PROPS: Dict[str, int] = {
    "brightness": cv2.CAP_PROP_BRIGHTNESS,
    "contrast":   cv2.CAP_PROP_CONTRAST,
    "saturation": cv2.CAP_PROP_SATURATION,
    "hue":        cv2.CAP_PROP_HUE,
    "gain":       cv2.CAP_PROP_GAIN,
    "exposure":   cv2.CAP_PROP_EXPOSURE,
}

# ----------------------------------------------------------------------------
# Global state
# ----------------------------------------------------------------------------
settings_state: Dict[str, Any] = {}
camera = None
current_idx = 0
_fallback_bytes: bytes = b""
USING_FALLBACK = False
start_time = datetime.utcnow()
cam_lock = threading.Lock()

# Audio streaming
audio_proc: Optional[subprocess.Popen] = None
current_audio_idx = 0
audio_lock = threading.Lock()
detected_cameras: List[Dict[str, Any]] = []
detected_audio_devices: List[Dict[str, Any]] = []

# ----------------------------------------------------------------------------
# Device detection functions
# ----------------------------------------------------------------------------
def detect_cameras() -> List[Dict[str, Any]]:
    """
    Dynamically detect available cameras and their capabilities.
    Returns a list of camera device dictionaries.
    """
    cameras = []
    # Try to detect cameras through OpenCV by checking indices 0-9
    for i in range(10):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            # Get camera info
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            cameras.append({
                "id": i,
                "path": f"/dev/video{i}",
                "name": f"Camera {i}",
                "width": width,
                "height": height,
                "fps": fps
            })
            cap.release()
    
    # Also check for common camera paths in Linux
    for i in range(10):
        path = f"/dev/video{i}"
        if Path(path).exists() and not any(c["path"] == path for c in cameras):
            cameras.append({
                "id": i,
                "path": path,
                "name": f"Camera {i}",
                "width": 640,
                "height": 480,
                "fps": 30.0
            })
    
    return cameras

def detect_audio_devices() -> List[Dict[str, Any]]:
    """
    Dynamically detect available audio input devices.
    Returns a list of audio device dictionaries.
    """
    devices = []
    
    # Try to get ALSA devices using arecord
    try:
        proc = subprocess.run(
            ["arecord", "-L"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if proc.returncode == 0:
            current_device = None
            for line in proc.stdout.splitlines():
                if not line.startswith(" "):
                    current_device = line.strip()
                    if current_device and not current_device.startswith("null"):
                        devices.append({
                            "id": len(devices),
                            "path": current_device,
                            "name": current_device,
                            "type": "alsa"
                        })
    except FileNotFoundError:
        logger.warning("arecord not found, ALSA device detection skipped")
    
    # Try to get PulseAudio devices using pactl
    try:
        proc = subprocess.run(
            ["pactl", "list", "sources"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if proc.returncode == 0:
            current_device = None
            current_name = None
            
            for line in proc.stdout.splitlines():
                line = line.strip()
                
                if line.startswith("Name:"):
                    current_device = line[5:].strip()
                elif line.startswith("Description:") and current_device:
                    current_name = line[12:].strip()
                    # Check if it's not a monitor device (which records output, not input)
                    if not "monitor" in current_device.lower() and current_device not in [d["path"] for d in devices]:
                        devices.append({
                            "id": len(devices),
                            "path": current_device,
                            "name": current_name or current_device,
                            "type": "pulse"
                        })
                    current_device = None
                    current_name = None
    except FileNotFoundError:
        logger.warning("pactl not found, PulseAudio device detection skipped")
    
    # Always add a default device
    if not any(d["path"] == "default" for d in devices):
        devices.append({
            "id": len(devices),
            "path": "default",
            "name": "System Default",
            "type": "default"
        })
    
    return devices

def cache_devices(cameras, audio_devices):
    """Save detected devices to cache file."""
    try:
        with open(DEVICE_CACHE_PATH, 'w') as f:
            json.dump({
                'timestamp': time.time(),
                'cameras': cameras,
                'audio_devices': audio_devices
            }, f)
        logger.info(f"Saved device cache to {DEVICE_CACHE_PATH}")
    except Exception as e:
        logger.error(f"Failed to cache devices: {e}")

def load_cached_devices() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Load devices from cache if available and not expired."""
    try:
        if Path(DEVICE_CACHE_PATH).exists():
            with open(DEVICE_CACHE_PATH, 'r') as f:
                data = json.load(f)
                
            if time.time() - data['timestamp'] < DEVICE_CACHE_TTL:
                return data['cameras'], data['audio_devices']
    except Exception as e:
        logger.error(f"Failed to load device cache: {e}")
    
    return [], []

def refresh_devices():
    """Refresh device lists and update cache."""
    global detected_cameras, detected_audio_devices
    
    logger.info("Refreshing device lists...")
    detected_cameras = detect_cameras()
    detected_audio_devices = detect_audio_devices()
    
    # Cache the results
    cache_devices(detected_cameras, detected_audio_devices)
    
    logger.info(f"Found {len(detected_cameras)} cameras and {len(detected_audio_devices)} audio devices")
    return detected_cameras, detected_audio_devices

# ----------------------------------------------------------------------------
# Pydantic models
# ----------------------------------------------------------------------------
class BulkSettings(BaseModel):
    settings: Dict[str, Any]

class SingleSetting(BaseModel):
    value: Any

# ----------------------------------------------------------------------------
# Camera wrapper
# ----------------------------------------------------------------------------
class Camera:
    def __init__(self, source: str, config: Dict[str, Any]):
        self.source = source
        self.config = config.copy()
        self.capture = None
        self._init_camera()

    def _init_camera(self):
        if self.capture:
            self.capture.release()
        logger.info(f"Opening camera: {self.source}")
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera: {self.source}")
        self.capture = cap
        self.apply_settings()

    def apply_settings(self) -> bool:
        if not self.capture or not self.capture.isOpened():
            return False
        ok = True
        for name, val in self.config.items():
            prop = CAMERA_PROPS.get(name)
            if prop is None:
                continue
            if not self.capture.set(prop, float(val)):
                logger.warning(f"Failed to set {name}={val}")
                ok = False
            else:
                logger.info(f"Set {name}={val}")
        return ok

    def update(self, new: Dict[str, Any]) -> bool:
        self.config.update(new)
        with cam_lock:
            return self.apply_settings() or self._reinit()

    def _reinit(self) -> bool:
        try:
            self._init_camera()
            return True
        except Exception as e:
            logger.error(f"Re-init failed: {e}")
            return False

    def read_frame(self):
        if not self.capture or not self.capture.isOpened():
            return False, None
        return self.capture.read()

    def is_opened(self) -> bool:
        return bool(self.capture and self.capture.isOpened())

    def close(self):
        if self.capture:
            self.capture.release()
            self.capture = None

# ----------------------------------------------------------------------------
# Initialization helpers
# ----------------------------------------------------------------------------
def open_camera(idx: int = 0) -> bool:
    global camera, current_idx
    
    # Make sure we have cameras detected
    if not detected_cameras:
        refresh_devices()
    
    if idx < 0 or idx >= len(detected_cameras):
        raise IndexError("Camera index out of range")
    
    current_idx = idx
    if camera:
        camera.close()
    
    try:
        camera = Camera(detected_cameras[idx]["path"], settings_state)
        return True
    except Exception as e:
        logger.error(f"Open camera failed: {e}")
        return False

def generate_fallback():
    global _fallback_bytes
    if FALLBACK_PATH and Path(FALLBACK_PATH).is_file():
        img = cv2.imread(FALLBACK_PATH)
        ok, buf = cv2.imencode('.jpg', img)
        if ok:
            _fallback_bytes = buf.tobytes()
            logger.info("Loaded fallback image")

def generate_frames():
    global USING_FALLBACK
    while True:
        if not camera or not camera.is_opened():
            if _fallback_bytes:
                USING_FALLBACK = True
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' +
                       _fallback_bytes + b'\r\n')
                time.sleep(RECONNECT_DELAY)
                open_camera(current_idx)
                continue
            time.sleep(RECONNECT_DELAY)
            continue

        with cam_lock:
            ok, frame = camera.read_frame()
        if not ok or frame is None:
            time.sleep(RECONNECT_DELAY)
            continue

        USING_FALLBACK = False
        ok, buf = cv2.imencode('.jpg', frame)
        if not ok:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' +
               buf.tobytes() + b'\r\n')

def open_audio(idx: int = 0):
    global audio_proc, current_audio_idx
    
    # Make sure we have audio devices detected
    if not detected_audio_devices:
        refresh_devices()
    
    if idx < 0 or idx >= len(detected_audio_devices):
        raise IndexError("Audio index out of range")
    
    with audio_lock:
        if audio_proc and audio_proc.poll() is None:
            audio_proc.terminate()
            audio_proc.wait(timeout=2)
        
        dev = detected_audio_devices[idx]["path"]
        dev_type = detected_audio_devices[idx]["type"]
        
        # Adjust command based on the device type
        if dev_type == "pulse":
            input_args = ["-f", "pulse", "-i", dev]
        else:  # alsa or default
            input_args = ["-f", "alsa", "-i", dev]
        
        cmd = [
            "ffmpeg",
            *input_args,
            "-c:a", "libopus",      # Changed from -acodec to -c:a
            "-b:a", "48k",          # Lower bitrate for better stability
            "-ar", "48000",         # Standard sample rate
            "-ac", "2",             # Stereo output
            "-vbr", "on",           # Variable bit rate
            "-compression_level", "10",  # Maximum compression
            "-application", "audio",  # Optimize for audio
            "-packet_loss", "5",    # More resilient streaming
            "-f", "ogg",            # Container format
            "pipe:1"
        ]
        
        try:
            audio_proc = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.DEVNULL
            )
            current_audio_idx = idx
            logger.info(f"Audio streaming on device: {dev} (type: {dev_type})")
            return True
        except Exception as e:
            logger.error(f"Failed to start audio: {e}")
            return False

# ----------------------------------------------------------------------------
# Custom middleware for log filtering
# ----------------------------------------------------------------------------
class LogFilterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # Skip logging for streaming endpoints
        if path in ['/api/stream/audio', '/stream/audio']:
            # Process the request without logging
            return await call_next(request)
        
        # Normal processing for other paths
        return await call_next(request)

# ----------------------------------------------------------------------------
# FastAPI setup
# ----------------------------------------------------------------------------
app = FastAPI(openapi_prefix=API_PREFIX)

# Add the log filter middleware
app.add_middleware(LogFilterMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    # Try to load devices from cache first
    global detected_cameras, detected_audio_devices
    cached_cameras, cached_audio = load_cached_devices()
    
    if cached_cameras and cached_audio:
        detected_cameras = cached_cameras
        detected_audio_devices = cached_audio
        logger.info(f"Loaded {len(detected_cameras)} cameras and {len(detected_audio_devices)} audio devices from cache")
    else:
        # If no cache or expired, refresh devices
        refresh_devices()
    
    # load env defaults for camera
    for key in CAMERA_PROPS:
        val = os.getenv(f"CAMERA_{key.upper()}")
        if val:
            try:
                settings_state[key] = float(val)
            except ValueError:
                pass
    
    generate_fallback()
    
    # Open the first available camera and audio device
    if detected_cameras:
        open_camera(0)
    
    if detected_audio_devices:
        open_audio(0)

@app.on_event("shutdown")
def on_shutdown():
    if camera:
        camera.close()
    if audio_proc and audio_proc.poll() is None:
        audio_proc.terminate()

# ----------------------------------------------------------------------------
# Device management routes
# ----------------------------------------------------------------------------
@app.post("/refresh-devices")
def api_refresh_devices():
    """Force refresh of camera and audio device lists."""
    cameras, audio = refresh_devices()
    return {
        "cameras": cameras,
        "audio_devices": audio
    }

# ----------------------------------------------------------------------------
# Video routes
# ----------------------------------------------------------------------------
@app.get("/stream")
def stream():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/cameras")
def list_cameras():
    return {"sources": detected_cameras, "active_idx": current_idx}

@app.post("/switch/{idx}")
def switch_camera(idx: int):
    try:
        success = open_camera(idx)
        if not success:
            raise RuntimeError("Could not open camera")
        return {"active_idx": current_idx, "camera": detected_cameras[current_idx]}
    except IndexError:
        raise HTTPException(400, "Camera index out of range")
    except Exception as e:
        raise HTTPException(500, str(e))

# ----------------------------------------------------------------------------
# Settings routes
# ----------------------------------------------------------------------------
@app.get("/settings")
def get_settings():
    return {"settings": settings_state}

@app.post("/settings/{setting}")
def set_one(setting: str, item: SingleSetting):
    if setting not in CAMERA_PROPS:
        raise HTTPException(400, "Invalid setting")
    try:
        val = float(item.value)
        settings_state[setting] = val
        applied = camera.update({setting: val}) if camera else False
        return {"setting": setting, "value": val, "applied": applied}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/settings")
def set_bulk(data: BulkSettings):
    invalid, to_apply = [], {}
    for k,v in data.settings.items():
        if k in CAMERA_PROPS:
            try:
                to_apply[k] = float(v)
            except ValueError:
                invalid.append(k)
        else:
            invalid.append(k)
    settings_state.update(to_apply)
    success = camera.update(to_apply) if camera else False
    return {"applied": list(to_apply.keys()), "invalid": invalid, "success": success}

@app.post("/reload_settings")
def reload_settings():
    if not camera:
        raise HTTPException(503, "Camera not initialized")
    ok = camera.apply_settings()
    if not ok:
        raise HTTPException(500, "Reload failed")
    return {"status": "reloaded", "settings": settings_state}

@app.post("/restart")
def restart():
    ok = open_camera(current_idx)
    return {"status": "restarted" if ok else "failed", "active_idx": current_idx}

@app.get("/health")
def health():
    return JSONResponse({
        "uptime": (datetime.utcnow() - start_time).total_seconds(),
        "camera_open": bool(camera and camera.is_opened()),
        "using_fallback": USING_FALLBACK,
        "active_idx": current_idx,
        "settings": settings_state,
        "audio_open": bool(audio_proc and audio_proc.poll() is None),
        "audio_idx": current_audio_idx,
        "detected_cameras": len(detected_cameras),
        "detected_audio_devices": len(detected_audio_devices),
    }, status_code=200)

# ----------------------------------------------------------------------------
# Audio routes
# ----------------------------------------------------------------------------
@app.get("/audio-sources")
def list_audio():
    return {"sources": detected_audio_devices, "active_idx": current_audio_idx}

@app.post("/switch-audio/{idx}")
def switch_audio(idx: int):
    try:
        success = open_audio(idx)
        if not success:
            raise HTTPException(500, "Failed to open audio device")
        return {"active_idx": current_audio_idx, "device": detected_audio_devices[current_audio_idx]}
    except IndexError:
        raise HTTPException(400, "Audio index out of range")
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/stream/audio")
def stream_audio():
    if not audio_proc or audio_proc.stdout is None:
        raise HTTPException(503, "Audio not initialized")
    
    # Add proper headers for streaming and CORS
    headers = {
        "Content-Type": "audio/ogg",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
        "Access-Control-Allow-Origin": "*",  # Allow cross-origin access
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*"
    }
    
    return StreamingResponse(
        audio_proc.stdout,
        media_type="audio/ogg",
        headers=headers
    )

# Also add the API path to ensure compatibility with updated nginx config
@app.get("/api/stream/audio")
def api_stream_audio():
    if not audio_proc or audio_proc.stdout is None:
        raise HTTPException(503, "Audio not initialized")
    
    # Add proper headers for streaming
    headers = {
        "Content-Type": "audio/ogg",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    
    return StreamingResponse(
        audio_proc.stdout,
        media_type="audio/ogg",
        headers=headers
    )

# ----------------------------------------------------------------------------
# Run as script
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=STREAM_PORT,
        log_level="warning",  # Changed from info to warning
        access_log=False      # Disable access logs completely
    )