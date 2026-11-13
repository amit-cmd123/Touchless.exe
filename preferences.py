"""Typed, validated user preferences and cursor calibration for Touchless."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import os


def preferences_path() -> Path:
    """Return the per-user settings path, outside the application source tree."""
    base = Path(os.environ.get("APPDATA", Path.home()))
    return base / "Touchless" / "preferences.json"


@dataclass
class Calibration:
    """Camera-frame hand movement bounds used to normalize cursor input."""

    min_x: float = 0.0
    max_x: float = 640.0
    min_y: float = 0.0
    max_y: float = 480.0

    def is_valid(self) -> bool:
        values = (self.min_x, self.max_x, self.min_y, self.max_y)
        return (all(math.isfinite(v) for v in values)
                and 0 <= self.min_x < self.max_x <= 640
                and 0 <= self.min_y < self.max_y <= 480
                and self.min_x < self.max_x and self.min_y < self.max_y)

    def normalize(
        self,
        x: float,
        y: float,
        frame_width: int = 640,
        frame_height: int = 480,
    ) -> tuple[float, float]:
        if not self.is_valid():
            return x, y
        nx = min(1.0, max(0.0, (x - self.min_x) / (self.max_x - self.min_x)))
        ny = min(1.0, max(0.0, (y - self.min_y) / (self.max_y - self.min_y)))
        return nx * frame_width, ny * frame_height


@dataclass
class Preferences:
    sensitivity: float = 8.5
    smoothing: float = 0.55
    scroll_sensitivity: float = 3.0
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    calibration: Calibration | None = None

    def __post_init__(self):
        if self.calibration is None:
            self.calibration = Calibration()


def _valid_preferences(data: dict) -> Preferences:
    defaults = Preferences()
    def number(key, default, low, high):
        value = data.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        value = float(value)
        return value if math.isfinite(value) and low <= value <= high else default

    raw_cal = data.get("calibration")
    calibration = defaults.calibration
    if isinstance(raw_cal, dict):
        try:
            candidate = Calibration(*(float(raw_cal[k]) for k in ("min_x", "max_x", "min_y", "max_y")))
            if candidate.is_valid():
                calibration = candidate
        except (KeyError, TypeError, ValueError):
            pass
    return Preferences(
        sensitivity=number("sensitivity", defaults.sensitivity, 1.0, 15.0),
        smoothing=number("smoothing", defaults.smoothing, 0.05, 0.95),
        scroll_sensitivity=number("scroll_sensitivity", defaults.scroll_sensitivity, 0.1, 10.0),
        camera_index=int(data.get("camera_index", defaults.camera_index)) if isinstance(data.get("camera_index", 0), int) else defaults.camera_index,
        frame_width=int(data.get("frame_width", defaults.frame_width)) if isinstance(data.get("frame_width", 640), int) else defaults.frame_width,
        frame_height=int(data.get("frame_height", defaults.frame_height)) if isinstance(data.get("frame_height", 480), int) else defaults.frame_height,
        calibration=calibration,
    )


def load_preferences(path: Path | None = None) -> Preferences:
    try:
        data = json.loads((path or preferences_path()).read_text(encoding="utf-8"))
        return _valid_preferences(data) if isinstance(data, dict) else Preferences()
    except (OSError, ValueError, TypeError):
        return Preferences()


def save_preferences(preferences: Preferences, path: Path | None = None) -> None:
    target = path or preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(preferences), indent=2), encoding="utf-8")
