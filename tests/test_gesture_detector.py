from unittest.mock import Mock
from unittest.mock import patch

from gesture_detector import GestureDetector
from tests.fixtures.landmarks import double_click_hand
from tests.fixtures.landmarks import left_click_hand
from tests.fixtures.landmarks import right_click_hand
from mouse_controller import MouseController


def test_gesture_detector_initial_state():
    detector = GestureDetector()

    assert detector.is_dragging is False
    assert detector.left_pinch_start_time is None
    assert detector.right_pinch_active is False
    assert detector.double_pinch_active is False

def test_tracking_loss_releases_drag():
    mouse_controller = Mock()
    detector = GestureDetector(mouse_controller=mouse_controller)
    detector.is_dragging = True

    detector.detect_gesture([])
    mouse_controller.mouse_up.assert_called_once()

    assert detector.is_dragging is False

def test_left_click_fixture_has_21_landmarks():
    points = left_click_hand()

    assert len(points) == 21


def test_left_click():
    mouse_controller = Mock()
    detector = GestureDetector(mouse_controller=mouse_controller)
    points = left_click_hand()

    # First call starts the left-pinch state.
    gesture, frozen = detector.detect_gesture(points)

    assert gesture == "Left Click"
    assert frozen is True
    assert detector.left_pinch_start_time is not None

    # Move the index finger away to simulate releasing the pinch.
    points[8] = (100, 50)

    gesture, frozen = detector.detect_gesture(points)
    mouse_controller.click.assert_called_once()

    assert gesture == "Left Click"
    assert frozen is True
def test_right_click():
    mouse_controller = Mock()
    detector = GestureDetector(mouse_controller=mouse_controller)
    points = right_click_hand()

    # First call starts the right-pinch state.
    gesture, frozen = detector.detect_gesture(points)

    assert gesture == "Right Click"
    assert frozen is True
    assert detector.right_pinch_active is True

    # Move the middle finger away to release the pinch.
    points[12] = (100, 50)

    gesture, frozen = detector.detect_gesture(points)
    mouse_controller.right_click.assert_called_once()

    assert detector.right_pinch_active is False
def test_left_pinch_starts_dragging():
    mouse_controller = Mock()
    detector = GestureDetector(mouse_controller=mouse_controller)
    points = left_click_hand()

    # Start the left-pinch state.
    detector.detect_gesture(points)

    # Pretend the pinch has been held for more than 0.5 seconds.
    detector.left_pinch_start_time -= 1.0

    gesture, frozen = detector.detect_gesture(points)
    mouse_controller.mouse_down.assert_called_once()

    assert detector.is_dragging is True
    assert gesture == "Dragging"
    assert frozen is False
def test_left_pinch_releases_dragging():
    mouse_controller = Mock()
    detector = GestureDetector(mouse_controller=mouse_controller)
    points = left_click_hand()

    # Put the detector into the dragging state.
    detector.is_dragging = True
    detector.left_pinch_start_time = 0

    # Move the index finger away to simulate releasing the pinch.
    points[8] = (100, 50)

    gesture, frozen = detector.detect_gesture(points)
    mouse_controller.mouse_up.assert_called_once()

    assert detector.is_dragging is False
def test_double_click():
    mouse_controller = Mock()
    detector = GestureDetector(mouse_controller=mouse_controller)
    points = double_click_hand()

    gesture, frozen = detector.detect_gesture(points)
    mouse_controller.double_click.assert_called_once()

    assert gesture == "Double Click"
    assert frozen is True
    assert detector.double_pinch_active is True
def test_tracking_loss_resets_gesture_states():
    mouse_controller = Mock()
    detector = GestureDetector(mouse_controller=mouse_controller)

    detector.is_dragging = True
    detector.left_pinch_start_time = 123.0
    detector.right_pinch_active = True
    detector.double_pinch_active = True

    gesture, frozen = detector.detect_gesture([])
    mouse_controller.mouse_up.assert_called_once()

    assert detector.is_dragging is False
    assert detector.left_pinch_start_time is None
    assert detector.right_pinch_active is False
    assert detector.double_pinch_active is False
    assert gesture == "Move"
    assert frozen is False


def test_gesture_action_routes_through_mouse_controller():
    with patch("mouse_controller.pyautogui.size", return_value=(1920, 1080)), \
         patch("mouse_controller.pyautogui.rightClick") as right_click:
        controller = MouseController()
        detector = GestureDetector(mouse_controller=controller)
        detector.detect_gesture(right_click_hand())

    right_click.assert_called_once()
