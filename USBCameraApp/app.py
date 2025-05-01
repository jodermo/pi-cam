#!/usr/bin/env python3
"""
FastAPI-based USB camera & audio service with dynamic settings, on-the-fly apply,
MJPEG video streaming, and Ogg/Opus audio streaming.
"""
import os
import cv2
import threading
import logging
import time
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
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

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
RAW_SOURCES        = os.getenv("CAMERA_LOCATIONS", "/dev/video0")
CAMERA_SOURCES     = [s.strip() for s in RAW_SOURCES.split(",") if s.strip()] or ["/dev/video0"]
RAW_AUDIO_INPUTS   = os.getenv("AUDIO_INPUTS", "pulse,alsa_input.usb-046d_0825_123456-02.analog-stereo,hw:1,0")
AUDIO_INPUTS       = [s.strip() for s in RAW_AUDIO_INPUTS.split(",") if s.strip()] or ["default"]

API_PREFIX         = os.getenv("CAMERA_API_URL", "/api").rstrip("/")
STREAM_PORT        = int(os.getenv("STREAM_PORT", "8000"))
RECONNECT_DELAY    = float(os.getenv("RECONNECT_DELAY", "1.0"))
FALLBACK_PATH      = os.getenv("FALLBACK_IMAGE", "")

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

audio_proc        = None
current_audio_idx = 0
audio_lock        = threading.Lock()

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
    if idx < 0 or idx >= len(CAMERA_SOURCES):
        raise IndexError("Camera index out of range")
    current_idx = idx
    if camera:
        camera.close()
    try:
        camera = Camera(CAMERA_SOURCES[idx], settings_state)
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
    if idx < 0 or idx >= len(AUDIO_INPUTS):
        raise IndexError("Audio index out of range")
    with audio_lock:
        if audio_proc and audio_proc.poll() is None:
            audio_proc.kill()
        dev = AUDIO_INPUTS[idx]
        cmd = [
            "ffmpeg",
            "-f", "alsa", "-i", dev,
            "-acodec", "libopus", "-f", "ogg", "pipe:1"
        ]
        audio_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        current_audio_idx = idx
        logger.info(f"Audio streaming on device: {dev}")

# ----------------------------------------------------------------------------
# FastAPI setup
# ----------------------------------------------------------------------------
app = FastAPI(openapi_prefix=API_PREFIX)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    # load env defaults for camera
    for key in CAMERA_PROPS:
        val = os.getenv(f"CAMERA_{key.upper()}")
        if val:
            try:
                settings_state[key] = float(val)
            except ValueError:
                pass
    generate_fallback()
    open_camera(0)
    open_audio(0)

@app.on_event("shutdown")
def on_shutdown():
    if camera:
        camera.close()
    if audio_proc and audio_proc.poll() is None:
        audio_proc.kill()

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
    return {"sources": CAMERA_SOURCES, "active_idx": current_idx}

@app.post("/switch/{idx}")
def switch_camera(idx: int):
    try:
        success = open_camera(idx)
        if not success:
            raise RuntimeError("Could not open camera")
        return {"active_idx": current_idx}
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
    }, status_code=200)

# ----------------------------------------------------------------------------
# Audio routes
# ----------------------------------------------------------------------------
@app.get("/audio-sources")
def list_audio():
    return {"sources": AUDIO_INPUTS, "active_idx": current_audio_idx}

@app.post("/switch-audio/{idx}")
def switch_audio(idx: int):
    try:
        open_audio(idx)
        return {"active_idx": current_audio_idx}
    except IndexError:
        raise HTTPException(400, "Audio index out of range")
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/stream/audio")
def stream_audio():
    if not audio_proc or audio_proc.stdout is None:
        raise HTTPException(503, "Audio not initialized")
    return StreamingResponse(
        audio_proc.stdout,
        media_type="audio/ogg"
    )

# ----------------------------------------------------------------------------
# Run as script
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=STREAM_PORT, log_level="info")
