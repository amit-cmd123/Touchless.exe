import sys
import os
import time
import cv2
import numpy as np

# pyrefly: ignore [missing-import]
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QSize
# pyrefly: ignore [missing-import]
from PyQt6.QtGui import QImage, QPixmap, QFont, QIcon
# pyrefly: ignore [missing-import]
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QSlider, QCheckBox, QGroupBox,
    QFrame
)

from camera import Camera
from hand_tracker import HandTracker
from mouse_controller import MouseController
from gesture_detector import GestureDetector

# Touchless configuration constants
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
MARGIN_LEFT = 0
MARGIN_RIGHT = 0
MARGIN_TOP = 0
MARGIN_BOTTOM = 0
DEFAULT_SENSITIVITY = 8.5
DEFAULT_SMOOTHING = 0.55

class TrackingWorker(QThread):
    """Background worker thread to run camera capture, landmark tracking,
    gesture detection, and relative mouse control without freezing the UI.
    """
    frame_ready = pyqtSignal(np.ndarray, str, float)  # Emits (annotated_frame, gesture_state, fps)

    def __init__(self, sensitivity: float, smoothing: float, preview_enabled: bool):
        super().__init__()
        self.sensitivity = sensitivity
        self.smoothing = smoothing
        self.preview_enabled = preview_enabled
        self.running = True

    def run(self):
        try:
            cam = Camera(device_index=CAMERA_INDEX, width=FRAME_WIDTH, height=FRAME_HEIGHT)
        except Exception as e:
            print(f"[ERROR] Camera failed to start: {e}")
            return

        tracker = HandTracker()
        mc = MouseController(
            frame_w=FRAME_WIDTH,
            frame_h=FRAME_HEIGHT,
            margin_left=MARGIN_LEFT,
            margin_right=MARGIN_RIGHT,
            margin_top=MARGIN_TOP,
            margin_bottom=MARGIN_BOTTOM,
            smoothing=self.smoothing,
            sensitivity_x=self.sensitivity,
            sensitivity_y=self.sensitivity
        )
        gd = GestureDetector()

        prev_time = time.time()
        smoothed_fps = 0.0

        while self.running:
            # Dynamically update parameters
            mc.sensitivity_x = self.sensitivity
            mc.sensitivity_y = self.sensitivity
            mc.smoothing = self.smoothing

            ret, frame = cam.read()
            if not ret or frame is None:
                time.sleep(0.002)
                continue

            # Mirror the frame horizontally
            frame = cv2.flip(frame, 1)

            # Process hand landmarks
            # Disable drawing in tracker if preview is disabled to save CPU
            annotated_frame, hand_present, points, is_palm_open, is_fist, is_index_straight = tracker.process(
                frame, draw=self.preview_enabled
            )

            # Knuckle (point 5) is used for stable relative cursor movement
            tracking_pos = None
            if hand_present and points and len(points) > 5:
                tracking_pos = points[5]

            # Detect gesture
            gesture_state = "Move"
            is_frozen = False
            if hand_present and points:
                gesture_state, is_frozen = gd.detect_gesture(
                    points, is_palm_open=is_palm_open, is_fist=is_fist
                )

            # Clutch mechanism: Move ONLY during open palm or active dragging
            movement_allowed = hand_present and (is_palm_open or gd.is_dragging)
            is_clutch_active = not movement_allowed

            # Update relative cursor
            dx, dy = 0.0, 0.0
            if hand_present and tracking_pos:
                _, dx, dy = mc.move_cursor_relative(
                    tracking_pos[0], tracking_pos[1], is_clutch_active, is_frozen=is_frozen
                )

            # Calculate FPS
            curr_time = time.time()
            dt = curr_time - prev_time
            prev_time = curr_time
            fps = 1.0 / dt if dt > 0 else 0.0
            smoothed_fps = (0.9 * smoothed_fps) + (0.1 * fps)

            # Emit results to main GUI thread
            self.frame_ready.emit(annotated_frame, gesture_state, smoothed_fps)

        # Cleanup resources
        try:
            import pyautogui
            pyautogui.mouseUp()
        except Exception:
            pass
        tracker.close()
        cam.release()

    def stop(self):
        self.running = False


class FloatingPreviewWindow(QWidget):
    """A small frameless always-on-top window that displays the camera feed in a corner of the screen."""
    
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setObjectName("FloatingPreview")
        self.setFixedSize(200, 150)
        
        # Rounded corners stylesheet
        self.setStyleSheet("""
            QWidget#FloatingPreview {
                background-color: #18181b;
                border: 2px solid #00f0ff;
                border-radius: 12px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        
        self.lbl_feed = QLabel()
        self.lbl_feed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_feed.setStyleSheet("border-radius: 10px; background-color: #121214;")
        layout.addWidget(self.lbl_feed)
        
        self.position_in_corner()
        self.drag_position = None
        
    def position_in_corner(self):
        screen = QApplication.primaryScreen().geometry()
        margin = 30
        x = screen.width() - self.width() - margin
        y = screen.height() - self.height() - margin
        self.move(x, y)
        
    def update_frame(self, pixmap):
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                self.lbl_feed.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_feed.setPixmap(scaled)
            
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position is not None:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
            
    def mouseReleaseEvent(self, event):
        self.drag_position = None


class TouchlessGUI(QMainWindow):
    """Main window for the modern desktop control panel."""
    
    def __init__(self):
        super().__init__()
        self.worker = None
        self.sensitivity_val = DEFAULT_SENSITIVITY
        self.smoothing_val = DEFAULT_SMOOTHING
        self.preview_on = True
        self.floating_preview = None

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Touchless - Control Center")
        self.setMinimumSize(850, 520)
        self.setObjectName("MainWindow")
        
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        # Global stylesheet for premium dark mode
        self.setStyleSheet("""
            QMainWindow#MainWindow {
                background-color: #121214;
            }
            QWidget {
                color: #e1e1e6;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #29292e;
                border-radius: 8px;
                margin-top: 20px;
                padding-top: 15px;
                background-color: #18181b;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 12px;
                padding: 0 5px;
                color: #00f0ff;
                background-color: #121214;
            }
            QLabel {
                font-size: 13px;
            }
            QPushButton {
                font-size: 13px;
                font-weight: bold;
                border-radius: 6px;
                padding: 10px;
                min-width: 100px;
                border: 1px solid #29292e;
            }
            QSlider::groove:horizontal {
                border: 1px solid #29292e;
                height: 6px;
                background: #202024;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #00f0ff;
                border: 1px solid #00f0ff;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #ffffff;
                border-color: #ffffff;
            }
            QCheckBox {
                spacing: 8px;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #29292e;
                border-radius: 4px;
                background-color: #202024;
            }
            QCheckBox::indicator:checked {
                background-color: #00f0ff;
                border-color: #00f0ff;
            }
            QFrame#cardFrame {
                background-color: #18181b;
                border: 1px solid #29292e;
                border-radius: 8px;
            }
        """)

        # Main Layout container
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # ----------------- LEFT PANEL (CONTROLS) -----------------
        left_layout = QVBoxLayout()
        left_layout.setSpacing(15)

        # Header Layout (Logo + Title)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        
        # Logo Label
        logo_label = QLabel()
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
        if os.path.exists(logo_path):
            logo_pixmap = QPixmap(logo_path)
            # Scale logo to a nice header size, e.g. 36x36
            scaled_logo = logo_pixmap.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled_logo)
        else:
            logo_label.setVisible(False)
            
        header_layout.addWidget(logo_label)
        
        # Title Label
        title_label = QLabel("TOUCHLESS")
        title_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #00f0ff; letter-spacing: 1.5px;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        left_layout.addLayout(header_layout)

        # Group Box: System Control
        group_ctrl = QGroupBox("System Actions")
        ctrl_layout = QVBoxLayout(group_ctrl)
        ctrl_layout.setSpacing(10)

        self.btn_start = QPushButton("Start Tracking")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #00875f;
                color: #ffffff;
                border-color: #00875f;
            }
            QPushButton:hover {
                background-color: #00b07b;
                border-color: #00b07b;
            }
        """)
        self.btn_start.clicked.connect(self.start_tracking)
        ctrl_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("Stop Tracking")
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #202024;
                color: #7c7c8a;
                border-color: #29292e;
            }
            QPushButton:hover:enabled {
                background-color: #ab2222;
                border-color: #f75a68;
                color: #ffffff;
            }
        """)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_tracking)
        ctrl_layout.addWidget(self.btn_stop)

        left_layout.addWidget(group_ctrl)

        # Group Box: Parameters
        group_params = QGroupBox("Adjust Parameters")
        params_layout = QVBoxLayout(group_params)
        params_layout.setSpacing(12)

        # Sensitivity Slider
        lbl_sens_title = QLabel("Cursor Sensitivity")
        lbl_sens_title.setStyleSheet("font-weight: bold; color: #c4c4cc;")
        params_layout.addWidget(lbl_sens_title)

        sens_sub_layout = QHBoxLayout()
        self.sens_slider = QSlider(Qt.Orientation.Horizontal)
        self.sens_slider.setRange(10, 150)  # Multiplied by 10 internally
        self.sens_slider.setValue(int(DEFAULT_SENSITIVITY * 10))
        self.sens_slider.valueChanged.connect(self.on_sens_changed)
        sens_sub_layout.addWidget(self.sens_slider)

        self.lbl_sens_val = QLabel(f"{DEFAULT_SENSITIVITY:.1f}")
        self.lbl_sens_val.setMinimumWidth(30)
        self.lbl_sens_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_sens_val.setStyleSheet("color: #00f0ff; font-weight: bold;")
        sens_sub_layout.addWidget(self.lbl_sens_val)
        params_layout.addLayout(sens_sub_layout)

        # Smoothing Slider
        lbl_smooth_title = QLabel("Cursor Smoothing")
        lbl_smooth_title.setStyleSheet("font-weight: bold; color: #c4c4cc;")
        params_layout.addWidget(lbl_smooth_title)

        smooth_sub_layout = QHBoxLayout()
        self.smooth_slider = QSlider(Qt.Orientation.Horizontal)
        self.smooth_slider.setRange(5, 95)  # Multiplied by 100 internally
        self.smooth_slider.setValue(int(DEFAULT_SMOOTHING * 100))
        self.smooth_slider.valueChanged.connect(self.on_smooth_changed)
        smooth_sub_layout.addWidget(self.smooth_slider)

        self.lbl_smooth_val = QLabel(f"{DEFAULT_SMOOTHING:.2f}")
        self.lbl_smooth_val.setMinimumWidth(30)
        self.lbl_smooth_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_smooth_val.setStyleSheet("color: #00f0ff; font-weight: bold;")
        smooth_sub_layout.addWidget(self.lbl_smooth_val)
        params_layout.addLayout(smooth_sub_layout)

        left_layout.addWidget(group_params)

        # Preferences
        self.chk_preview = QCheckBox("Camera Preview Feed")
        self.chk_preview.setChecked(True)
        self.chk_preview.toggled.connect(self.on_preview_toggled)
        left_layout.addWidget(self.chk_preview)

        self.chk_minimize = QCheckBox("Minimize Feed to Corner")
        self.chk_minimize.setChecked(False)
        self.chk_minimize.toggled.connect(self.on_minimize_toggled)
        left_layout.addWidget(self.chk_minimize)

        left_layout.addStretch()
        left_layout.setStretch(2, 2)
        
        main_layout.addLayout(left_layout, stretch=1)

        # ----------------- RIGHT PANEL (FEED & HUD) -----------------
        right_layout = QVBoxLayout()
        right_layout.setSpacing(15)

        # Camera Display Viewport
        self.video_viewport = QLabel()
        self.video_viewport.setMinimumSize(480, 360)
        self.video_viewport.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_viewport.setStyleSheet("""
            background-color: #18181b;
            border: 1px solid #29292e;
            border-radius: 8px;
            color: #7c7c8a;
            font-size: 15px;
            font-weight: bold;
        """)
        self.video_viewport.setText("TRACKING OFFLINE\nClick 'Start Tracking' to begin camera feed.")
        right_layout.addWidget(self.video_viewport, stretch=4)

        # Dashboard / Metrics Card Layout
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(15)

        # Gesture Card
        card_gesture = QFrame()
        card_gesture.setObjectName("cardFrame")
        cg_layout = QVBoxLayout(card_gesture)
        cg_title = QLabel("ACTIVE GESTURE")
        cg_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        cg_title.setStyleSheet("color: #7c7c8a; text-transform: uppercase;")
        self.lbl_gesture = QLabel("MOVE")
        self.lbl_gesture.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.lbl_gesture.setStyleSheet("color: #ffffff;")
        cg_layout.addWidget(cg_title)
        cg_layout.addWidget(self.lbl_gesture)
        metrics_layout.addWidget(card_gesture)

        # FPS Card
        card_fps = QFrame()
        card_fps.setObjectName("cardFrame")
        cf_layout = QVBoxLayout(card_fps)
        cf_title = QLabel("SYSTEM FPS")
        cf_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        cf_title.setStyleSheet("color: #7c7c8a; text-transform: uppercase;")
        self.lbl_fps = QLabel("0.0")
        self.lbl_fps.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.lbl_fps.setStyleSheet("color: #ffffff;")
        cf_layout.addWidget(cf_title)
        cf_layout.addWidget(self.lbl_fps)
        metrics_layout.addWidget(card_fps)

        right_layout.addLayout(metrics_layout, stretch=1)
        
        main_layout.addLayout(right_layout, stretch=2)

    def start_tracking(self):
        if self.worker is not None:
            return

        self.btn_start.setEnabled(False)
        self.btn_start.setText("Connecting...")
        self.btn_start.setStyleSheet("background-color: #202024; color: #7c7c8a; border-color: #29292e;")

        self.worker = TrackingWorker(
            sensitivity=self.sensitivity_val,
            smoothing=self.smoothing_val,
            preview_enabled=self.preview_on
        )
        self.worker.frame_ready.connect(self.update_frame)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

        self.btn_stop.setEnabled(True)
        self.btn_stop.setStyleSheet("""
            QPushButton {
                background-color: #ab2222;
                color: #ffffff;
                border-color: #ab2222;
            }
            QPushButton:hover {
                background-color: #f75a68;
                border-color: #f75a68;
            }
        """)

    def stop_tracking(self):
        if self.worker is None:
            return

        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("background-color: #202024; color: #7c7c8a; border-color: #29292e;")
        self.worker.stop()

    def on_worker_finished(self):
        self.worker = None
        self.btn_start.setEnabled(True)
        self.btn_start.setText("Start Tracking")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #00875f;
                color: #ffffff;
                border-color: #00875f;
            }
            QPushButton:hover {
                background-color: #00b07b;
                border-color: #00b07b;
            }
        """)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("background-color: #202024; color: #7c7c8a; border-color: #29292e;")
        
        self.video_viewport.setText("TRACKING OFFLINE\nClick 'Start Tracking' to begin camera feed.")
        self.lbl_gesture.setText("MOVE")
        self.lbl_fps.setText("0.0")
        if self.floating_preview:
            self.floating_preview.hide()

    def update_frame(self, frame: np.ndarray, gesture_state: str, fps: float):
        # Update Dashboard metrics
        self.lbl_gesture.setText(gesture_state.upper())
        self.lbl_fps.setText(f"{fps:.1f}")

        # Update HUD active styling on the dashboard
        if gesture_state in ["Left Click", "Right Click", "Double Click", "Scroll", "Dragging"]:
            self.lbl_gesture.setStyleSheet("color: #00f0ff;")
        else:
            self.lbl_gesture.setStyleSheet("color: #ffffff;")

        # Render video feed frame
        if self.preview_on and frame is not None:
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            # Convert frame back to RGB (Qt requirement)
            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image)
            
            if self.chk_minimize.isChecked():
                if not self.floating_preview:
                    self.floating_preview = FloatingPreviewWindow()
                if not self.floating_preview.isVisible():
                    self.floating_preview.show()
                self.floating_preview.update_frame(pixmap)
                self.video_viewport.setPixmap(QPixmap())
                self.video_viewport.setText("FEED MINIMIZED\nPreview visible in screen corner.")
            else:
                if self.floating_preview and self.floating_preview.isVisible():
                    self.floating_preview.hide()
                # Scaled rendering centered in viewport
                scaled_pixmap = pixmap.scaled(
                    self.video_viewport.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.video_viewport.setPixmap(scaled_pixmap)
        else:
            self.video_viewport.setPixmap(QPixmap())
            if not self.preview_on:
                self.video_viewport.setText("FEED ONLINE\nPreview is toggled off. Tracking remains active.")
            else:
                self.video_viewport.setText("TRACKING OFFLINE\nClick 'Start Tracking' to begin camera feed.")

    def on_sens_changed(self, value):
        self.sensitivity_val = value / 10.0
        self.lbl_sens_val.setText(f"{self.sensitivity_val:.1f}")
        if self.worker is not None:
            self.worker.sensitivity = self.sensitivity_val

    def on_smooth_changed(self, value):
        self.smoothing_val = value / 100.0
        self.lbl_smooth_val.setText(f"{self.smoothing_val:.2f}")
        if self.worker is not None:
            self.worker.smoothing = self.smoothing_val

    def on_preview_toggled(self, checked):
        self.preview_on = checked
        self.chk_minimize.setEnabled(checked)
        if self.worker is not None:
            self.worker.preview_enabled = self.preview_on
        if not self.preview_on:
            if self.floating_preview:
                self.floating_preview.hide()
            self.video_viewport.setPixmap(QPixmap())
            self.video_viewport.setText("FEED ONLINE\nPreview is toggled off. Tracking remains active.")
        else:
            if self.chk_minimize.isChecked():
                self.on_minimize_toggled(True)
            else:
                self.video_viewport.setText("FEED ONLINE\nLoading preview feed...")

    def on_minimize_toggled(self, checked):
        if checked and self.preview_on and self.worker is not None:
            if not self.floating_preview:
                self.floating_preview = FloatingPreviewWindow()
            self.floating_preview.show()
            self.video_viewport.setPixmap(QPixmap())
            self.video_viewport.setText("FEED MINIMIZED\nPreview visible in screen corner.")
        else:
            if self.floating_preview:
                self.floating_preview.hide()
            # Restore state text based on status
            if self.preview_on and self.worker is not None:
                self.video_viewport.setText("FEED ONLINE\nRestoring preview feed...")
            elif not self.preview_on:
                self.video_viewport.setText("FEED ONLINE\nPreview is toggled off. Tracking remains active.")
            else:
                self.video_viewport.setText("TRACKING OFFLINE\nClick 'Start Tracking' to begin camera feed.")

    def closeEvent(self, event):
        # Make sure worker is stopped and resources released on exit
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait()
        if self.floating_preview:
            self.floating_preview.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    # Modern clean font setting
    app.setFont(QFont("Segoe UI", 9))
    gui = TouchlessGUI()
    gui.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
