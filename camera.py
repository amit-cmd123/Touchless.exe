import cv2
import threading
import time
import sys

class Camera:
    """Encapsulates webcam initialization, threaded frame capture, and cleanup.

    Attributes:
        device_index (int): Index of the webcam device (default 0).
        width (int): Desired capture width.
        height (int): Desired capture height.
        cap (cv2.VideoCapture): OpenCV video capture object.
    """
    def __init__(self, device_index: int = 0, width: int = 640, height: int = 480, target_fps: int = 60):
        self.device_index = device_index
        self.width = width
        self.height = height
        if sys.platform == "win32":
            self.cap = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(self.device_index)
        if not self.cap.isOpened():
            self.cap.release()
            raise RuntimeError("Unable to open webcam (device index {0}).".format(self.device_index))
        
        # Configure MJPG format to enable higher frame rates
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, target_fps)

        # Thread variables
        self.ret = False
        self.frame = None
        self.running = True
        self.lock = threading.Lock()
        self.frame_ready = threading.Event()
        
        # Synchronously read the first frame to guarantee webcam operational readiness
        self.ret, self.frame = self.cap.read()
        
        # Start daemon reading thread
        self.thread = threading.Thread(target=self._update, args=(), daemon=True)
        self.thread.start()

    def _update(self) -> None:
        """Background thread task to continuously pull frames from the webcam."""
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.ret = ret
                    self.frame = frame
                self.frame_ready.set()
            else:
                time.sleep(0.01)

    def read(self) -> tuple[bool, any]:
        """Return the latest retrieved frame in a thread-safe manner.

        Returns:
            tuple: (ret, frame) where ret is a bool indicating success.
        """
        # Wait up to 100ms for a new frame from the background thread
        # to synchronize the processing loop with the camera's capture rate.
        self.frame_ready.wait(timeout=0.1)
        self.frame_ready.clear()
        
        with self.lock:
            # Return a copy to prevent concurrent write/read conflicts when editing the frame
            if self.frame is not None:
                return self.ret, self.frame.copy()
            return self.ret, None

    def release(self) -> None:
        """Safely terminate the background thread and release OpenCV resources."""
        self.running = False
        if hasattr(self, 'thread') and self.thread.is_alive():
            self.thread.join(timeout=1.0)
            
        if self.cap.isOpened():
            self.cap.release()
        cv2.destroyAllWindows()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
