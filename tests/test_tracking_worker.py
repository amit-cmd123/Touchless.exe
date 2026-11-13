import numpy as np
import pytest
from unittest.mock import patch

import gui
from camera import Camera
from preferences import Calibration, Preferences


class FakeCamera:
    instances = []
    worker = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.released = False
        self.instances.append(self)

    def read(self):
        if self.worker is not None:
            self.worker.running = False
        return True, np.zeros((480, 640, 3), dtype=np.uint8)

    def release(self):
        self.released = True


class FakeMouseController:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.released = False
        self.instances.append(self)

    def mouse_up(self):
        self.released = True

    def move_cursor_relative(self, *args, **kwargs):
        return False, 0.0, 0.0


class FakeTracker:
    instances = []
    fail_process = False

    def __init__(self):
        self.closed = False
        self.instances.append(self)

    def process(self, frame, draw=True):
        if self.fail_process:
            raise RuntimeError("synthetic tracker failure")
        return frame, False, None, False, False, False

    def close(self):
        self.closed = True


def _install_fakes(monkeypatch):
    FakeCamera.instances.clear()
    FakeMouseController.instances.clear()
    FakeTracker.instances.clear()
    FakeTracker.fail_process = False
    FakeCamera.worker = None
    monkeypatch.setattr(gui, "Camera", FakeCamera)
    monkeypatch.setattr(gui, "HandTracker", FakeTracker)
    monkeypatch.setattr(gui, "MouseController", FakeMouseController)


def test_worker_passes_preferences_and_cleans_up(monkeypatch):
    _install_fakes(monkeypatch)
    prefs = Preferences(
        camera_index=2,
        frame_width=800,
        frame_height=600,
        sensitivity=4.0,
        smoothing=0.4,
        scroll_sensitivity=5.0,
        calibration=Calibration(10, 600, 20, 450),
    )
    worker = gui.TrackingWorker(4.0, 0.4, False, prefs)
    FakeCamera.worker = worker
    worker.run()

    assert FakeCamera.instances[0].kwargs == {
        "device_index": 2, "width": 800, "height": 600
    }
    controller = FakeMouseController.instances[0]
    assert controller.kwargs["frame_w"] == 800
    assert controller.kwargs["frame_h"] == 600
    assert controller.kwargs["sensitivity_x"] == 4.0
    assert controller.kwargs["smoothing"] == 0.4
    assert controller.kwargs["scroll_sensitivity"] == 5.0
    assert controller.kwargs["calibration"] is prefs.calibration
    assert controller.released
    assert FakeTracker.instances[0].closed
    assert FakeCamera.instances[0].released


def test_worker_reports_initialization_failure_and_releases_camera(monkeypatch):
    _install_fakes(monkeypatch)

    def fail_tracker_init():
        raise RuntimeError("internal detail")

    monkeypatch.setattr(gui, "HandTracker", fail_tracker_init)
    worker = gui.TrackingWorker(8.5, 0.55, False, Preferences())
    errors = []
    worker.error.connect(errors.append)
    worker.run()

    assert FakeCamera.instances[0].released
    assert errors == [
        "Hand tracking could not be initialized. Check the installation and model file."
    ]
    assert "internal detail" not in errors[0]


def test_worker_runtime_failure_closes_tracker_camera_and_mouse(monkeypatch):
    _install_fakes(monkeypatch)
    FakeTracker.fail_process = True
    worker = gui.TrackingWorker(8.5, 0.55, False, Preferences())
    FakeCamera.worker = worker
    errors = []
    worker.error.connect(errors.append)
    worker.run()

    assert FakeTracker.instances[0].closed
    assert FakeCamera.instances[0].released
    assert FakeMouseController.instances[0].released
    assert errors == [
        "Tracking stopped after an unexpected error. You can try starting it again."
    ]


def test_worker_repeated_frame_failure_reports_error_and_cleans_up(monkeypatch):
    _install_fakes(monkeypatch)

    class NoFramesCamera(FakeCamera):
        def read(self):
            return False, None

    monkeypatch.setattr(gui, "Camera", NoFramesCamera)
    worker = gui.TrackingWorker(8.5, 0.55, False, Preferences())
    errors = []
    worker.error.connect(errors.append)
    worker.run()

    assert NoFramesCamera.instances[-1].released
    assert FakeTracker.instances[-1].closed
    assert FakeMouseController.instances[-1].released
    assert errors == [
        "The camera stopped providing frames. Check its connection and try again."
    ]


def test_camera_open_failure_releases_capture_handle():
    class ClosedCapture:
        released = False

        def isOpened(self):
            return False

        def release(self):
            self.released = True

    capture = ClosedCapture()
    with patch("camera.cv2.VideoCapture", return_value=capture):
        with pytest.raises(RuntimeError, match="Unable to open webcam"):
            Camera()
    assert capture.released


def test_gui_error_handler_presents_worker_message(monkeypatch):
    presented = []
    monkeypatch.setattr(
        gui.QMessageBox,
        "warning",
        lambda parent, title, message: presented.append((title, message)),
    )
    gui.TouchlessGUI.on_worker_error(object(), "Camera is unavailable.")
    assert presented == [("Touchless tracking stopped", "Camera is unavailable.")]
