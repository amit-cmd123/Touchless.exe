# pyrefly: ignore [missing-import]
import cv2
# pyrefly: ignore [missing-import]
import mediapipe as mp
import numpy as np
import os
import urllib.request
import time
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# Predefined connections for MediaPipe hand landmarks skeleton.
HAND_CONNECTIONS = [
    # Thumb
    (0, 1), (1, 2), (2, 3), (3, 4),
    # Index finger
    (0, 5), (5, 6), (6, 7), (7, 8),
    # Middle finger
    (9, 10), (10, 11), (11, 12),
    # Ring finger
    (13, 14), (14, 15), (15, 16),
    # Pinky finger
    (0, 17), (17, 18), (18, 19), (19, 20),
    # Palm knuckles connection
    (5, 9), (9, 13), (13, 17)
]

import sys

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
current_dir = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(current_dir, "hand_landmarker.task")

class HandTracker:
    """Encapsulates MediaPipe Tasks Hands detection and drawing utilities.

    Attributes:
        max_num_hands (int): Maximum number of hands to detect (set to 1).
        detection_confidence (float): Minimum confidence for hand detection.
        tracking_confidence (float): Minimum confidence for hand tracking.
        detector (vision.HandLandmarker): MediaPipe HandLandmarker detector.
    """
    def __init__(self, max_num_hands: int = 1, detection_confidence: float = 0.5,
                 tracking_confidence: float = 0.5):
        self.max_num_hands = max_num_hands
        self.detection_confidence = detection_confidence
        self.tracking_confidence = tracking_confidence
        self.prev_wrist_pos = None
        self.start_time = time.time()
        self.last_timestamp_ms = -1
        # Automatically download the required model task file if missing
        self._ensure_model_downloaded()

        # Initialize detector options.
        base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=self.max_num_hands,
            min_hand_detection_confidence=self.detection_confidence,
            min_hand_presence_confidence=self.tracking_confidence,
        )
        self.detector = vision.HandLandmarker.create_from_options(options)

    def _ensure_model_downloaded(self):
        """Downloads the model task file from Google's CDN if it does not exist."""
        if not os.path.exists(MODEL_PATH):
            print(f"[INFO] Downloading hand landmarker model to '{MODEL_PATH}'...")
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
            print("[INFO] Model download complete.")

    def _check_open_palm(self, points: list[tuple[int, int]]) -> bool:
        """Determines if the hand is in an open palm state using distance ratios from the wrist.
        This is rotation-invariant.
        """
        if len(points) < 21:
            return False
            
        def dist(p1, p2):
            return ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5
            
        wrist = points[0]
        # PIP joints: 6 (index), 10 (middle), 14 (ring), 18 (pinky)
        # Tips: 8 (index), 12 (middle), 16 (ring), 20 (pinky)
        index_ext = dist(points[8], wrist) > dist(points[6], wrist)
        middle_ext = dist(points[12], wrist) > dist(points[10], wrist)
        ring_ext = dist(points[16], wrist) > dist(points[14], wrist)
        pinky_ext = dist(points[20], wrist) > dist(points[18], wrist)
        
        return index_ext and middle_ext and ring_ext and pinky_ext

    def _check_fist(self, points: list[tuple[int, int]]) -> bool:
        """Determines if the hand is in a fist state (all fingers folded).
        This is rotation-invariant and robust against index finger foreshortening.
        """
        if len(points) < 21:
            return False
            
        def dist(p1, p2):
            return ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5
            
        wrist = points[0]
        # PIP joints: 6 (index), 10 (middle), 14 (ring), 18 (pinky)
        # Tips: 8 (index), 12 (middle), 16 (ring), 20 (pinky)
        index_ext = dist(points[8], wrist) > dist(points[6], wrist)
        middle_ext = dist(points[12], wrist) > dist(points[10], wrist)
        ring_ext = dist(points[16], wrist) > dist(points[14], wrist)
        pinky_ext = dist(points[20], wrist) > dist(points[18], wrist)
        
        # If middle, ring, and pinky are folded, check if the index finger is extended 
        # relative to the curled middle fingertip. This resolves foreshortening overlap
        # when pointing the index finger towards the camera.
        if not middle_ext and not ring_ext and not pinky_ext:
            if dist(points[8], wrist) > dist(points[12], wrist) * 1.15:
                return False  # Classified as pointing index finger (active), not a fist
        
        return not index_ext and not middle_ext and not ring_ext and not pinky_ext

    def _check_index_straight(self, points: list[tuple[int, int]]) -> bool:
        """Determines if the index finger is extended straight using joint distance ratios.
        This is rotation-invariant, scale-invariant, and highly robust.
        """
        if len(points) < 21:
            return False
            
        def dist(p1, p2):
            return ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5
            
        # Distance from index tip (8) to index MCP (5)
        d_tip_mcp = dist(points[8], points[5])
        # Distance from index PIP (6) to index MCP (5)
        d_pip_mcp = dist(points[6], points[5])
        
        # Distance from wrist (0) to index MCP (5) as hand scale reference
        hand_scale = dist(points[5], points[0])
        if hand_scale == 0:
            hand_scale = 1.0
            
        # The finger is straight if the tip-to-knuckle distance is larger than the PIP-to-knuckle distance,
        # and tip-to-knuckle is a significant fraction of hand scale (e.g. > 0.45)
        return d_tip_mcp > d_pip_mcp * 1.1 and (d_tip_mcp / hand_scale) > 0.45

    def process(self, frame: np.ndarray, draw: bool = True):
        """Run hand detection on a BGR frame.

        Args:
            frame (np.ndarray): OpenCV BGR image.
            draw (bool): Whether to draw the landmarks and skeleton on the frame.

        Returns:
            tuple: (annotated_frame, hand_present, points, is_palm_open, is_fist, is_index_straight)
                annotated_frame (np.ndarray): Frame with landmarks drawn (if draw is True) and IDs rendered.
                hand_present (bool): True if at least one hand was detected.
                points (list[tuple[int, int]] | None): The 21 landmark coordinate tuples (cx, cy) or None if not detected.
                is_palm_open (bool): True if the detected hand has an open palm.
                is_fist (bool): True if the detected hand is in a fist.
                is_index_straight (bool): True if the index finger is extended straight.
        """
        # Store original dimensions
        h, w, _ = frame.shape

        # Resize frame to 640x480 to preserve high-frequency details for long-distance hand tracking
        if w != 640 or h != 480:
            small_frame = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_LINEAR)
        else:
            small_frame = frame

        # Convert OpenCV BGR to RGB (MediaPipe requires RGB)
        rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        # Calculate elapsed time in milliseconds for strictly increasing timestamp
        timestamp_ms = int((time.time() - self.start_time) * 1000)
        if timestamp_ms <= self.last_timestamp_ms:
            timestamp_ms = self.last_timestamp_ms + 1
        self.last_timestamp_ms = timestamp_ms

        # Perform hand detection (synchronous, video frame tracking)
        results = self.detector.detect_for_video(mp_image, timestamp_ms)
        hand_present = False
        points = None
        is_palm_open = False
        is_fist = False
        is_index_straight = False

        if results.hand_landmarks:
            # Select the hand closest to the previously tracked hand position
            best_idx = 0
            if self.prev_wrist_pos is not None:
                min_dist = float('inf')
                for idx, hand_lms in enumerate(results.hand_landmarks):
                    wrist_lm = hand_lms[0]
                    wrist_cx, wrist_cy = int(wrist_lm.x * w), int(wrist_lm.y * h)
                    dist = ((wrist_cx - self.prev_wrist_pos[0])**2 + (wrist_cy - self.prev_wrist_pos[1])**2)**0.5
                    if dist < min_dist:
                        min_dist = dist
                        best_idx = idx

            selected_hand_landmarks = results.hand_landmarks[best_idx]
            points = []
            for lm in selected_hand_landmarks:
                cx, cy = int(lm.x * w), int(lm.y * h)
                points.append((cx, cy))

            if len(points) > 0:
                hand_present = True
                self.prev_wrist_pos = points[0]  # landmark 0 is wrist
                
                if len(points) > 8:
                    is_palm_open = self._check_open_palm(points)
                    is_fist = self._check_fist(points)
                    is_index_straight = self._check_index_straight(points)

                if draw:
                    # Draw connection lines for the selected single hand
                    for start_idx, end_idx in HAND_CONNECTIONS:
                        if start_idx < len(points) and end_idx < len(points):
                            cv2.line(frame, points[start_idx], points[end_idx], (0, 255, 0), 2, cv2.LINE_AA)

                    # Draw landmark points for the selected single hand
                    for pt in points:
                        cv2.circle(frame, pt, 4, (255, 0, 0), -1, cv2.LINE_AA)
        else:
            self.prev_wrist_pos = None

        return frame, hand_present, points, is_palm_open, is_fist, is_index_straight

    def close(self):
        """Release MediaPipe HandLandmarker detector resources."""
        if hasattr(self, 'detector') and self.detector is not None:
            try:
                self.detector.close()
            except Exception:
                pass
            self.detector = None

    def __del__(self):
        self.close()
