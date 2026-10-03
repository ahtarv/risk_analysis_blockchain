#pragma once

#include "order_book.hpp"
#include <numeric>
#include <cmath>
#include <stdexcept>

namespace metrics {

[[nodiscard]] inline double bid_ask_spread(const BookSnapshot& s) noexcept {
    return s.best_ask - s.best_bid;
}

[[nodiscard]] inline double bid_ask_spread_bps(const BookSnapshot& s) noexcept {
    const double mid = (s.best_bid + s.best_ask) * 0.5;
    if (mid <= 0.0) return 0.0;
    return (bid_ask_spread(s) / mid) * 10'000.0;
}

[[nodiscard]] inline double depth_imbalance(const BookSnapshot& s,
                                             std::size_t levels = 5) noexcept {
    double bid_vol = 0.0, ask_vol = 0.0;

    const std::size_t n_bids = std::min(levels, s.top_bids.size());
    for (std::size_t i = 0; i < n_bids; ++i)
        bid_vol += s.top_bids[i].second;

    const std::size_t n_asks = std::min(levels, s.top_asks.size());
    for (std::size_t i = 0; i < n_asks; ++i)
        ask_vol += s.top_asks[i].second;

    const double total = bid_vol + ask_vol;
    if (total <= 0.0) return 0.0;
    return (bid_vol - ask_vol) / total;
}

struct SlippageResult {
    double vwap         = 0.0;   
    double slippage_bps = 0.0;   
    double filled_usd   = 0.0;   
    bool   fully_filled = false;
};

[[nodiscard]] inline SlippageResult vwap_slippage(
    const BookSnapshot& s,
    double notional_usd = 50'000.0) noexcept
{
    SlippageResult result;
    if (s.top_asks.empty() || s.best_ask <= 0.0) return result;

    double remaining    = notional_usd;
    double total_base   = 0.0;
    double total_quote  = 0.0;

    for (const auto& [price, volume] : s.top_asks) {
        if (remaining <= 0.0) break;
        const double level_value = price * volume;          
        const double consume_usd = std::min(remaining, level_value);
        const double consume_base = consume_usd / price;    

        total_quote += consume_usd;
        total_base  += consume_base;
        remaining   -= consume_usd;
    }

    if (total_base <= 0.0) return result;

    result.filled_usd   = total_quote;
    result.fully_filled = (remaining <= 1e-9);
    result.vwap         = total_quote / total_base;
    result.slippage_bps = ((result.vwap - s.best_ask) / s.best_ask) * 10'000.0;
    return result;
}

[[nodiscard]] inline double mid_price(const BookSnapshot& s) noexcept {
    return (s.best_bid + s.best_ask) * 0.5;
}

[[nodiscard]] inline bool is_quoting(const BookSnapshot& s,
                                      double max_spread_bps = 100.0) noexcept {
    if (!s.best_bid || !s.best_ask) return false;
    return bid_ask_spread_bps(s) <= max_spread_bps;
}

struct TickMetrics {
    int64_t timestamp_us   = 0;
    double  spread         = 0.0;   
    double  spread_bps     = 0.0;
    double  mid_price      = 0.0;
    double  imbalance      = 0.0;   
    double  vwap_50k       = 0.0;   
    double  slippage_bps   = 0.0;   
    bool    fully_filled   = false;
    bool    is_quoting     = false;
};

[[nodiscard]] inline TickMetrics compute_all(const BookSnapshot& s,
                                              std::size_t imbalance_levels = 5,
                                              double      notional_usd     = 50'000.0) {
    TickMetrics m;
    m.timestamp_us  = s.timestamp_us;
    m.spread        = bid_ask_spread(s);
    m.spread_bps    = bid_ask_spread_bps(s);
    m.mid_price     = mid_price(s);
    m.imbalance     = depth_imbalance(s, imbalance_levels);

    auto slip       = vwap_slippage(s, notional_usd);
    m.vwap_50k      = slip.vwap;
    m.slippage_bps  = slip.slippage_bps;
    m.fully_filled  = slip.fully_filled;
    m.is_quoting    = is_quoting(s);
    return m;
}

} 
