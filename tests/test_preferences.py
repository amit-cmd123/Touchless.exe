import json

from preferences import Calibration, Preferences, load_preferences, save_preferences
from mouse_controller import MouseController
from unittest.mock import patch


def test_default_preferences():
    prefs = load_preferences()
    assert prefs.sensitivity == 8.5
    assert prefs.smoothing == 0.55
    assert prefs.calibration.is_valid()


def test_missing_and_malformed_preferences_use_defaults(tmp_path):
    missing = tmp_path / "missing.json"
    assert load_preferences(missing) == Preferences()
    missing.write_text("{bad", encoding="utf-8")
    assert load_preferences(missing) == Preferences()


def test_valid_preference_loading_and_persistence(tmp_path):
    path = tmp_path / "prefs.json"
    path.write_text(json.dumps({"sensitivity": 4.2, "smoothing": 0.3}), encoding="utf-8")
    prefs = load_preferences(path)
    assert prefs.sensitivity == 4.2
    prefs.scroll_sensitivity = 4.0
    save_preferences(prefs, path)
    assert load_preferences(path).scroll_sensitivity == 4.0


def test_calibration_mapping_clamps_boundaries():
    cal = Calibration(100, 500, 60, 420)
    assert cal.normalize(100, 60, 640, 480) == (0.0, 0.0)
    assert cal.normalize(500, 420, 640, 480) == (640.0, 480.0)
    assert cal.normalize(0, 500, 640, 480) == (0.0, 480.0)


def test_calibration_maps_to_requested_frame_dimensions():
    cal = Calibration(100, 500, 60, 420)
    assert cal.normalize(300, 240, 1280, 720) == (640.0, 360.0)
    assert cal.normalize(500, 420, 1280, 720) == (1280.0, 720.0)


def test_invalid_calibration_rejected_during_load(tmp_path):
    path = tmp_path / "prefs.json"
    path.write_text(json.dumps({"calibration": {"min_x": 100, "max_x": 100, "min_y": 0, "max_y": 480}}), encoding="utf-8")
    assert load_preferences(path).calibration == Calibration()


def test_sensitivity_and_smoothing_values_are_validated(tmp_path):
    path = tmp_path / "prefs.json"
    path.write_text(json.dumps({"sensitivity": 99, "smoothing": 0}), encoding="utf-8")
    prefs = load_preferences(path)
    assert prefs.sensitivity == 8.5
    assert prefs.smoothing == 0.55


def test_cursor_sensitivity_scales_movement_without_real_mouse():
    controller = MouseController(smoothing=1.0, sensitivity_x=2.0,
                                 sensitivity_y=2.0, dead_zone=0.0)
    controller.move_cursor_relative(100, 100, False)
    with patch("mouse_controller.win32_get_cursor_pos", return_value=(200, 200)), \
         patch("mouse_controller.ctypes.windll.user32.SetCursorPos") as set_pos:
        moved, dx, dy = controller.move_cursor_relative(110, 100, False)
    assert moved is True
    assert dx == 36.0
    assert dy == 0.0
    set_pos.assert_called_once_with(236, 200)


def test_smoothing_reduces_first_cursor_delta():
    controller = MouseController(smoothing=0.5, sensitivity_x=1.0,
                                 sensitivity_y=1.0, dead_zone=0.0)
    controller.move_cursor_relative(100, 100, False)
    with patch("mouse_controller.win32_get_cursor_pos", return_value=(0, 0)), \
         patch("mouse_controller.ctypes.windll.user32.SetCursorPos"):
        _, dx, _ = controller.move_cursor_relative(110, 100, False)
    assert dx == 7.0
