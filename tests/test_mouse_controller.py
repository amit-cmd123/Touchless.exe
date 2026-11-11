from unittest.mock import patch

from mouse_controller import MouseController


def test_emergency_stop_blocks_cursor_movement():
    controller = MouseController()

    controller.emergency_stop()

    with patch("mouse_controller.win32_get_cursor_pos") as mock_get_pos:
        moved, dx, dy = controller.move_cursor_relative(
            300,
            200,
            is_clutch_active=False,
        )

    assert moved is False
    assert dx == 0.0
    assert dy == 0.0
    mock_get_pos.assert_not_called()


def test_emergency_stop_blocks_mouse_actions():
    controller = MouseController()
    controller.emergency_stop()

    with patch("mouse_controller.pyautogui.click") as click, \
         patch("mouse_controller.pyautogui.rightClick") as right_click, \
         patch("mouse_controller.pyautogui.doubleClick") as double_click, \
         patch("mouse_controller.pyautogui.scroll") as scroll, \
         patch("mouse_controller.pyautogui.mouseDown") as mouse_down:
        controller.click()
        controller.right_click()
        controller.double_click()
        controller.scroll(1)
        controller.mouse_down()

    click.assert_not_called()
    right_click.assert_not_called()
    double_click.assert_not_called()
    scroll.assert_not_called()
    mouse_down.assert_not_called()


def test_emergency_stop_releases_held_button():
    controller = MouseController()
    controller.button_held = True

    with patch("mouse_controller.pyautogui.mouseUp") as mouse_up:
        controller.emergency_stop()

    mouse_up.assert_called_once()
    assert controller.emergency_stopped is True
    assert controller.button_held is False


def test_emergency_stop_preserves_held_state_if_release_fails():
    controller = MouseController()
    controller.button_held = True

    with patch("mouse_controller.pyautogui.mouseUp", side_effect=RuntimeError):
        controller.emergency_stop()

    assert controller.emergency_stopped is True
    assert controller.button_held is True


def test_reset_emergency_stop_restores_mouse_actions():
    controller = MouseController()
    controller.emergency_stop()
    controller.reset_emergency_stop()

    with patch("mouse_controller.pyautogui.click") as click:
        controller.click()

    click.assert_called_once()


def test_mouse_up_keeps_held_state_when_pyautogui_fails():
    controller = MouseController()
    controller.button_held = True

    with patch("mouse_controller.pyautogui.mouseUp", side_effect=RuntimeError):
        controller.mouse_up()

    assert controller.button_held is True


def test_mouse_up_clears_held_state_after_success():
    controller = MouseController()
    controller.button_held = True

    with patch("mouse_controller.pyautogui.mouseUp") as mouse_up:
        controller.mouse_up()

    mouse_up.assert_called_once()
    assert controller.button_held is False
