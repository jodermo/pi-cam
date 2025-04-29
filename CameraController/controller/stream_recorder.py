# CameraController/controller/stream_recorder.py

import cv2
import time
import logging
import threading
import os

logger = logging.getLogger(__name__)

class StreamRecorder(threading.Thread):
    """
    MJPEG-Stream-Recorder:
    Continuously reads frames from an MJPEG HTTP stream
    and writes them into a video file with a fixed framerate
    and browser-compatible codec.

    Usage:
        rec = StreamRecorder(stream_url, '/path/to/output.mp4', fps=20.0)
        rec.start()
        …
        rec.stop_event.set()
        rec.join()
    """

    def __init__(self, stream_url: str, output_path: str, fps: float = 20.0):
        super().__init__()
        self.stream_url = stream_url
        self.output_path = output_path
        self.fps = fps
        self.stop_event = threading.Event()

    def _choose_fourcc(self):
        """
        Pick a fourcc code based on output_path extension:
          - .mp4 → try H.264 (‘avc1’), fallback to ‘mp4v’
          - .webm → VP8 (‘VP80’)
          - otherwise → default to ‘mp4v’
        """
        ext = os.path.splitext(self.output_path)[1].lower()
        if ext == '.mp4':
            # try H.264
            for code in ('avc1', 'H264'):
                fourcc = cv2.VideoWriter_fourcc(*code)
                # test if VideoWriter accepts it
                test = cv2.VideoWriter(self.output_path, fourcc, self.fps, (1,1))
                if test.isOpened():
                    test.release()
                    logger.info(f"[Recorder] Using H.264 fourcc '{code}' for MP4")
                    return fourcc
            logger.warning("[Recorder] H.264 unavailable, falling back to 'mp4v'")
            return cv2.VideoWriter_fourcc(*'mp4v')

        if ext == '.webm':
            logger.info("[Recorder] Using VP8 fourcc 'VP80' for WebM")
            return cv2.VideoWriter_fourcc(*'VP80')

        # default
        logger.info("[Recorder] Using default fourcc 'mp4v'")
        return cv2.VideoWriter_fourcc(*'mp4v')

    def run(self):
        retry_delay = 2
        cap = None
        writer = None

        try:
            while not self.stop_event.is_set():
                # (re)open capture if needed
                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(self.stream_url)
                    if not cap.isOpened():
                        logger.warning(f"[Recorder] Cannot open stream, retry in {retry_delay}s…")
                        time.sleep(retry_delay)
                        continue

                    # once opened, set up writer
                    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))  or 640
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
                    fourcc = self._choose_fourcc()
                    writer = cv2.VideoWriter(self.output_path, fourcc, self.fps, (width, height))
                    if not writer.isOpened():
                        logger.error(f"[Recorder] Failed to open VideoWriter for {self.output_path}")
                        cap.release()
                        cap = None
                        time.sleep(retry_delay)
                        continue

                    logger.info(f"[Recorder] Recording started → {self.output_path} ({width}×{height} @ {self.fps}fps)")

                # read frame
                ret, frame = cap.read()
                if not ret or frame is None:
                    logger.warning("[Recorder] Frame read failed, retrying…")
                    time.sleep(0.1)
                    continue

                writer.write(frame)

        except Exception:
            logger.exception("[Recorder] Fatal error in recording loop")

        finally:
            if cap:
                cap.release()
            if writer:
                writer.release()
            logger.info("[Recorder] Recording stopped and file closed.")
