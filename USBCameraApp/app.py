import os
import cv2
import threading
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI()

# Camera device and capture (initialized on startup)
CAMERA_DEVICE = os.getenv("CAMERA_DEVICE", "/dev/video0")
lock = threading.Lock()
cap = None

def open_camera():
    """Opens or re-opens the camera device."""
    global cap
    if cap is not None:
        cap.release()
        logger.info("Previous camera released.")
    cap = cv2.VideoCapture(CAMERA_DEVICE)
    if not cap.isOpened():
        logger.error(f"Failed to open camera {CAMERA_DEVICE}.")
        raise RuntimeError(f"Cannot open camera {CAMERA_DEVICE}")
    logger.info(f"Camera {CAMERA_DEVICE} opened successfully.")

@app.on_event("startup")
def startup_event():
    try:
        open_camera()
    except Exception:
        logger.exception("Error opening camera on startup")

@app.on_event("shutdown")
def shutdown_event():
    if cap is not None:
        cap.release()
        logger.info("Camera released on shutdown.")

def generate_frames():
    """Yields MJPEG frames, with auto-recovery on failure."""
    while True:
        try:
            with lock:
                success, frame = cap.read()
            if not success or frame is None:
                logger.warning("Frame capture failed — retrying...")
                try:
                    open_camera()
                except RuntimeError:
                    continue
                else:
                    continue

            ret, buf = cv2.imencode('.jpg', frame)
            if not ret:
                logger.error("Failed to encode frame.")
                continue

            frame_bytes = buf.tobytes()
            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                frame_bytes +
                b'\r\n'
            )
        except Exception:
            logger.exception("Unexpected error in frame loop")
            break

@app.get("/stream")
def stream():
    """Live MJPEG stream."""
    if cap is None or not cap.isOpened():
        raise HTTPException(503, "Camera not available")
    return StreamingResponse(
        generate_frames(),
        media_type='multipart/x-mixed-replace; boundary=frame'
    )

@app.get("/health")
def health_check():
    """Service & camera health."""
    camera_ok = cap is not None and cap.isOpened()
    status = "ok" if camera_ok else "error"
    code = 200 if camera_ok else 503
    return JSONResponse(status_code=code, content={
        "status": status,
        "camera_open": camera_ok
    })

@app.post("/settings/{setting}")
def set_setting(setting: str, value: int):
    """Adjust camera property."""
    props = {
        "brightness": cv2.CAP_PROP_BRIGHTNESS,
        "contrast":   cv2.CAP_PROP_CONTRAST,
        "saturation": cv2.CAP_PROP_SATURATION,
        "hue":        cv2.CAP_PROP_HUE,
        "gain":       cv2.CAP_PROP_GAIN,
        "exposure":   cv2.CAP_PROP_EXPOSURE
    }
    if setting not in props:
        raise HTTPException(400, "Invalid setting")
    with lock:
        success = cap.set(props[setting], value)
    if not success:
        raise HTTPException(500, "Failed to set setting")
    return {"setting": setting, "value": value}

@app.post("/restart")
def restart_camera():
    """Reopen the camera without restarting the container."""
    try:
        open_camera()
        return {"status": "restarted", "camera_open": cap.isOpened()}
    except RuntimeError as e:
        raise HTTPException(500, str(e))
