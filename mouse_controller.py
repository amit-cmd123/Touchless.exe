import pyautogui
import ctypes
from preferences import Calibration


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def win32_get_cursor_pos() -> tuple[int, int]:
    """Retrieves current cursor coordinates on Windows via direct system call."""
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


class MouseController:
    """Handles cursor movement and centralized mouse actions with safety controls."""

    def __init__(
        self,
        frame_w: int = 640,
        frame_h: int = 480,
        margin_left: int = 100,
        margin_right: int = 100,
        margin_top: int = 80,
        margin_bottom: int = 80,
        smoothing: float = 0.2,
        sensitivity_x: float = 1.5,
        sensitivity_y: float = 1.5,
        acceleration_factor: float = 0.08,
        dead_zone: float = 1.2,
        calibration: Calibration | None = None,
        scroll_sensitivity: float = 3.0,
    ):
        # Retrieve screen bounds
        self.screen_width, self.screen_height = pyautogui.size()
        self.frame_w = frame_w
        self.frame_h = frame_h

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
        self.calibration = calibration or Calibration()
        self.scroll_sensitivity = scroll_sensitivity

        # Track previous index finger position
        self.prev_cx = None
        self.prev_cy = None

        # Smoothed delta variables
        self.smoothed_dx = 0.0
        self.smoothed_dy = 0.0

        # Configure PyAutoGUI
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0.0

        # Safety state
        self.emergency_stopped = False
        self.button_held = False

    # ------------------------------------------------------------------
    # Safety
    # ------------------------------------------------------------------

    def emergency_stop(self) -> None:
        """Immediately stop all mouse activity and release any held button."""
        self.emergency_stopped = True

        if self.button_held:
            try:
                pyautogui.mouseUp()
            except Exception:
                pass
            else:
                self.button_held = False

    def reset_emergency_stop(self) -> None:
        """Re-enable mouse control after an emergency stop."""
        self.emergency_stopped = False

    # ------------------------------------------------------------------
    # Centralized mouse actions
    # ------------------------------------------------------------------

    def mouse_down(self) -> None:
        """Press and hold the left mouse button unless stopped."""
        if self.emergency_stopped:
            return

        try:
            pyautogui.mouseDown()
            self.button_held = True
        except Exception:
            pass

    def mouse_up(self) -> None:
        """Release the left mouse button and clear held-button state."""
        if not self.button_held:
            return

        try:
            pyautogui.mouseUp()
        except Exception:
            return

        self.button_held = False

    def click(self) -> None:
        """Perform a left click unless stopped."""
        if self.emergency_stopped:
            return

        try:
            pyautogui.click()
        except Exception:
            pass

    def right_click(self) -> None:
        """Perform a right click unless stopped."""
        if self.emergency_stopped:
            return

        try:
            pyautogui.rightClick()
        except Exception:
            pass

    def double_click(self) -> None:
        """Perform a double click unless stopped."""
        if self.emergency_stopped:
            return

        try:
            pyautogui.doubleClick()
        except Exception:
            pass

    def scroll(self, amount: int) -> None:
        """Scroll unless stopped."""
        if self.emergency_stopped:
            return

        try:
            pyautogui.scroll(amount)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Cursor movement
    # ------------------------------------------------------------------

    def is_inside_control_box(self, cx: int, cy: int) -> bool:
        """Checks whether the index fingertip is inside the control box."""
        return (
            self.ctrl_x1 <= cx <= self.ctrl_x2
            and self.ctrl_y1 <= cy <= self.ctrl_y2
        )

    def move_cursor_relative(
        self,
        cx: int,
        cy: int,
        is_clutch_active: bool,
        is_frozen: bool = False,
    ) -> tuple[bool, float, float]:
        """Calculates fingertip deltas and moves the desktop cursor."""

        # Emergency stop takes priority over all cursor movement.
        if self.emergency_stopped:
            return False, 0.0, 0.0

        # If tracking was lost or first frame, initialize previous coordinates.
        if self.prev_cx is None or self.prev_cy is None:
            mapped_x, mapped_y = self.calibration.normalize(
                cx, cy, self.frame_w, self.frame_h
            )
            self.prev_cx = float(mapped_x)
            self.prev_cy = float(mapped_y)
            self.smoothed_cx = float(mapped_x)
            self.smoothed_cy = float(mapped_y)
            self.smoothed_dx = 0.0
            self.smoothed_dy = 0.0
            return False, 0.0, 0.0

        # Pause movement when outside control box, clutching, or frozen.
        if (
            not self.is_inside_control_box(cx, cy)
            or is_clutch_active
            or is_frozen
        ):
            mapped_x, mapped_y = self.calibration.normalize(
                cx, cy, self.frame_w, self.frame_h
            )
            self.prev_cx = float(mapped_x)
            self.prev_cy = float(mapped_y)
            self.smoothed_cx = float(mapped_x)
            self.smoothed_cy = float(mapped_y)
            self.smoothed_dx = 0.0
            self.smoothed_dy = 0.0
            return False, 0.0, 0.0

        # Normalize camera coordinates through the validated user calibration.
        cx, cy = self.calibration.normalize(
            cx, cy, self.frame_w, self.frame_h
        )

        # Apply exponential smoothing.
        self.smoothed_cx = (
            (1.0 - self.smoothing) * self.smoothed_cx
            + self.smoothing * cx
        )

        self.smoothed_cy = (
            (1.0 - self.smoothing) * self.smoothed_cy
            + self.smoothing * cy
        )

        # Calculate smoothed deltas.
        delta_x = self.smoothed_cx - self.prev_cx
        delta_y = self.smoothed_cy - self.prev_cy

        # Compute movement speed.
        speed = (delta_x**2 + delta_y**2) ** 0.5

        # Ignore micro-tremors.
        if speed < self.dead_zone:
            self.prev_cx = self.smoothed_cx
            self.prev_cy = self.smoothed_cy
            return True, 0.0, 0.0

        # Apply soft dead-zone.
        scale = (speed - self.dead_zone) / speed
        delta_x_clean = delta_x * scale
        delta_y_clean = delta_y * scale

        # Compute accelerated speed.
        clean_speed = (
            delta_x_clean**2 + delta_y_clean**2
        ) ** 0.5

        multiplier_x = (
            self.sensitivity_x
            * (1.0 + self.acceleration_factor * clean_speed)
        )

        multiplier_y = (
            self.sensitivity_y
            * (1.0 + self.acceleration_factor * clean_speed)
        )

        move_dx = delta_x_clean * multiplier_x
        move_dy = delta_y_clean * multiplier_y

        # Update previous coordinates.
        self.prev_cx = self.smoothed_cx
        self.prev_cy = self.smoothed_cy

        # Get current desktop cursor position.
        curr_x, curr_y = win32_get_cursor_pos()

        target_x = int(round(curr_x + move_dx))
        target_y = int(round(curr_y + move_dy))

        # Clamp to screen limits.
        target_x = max(
            0,
            min(target_x, self.screen_width - 1),
        )

        target_y = max(
            0,
            min(target_y, self.screen_height - 1),
        )

        # Move cursor through Win32.
        ctypes.windll.user32.SetCursorPos(target_x, target_y)

        return True, move_dx, move_dy
