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

# Threading lock and camera handle
lock        = threading.Lock()
cap         = None
start_time  = datetime.utcnow()
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


def open_camera(idx=None):
    """Open or reopen the camera at CAMERA_SOURCES[idx]."""
    global cap, current_idx
    if idx is not None:
        if idx < 0 or idx >= len(CAMERA_SOURCES):
            raise IndexError("Camera index out of range")
        current_idx = idx

    src = CAMERA_SOURCES[current_idx]
    if cap is not None:
        cap.release()
        logger.info("Released previous camera handle.")

    logger.info(f"Opening camera #{current_idx}: {src}")
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        logger.error(f"Cannot open camera source {src}")
        raise RuntimeError(f"Cannot open camera {src}")
    logger.info(f"Camera {src} opened successfully.")

    # Re-apply any saved settings
    for setting, val in settings_state.items():
        prop = CAMERA_PROPS.get(setting)
        if prop is not None:
            cap.set(prop, val)
            logger.info(f"Restored camera {setting} → {val}")


@app.on_event("startup")
def startup_event():
    # Attempt to open the first camera
    try:
        open_camera(0)
    except Exception as e:
        logger.warning(f"Startup failed to open camera: {e}")
        return

    # Load defaults from environment variables
    for setting, prop in CAMERA_PROPS.items():
        envvar = os.getenv(f"CAMERA_{setting.upper()}")
        if envvar is not None:
            try:
                val = int(envvar)
                cap.set(prop, val)
                settings_state[setting] = val
                logger.info(f"Loaded default {setting}={val} from env")
            except ValueError:
                logger.warning(f"Ignoring invalid CAMERA_{setting.upper()}={envvar}")


@app.on_event("shutdown")
def shutdown_event():
    global cap
    if cap:
        cap.release()
        logger.info("Camera released on shutdown.")


def generate_frames():
    """MJPEG frame generator with auto-reconnect, back-off, and fallback."""
    global cap
    while True:
        try:
            # Serve fallback if camera is down
            if (cap is None or not cap.isOpened()) and _fallback_bytes:
                USING_FALLBACK = True
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' +
                    _fallback_bytes +
                    b'\r\n'
                )
                time.sleep(RECONNECT_DELAY)
                continue

            with lock:
                if cap is None or not cap.isOpened():
                    logger.warning("Camera not open; attempting reopen…")
                    open_camera()
                ok, frame = cap.read()

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
        except Exception:
            logger.exception("Unexpected error in frame loop")
            time.sleep(RECONNECT_DELAY)


@app.get("/stream")
def stream():
    """
    Live MJPEG stream.
    If camera is unavailable but fallback is configured, streams the fallback image.
    """
    if cap is None or not cap.isOpened():
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
    ok = cap is not None and cap.isOpened()
    uptime = (datetime.utcnow() - start_time).total_seconds()
    return JSONResponse(
        status_code=(200 if ok else 503),
        content={
            "status":      "ok" if ok else "error",
            "camera_open": ok,
            "using_fallback": USING_FALLBACK,
            "uptime_secs": round(uptime,1),
            "current_idx": current_idx,
            "current_src": CAMERA_SOURCES[current_idx],
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
        open_camera(idx)
        return {"status": "switched", "active_idx": current_idx}
    except IndexError:
        raise HTTPException(400, f"Index {idx} out of range")
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@app.post("/settings/{setting}")
def set_setting(setting: str, value: int):
    """Set and persist a camera property."""
    if setting not in CAMERA_PROPS:
        raise HTTPException(400, "Invalid setting")
    with lock:
        success = cap.set(CAMERA_PROPS[setting], value)
    if not success:
        raise HTTPException(500, "Failed to set setting")
    # Keep track of latest value
    settings_state[setting] = value

    return {"setting": setting, "value": value}


@app.post("/restart")
def restart_camera():
    """
    Attempt to reopen the current camera source.
    If it fails, fall back but still return 200 OK.
    """
    try:
        open_camera(current_idx)
        return {
            "status":       "restarted",
            "camera_open":  cap.isOpened(),
            "active_idx":   current_idx,
        }
    except RuntimeError as e:
        logger.warning(f"Restart failed ({e}); streaming fallback image instead.")
        return {
            "status":     "fallback",
            "error":      str(e),
            "active_idx": current_idx,
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=STREAM_PORT)
