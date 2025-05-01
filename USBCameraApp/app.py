#!/usr/bin/env python3
"""
FastAPI-based USB camera service with dynamic settings, on-the-fly apply, and MJPEG streaming.
"""
import os
import cv2
import threading
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Depends
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
RAW_SOURCES      = os.getenv("CAMERA_LOCATIONS", "/dev/video0")
CAMERA_SOURCES   = [s.strip() for s in RAW_SOURCES.split(",") if s.strip()]
if not CAMERA_SOURCES:
    CAMERA_SOURCES = ["/dev/video0"]

API_PREFIX       = os.getenv("CAMERA_API_URL", "/api").rstrip("/")
STREAM_PORT      = int(os.getenv("STREAM_PORT", "8000"))
RECONNECT_DELAY  = float(os.getenv("RECONNECT_DELAY", "1.0"))

FALLBACK_PATH    = os.getenv("FALLBACK_IMAGE", "")

# OpenCV property mapping
CAMERA_PROPS: Dict[str, int] = {
    "brightness": cv2.CAP_PROP_BRIGHTNESS,
    "contrast":   cv2.CAP_PROP_CONTRAST,
    "saturation": cv2.CAP_PROP_SATURATION,
    "hue":        cv2.CAP_PROP_HUE,
    "gain":       cv2.CAP_PROP_GAIN,
    "exposure":   cv2.CAP_PROP_EXPOSURE,
}

# In-memory state
settings_state: Dict[str, Any] = {}
camera = None
current_idx = 0
_fallback_bytes: bytes = b""
USING_FALLBACK = False
start_time = datetime.utcnow()
lock = threading.Lock()

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
            self.capture = None
        logger.info(f"Opening camera: {self.source}")
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera: {self.source}")
        self.capture = cap
        self.apply_settings()

    def apply_settings(self) -> bool:
        if not self.capture or not self.capture.isOpened():
            return False
        success = True
        for name, val in self.config.items():
            prop = CAMERA_PROPS.get(name)
            if prop is None:
                continue
            if not self.capture.set(prop, float(val)):
                logger.warning(f"Failed to set {name}={val}")
                success = False
            else:
                logger.info(f"Set {name}={val}")
        return success

    def update(self, new: Dict[str, Any]) -> bool:
        self.config.update(new)
        with lock:
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
# Initialization functions
# ----------------------------------------------------------------------------
def open_camera(idx: int = 0) -> bool:
    global camera, current_idx
    if idx < 0 or idx >= len(CAMERA_SOURCES):
        raise IndexError("Camera index out of range")
    current_idx = idx
    src = CAMERA_SOURCES[idx]
    if camera:
        camera.close()
    try:
        camera = Camera(src, settings_state)
        logger.info(f"Camera opened: {src}")
        return True
    except Exception as ex:
        logger.error(f"Open camera failed: {ex}")
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
                       b'Content-Type: image/jpeg\r\n\r\n'
                       + _fallback_bytes + b'\r\n')
                time.sleep(RECONNECT_DELAY)
                open_camera(current_idx)
                continue
            else:
                time.sleep(RECONNECT_DELAY)
                continue

        with lock:
            ok, frame = camera.read_frame()
        if not ok or frame is None:
            time.sleep(RECONNECT_DELAY)
            continue
        USING_FALLBACK = False
        ok, buf = cv2.imencode('.jpg', frame)
        if not ok:
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n'
               + buf.tobytes() + b'\r\n')

# ----------------------------------------------------------------------------
# FastAPI setup
# ----------------------------------------------------------------------------
app = FastAPI(openapi_prefix=API_PREFIX)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET","POST","PUT","DELETE","OPTIONS"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    # load defaults from env
    for key in CAMERA_PROPS.keys():
        val = os.getenv(f"CAMERA_{key.upper()}")
        if val is not None:
            try:
                settings_state[key] = float(val)
                logger.info(f"Default {key}={val} from ENV")
            except ValueError:
                logger.warning(f"Invalid ENV {key}={val}")
    # load fallback image
    generate_fallback()
    # open camera
    open_camera(0)

@app.on_event("shutdown")
def on_shutdown():
    if camera:
        camera.close()
        logger.info("Camera closed on shutdown")

# ----------------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------------
@app.get("/stream")
def stream():
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/health")
def health():
    status = camera and camera.is_opened()
    return JSONResponse(
        status_code=200 if status else 503,
        content={
            "uptime": (datetime.utcnow() - start_time).total_seconds(),
            "camera_open": bool(status),
            "using_fallback": USING_FALLBACK,
            "active_idx": current_idx,
            "settings": settings_state,
        }
    )

@app.get("/cameras")
def list_cameras():
    return {"sources": CAMERA_SOURCES, "active_idx": current_idx}

@app.post("/switch/{idx}")
def switch_camera(idx: int):
    try:
        ok = open_camera(idx)
        if not ok:
            raise RuntimeError("Failed to reopen camera")
        return {"active_idx": current_idx}
    except IndexError:
        raise HTTPException(400, "Index out of range")
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/settings")
def get_settings():
    return {"settings": settings_state}

@app.post("/settings/{setting}")
def set_one(setting: str, item: SingleSetting):
    if setting not in CAMERA_PROPS:
        raise HTTPException(400, f"Invalid setting: {setting}")
    try:
        value = float(item.value)
        settings_state[setting] = value
        success = camera.update({setting: value}) if camera else False
        return {"setting": setting, "value": value, "applied": success}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/settings")
def set_bulk(data: BulkSettings):
    invalid = []
    to_apply = {}
    for k, v in data.settings.items():
        if k in CAMERA_PROPS:
            try:
                to_apply[k] = float(v)
            except ValueError:
                invalid.append(k)
        else:
            invalid.append(k)
    settings_state.update(to_apply)
    success = camera.update(to_apply) if camera else False
    resp = {"applied": list(to_apply.keys()),
            "invalid": invalid}
    if not success:
        raise HTTPException(500, "Failed to apply some settings")
    return resp

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

# ----------------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=STREAM_PORT, log_level="info")