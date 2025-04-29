# CameraController/controller/stream_recorder.py

import cv2
import time
import logging
import threading


class StreamRecorder(threading.Thread):
    """
    MJPEG-Stream-Recorder: Liest kontinuierlich Frames aus einem MJPEG-Stream
    und speichert sie als MP4-Video mit fester Framerate.

    Verwendung:
        recorder = StreamRecorder(stream_url, output_path)
        recorder.start()
        ...
        recorder.stop_event.set()
        recorder.join()
    """

    def __init__(self, stream_url: str, output_path: str, fps: float = 20.0):
        super().__init__()
        self.stream_url = stream_url
        self.output_path = output_path
        self.stop_event = threading.Event()
        self.fps = fps

    def run(self):
        retry_delay = 2
        attempt = 0
        cap = None
        writer = None

        try:
            while not self.stop_event.is_set():
                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(self.stream_url)
                    if not cap.isOpened():
                        attempt += 1
                        logging.warning(
                            f"[Recorder] Stream not available (attempt {attempt}), retrying in {retry_delay}s…"
                        )
                        time.sleep(retry_delay)
                        continue
                    else:
                        logging.info(f"[Recorder] Connected to stream: {self.stream_url}")

                        # Initialisiere VideoWriter
                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
                        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
                        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                        writer = cv2.VideoWriter(self.output_path, fourcc, self.fps, (width, height))
                        logging.info(f"[Recorder] Recording to {self.output_path} ({width}x{height})")

                ret, frame = cap.read()
                if not ret or frame is None:
                    logging.warning("[Recorder] Frame read failed, retrying…")
                    time.sleep(0.2)
                    continue

                writer.write(frame)

        except Exception as e:
            logging.exception(f"[Recorder] Fatal error: {e}")

        finally:
            if cap:
                cap.release()
            if writer:
                writer.release()
            logging.info("[Recorder] Recording stopped and file saved.")
