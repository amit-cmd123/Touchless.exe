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