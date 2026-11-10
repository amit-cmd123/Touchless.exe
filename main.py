import cv2
import time

from camera import Camera
from hand_tracker import HandTracker
from mouse_controller import MouseController
from gesture_detector import GestureDetector

# Configuration constants
WINDOW_NAME = "Touchless - Stage 3 (Relative & Gestures)"
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
FPS_SMOOTHING = 0.9  # exponential smoothing factor for FPS display

# Virtual control box margins (set to 0 for full-frame trackpad control)
MARGIN_LEFT = 0
MARGIN_RIGHT = 0
MARGIN_TOP = 0
MARGIN_BOTTOM = 0
SMOOTHING_FACTOR = 0.55  # Smoothing factor for mouse cursor movement (0.0 to 1.0)
SENSITIVITY_X = 8.5     # Base relative movement sensitivity multiplier
SENSITIVITY_Y = 8.5     # Base relative movement sensitivity multiplier

def draw_corner_decorations(frame, x1, y1, x2, y2, color, thickness=2, length=15):
    """Draws stylish L-shaped corner decorations on the virtual control box."""
    # Bottom-Left
    cv2.line(frame, (x1, y2), (x1 + length, y2), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (x1, y2), (x1, y2 - length), color, thickness, cv2.LINE_AA)
    
    # Bottom-Right
    cv2.line(frame, (x2, y2), (x2 - length, y2), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (x2, y2), (x2, y2 - length), color, thickness, cv2.LINE_AA)
    
    # Top-Left
    cv2.line(frame, (x1, y1), (x1 + length, y1), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (x1, y1), (x1, y1 + length), color, thickness, cv2.LINE_AA)
    
    # Top-Right
    cv2.line(frame, (x2, y1), (x2 - length, y1), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (x2, y1), (x2, y1 + length), color, thickness, cv2.LINE_AA)

def draw_hud(frame, fps, hand_detected, tracking_pos, cursor_active, is_clutch_active, dx, dy, gesture_state):
    """Draws a beautiful head-up display overlay with a semi-transparent panel."""
    # Define HUD background panel bounds (top-left)
    panel_x1, panel_y1 = 5, 5
    panel_x2, panel_y2 = 270, 180
    
    # Extract the ROI where the HUD will be drawn
    roi = frame[panel_y1:panel_y2, panel_x1:panel_x2]
    
    # Create semi-transparent overlay just for this ROI instead of copying/blending the whole frame
    overlay = roi.copy()
    cv2.rectangle(overlay, (0, 0), (panel_x2 - panel_x1, panel_y2 - panel_y1), (25, 25, 25), -1)
    
    # Blend the ROI overlay back into the frame
    alpha = 0.75
    cv2.addWeighted(overlay, alpha, roi, 1.0 - alpha, 0.0, roi)
    
    # Draw panel border
    cv2.rectangle(frame, (panel_x1, panel_y1), (panel_x2, panel_y2), (80, 80, 80), 1, cv2.LINE_AA)
    
    # Prepare text overlays
    mode_text = "Mode: Relative"
    mode_color = (255, 255, 255)
    
    hand_text = "Hand: Detected" if hand_detected else "Hand: No Hand"
    hand_color = (0, 255, 0) if hand_detected else (0, 0, 255)
    
    fps_text = f"FPS: {fps:.1f}"
    
    # Determine Status
    if not hand_detected:
        cursor_status = "No Hand"
        cursor_color = (0, 0, 255)
    elif is_clutch_active:
        cursor_status = "Paused (Clutch)"
        cursor_color = (0, 165, 255)  # Orange
    elif cursor_active:
        cursor_status = "Cursor Active"
        cursor_color = (255, 255, 0)  # Cyan
    else:
        cursor_status = "Outside Control Box"
        cursor_color = (0, 165, 255)  # Orange
        
    status_text = f"Status: {cursor_status}"
    
    if hand_detected and tracking_pos and not is_clutch_active and cursor_active:
        deltas_text = f"Deltas (dx, dy): {dx:+.1f}, {dy:+.1f}"
    else:
        deltas_text = "Deltas (dx, dy): 0.0, 0.0"
        
    deltas_color = (220, 220, 220)
    
    # Gesture state text
    gesture_text = f"Gesture: {gesture_state}"
    gesture_color = (0, 255, 0) if gesture_state in ["Left Click", "Scroll", "Dragging"] else (220, 220, 220)
    
    # Render HUD texts
    y_offset = 22
    line_height = 25
    
    texts = [
        (mode_text, mode_color),
        (hand_text, hand_color),
        (status_text, cursor_color),
        (deltas_text, deltas_color),
        (gesture_text, gesture_color),
        (fps_text, (255, 255, 255))
    ]
    
    for text, color in texts:
        cv2.putText(
            frame,
            text,
            (15, y_offset),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA
        )
        y_offset += line_height

def is_window_minimized(window_name: str) -> bool:
    """Checks if the window is minimized on Windows using the IsIconic Win32 API."""
    import sys
    if sys.platform == "win32":
        import ctypes
        hwnd = ctypes.windll.user32.FindWindowW(None, window_name)
        if hwnd:
            return ctypes.windll.user32.IsIconic(hwnd) != 0
    return False

def main():
    # Set high process priority class on Windows to prevent background CPU/scheduling throttling
    import sys
    if sys.platform == "win32":
        import ctypes
        # HIGH_PRIORITY_CLASS = 0x00000080
        ctypes.windll.kernel32.SetPriorityClass(
            ctypes.windll.kernel32.GetCurrentProcess(),
            0x00000080
        )

    # Initialize camera, tracker, and mouse controller
    try:
        cam = Camera(device_index=CAMERA_INDEX, width=FRAME_WIDTH, height=FRAME_HEIGHT)
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        return

    tracker = HandTracker(max_num_hands=1)
    mc = MouseController(
        frame_w=FRAME_WIDTH,
        frame_h=FRAME_HEIGHT,
        margin_left=MARGIN_LEFT,
        margin_right=MARGIN_RIGHT,
        margin_top=MARGIN_TOP,
        margin_bottom=MARGIN_BOTTOM,
        smoothing=SMOOTHING_FACTOR,
        sensitivity_x=SENSITIVITY_X,
        sensitivity_y=SENSITIVITY_Y
    )
    gd = GestureDetector()

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    
    # Resize and move to top-right corner
    try:
        import pyautogui
        screen_w, screen_h = pyautogui.size()
        win_w = 320
        win_h = 240
        cv2.resizeWindow(WINDOW_NAME, win_w, win_h)
        cv2.moveWindow(WINDOW_NAME, screen_w - win_w - 30, 40)
    except Exception as e:
        print(f"[WARNING] Could not position window: {e}")
        cv2.resizeWindow(WINDOW_NAME, FRAME_WIDTH, FRAME_HEIGHT)

    # Set always on top (topmost) so it remains visible during mouse control
    try:
        cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_TOPMOST, 1)
    except Exception as e:
        print(f"[WARNING] Could not set always-on-top property: {e}")

    prev_time = time.time()
    smoothed_fps = 0.0
    window_created = False
    frame_count = 0
    minimized_cached = False

    while True:
        ret, frame = cam.read()
        if not ret:
            print("[WARNING] Frame capture failed, exiting.")
            break

        # Check if the window is minimized to toggle background mode optimizations
        if frame_count % 15 == 0:
            minimized_cached = is_window_minimized(WINDOW_NAME)
        frame_count += 1
        draw_enabled = not minimized_cached

        # Mirror the frame horizontally to make control intuitive (like a mirror)
        frame = cv2.flip(frame, 1)

        # Process hand detection and draw landmarks (conditional drawing to save background CPU)
        annotated_frame, hand_present, points, is_palm_open, is_fist, is_index_straight = tracker.process(frame, draw=draw_enabled)

        # Extract cursor tracking position (landmark 5 - Index MCP joint / knuckle) if hand is detected.
        # Using the knuckle instead of the fingertip prevents cursor drift when bending the finger to click.
        tracking_pos = None
        if hand_present and points and len(points) > 5:
            tracking_pos = points[5]

        # Detect gestures (left/right/double click, dragging) and determine freeze status
        gesture_state = "Move"
        is_frozen = False
        if hand_present and points:
            gesture_state, is_frozen = gd.detect_gesture(points, is_palm_open=is_palm_open, is_fist=is_fist)

        # Clutch mechanism: Cursor moves normally ONLY when open palm is detected,
        # OR when we are actively dragging (holding a long pinch).
        movement_allowed = hand_present and (is_palm_open or gd.is_dragging)
        is_clutch_active = not movement_allowed

        # Update cursor position relatively if hand and tracking position are detected
        cursor_active = False
        dx, dy = 0.0, 0.0
        if hand_present and tracking_pos:
            cursor_active, dx, dy = mc.move_cursor_relative(tracking_pos[0], tracking_pos[1], is_clutch_active, is_frozen=is_frozen)

        # FPS calculation (actual elapsed time)
        curr_time = time.time()
        dt = curr_time - prev_time
        prev_time = curr_time
        fps = 1.0 / dt if dt > 0 else 0.0
        # Apply exponential smoothing for a steadier display
        smoothed_fps = (FPS_SMOOTHING * smoothed_fps) + ((1 - FPS_SMOOTHING) * fps)

        if draw_enabled:
            # Determine color for the control box based on status
            if hand_present and tracking_pos and not is_clutch_active and cursor_active:
                box_color = (255, 255, 0)      # Neon Cyan
                box_thickness = 2
            elif hand_present and tracking_pos and is_clutch_active:
                box_color = (0, 165, 255)      # Neon Orange (Paused Clutch)
                box_thickness = 1
            elif hand_present and tracking_pos:
                box_color = (0, 165, 255)      # Neon Orange (Outside Box)
                box_thickness = 1
            else:
                box_color = (120, 120, 120)    # Gray
                box_thickness = 1

            # Draw the virtual control box outline
            cv2.rectangle(
                annotated_frame,
                (mc.ctrl_x1, mc.ctrl_y1),
                (mc.ctrl_x2, mc.ctrl_y2),
                box_color,
                box_thickness,
                cv2.LINE_AA
            )

            # Draw techy corner decorations on the control box
            draw_corner_decorations(
                annotated_frame,
                mc.ctrl_x1,
                mc.ctrl_y1,
                mc.ctrl_x2,
                mc.ctrl_y2,
                box_color,
                thickness=2,
                length=15
            )

            # Render the HUD overlay panel with metrics and status
            draw_hud(
                annotated_frame,
                smoothed_fps,
                hand_present,
                tracking_pos,
                cursor_active,
                is_clutch_active,
                dx,
                dy,
                gesture_state
            )

            cv2.imshow(WINDOW_NAME, annotated_frame)

        # Exit on 'q' key press (waitKey still required for OpenCV window events pumps)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("[INFO] 'q' pressed – exiting application.")
            break

        # Exit if the window is closed (checked robustly via Win32 API to ignore minimization)
        if sys.platform == "win32":
            hwnd = ctypes.windll.user32.FindWindowW(None, WINDOW_NAME)
            if hwnd != 0:
                window_created = True
            elif window_created:
                print("[INFO] Window closed – exiting application.")
                break
        else:
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                print("[INFO] Window close button clicked – exiting application.")
                break

    # Cleanup resources
    try:
        import pyautogui
        pyautogui.mouseUp()
    except Exception:
        pass
    tracker.close()
    cam.release()

if __name__ == "__main__":
    main()
