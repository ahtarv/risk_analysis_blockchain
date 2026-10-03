

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional, Tuple

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

@dataclass
class DetectionResult:

    y_true:       np.ndarray
    y_pred:       np.ndarray
    y_score:      np.ndarray      

    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    precision:    float = 0.0
    recall:       float = 0.0
    f1:           float = 0.0
    fpr:          float = 0.0     
    accuracy:     float = 0.0

    threshold:    float = 0.0
    method:       str   = "rule"

    def __post_init__(self):

        self.tp = int(np.sum((self.y_pred == 1) & (self.y_true == 1)))
        self.fp = int(np.sum((self.y_pred == 1) & (self.y_true == 0)))
        self.tn = int(np.sum((self.y_pred == 0) & (self.y_true == 0)))
        self.fn = int(np.sum((self.y_pred == 0) & (self.y_true == 1)))

        total   = self.tp + self.fp + self.tn + self.fn
        self.accuracy  = (self.tp + self.tn) / max(total, 1)
        self.precision = self.tp / max(self.tp + self.fp, 1)
        self.recall    = self.tp / max(self.tp + self.fn, 1)
        self.f1        = (2 * self.precision * self.recall /
                          max(self.precision + self.recall, 1e-9))
        self.fpr       = self.fp / max(self.fp + self.tn, 1)

_FEATURE_COLS = [
    "otr_1m",
    "cfr_1m",
    "spoof_ratio_1m",
    "top3_cancels_1m",
    "lifetime_zscore",
    "otr_5m",
    "cfr_5m",
]

_FEATURE_COLS_PANDAS = [
    "otr_1m",
    "cfr_1m",
    "spoof_ratio_1m",
    "lifetime_zscore",
    "otr_5m",
    "cfr_5m",
]

def _available_feature_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in _FEATURE_COLS if c in df.columns] or \
           [c for c in _FEATURE_COLS_PANDAS if c in df.columns]

def _rule_score(df: pd.DataFrame) -> np.ndarray:

    score = np.zeros(len(df), dtype=float)

    if "otr_1m" in df.columns:
        score += np.where(df["otr_1m"].fillna(0) > 10,   0.30, 0.0)
    if "cfr_1m" in df.columns:
        score += np.where(df["cfr_1m"].fillna(0) > 5,    0.25, 0.0)
    if "spoof_ratio_1m" in df.columns:
        score += np.where(df["spoof_ratio_1m"].fillna(0) > 0.30, 0.25, 0.0)
    if "lifetime_zscore" in df.columns:
        score += np.where(df["lifetime_zscore"].fillna(0) > 2.0,  0.20, 0.0)

    return np.clip(score, 0.0, 1.0)

def _zscore_ensemble_score(df: pd.DataFrame) -> np.ndarray:

    cols = _available_feature_cols(df)
    if not cols:
        return np.zeros(len(df))

    X = df[cols].fillna(0).values.astype(float)
    mu  = X.mean(axis=0)
    sig = X.std(axis=0)
    sig = np.where(sig < 1e-9, 1.0, sig)

    z = (X - mu) / sig
    z = np.clip(z, 0.0, None)   
    score = z.mean(axis=1)

    s_max = score.max()
    if s_max > 0:
        score = score / s_max
    return score

def _isolation_forest_score(
    df: pd.DataFrame,
    contamination: float = 0.05,
) -> np.ndarray:

    if not SKLEARN_AVAILABLE:
        print("[AnomalyDetector] scikit-learn not installed. "
              "Falling back to z-score ensemble.")
        return _zscore_ensemble_score(df)

    cols = _available_feature_cols(df)
    if not cols:
        return np.zeros(len(df))

    X = df[cols].fillna(0).values.astype(float)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_scaled)

    raw_score = -model.decision_function(X_scaled)

    s_min, s_max = raw_score.min(), raw_score.max()
    if s_max > s_min:
        return (raw_score - s_min) / (s_max - s_min)
    return np.zeros(len(df))

def _optimise_threshold(
    y_true:     np.ndarray,
    y_score:    np.ndarray,
    fpr_target: float = 0.008,
    n_steps:    int   = 200,
) -> Tuple[float, float]:

    thresholds = np.linspace(0.0, 1.0, n_steps)
    best_thresh  = 1.0
    best_recall  = 0.0

    for t in thresholds:
        pred = (y_score >= t).astype(int)
        tp = np.sum((pred == 1) & (y_true == 1))
        fp = np.sum((pred == 1) & (y_true == 0))
        tn = np.sum((pred == 0) & (y_true == 0))
        fn = np.sum((pred == 0) & (y_true == 1))

        fpr = fp / max(fp + tn, 1)
        if fpr <= fpr_target:
            recall = tp / max(tp + fn, 1)
            if recall > best_recall:
                best_recall = recall
                best_thresh = t

    return best_thresh, best_recall

class AnomalyDetector:

    METHODS = ("rule", "zscore", "iforest")

    def __init__(
        self,
        method:     str   = "zscore",
        fpr_target: float = 0.008,
    ):
        if method not in self.METHODS:
            raise ValueError(f"method must be one of {self.METHODS}")
        self.method     = method
        self.fpr_target = fpr_target
        self._threshold: Optional[float] = None

    def _score(self, df: pd.DataFrame) -> np.ndarray:
        if self.method == "rule":
            return _rule_score(df)
        elif self.method == "zscore":
            return _zscore_ensemble_score(df)
        else:
            return _isolation_forest_score(df)

    def fit(self, df: pd.DataFrame) -> "AnomalyDetector":

        if "is_anomaly" not in df.columns:
            raise ValueError("DataFrame must have 'is_anomaly' boolean column.")

        y_true  = df["is_anomaly"].astype(int).values
        y_score = self._score(df)

        threshold, recall = _optimise_threshold(y_true, y_score, self.fpr_target)
        self._threshold = threshold

        print(f"[AnomalyDetector] Calibrated: method={self.method}, "
              f"threshold={threshold:.4f}, "
              f"recall={recall:.2%}, "
              f"fpr_target={self.fpr_target:.2%}")
        return self

    def predict(self, df: pd.DataFrame) -> np.ndarray:

        if self._threshold is None:
            raise RuntimeError("Call fit() before predict().")
        score = self._score(df)
        return (score >= self._threshold).astype(int)

    def score(self, df: pd.DataFrame) -> np.ndarray:

        return self._score(df)

    def evaluate(self, df: pd.DataFrame) -> DetectionResult:

        if "is_anomaly" not in df.columns:
            raise ValueError("DataFrame must have 'is_anomaly' boolean column.")
        if self._threshold is None:
            self.fit(df)

        y_true  = df["is_anomaly"].astype(int).values
        y_score = self._score(df)
        y_pred  = (y_score >= self._threshold).astype(int)

        result = DetectionResult(
            y_true    = y_true,
            y_pred    = y_pred,
            y_score   = y_score,
            threshold = self._threshold,
            method    = self.method,
        )
        return result

    @staticmethod
    def print_report(result: DetectionResult) -> None:

        print()
        print("╔══════════════════════════════════════════════════════════╗")
        print("║  Anomaly Detector — Evaluation Report                    ║")
        print("╠══════════════════════════════════════════════════════════╣")
        print(f"║  Method      : {result.method:<42}║")
        print(f"║  Threshold   : {result.threshold:<42.4f}║")
        print("╠═══════════════════════════╦══════════════════════════════╣")
        print("║  Confusion Matrix         ║  Performance Metrics         ║")
        print("╠═══════════════════════════╬══════════════════════════════╣")
        print(f"║  TP : {result.tp:>8}           ║  Precision : {result.precision:>8.2%}         ║")
        print(f"║  FP : {result.fp:>8}           ║  Recall    : {result.recall:>8.2%}         ║")
        print(f"║  TN : {result.tn:>8}           ║  F1-Score  : {result.f1:>8.2%}         ║")
        print(f"║  FN : {result.fn:>8}           ║  Accuracy  : {result.accuracy:>8.2%}         ║")
        print("╠═══════════════════════════╩══════════════════════════════╣")

        fpr_color = "✓" if result.fpr <= 0.008 else "✗"
        print(f"║  FPR : {result.fpr:>8.4%}  {fpr_color} (target ≤ 0.8%)              ║")
        print("╚══════════════════════════════════════════════════════════╝")
        print()

    @staticmethod
    def label_breakdown(df: pd.DataFrame, y_pred: np.ndarray) -> pd.DataFrame:

        if "label" not in df.columns:
            raise ValueError("DataFrame must have 'label' column.")

        df = df.copy()
        df["predicted"] = y_pred
        summary = (
            df.groupby("label")
              .agg(
                  total      = ("predicted", "count"),
                  detected   = ("predicted", "sum"),
              )
              .assign(detection_rate=lambda x: x["detected"] / x["total"])
        )
        return summary
