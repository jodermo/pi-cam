# CameraController/controller/apps.py

import os
import threading
import logging
from datetime import datetime

import cv2
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()
lock = threading.Lock()

# mirror the constants from views.py
API_PREFIX          = os.getenv('CAMERA_API_URL', '/api')
STREAM_PATH         = f"{API_PREFIX}/stream"
CAMERA_SERVICE_BASE = os.getenv('CAMERA_SERVICE_URL', 'http://pi-cam-camera:8000')
INTERNAL_STREAM_URL = f"{CAMERA_SERVICE_BASE.rstrip('/')}{STREAM_PATH}"


def capture_timelapse_frame():
    from .models import AppConfigSettings

    config = AppConfigSettings.objects.first()
    if not config or not config.enable_timelapse:
        logger.info("[Timelapse] disabled – skipping capture.")
        return

    try:
        with lock:
            cap = cv2.VideoCapture(INTERNAL_STREAM_URL)
            if not cap.isOpened():
                logger.warning(f"[Timelapse] cannot open stream at {INTERNAL_STREAM_URL!r}")
                return

            # flush old frames
            for _ in range(5):
                cap.read()

            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                logger.warning("[Timelapse] failed to read a fresh frame")
                return

            # resize if needed
            w, h = config.capture_resolution_width, config.capture_resolution_height
            if frame.shape[1] != w or frame.shape[0] != h:
                frame = cv2.resize(frame, (w, h))

            # ensure output folder
            folder = os.path.join(settings.MEDIA_ROOT, config.timelapse_folder or 'timelapse')
            os.makedirs(folder, exist_ok=True)

            # write file
            ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            fname = os.path.join(folder, f"timelapse_{ts}.jpg")
            if not cv2.imwrite(fname, frame):
                logger.error(f"[Timelapse] failed to write {fname}")
                return

            logger.info(f"[Timelapse] saved frame → {fname}")

    except Exception:
        logger.exception("[Timelapse] unexpected error during capture")



class ControllerConfig(AppConfig):
    name = 'controller'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        # defer model import until apps are loaded
        from .models import AppConfigSettings
        # import the DB exceptions we’ll catch
        from django.db.utils import ProgrammingError, OperationalError

        try:
            config = AppConfigSettings.objects.first()
        except (ProgrammingError, OperationalError) as e:
            logger.warning(f"[Timelapse] cannot read AppConfigSettings yet: {e!r}")
            return

        if config and config.enable_timelapse:
            interval = config.timelapse_interval_minutes or 1
            logger.info(f"[Timelapse] scheduling capture every {interval} minute(s)")
            # ensure we don’t double-start
            if not scheduler.get_job('timelapse_job'):
                scheduler.add_job(
                    func=capture_timelapse_frame,
                    trigger=IntervalTrigger(minutes=interval),
                    id='timelapse_job',
                    replace_existing=True,
                )
                scheduler.start()
        else:
            logger.info("[Timelapse] not scheduling – timelapse disabled or no config found")