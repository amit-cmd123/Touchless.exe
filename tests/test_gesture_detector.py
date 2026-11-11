from gesture_detector import GestureDetector


def test_gesture_detector_initial_state():
    detector = GestureDetector()

    assert detector.is_dragging is False
    assert detector.left_pinch_start_time is None
    assert detector.right_pinch_active is False
    assert detector.double_pinch_active is False

from unittest.mock import patch

from gesture_detector import GestureDetector


def test_gesture_detector_initial_state():
    detector = GestureDetector()

    assert detector.is_dragging is False
    assert detector.left_pinch_start_time is None
    assert detector.right_pinch_active is False
    assert detector.double_pinch_active is False


def test_tracking_loss_releases_drag():
    detector = GestureDetector()
    detector.is_dragging = True

    with patch("gesture_detector.pyautogui.mouseUp") as mock_mouse_up:
        detector.detect_gesture([])

        mock_mouse_up.assert_called_once()

    assert detector.is_dragging is False

from tests.fixtures.landmarks import left_click_hand


def test_left_click_fixture_has_21_landmarks():
    points = left_click_hand()

    assert len(points) == 21
from unittest.mock import patch

from gesture_detector import GestureDetector
from tests.fixtures.landmarks import left_click_hand


def test_left_click():
    detector = GestureDetector()
    points = left_click_hand()

    # First call starts the left-pinch state.
    gesture, frozen = detector.detect_gesture(points)

    assert gesture == "Left Click"
    assert frozen is True
    assert detector.left_pinch_start_time is not None

    # Move the index finger away to simulate releasing the pinch.
    points[8] = (100, 50)

    with patch("gesture_detector.pyautogui.click") as mock_click:
        gesture, frozen = detector.detect_gesture(points)

        mock_click.assert_called_once()

    assert gesture == "Left Click"
    assert frozen is True
from tests.fixtures.landmarks import right_click_hand


def test_right_click():
    detector = GestureDetector()
    points = right_click_hand()

    # First call starts the right-pinch state.
    gesture, frozen = detector.detect_gesture(points)

    assert gesture == "Right Click"
    assert frozen is True
    assert detector.right_pinch_active is True

    # Move the middle finger away to release the pinch.
    points[12] = (100, 50)

    with patch("gesture_detector.pyautogui.rightClick") as mock_right_click:
        gesture, frozen = detector.detect_gesture(points)

        mock_right_click.assert_not_called()

    assert detector.right_pinch_active is False
def test_left_pinch_starts_dragging():
    detector = GestureDetector()
    points = left_click_hand()

    # Start the left-pinch state.
    detector.detect_gesture(points)

    # Pretend the pinch has been held for more than 0.5 seconds.
    detector.left_pinch_start_time -= 1.0

    with patch("gesture_detector.pyautogui.mouseDown") as mock_mouse_down:
        gesture, frozen = detector.detect_gesture(points)

        mock_mouse_down.assert_called_once()

    assert detector.is_dragging is True
    assert gesture == "Dragging"
    assert frozen is False
def test_left_pinch_releases_dragging():
    detector = GestureDetector()
    points = left_click_hand()

    # Put the detector into the dragging state.
    detector.is_dragging = True
    detector.left_pinch_start_time = 0

    # Move the index finger away to simulate releasing the pinch.
    points[8] = (100, 50)

    with patch("gesture_detector.pyautogui.mouseUp") as mock_mouse_up:
        gesture, frozen = detector.detect_gesture(points)

        mock_mouse_up.assert_called_once()

    assert detector.is_dragging is False
from tests.fixtures.landmarks import double_click_hand


def test_double_click():
    detector = GestureDetector()
    points = double_click_hand()

    with patch("gesture_detector.pyautogui.doubleClick") as mock_double_click:
        gesture, frozen = detector.detect_gesture(points)

        mock_double_click.assert_called_once()

    assert gesture == "Double Click"
    assert frozen is True
    assert detector.double_pinch_active is True
def test_tracking_loss_resets_gesture_states():
    detector = GestureDetector()

    detector.is_dragging = True
    detector.left_pinch_start_time = 123.0
    detector.right_pinch_active = True
    detector.double_pinch_active = True

    with patch("gesture_detector.pyautogui.mouseUp") as mock_mouse_up:
        gesture, frozen = detector.detect_gesture([])

        mock_mouse_up.assert_called_once()

    assert detector.is_dragging is False
    assert detector.left_pinch_start_time is None
    assert detector.right_pinch_active is False
    assert detector.double_pinch_active is False
    assert gesture == "Move"
    assert frozen is False
