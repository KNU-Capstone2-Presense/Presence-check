import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Settings:
    data_dir: Path
    threshold_ms: float | None
    samples: int = 10
    warmups: int = 2
    probe_timeout: float = 2.0
    interval: float = 0.1

def load_settings() -> Settings:
    import math
    raw = os.getenv('RTT_THRESHOLD_MS', '').strip()
    threshold = float(raw) if raw else None
    if threshold is not None and (not math.isfinite(threshold) or threshold <= 0):
        raise ValueError('RTT_THRESHOLD_MS must be a positive finite number')
    default = Path(__file__).resolve().parents[1] / 'data'
    return Settings(Path(os.getenv('ATTENDANCE_DATA_DIR', str(default))).resolve(), threshold)
