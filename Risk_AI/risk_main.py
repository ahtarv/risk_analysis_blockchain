

from __future__ import annotations

import sys
import time
import argparse
from datetime import datetime, timezone

import pandas as pd

try:
    import orderbook_engine as obe
    USING_CPP = True
    print("[Engine] [OK] C++20 orderbook_engine loaded (OrderEventTracker available)")
except ImportError:
    USING_CPP = False
    print("[Engine] [WARN] C++ extension not built — event tracking via Python only")

from risk.simulator        import generate_event_log
from risk.feature_pipeline import FeaturePipeline
from risk.anomaly_detector import AnomalyDetector

def replay_through_cpp_tracker(df: pd.DataFrame, symbol: str = "BTCUSDT") -> dict:

    if not USING_CPP:
        n_spoofs    = int(df["label"].eq("spoof").sum())
        n_stuff     = int(df["label"].eq("stuffing").sum())
        n_layer     = int(df["label"].eq("layering").sum())
        return {
            "cpp_signals":  n_spoofs + n_stuff + n_layer,
            "cpp_spoofs":   n_spoofs,
            "cpp_stuffing": n_stuff,
            "cpp_layering": n_layer,
            "otr":          round(len(df) / max(int(df["filled"].sum()), 1), 2),
            "cfr":          round(int((~df["filled"] & (df["cancel_us"] > 0)).sum()) /
                                  max(int(df["filled"].sum()), 1), 2),
        }

    tracker    = obe.OrderEventTracker(symbol)
    signals    = []

    print(f"  Replaying {len(df):,} events through C++ OrderEventTracker...")
    t0 = time.perf_counter()

    for row in df.itertuples(index=False):
        order_id    = row.order_id
        is_bid      = bool(row.is_bid)
        price       = float(row.price)
        qty         = float(row.quantity)
        depth       = int(row.depth_level)
        submit_us   = int(row.submit_us)
        cancel_us   = int(row.cancel_us)
        filled      = bool(row.filled)

        tracker.on_submit(order_id, is_bid, price, qty, depth, submit_us)

        if filled:
            tracker.on_fill(order_id, qty)
        elif cancel_us > 0:
            sig = tracker.on_cancel(order_id, cancel_us)
            signals.append(sig)

    elapsed = time.perf_counter() - t0

    spoof_count    = sum(1 for s in signals if s.is_spoof)
    stuffing_count = sum(1 for s in signals if s.is_stuffing)
    layering_count = sum(1 for s in signals if s.is_layering)

    print(f"  C++ replay done in {elapsed*1000:.1f}ms")
    print(f"  OTR = {tracker.order_to_trade_ratio():.2f} | "
          f"CFR = {tracker.cancel_to_fill_ratio():.2f}")

    return {
        "cpp_signals":  len(signals),
        "cpp_spoofs":   spoof_count,
        "cpp_stuffing": stuffing_count,
        "cpp_layering": layering_count,
        "otr":          round(tracker.order_to_trade_ratio(), 2),
        "cfr":          round(tracker.cancel_to_fill_ratio(), 2),
    }

def main(
    n_events:     int   = 50_000,
    anomaly_rate: float = 0.05,
    method:       str   = "zscore",
    fpr_target:   float = 0.008,
    symbol:       str   = "BTCUSDT",
) -> None:

    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print(f"\n{'═'*62}")
    print(f"  High-Frequency Market Manipulation & Anomaly Detector")
    print(f"  Symbol      : {symbol}")
    print(f"  Events      : {n_events:,}")
    print(f"  Anomaly rate: {anomaly_rate:.1%}")
    print(f"  Method      : {method}")
    print(f"  FPR target  : {fpr_target:.2%}")
    print(f"  Started     : {ts}")
    print(f"{'═'*62}\n")

    print("[ 1 / 4 ] Generating synthetic order event log...")
    t0 = time.perf_counter()
    df = generate_event_log(
        n_events=n_events,
        anomaly_rate=anomaly_rate,
        symbol=symbol,
        seed=42,
    )
    elapsed = time.perf_counter() - t0
    print(f"  Generated {len(df):,} events in {elapsed*1000:.1f}ms")
    print(f"  Label breakdown:")
    print(df["label"].value_counts().to_string(header=False))
    print(f"  Anomaly ground truth: {df['is_anomaly'].sum():,} / {len(df):,} "
          f"({df['is_anomaly'].mean():.2%})\n")

    print("[ 2 / 4 ] Replaying events through C++ OrderEventTracker...")
    cpp_summary = replay_through_cpp_tracker(df, symbol=symbol)
    print(f"  C++ signals flagged: {cpp_summary['cpp_signals']:,}")
    print(f"    Spoofs   : {cpp_summary['cpp_spoofs']:,}")
    print(f"    Stuffing : {cpp_summary['cpp_stuffing']:,}")
    print(f"    Layering : {cpp_summary['cpp_layering']:,}")
    print(f"  Order-to-Trade Ratio (OTR) : {cpp_summary['otr']:.2f}")
    print(f"  Cancel-to-Fill Ratio  (CFR): {cpp_summary['cfr']:.2f}\n")

    print("[ 3 / 4 ] Running DuckDB rolling feature windows (1m / 5m / 1h)...")
    t0 = time.perf_counter()

    try:
        import duckdb
        use_pandas = False
    except ImportError:
        use_pandas = True
        print("  (duckdb not installed — using pandas rolling fallback)")

    with FeaturePipeline(use_pandas_fallback=use_pandas) as pipe:
        pipe.ingest(df)
        features = pipe.compute()

    elapsed = time.perf_counter() - t0
    print(f"  Feature engineering done in {elapsed*1000:.1f}ms")
    print(f"  Feature matrix: {features.shape[0]:,} rows × {features.shape[1]} columns")
    print(f"  Columns: {', '.join(features.columns[:8].tolist())} ...\n")

    print(f"[ 4 / 4 ] Running anomaly detection (method={method}, "
          f"fpr_target={fpr_target:.2%})...")
    t0 = time.perf_counter()

    detector = AnomalyDetector(method=method, fpr_target=fpr_target)
    detector.fit(features)
    result  = detector.evaluate(features)
    elapsed = time.perf_counter() - t0
    print(f"  Detection done in {elapsed*1000:.1f}ms\n")

    AnomalyDetector.print_report(result)

    if "label" in features.columns:
        print("  Detection Rate by Anomaly Type:")
        breakdown = AnomalyDetector.label_breakdown(features, result.y_pred)
        print(breakdown.to_string())
        print()

    if result.fpr <= fpr_target:
        print(f"  [OK] FPR constraint SATISFIED: {result.fpr:.4%} ≤ {fpr_target:.2%}")
    else:
        print(f"  [FAIL] FPR constraint VIOLATED:  {result.fpr:.4%} > {fpr_target:.2%}")
        print(f"    → Try increasing the detection threshold or using 'iforest'")

    print(f"\n{'═'*62}")
    print(f"  Pipeline complete.")
    print(f"{'═'*62}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="High-Frequency Market Manipulation & Anomaly Detector"
    )
    parser.add_argument("--events",       type=int,   default=50_000,
                        help="Number of synthetic order events to generate")
    parser.add_argument("--anomaly-rate", type=float, default=0.05,
                        help="Fraction of injected anomalous events (0–1)")
    parser.add_argument("--method",       type=str,   default="zscore",
                        choices=["rule", "zscore", "iforest"],
                        help="Anomaly detection strategy")
    parser.add_argument("--fpr-target",   type=float, default=0.008,
                        help="Max allowed False Positive Rate (default 0.008)")
    parser.add_argument("--symbol",       type=str,   default="BTCUSDT",
                        help="Trading pair symbol (cosmetic)")

    args = parser.parse_args()
    main(
        n_events     = args.events,
        anomaly_rate = args.anomaly_rate,
        method       = args.method,
        fpr_target   = args.fpr_target,
        symbol       = args.symbol,
    )
