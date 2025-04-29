from django.apps import AppConfig
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import os
import cv2
import threading
from datetime import datetime
from django.conf import settings

scheduler = BackgroundScheduler()
lock = threading.Lock()

logger = logging.getLogger(__name__)

class ControllerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'controller'

    def ready(self):
        from .models import AppConfigSettings  # import your settings model

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )

        try:
            config = AppConfigSettings.objects.first()

            if config and config.enable_timelapse:
                interval = config.timelapse_interval_minutes or 1
                logger.info(f"[Timelapse] Starting scheduler every {interval} minutes")

                scheduler.add_job(
                    capture_timelapse_frame,
                    trigger=IntervalTrigger(minutes=interval),
                    id="timelapse_job",
                    replace_existing=True
                )
                scheduler.start()
            else:
                logger.info("[Timelapse] Timelapse is disabled in app settings.")

        except Exception as e:
            logger.exception(f"[Timelapse] Failed to start scheduler: {e}")

def capture_timelapse_frame():
    """Capture one frame from STREAM_URL and save it as a JPEG."""
    from .models import AppConfigSettings

    config = AppConfigSettings.objects.first()
    if not config or not config.enable_timelapse:
        logger.info("[Timelapse] Skipping capture: Timelapse disabled.")
        return

    stream_url = os.getenv("CAMERA_SERVICE_URL", "http://pi-cam-camera:8000") + os.getenv("CAMERA_API_URL", "/api/stream")

    try:
        with lock:
            cap = cv2.VideoCapture(stream_url)
            if not cap.isOpened():
                logger.warning("[Timelapse] Could not open stream")
                return

            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                logger.warning("[Timelapse] Failed to read frame")
                return

            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            folder = os.path.join(settings.MEDIA_ROOT, config.timelapse_folder or 'timelapse')
            os.makedirs(folder, exist_ok=True)

            filename = os.path.join(folder, f"timelapse_{timestamp}.jpg")
            cv2.imwrite(filename, frame)
            logger.info(f"[Timelapse] Saved: {filename}")

    except Exception as e:
        logger.exception(f"[Timelapse] Unexpected error: {e}")
