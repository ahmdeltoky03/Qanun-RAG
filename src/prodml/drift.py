"""Embedding drift: has the *kind* of question users ask moved away from what we evaluated on?"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return 1.0 - float(a @ b / denom) if denom else 1.0


def centroid(vectors: np.ndarray) -> np.ndarray:
    return np.asarray(vectors, dtype=np.float64).mean(axis=0)


def save_baseline(vectors: np.ndarray, path: Path, model_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": model_name, "n": len(vectors), "centroid": centroid(vectors).tolist()}))


class DriftMonitor:
    """Rolling centroid of recent query embeddings vs. the baseline (eval-set) centroid."""

    MIN_SAMPLES = 20

    def __init__(self, baseline_path: Path, window: int = 200, model_name: str = ""):
        self.window: deque[np.ndarray] = deque(maxlen=window)
        self.baseline: np.ndarray | None = None
        try:
            data = json.loads(baseline_path.read_text())
            if not model_name or data.get("model") == model_name:
                self.baseline = np.asarray(data["centroid"])
        except (OSError, ValueError, KeyError):
            pass

    def observe(self, vector: list[float] | np.ndarray) -> float | None:
        self.window.append(np.asarray(vector, dtype=np.float64))
        return self.current()

    def current(self) -> float | None:
        if self.baseline is None or len(self.window) < self.MIN_SAMPLES:
            return None
        return cosine_distance(centroid(np.stack(self.window)), self.baseline)
