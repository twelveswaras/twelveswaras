"""Model: architecture + load/save (PRD §17).

Framework is PyTorch (D15). The v0 floor (D16 step 1) is an XGBoost classifier over
the fixed-length frame vector — cheap, strong, trains in minutes on CPU. The CNN /
TDMS / transformer rungs come later; `RaagaCNN` is a stub marking that seam.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .config import MODELS_DIR, TOP_K


@dataclass
class Prediction:
    raaga: str
    confidence: float


class RaagaXGB:
    """XGBoost floor over frame vectors. Wraps label<->index + top-k decode."""

    def __init__(self, classes: list[str], booster=None):
        self.classes = list(classes)
        self._booster = booster

    def fit(self, X: np.ndarray, y_idx: np.ndarray, **kwargs):
        from xgboost import XGBClassifier

        self._booster = XGBClassifier(
            objective="multi:softprob",
            num_class=len(self.classes),
            n_estimators=kwargs.pop("n_estimators", 400),
            max_depth=kwargs.pop("max_depth", 6),
            learning_rate=kwargs.pop("learning_rate", 0.1),
            n_jobs=-1,
            **kwargs,
        )
        self._booster.fit(X, y_idx)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if self._booster is None:
            raise RuntimeError("model is not trained/loaded")
        return self._booster.predict_proba(X)

    def top_k(self, x: np.ndarray, k: int = TOP_K) -> list[Prediction]:
        """Top-k raagas + confidence for one frame vector (D6: always top-3)."""
        proba = self.predict_proba(x.reshape(1, -1))[0]
        order = np.argsort(proba)[::-1][:k]
        return [Prediction(self.classes[i], float(proba[i])) for i in order]

    def save(self, path: str | Path | None = None) -> Path:
        path = Path(path) if path else MODELS_DIR / "raaga_xgb.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._booster.save_model(str(path))
        path.with_suffix(".classes.json").write_text(json.dumps(self.classes))
        return path

    @classmethod
    def load(cls, path: str | Path) -> "RaagaXGB":
        from xgboost import XGBClassifier

        path = Path(path)
        booster = XGBClassifier()
        booster.load_model(str(path))
        classes = json.loads(path.with_suffix(".classes.json").read_text())
        return cls(classes, booster)


class RaagaCNN:
    """PHASE 2 SEAM (D16). CNN on tonic-normalized mel/CQT, in torch/Lightning.
    Benchmark target: compIAM `DEEPSRGM`."""

    def __init__(self, *_, **__):
        raise NotImplementedError("CNN rung — implement after the XGBoost floor lands")
