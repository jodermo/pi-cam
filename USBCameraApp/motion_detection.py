# Add these imports to your FastAPI app.py
import numpy as np
import cv2
import threading
import json
import requests
from datetime import datetime
from collections import deque

# Motion detection configuration
MOTION_DETECTION_ENABLED = True
OBJECT_DETECTION_ENABLED = False  # Set to True if you want to enable object detection with YOLO
MOTION_THRESHOLD = 30  # Minimum contour area to be considered motion
NOTIFICATION_URL = "http://pi-cam-controller:8001/api/motion-event/"  # Django endpoint to receive notifications
MOTION_FRAMES_BUFFER = 5  # Number of frames to keep in the motion buffer
MOTION_COOLDOWN = 3.0  # Seconds to wait between notifications
DETECTION_INTERVAL = 10  # Process every Nth frame for motion detection

# Global variables
motion_detected = False
last_notification_time = datetime.min
motion_frames = deque(maxlen=MOTION_FRAMES_BUFFER)
background_subtractor = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=25, detectShadows=False)
frame_count = 0

# Object detection with YOLO (if enabled)
if OBJECT_DETECTION_ENABLED:
    # Load YOLO model
    try:
        # You'll need to download the model files and place them in the correct location
        net = cv2.dnn.readNet("yolov3.weights", "yolov3.cfg")
        with open("coco.names", "r") as f:
            classes = [line.strip() for line in f.readlines()]
        layer_names = net.getLayerNames()
        # Handle different OpenCV versions:
        try:
            output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]
        except:
            output_layers = [layer_names[i[0] - 1] for i in net.getUnconnectedOutLayers()]
    except Exception as e:
        logger.error(f"Failed to load YOLO model: {e}")
        OBJECT_DETECTION_ENABLED = False

# Motion detection function
def detect_motion(frame):
    """
    Detect motion in frame using background subtraction
    Returns: (motion_detected, processed_frame, motion_regions)
    """
    global motion_frames
    
    # Convert frame to grayscale and apply gaussian blur
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)
    
    # Add to motion frames buffer
    motion_frames.append(gray)
    
    # Need at least 2 frames to compare
    if len(motion_frames) < 2:
        return False, frame, []
    
    # Apply background subtraction
    mask = background_subtractor.apply(gray)
    
    # Apply threshold to get binary image
    _, thresh = cv2.threshold(mask, 20, 255, cv2.THRESH_BINARY)
    
    # Dilate to fill in holes and increase detection area
    dilated = cv2.dilate(thresh, None, iterations=2)
    
    # Find contours
    contours, _ = cv2.findContours(dilated.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Initialize motion regions list
    motion_regions = []
    
    # Process each contour
    for contour in contours:
        # If contour is too small, ignore it
        if cv2.contourArea(contour) < MOTION_THRESHOLD:
            continue
            
        # Get bounding box for contour
        (x, y, w, h) = cv2.boundingRect(contour)
        
        # Add to motion regions
        motion_regions.append({
            'x': int(x),
            'y': int(y),
            'width': int(w),
            'height': int(h),
            'area': int(cv2.contourArea(contour))
        })
        
        # Draw rectangle on frame
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
    
    # Determine if motion was detected
    motion_detected = len(motion_regions) > 0
    
    return motion_detected, frame, motion_regions

# Object detection function (using YOLO)
def detect_objects(frame):
    """
    Detect objects in frame using YOLO
    Returns: (processed_frame, detected_objects)
    """
    if not OBJECT_DETECTION_ENABLED:
        return frame, []
        
    height, width, _ = frame.shape
    
    # Create blob from image
    blob = cv2.dnn.blobFromImage(frame, 0.00392, (416, 416), (0, 0, 0), True, crop=False)
    
    # Set input and forward pass
    net.setInput(blob)
    outs = net.forward(output_layers)
    
    # Initialize lists
    class_ids = []
    confidences = []
    boxes = []
    detected_objects = []
    
    # Process detections
    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = np.argmax(scores)
            confidence = scores[class_id]
            
            # Filter out weak predictions
            if confidence > 0.5:
                # Object detected
                center_x = int(detection[0] * width)
                center_y = int(detection[1] * height)
                w = int(detection[2] * width)
                h = int(detection[3] * height)
                
                # Rectangle coordinates
                x = int(center_x - w / 2)
                y = int(center_y - h / 2)
                
                boxes.append([x, y, w, h])
                confidences.append(float(confidence))
                class_ids.append(class_id)
    
    # Apply non-max suppression to remove overlapping boxes
    indexes = cv2.dnn.NMSBoxes(boxes, confidences, 0.5, 0.4)
    
    # Draw boxes and add to detected objects list
    for i in range(len(boxes)):
        if i in indexes:
            x, y, w, h = boxes[i]
            label = str(classes[class_ids[i]])
            confidence = confidences[i]
            
            # Add to detected objects
            detected_objects.append({
                'label': label,
                'confidence': float(confidence),
                'x': int(x),
                'y': int(y),
                'width': int(w),
                'height': int(h)
            })
            
            # Draw bounding box
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
            
            # Draw label
            cv2.putText(frame, f"{label} {confidence:.2f}", (x, y - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    
    return frame, detected_objects

# Notification function
def send_motion_notification(motion_regions, detected_objects=None):
    """Send motion detection notification to Django application"""
    global last_notification_time
    
    # Check if we're in cooldown period
    now = datetime.now()
    if (now - last_notification_time).total_seconds() < MOTION_COOLDOWN:
        return
    
    last_notification_time = now
    
    # Create notification payload
    payload = {
        'timestamp': now.isoformat(),
        'motion_detected': True,
        'motion_regions': motion_regions
    }
    
    if detected_objects:
        payload['detected_objects'] = detected_objects
    
    # Log the detection
    logger.info(f"Motion detected! Regions: {len(motion_regions)}")
    if detected_objects:
        logger.info(f"Objects detected: {', '.join([obj['label'] for obj in detected_objects])}")
    
    try:
        # Send notification to Django app
        requests.post(
            NOTIFICATION_URL,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=1.0  # Short timeout to avoid blocking
        )
    except Exception as e:
        logger.error(f"Failed to send motion notification: {e}")

# Modify your generate_frames function to include motion detection
def generate_frames():
    global USING_FALLBACK, frame_count
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
        
        # Increment frame counter
        frame_count += 1
        
        # Process motion detection on every DETECTION_INTERVAL frame
        if MOTION_DETECTION_ENABLED and frame_count % DETECTION_INTERVAL == 0:
            motion_detected, processed_frame, motion_regions = detect_motion(frame)
            
            # If motion detected, process object detection and send notification
            if motion_detected:
                if OBJECT_DETECTION_ENABLED:
                    processed_frame, detected_objects = detect_objects(processed_frame)
                    # Send notification in a non-blocking way
                    threading.Thread(
                        target=send_motion_notification, 
                        args=(motion_regions, detected_objects)
                    ).start()
                else:
                    # Send notification with only motion regions
                    threading.Thread(
                        target=send_motion_notification, 
                        args=(motion_regions, None)
                    ).start()
                
                # Use the processed frame with detection boxes
                frame = processed_frame

        # Encode frame to JPEG
        ok, buf = cv2.imencode('.jpg', frame)
        if not ok:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' +
               buf.tobytes() + b'\r\n')