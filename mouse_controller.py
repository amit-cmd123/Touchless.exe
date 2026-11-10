import pyautogui
import numpy as np
import ctypes

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def win32_get_cursor_pos() -> tuple[int, int]:
    """Retrieves current cursor coordinates on Windows via direct system call."""
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

class MouseController:
    """Handles relative mapping of webcam deltas to desktop cursor displacement,
    jitter smoothing, clutches, soft dead-zone filtering, and fail-safe safety triggers.
    """
    def __init__(self, frame_w: int = 640, frame_h: int = 480,
                 margin_left: int = 100, margin_right: int = 100,
                 margin_top: int = 80, margin_bottom: int = 80,
                 smoothing: float = 0.2,
                 sensitivity_x: float = 1.5, sensitivity_y: float = 1.5,
                 acceleration_factor: float = 0.08,
                 dead_zone: float = 1.2):
        """Initializes the Relative MouseController.

        Args:
            frame_w (int): Width of the camera frame.
            frame_h (int): Height of the camera frame.
            margin_left (int): Pixels from left edge for control box.
            margin_right (int): Pixels from right edge for control box.
            margin_top (int): Pixels from top edge for control box.
            margin_bottom (int): Pixels from bottom edge for control box.
            smoothing (float): Jitter smoothing factor (0.0 to 1.0).
            sensitivity_x (float): Horizontal movement sensitivity multiplier.
            sensitivity_y (float): Vertical movement sensitivity multiplier.
            acceleration_factor (float): Relative acceleration multiplier for fast sweeps.
            dead_zone (float): Minimum coordinate delta to trigger cursor movement (ignoring tremors).
        """
        # Retrieve screen bounds
        self.screen_width, self.screen_height = pyautogui.size()
        
        # Virtual control box boundaries
        self.ctrl_x1 = margin_left
        self.ctrl_y1 = margin_top
        self.ctrl_x2 = frame_w - margin_right
        self.ctrl_y2 = frame_h - margin_bottom
        
        # Relative mouse parameters
        self.smoothing = smoothing
        self.sensitivity_x = sensitivity_x
        self.sensitivity_y = sensitivity_y
        self.acceleration_factor = acceleration_factor
        self.dead_zone = dead_zone
        
        # Track previous index finger position in webcam space
        self.prev_cx = None
        self.prev_cy = None
        
        # Smoothed delta variables
        self.smoothed_dx = 0.0
        self.smoothed_dy = 0.0
        
        # Configure PyAutoGUI
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0.0

    def is_inside_control_box(self, cx: int, cy: int) -> bool:
        """Checks whether the index fingertip coordinates are inside the control box."""
        return self.ctrl_x1 <= cx <= self.ctrl_x2 and self.ctrl_y1 <= cy <= self.ctrl_y2

    def move_cursor_relative(self, cx: int, cy: int, is_clutch_active: bool, is_frozen: bool = False) -> tuple[bool, float, float]:
        """Calculates fingertip deltas, applies soft dead-zone, smoothing/sensitivity, and moves the cursor.

        If the hand is not in the control box, the clutch is active, or the cursor is frozen,
        cursor movement is paused and previous coordinates are updated to prevent jumps.

        Args:
            cx (int): Current index fingertip X in webcam space.
            cy (int): Current index fingertip Y in webcam space.
            is_clutch_active (bool): True if open-palm or fist gesture is detected.
            is_frozen (bool): True if the cursor is locked in place during pinch click.

        Returns:
            tuple: (is_active, dx, dy)
                is_active (bool): True if cursor was moved, False if paused.
                dx (float): Smoothed X delta applied.
                dy (float): Smoothed Y delta applied.
        """
        # If tracking was lost or first frame, initialize previous and smoothed coordinates
        if self.prev_cx is None or self.prev_cy is None:
            self.prev_cx = float(cx)
            self.prev_cy = float(cy)
            self.smoothed_cx = float(cx)
            self.smoothed_cy = float(cy)
            self.smoothed_dx = 0.0
            self.smoothed_dy = 0.0
            return False, 0.0, 0.0
        # Check if the movement should be paused (clutch active, outside box, or cursor is frozen during click prep)
        if not self.is_inside_control_box(cx, cy) or is_clutch_active or is_frozen:
            # [Rule 6] Prevent cursor jumps: Update previous positions to the current coordinates continuously.
            # This ensures that when movement resumes (Move or Drag), the next delta is near 0.
            self.prev_cx = float(cx)
            self.prev_cy = float(cy)
            self.smoothed_cx = float(cx)
            self.smoothed_cy = float(cy)
            self.smoothed_dx = 0.0
            self.smoothed_dy = 0.0
            return False, 0.0, 0.0

        # Apply exponential smoothing directly to the coordinates (removes floaty drift/lag)
        self.smoothed_cx = (1.0 - self.smoothing) * self.smoothed_cx + self.smoothing * cx
        self.smoothed_cy = (1.0 - self.smoothing) * self.smoothed_cy + self.smoothing * cy

        # Calculate raw deltas of the smoothed coordinates
        delta_x = self.smoothed_cx - self.prev_cx
        delta_y = self.smoothed_cy - self.prev_cy

        # Compute fingertip movement speed (distance traveled this frame)
        speed = (delta_x**2 + delta_y**2)**0.5

        # Check dead-zone threshold to ignore micro-tremors/human hand shakiness
        if speed < self.dead_zone:
            # We still update prev_cx/cy to keep tracking aligned, but we do not move the cursor
            self.prev_cx = self.smoothed_cx
            self.prev_cy = self.smoothed_cy
            return True, 0.0, 0.0

        # Apply soft dead-zone scale to ensure smooth transition
        scale = (speed - self.dead_zone) / speed
        delta_x_clean = delta_x * scale
        delta_y_clean = delta_y * scale

        # Compute accelerated speed from the cleaned delta
        clean_speed = (delta_x_clean**2 + delta_y_clean**2)**0.5

        # Apply acceleration multiplier: multiplier increases dynamically for fast sweeps
        multiplier_x = self.sensitivity_x * (1.0 + self.acceleration_factor * clean_speed)
        multiplier_y = self.sensitivity_y * (1.0 + self.acceleration_factor * clean_speed)

        move_dx = delta_x_clean * multiplier_x
        move_dy = delta_y_clean * multiplier_y

        # Update previous coordinates for the next iteration
        self.prev_cx = self.smoothed_cx
        self.prev_cy = self.smoothed_cy

        # Get current desktop cursor coordinates
        curr_x, curr_y = win32_get_cursor_pos()
        target_x = int(round(curr_x + move_dx))
        target_y = int(round(curr_y + move_dy))

        # Clamp target coordinates to keep cursor inside screen limits
        target_x = max(0, min(target_x, self.screen_width - 1))
        target_y = max(0, min(target_y, self.screen_height - 1))

        # Trigger Win32 system call for instant mouse movement
        ctypes.windll.user32.SetCursorPos(target_x, target_y)

        return True, move_dx, move_dy
