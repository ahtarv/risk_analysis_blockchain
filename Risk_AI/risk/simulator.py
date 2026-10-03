

from __future__ import annotations

import random
import time
import uuid
import math
from dataclasses import dataclass, asdict, field
from typing import List, Tuple

import pandas as pd

@dataclass
class SimOrderEvent:
    order_id:      str
    symbol:        str
    is_bid:        bool
    price:         float
    quantity:      float
    submit_us:     int         
    cancel_us:     int = 0     
    filled:        bool = False
    depth_level:   int  = -1
    label:         str  = "normal"   
    lifetime_us:   int  = 0

class MarketSimulator:

    def __init__(
        self,
        symbol:       str   = "BTCUSDT",
        mid_price:    float = 65_000.0,
        tick_size:    float = 0.01,
        seed:         int   = 42,
    ):
        self.symbol     = symbol
        self.mid        = mid_price
        self.tick_size  = tick_size
        random.seed(seed)
        self._t_us      = int(time.time() * 1_000_000)

    def _next_ts(self, delta_us: int = 1_000) -> int:

        self._t_us += delta_us + random.randint(0, 500)
        return self._t_us

    def _gbm_step(self) -> None:

        self.mid *= math.exp(random.gauss(0, 0.0002))

    def _spread_half(self) -> float:
        return round(random.uniform(0.5, 3.0) * self.tick_size, 8)

    def _depth_levels(self) -> List[Tuple[float, float]]:

        half = self._spread_half()
        levels = []
        for i in range(5):
            p = round(self.mid + half + i * self.tick_size * 10, 2)
            q = round(random.uniform(0.05, 2.0), 4)
            levels.append((p, q))
        return levels

    def _normal_order(self) -> SimOrderEvent:
        self._gbm_step()
        is_bid  = random.random() < 0.5
        half    = self._spread_half()
        level   = random.randint(0, 4)
        price   = round(self.mid + (-half if is_bid else half) + level * self.tick_size * 10, 2)
        qty     = round(random.uniform(0.01, 1.5), 4)
        submit  = self._next_ts(random.randint(1_000, 10_000))
        filled  = random.random() < 0.45   
        cancel_us = 0
        lifetime  = 0
        if not filled:
            lifetime  = random.randint(500_000, 30_000_000)  
            cancel_us = submit + lifetime
        return SimOrderEvent(
            order_id    = str(uuid.uuid4())[:12],
            symbol      = self.symbol,
            is_bid      = is_bid,
            price       = price,
            quantity    = qty,
            submit_us   = submit,
            cancel_us   = cancel_us,
            filled      = filled,
            depth_level = level,
            label       = "normal",
            lifetime_us = lifetime,
        )

    def _spoof_order(self) -> SimOrderEvent:

        is_bid  = random.random() < 0.5
        half    = self._spread_half()
        level   = random.randint(0, 2)           
        price   = round(self.mid + (-half if is_bid else half) + level * self.tick_size * 5, 2)
        qty     = round(random.uniform(2.0, 10.0), 4)  
        submit  = self._next_ts(random.randint(500, 2_000))
        lifetime = random.randint(5_000, 195_000)       
        return SimOrderEvent(
            order_id    = str(uuid.uuid4())[:12],
            symbol      = self.symbol,
            is_bid      = is_bid,
            price       = price,
            quantity    = qty,
            submit_us   = submit,
            cancel_us   = submit + lifetime,
            filled      = False,
            depth_level = level,
            label       = "spoof",
            lifetime_us = lifetime,
        )

    def _stuffing_burst(self, burst_size: int = 20) -> List[SimOrderEvent]:

        events = []
        base_t = self._next_ts(100)
        for i in range(burst_size):
            is_bid  = random.random() < 0.5
            half    = self._spread_half()
            level   = random.randint(0, 4)
            price   = round(self.mid + (-half if is_bid else half) + level * self.tick_size * 10, 2)
            qty     = round(random.uniform(0.1, 0.5), 4)
            submit  = base_t + i * random.randint(100, 800)   
            lifetime = random.randint(10_000, 80_000)          
            events.append(SimOrderEvent(
                order_id    = str(uuid.uuid4())[:12],
                symbol      = self.symbol,
                is_bid      = is_bid,
                price       = price,
                quantity    = qty,
                submit_us   = submit,
                cancel_us   = submit + lifetime,
                filled      = False,
                depth_level = level,
                label       = "stuffing",
                lifetime_us = lifetime,
            ))
        self._t_us = events[-1].cancel_us + 1_000
        return events

    def _layering_episode(self, layers: int = 6) -> List[SimOrderEvent]:

        is_bid   = random.random() < 0.5
        half     = self._spread_half()
        events   = []
        for lvl in range(layers):
            price  = round(self.mid + (-half if is_bid else half) + lvl * self.tick_size * 5, 2)
            qty    = round(random.uniform(1.0, 5.0), 4)
            submit = self._next_ts(random.randint(200, 1_000))
            lifetime = random.randint(10_000, 180_000)
            events.append(SimOrderEvent(
                order_id    = str(uuid.uuid4())[:12],
                symbol      = self.symbol,
                is_bid      = is_bid,
                price       = price,
                quantity    = qty,
                submit_us   = submit,
                cancel_us   = submit + lifetime,
                filled      = False,
                depth_level = lvl,
                label       = "layering",
                lifetime_us = lifetime,
            ))
        return events

    def generate(
        self,
        n_events:      int   = 50_000,
        anomaly_rate:  float = 0.05,   
    ) -> pd.DataFrame:

        events: List[SimOrderEvent] = []
        target_anomaly = int(n_events * anomaly_rate)
        anomaly_count  = 0

        while len(events) < n_events:
            remaining  = n_events - len(events)
            inject     = (anomaly_count < target_anomaly) and (random.random() < anomaly_rate * 3)

            if inject:
                kind = random.choice(["spoof", "stuffing", "layering"])
                if kind == "spoof":
                    new_evts = [self._spoof_order()]
                elif kind == "stuffing":
                    burst = min(random.randint(10, 25), remaining)
                    new_evts = self._stuffing_burst(burst)
                else:
                    layers = min(random.randint(4, 8), remaining)
                    new_evts = self._layering_episode(layers)
                anomaly_count += len(new_evts)
            else:
                new_evts = [self._normal_order()]

            events.extend(new_evts)

        events = events[:n_events]

        rows = [asdict(e) for e in events]
        df = pd.DataFrame(rows)
        df.sort_values("submit_us", inplace=True)
        df.reset_index(drop=True, inplace=True)

        df["lifetime_ms"] = df["lifetime_us"] / 1_000.0
        df["is_anomaly"]  = df["label"].isin(["spoof", "stuffing", "layering"])

        return df

def generate_event_log(
    n_events:     int   = 50_000,
    anomaly_rate: float = 0.05,
    symbol:       str   = "BTCUSDT",
    seed:         int   = 42,
) -> pd.DataFrame:

    sim = MarketSimulator(symbol=symbol, seed=seed)
    return sim.generate(n_events=n_events, anomaly_rate=anomaly_rate)
