import time

class GestureDetector:
    def __init__(
        self,
        mouse_controller=None,
        threshold: float = 0.18,
        hysteresis: float = 0.04,
    ):
        """Initializes the GestureDetector.

        Args:
            threshold (float): Normalized distance threshold for pinches.
            hysteresis (float): Hysteresis margin to prevent flicker.
        """
        self.threshold = threshold
        self.mouse_controller = mouse_controller
        self.hysteresis = hysteresis
        self.ema_alpha = 0.8       # Smoothing factor (0.0 < alpha <= 1.0)

        # State tracking for Left Click / Drag Mode
        self.left_pinch_start_time = None
        self.is_dragging = False

        # State tracking for Right Click
        self.right_pinch_active = False

        # State tracking for Double Click
        self.double_pinch_active = False

        # Smoothed distances
        self.smoothed_left_dist = None
        self.smoothed_right_dist = None
        self.smoothed_double_dist = None

        # State tracking for Scroll Mode
        self.scroll_mode = None
        self.prev_scroll_pos = None
        self.scroll_accum_y = 0.0
        self.scroll_accum_x = 0.0
        self.smoothed_scroll_dx = 0.0
        self.smoothed_scroll_dy = 0.0

        # Keep standalone construction safe for callers that only detect gestures.
        # Mouse actions are ignored until a controller is supplied.

    def _dist(self, p1: tuple[int, int], p2: tuple[int, int]) -> float:
        """Euclidean distance between two pixel coordinates."""
        return ((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)**0.5

    def _check_scroll_pose(self, points: list[tuple[int, int]]) -> bool:
        """Determines if the hand is in scroll pose (index and middle fingers extended, ring and pinky folded)."""
        if len(points) < 21:
            return False
        
        wrist = points[0]
        index_ext = self._dist(points[8], wrist) > self._dist(points[6], wrist)
        middle_ext = self._dist(points[12], wrist) > self._dist(points[10], wrist)
        ring_ext = self._dist(points[16], wrist) > self._dist(points[14], wrist)
        pinky_ext = self._dist(points[20], wrist) > self._dist(points[18], wrist)
        
        return index_ext and middle_ext and not ring_ext and not pinky_ext

    def detect_gesture(self, points: list[tuple[int, int]], is_clutch_active: bool = False, is_palm_open: bool = False, is_fist: bool = False) -> tuple[str, bool]:
        """Analyzes landmarks to detect gestures and triggers actions.

        Args:
            points (list[tuple[int, int]]): 21 hand landmarks in pixel coordinates.
            is_clutch_active (bool): Deprecated/unused but kept for compatibility.

        Returns:
            tuple: (gesture_state, is_frozen)
                gesture_state (str): "Move", "Left Click", "Dragging", "Right Click", "Double Click"
                is_frozen (bool): True if the cursor should freeze to prevent clicking drift.
        """
        if len(points) < 21:
            # Safely release dragging on lost tracking
            if self.is_dragging:
                if self.mouse_controller is not None:
                    self.mouse_controller.mouse_up()
            self.is_dragging = False
            self.left_pinch_start_time = None
            self.right_pinch_active = False
            self.double_pinch_active = False
            self.smoothed_left_dist = None
            self.smoothed_right_dist = None
            self.smoothed_double_dist = None
            self.prev_scroll_pos = None
            self.scroll_mode = None
            self.scroll_accum_y = 0.0
            self.scroll_accum_x = 0.0
            self.smoothed_scroll_dx = 0.0
            self.smoothed_scroll_dy = 0.0
            return "Move", False

        # Calculate wrist to middle-finger knuckle (0 to 9) as hand scale reference
        hand_scale = self._dist(points[0], points[9])
        if hand_scale == 0:
            hand_scale = 1.0  # Prevent division by zero

        # Calculate raw normalized distances
        left_dist = self._dist(points[4], points[8]) / hand_scale
        right_dist = self._dist(points[4], points[12]) / hand_scale
        double_dist = self._dist(points[4], points[16]) / hand_scale

        # Apply EMA filters
        if self.smoothed_left_dist is None:
            self.smoothed_left_dist = left_dist
        else:
            self.smoothed_left_dist = (1.0 - self.ema_alpha) * self.smoothed_left_dist + self.ema_alpha * left_dist

        if self.smoothed_right_dist is None:
            self.smoothed_right_dist = right_dist
        else:
            self.smoothed_right_dist = (1.0 - self.ema_alpha) * self.smoothed_right_dist + self.ema_alpha * right_dist

        if self.smoothed_double_dist is None:
            self.smoothed_double_dist = double_dist
        else:
            self.smoothed_double_dist = (1.0 - self.ema_alpha) * self.smoothed_double_dist + self.ema_alpha * double_dist

        # Compute finger extensions early to apply pinch isolation constraints
        wrist = points[0]
        index_ext = self._dist(points[8], wrist) > self._dist(points[6], wrist)
        middle_ext = self._dist(points[12], wrist) > self._dist(points[10], wrist)
        ring_ext = self._dist(points[16], wrist) > self._dist(points[14], wrist)
        pinky_ext = self._dist(points[20], wrist) > self._dist(points[18], wrist)

        # A new pinch can only start if at least 2 of the other fingers are extended (prevents fist misfires)
        left_pinch_allowed = self.left_pinch_start_time is not None or self.is_dragging or (sum([middle_ext, ring_ext, pinky_ext]) >= 2)
        right_pinch_allowed = self.right_pinch_active or (sum([index_ext, ring_ext, pinky_ext]) >= 2)
        double_pinch_allowed = self.double_pinch_active or (sum([index_ext, middle_ext, pinky_ext]) >= 2)

        # Check pinch active states with hysteresis and constraints
        left_dist_active = left_pinch_allowed and (self.smoothed_left_dist < (self.threshold + self.hysteresis) if (self.left_pinch_start_time is not None or self.is_dragging) else self.smoothed_left_dist < self.threshold)
        right_dist_active = right_pinch_allowed and (self.smoothed_right_dist < (self.threshold + self.hysteresis) if self.right_pinch_active else self.smoothed_right_dist < self.threshold)
        double_dist_active = double_pinch_allowed and (self.smoothed_double_dist < (self.threshold + self.hysteresis) if self.double_pinch_active else self.smoothed_double_dist < self.threshold)

        active_gesture = "Move"
        is_frozen = False

        # 1. Run Click State Machine
        if self.is_dragging:
            # We are currently in Drag Mode holding the left pinch
            if left_dist_active:
                is_frozen = False
                active_gesture = "Dragging"
            else:
                if self.mouse_controller is not None:
                    self.mouse_controller.mouse_up()
                self.is_dragging = False
                self.left_pinch_start_time = None
                active_gesture = "Move"
                is_frozen = False

        elif self.right_pinch_active:
            if right_dist_active:
                is_frozen = True
                active_gesture = "Right Click"
            else:
                self.right_pinch_active = False

        elif self.double_pinch_active:
            if double_dist_active:
                is_frozen = True
                active_gesture = "Double Click"
            else:
                self.double_pinch_active = False

        elif self.left_pinch_start_time is not None:
            if left_dist_active:
                elapsed = time.time() - self.left_pinch_start_time
                if elapsed > 0.5:
                    if self.mouse_controller is not None:
                        self.mouse_controller.mouse_down()
                    self.is_dragging = True
                    is_frozen = False
                    active_gesture = "Dragging"
                else:
                    is_frozen = True
                    active_gesture = "Left Click"
            else:
                if self.mouse_controller is not None:
                    self.mouse_controller.click()
                self.left_pinch_start_time = None
                active_gesture = "Left Click"
                is_frozen = True

        else:
            # Detect new pinches in order of priority (Right, Double, Left)
            if right_dist_active:
                if self.mouse_controller is not None:
                    self.mouse_controller.right_click()
                self.right_pinch_active = True
                active_gesture = "Right Click"
                is_frozen = True
                self.scroll_mode = None
            elif double_dist_active:
                if self.mouse_controller is not None:
                    self.mouse_controller.double_click()
                self.double_pinch_active = True
                active_gesture = "Double Click"
                is_frozen = True
                self.scroll_mode = None
            elif left_dist_active:
                self.left_pinch_start_time = time.time()
                active_gesture = "Left Click"
                is_frozen = True
                self.scroll_mode = None

        # 2. Run Scroll Pose & Scroll Action Logic
        # Calculate relative Y position of index and middle finger tips
        rel_y = ((points[8][1] - points[5][1]) + (points[12][1] - points[9][1])) / 2.0

        if is_fist:
            self.scroll_mode = "down_prep"
            self.prev_scroll_pos = rel_y
            self.scroll_accum_y = 0.0
            if self.is_dragging:
                if self.mouse_controller is not None:
                    self.mouse_controller.mouse_up()
            self.is_dragging = False
            self.left_pinch_start_time = None
            self.right_pinch_active = False
            self.double_pinch_active = False
        elif is_palm_open:
            self.scroll_mode = "up_prep"
            self.prev_scroll_pos = rel_y
            self.scroll_accum_y = 0.0

        is_scrolling = False

        if self.scroll_mode in ["down_prep", "down_active"]:
            # Scrolling down: start from fist, curl/extend index/middle upwards (dy < 0)
            # Ring and pinky must stay folded
            ring_folded = not ring_ext
            pinky_folded = not pinky_ext
            if ring_folded and pinky_folded:
                if self.prev_scroll_pos is not None:
                    raw_dy = rel_y - self.prev_scroll_pos
                    scroll_alpha = 0.5
                    self.smoothed_scroll_dy = (1.0 - scroll_alpha) * self.smoothed_scroll_dy + scroll_alpha * raw_dy
                    
                    dead_zone = 0.5
                    if self.smoothed_scroll_dy < -dead_zone:
                        self.scroll_mode = "down_active"
                        is_scrolling = True
                        dy = self.smoothed_scroll_dy
                        sensitivity_y = 3.0
                        accel_y = 1.0 + 0.08 * abs(dy)
                        
                        self.scroll_accum_y += dy * sensitivity_y * accel_y
                        clicks_y = int(self.scroll_accum_y)
                        if clicks_y != 0:
                            if self.mouse_controller is not None:
                                self.mouse_controller.scroll(clicks_y)
                            self.scroll_accum_y -= clicks_y
                self.prev_scroll_pos = rel_y
            else:
                self.scroll_mode = None
                self.prev_scroll_pos = None

        elif self.scroll_mode in ["up_prep", "up_active"]:
            # Scrolling up: start from open palm, curl fingers downwards (dy > 0)
            if not (left_dist_active or right_dist_active or double_dist_active or self.is_dragging or self.right_pinch_active or self.double_pinch_active or self.left_pinch_start_time is not None):
                if not index_ext and not middle_ext:
                    if self.prev_scroll_pos is not None:
                        raw_dy = rel_y - self.prev_scroll_pos
                        scroll_alpha = 0.5
                        self.smoothed_scroll_dy = (1.0 - scroll_alpha) * self.smoothed_scroll_dy + scroll_alpha * raw_dy
                        
                        dead_zone = 0.5
                        if self.smoothed_scroll_dy > dead_zone:
                            self.scroll_mode = "up_active"
                            is_scrolling = True
                            dy = self.smoothed_scroll_dy
                            sensitivity_y = 3.0
                            accel_y = 1.0 + 0.08 * abs(dy)
                            
                            self.scroll_accum_y += dy * sensitivity_y * accel_y
                            clicks_y = int(self.scroll_accum_y)
                            if clicks_y != 0:
                                if self.mouse_controller is not None:
                                    self.mouse_controller.scroll(clicks_y)
                                self.scroll_accum_y -= clicks_y
                    self.prev_scroll_pos = rel_y
                else:
                    if self.scroll_mode == "up_active":
                        self.scroll_mode = None
                        self.prev_scroll_pos = None
                    else:
                        self.prev_scroll_pos = rel_y
            else:
                self.scroll_mode = None
                self.prev_scroll_pos = None

        # 3. Override active gesture and frozen status with scroll status if applicable
        if self.scroll_mode in ["down_prep", "down_active", "up_active"] or is_scrolling:
            active_gesture = "Scroll" if (self.scroll_mode in ["down_active", "up_active"] or is_scrolling) else "Cursor Paused"
            is_frozen = True

        return active_gesture, is_frozen
