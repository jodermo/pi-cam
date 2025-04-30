"""
This implementation integrates dynamic camera settings updates with your existing FastAPI application.
The key changes:
1. Convert the OpenCV camera handling to use your Camera class
2. Add proper endpoints for updating settings on the fly
3. Ensure settings are applied immediately without restarting the Pi
"""

import os
import cv2
import threading
import logging
import time
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Read and parse camera sources
raw = os.getenv("CAMERA_LOCATIONS", "/dev/video0")
CAMERA_SOURCES = [src.strip() for src in raw.split(",") if src.strip()]
if not CAMERA_SOURCES:
    CAMERA_SOURCES = ["/dev/video0"]
logger.info(f"Configured camera sources: {CAMERA_SOURCES}")

# API configuration
STREAM_PORT     = int(os.getenv("STREAM_PORT", 8000))
API_PREFIX      = os.getenv("CAMERA_API_URL", "/api")
RECONNECT_DELAY = float(os.getenv("RECONNECT_DELAY", 1.0))
global USING_FALLBACK
USING_FALLBACK = True

# FastAPI app setup
app = FastAPI(openapi_prefix=API_PREFIX)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Threading lock 
lock = threading.Lock()
start_time = datetime.utcnow()
current_idx = 0  # index of the active camera source

# ----------------------------------------------------------------------------
# Camera settings mapping and state storage
# ----------------------------------------------------------------------------
CAMERA_PROPS = {
    "brightness": cv2.CAP_PROP_BRIGHTNESS,
    "contrast":   cv2.CAP_PROP_CONTRAST,
    "saturation": cv2.CAP_PROP_SATURATION,
    "hue":        cv2.CAP_PROP_HUE,
    "gain":       cv2.CAP_PROP_GAIN,
    "exposure":   cv2.CAP_PROP_EXPOSURE,
    # Add other properties as needed
}

# In-memory store of current camera settings
settings_state = {}

# Fallback image loading
FALLBACK_PATH = os.getenv("FALLBACK_IMAGE", "/app/fallback_image.png")
_fallback_bytes = None
if Path(FALLBACK_PATH).is_file():
    img = cv2.imread(FALLBACK_PATH)
    ret, buf = cv2.imencode('.jpg', img)
    if ret:
        _fallback_bytes = buf.tobytes()
        logger.info(f"Loaded fallback image from {FALLBACK_PATH}")
    else:
        logger.warning(f"Failed to encode fallback image at {FALLBACK_PATH}")
else:
    logger.warning(f"No fallback image found at {FALLBACK_PATH}")


class Camera:
    def __init__(self, source=None, config=None):
        """Initialize camera with source and settings"""
        self.source = source
        self.config = config or {}
        self.capture = None
        self.initialize_camera()
        
    def initialize_camera(self):
        """Initialize the camera with current settings"""
        # Close existing camera instance if it exists
        if self.capture is not None:
            self.capture.release()
            self.capture = None
            logger.info(f"Released previous camera handle for {self.source}")
            
        # Initialize with current settings
        logger.info(f"Opening camera: {self.source}")
        self.capture = cv2.VideoCapture(self.source)
        if not self.capture.isOpened():
            logger.error(f"Cannot open camera source {self.source}")
            raise RuntimeError(f"Cannot open camera {self.source}")
        logger.info(f"Camera {self.source} opened successfully")
        
        # Apply settings from config
        self.apply_camera_settings()
        
    def apply_camera_settings(self):
        """Apply camera settings to active camera"""
        if not self.capture or not self.capture.isOpened():
            logger.error("Cannot apply settings: camera not open")
            return False
            
        try:
            # Apply each setting from config to camera
            for setting, value in self.config.items():
                prop = CAMERA_PROPS.get(setting)
                if prop is not None:
                    success = self.capture.set(prop, value)
                    if success:
                        logger.info(f"Applied {setting}={value}")
                    else:
                        logger.warning(f"Failed to set {setting}={value}")
            
            return True
        except Exception as e:
            logger.error(f"Error applying camera settings: {str(e)}")
            return False
    
    def reload_camera_settings(self):
        """Reload camera with new settings without system restart"""
        logger.info("Reloading camera settings...")
        
        # Option 1: Try to apply settings directly
        success = self.apply_camera_settings()
        
        # Option 2: If direct application fails, re-initialize camera
        if not success:
            logger.info("Direct setting application failed, reinitializing camera")
            self.initialize_camera()
        
        return True
    
    def update_settings(self, new_settings):
        """Update camera settings and apply them immediately"""
        logger.info(f"Updating camera settings: {new_settings}")
        
        # Update config with new settings
        for key, value in new_settings.items():
            self.config[key] = value
            
        # Apply new settings
        return self.reload_camera_settings()
        
    def read_frame(self):
        """Read a frame from the camera"""
        if self.capture and self.capture.isOpened():
            return self.capture.read()
        return False, None
        
    def is_opened(self):
        """Check if camera is open"""
        return self.capture is not None and self.capture.isOpened()
        
    def release(self):
        """Release camera resources"""
        if self.capture:
            self.capture.release()
            self.capture = None


# Global camera instance
camera = None

def open_camera(idx=None):
    """Open or reopen the camera at CAMERA_SOURCES[idx]."""
    global camera, current_idx, settings_state
    
    if idx is not None:
        if idx < 0 or idx >= len(CAMERA_SOURCES):
            raise IndexError("Camera index out of range")
        current_idx = idx

    src = CAMERA_SOURCES[current_idx]
    
    # Release existing camera
    if camera is not None:
        camera.release()
        logger.info("Released previous camera instance.")

    # Initialize camera with saved settings
    try:
        camera = Camera(source=src, config=settings_state)
        logger.info(f"Camera {src} initialized with settings: {settings_state}")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize camera: {str(e)}")
        return False


@app.on_event("startup")
def startup_event():
    # Attempt to open the first camera
    try:
        # Load defaults from environment variables
        for setting, prop in CAMERA_PROPS.items():
            envvar = os.getenv(f"CAMERA_{setting.upper()}")
            if envvar is not None:
                try:
                    val = int(envvar)
                    settings_state[setting] = val
                    logger.info(f"Loaded default {setting}={val} from env")
                except ValueError:
                    logger.warning(f"Ignoring invalid CAMERA_{setting.upper()}={envvar}")
        
        # Open camera with loaded settings
        open_camera(0)
    except Exception as e:
        logger.warning(f"Startup failed to open camera: {e}")


@app.on_event("shutdown")
def shutdown_event():
    global camera
    if camera:
        camera.release()
        logger.info("Camera released on shutdown.")


def generate_frames():
    """MJPEG frame generator with auto-reconnect, back-off, and fallback."""
    global camera
    
    while True:
        try:
            # Serve fallback if camera is down
            if (camera is None or not camera.is_opened()) and _fallback_bytes:
                USING_FALLBACK = True
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' +
                    _fallback_bytes +
                    b'\r\n'
                )
                time.sleep(RECONNECT_DELAY)
                
                # Try to reopen camera
                open_camera()
                continue

            with lock:
                if camera is None or not camera.is_opened():
                    logger.warning("Camera not open; attempting reopen…")
                    open_camera()
                ok, frame = camera.read_frame()

            if not ok or frame is None:
                logger.warning("Frame capture failed; retrying after delay…")
                time.sleep(RECONNECT_DELAY)
                continue
                
            if ok and frame is not None:
                USING_FALLBACK = False
                
            ret, buf = cv2.imencode('.jpg', frame)
            if not ret:
                logger.error("Failed to JPEG-encode frame")
                continue

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                buf.tobytes() +
                b'\r\n'
            )
        except Exception as e:
            logger.exception(f"Unexpected error in frame loop: {str(e)}")
            time.sleep(RECONNECT_DELAY)


@app.get("/stream")
def stream():
    """
    Live MJPEG stream.
    If camera is unavailable but fallback is configured, streams the fallback image.
    """
    if camera is None or not camera.is_opened():
        if _fallback_bytes:
            logger.info("Camera unavailable—streaming fallback image.")
            return StreamingResponse(
                generate_frames(),
                media_type='multipart/x-mixed-replace; boundary=frame'
            )
        else:
            raise HTTPException(503, "Camera not available and no fallback configured")

    return StreamingResponse(
        generate_frames(),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )


@app.get("/health")
def health_check():
    ok = camera is not None and camera.is_opened()
    uptime = (datetime.utcnow() - start_time).total_seconds()
    return JSONResponse(
        status_code=(200 if ok else 503),
        content={
            "status":        "ok" if ok else "error",
            "camera_open":   ok,
            "using_fallback": USING_FALLBACK,
            "uptime_secs":   round(uptime,1),
            "current_idx":   current_idx,
            "current_src":   CAMERA_SOURCES[current_idx],
            "settings":      settings_state
        }
    )


@app.get("/cameras")
def list_cameras():
    """List all configured camera sources and the active index."""
    return {"sources": CAMERA_SOURCES, "active_idx": current_idx}


@app.post("/switch/{idx}")
def switch_camera(idx: int):
    """Switch active camera to the given index and reopen."""
    try:
        success = open_camera(idx)
        if not success:
            raise RuntimeError(f"Failed to open camera at index {idx}")
        return {"status": "switched", "active_idx": current_idx}
    except IndexError:
        raise HTTPException(400, f"Index {idx} out of range")
    except RuntimeError as e:
        raise HTTPException(500, str(e))


# Model for bulk settings update
class CameraSettings(BaseModel):
    settings: Dict[str, Any]


@app.post("/settings/{setting}")
def set_setting(setting: str, value: int):
    """Set and persist a single camera property."""
    if setting not in CAMERA_PROPS:
        valid_settings = ", ".join(CAMERA_PROPS.keys())
        raise HTTPException(400, f"Invalid setting. Valid settings are: {valid_settings}")
    
    with lock:
        # Update the setting in our state
        settings_state[setting] = value
        
        # Update the camera setting
        if camera:
            success = camera.update_settings({setting: value})
            if not success:
                raise HTTPException(500, "Failed to update camera setting")
    
    return {"setting": setting, "value": value, "applied": True}


@app.post("/settings")
def update_multiple_settings(settings_data: CameraSettings):
    """Update multiple camera settings at once"""
    valid_settings = {}
    invalid_settings = []
    
    # Validate settings
    for setting, value in settings_data.settings.items():
        if setting in CAMERA_PROPS:
            valid_settings[setting] = value
        else:
            invalid_settings.append(setting)
    
    # Apply valid settings
    with lock:
        # Update settings state
        settings_state.update(valid_settings)
        
        # Apply to camera
        if camera and valid_settings:
            success = camera.update_settings(valid_settings)
            if not success:
                raise HTTPException(500, "Failed to apply some settings")
    
    response = {"applied": list(valid_settings.keys())}
    if invalid_settings:
        response["invalid"] = invalid_settings
        
    return response


@app.get("/settings")
def get_settings():
    """Get current camera settings."""
    return {"settings": settings_state}


@app.post("/restart")
def restart_camera():
    """
    Attempt to reopen the current camera source.
    If it fails, fall back but still return 200 OK.
    """
    try:
        success = open_camera(current_idx)
        return {
            "status":       "restarted" if success else "failed",
            "camera_open":  camera.is_opened() if camera else False,
            "active_idx":   current_idx,
        }
    except Exception as e:
        logger.warning(f"Restart failed ({e}); streaming fallback image instead.")
        return {
            "status":     "fallback",
            "error":      str(e),
            "active_idx": current_idx,
        }


@app.post("/reload_settings")
def reload_settings():
    """Explicitly reload camera with current settings without restarting the Pi"""
    if not camera:
        raise HTTPException(503, "Camera not initialized")
        
    try:
        with lock:
            success = camera.reload_camera_settings()
        
        return {
            "status": "settings reloaded" if success else "reload failed",
            "settings": settings_state
        }
    except Exception as e:
        logger.error(f"Error reloading settings: {str(e)}")
        raise HTTPException(500, f"Failed to reload settings: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=STREAM_PORT)