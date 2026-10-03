#pragma once

#include <unordered_map>
#include <vector>
#include <string>
#include <chrono>
#include <cstdint>
#include <algorithm>
#include <numeric>
#include <cmath>

struct OrderEvent {
    std::string order_id;
    bool        is_bid;         
    double      price;
    double      quantity;
    int64_t     submit_us;      
    int64_t     cancel_us = 0;  
    bool        filled   = false;
    int         depth_level = -1; 
};

struct RiskSignal {
    int64_t     timestamp_us   = 0;
    std::string order_id;

    bool        is_spoof       = false;

    bool        is_stuffing    = false;

    bool        is_layering    = false;

    int64_t     lifetime_us    = 0;     
    int         depth_level    = -1;
    double      price          = 0.0;
    double      quantity       = 0.0;
    bool        filled         = false;
};

struct RollingStats {
    static constexpr std::size_t WINDOW = 60; 

    std::vector<double> values;
    std::size_t         head = 0;
    bool                full = false;

    explicit RollingStats() { values.resize(WINDOW, 0.0); }

    void push(double v) {
        values[head] = v;
        head = (head + 1) % WINDOW;
        if (head == 0) full = true;
    }

    [[nodiscard]] double mean() const {
        std::size_t n = full ? WINDOW : head;
        if (n == 0) return 0.0;
        double s = 0.0;
        for (std::size_t i = 0; i < n; ++i) s += values[i];
        return s / static_cast<double>(n);
    }

    [[nodiscard]] double stddev() const {
        std::size_t n = full ? WINDOW : head;
        if (n < 2) return 0.0;
        double m = mean();
        double sq = 0.0;
        for (std::size_t i = 0; i < n; ++i)
            sq += (values[i] - m) * (values[i] - m);
        return std::sqrt(sq / static_cast<double>(n - 1));
    }

    [[nodiscard]] double z_score(double v) const {
        double sd = stddev();
        if (sd < 1e-12) return 0.0;
        return (v - mean()) / sd;
    }
};

class OrderEventTracker {
public:

    static constexpr int64_t SPOOF_MAX_LIFETIME_US  = 200'000; 
    static constexpr int     SPOOF_MAX_DEPTH_LEVEL  = 2;       
    static constexpr double  STUFFING_Z_THRESHOLD   = 3.0;     
    static constexpr int     LAYERING_MIN_LEVELS    = 4;       

    explicit OrderEventTracker(std::string symbol)
        : symbol_(std::move(symbol)) {}

    void on_submit(const std::string& order_id,
                   bool is_bid, double price, double qty,
                   int depth_level,
                   int64_t submit_us = 0) {
        if (submit_us == 0) submit_us = now_us();
        active_[order_id] = OrderEvent{
            order_id, is_bid, price, qty,
            submit_us, 0, false, depth_level
        };
        submit_count_++;
        submit_count_per_window_++;
    }

    void on_fill(const std::string& order_id, double ) {
        auto it = active_.find(order_id);
        if (it != active_.end()) {
            it->second.filled = true;
        }
        fill_count_++;
    }

    [[nodiscard]] RiskSignal on_cancel(const std::string& order_id,
                                       int64_t cancel_us = 0) {
        if (cancel_us == 0) cancel_us = now_us();
        RiskSignal sig;
        sig.timestamp_us = cancel_us;
        sig.order_id     = order_id;
        cancel_count_++;

        auto it = active_.find(order_id);
        if (it == active_.end()) return sig; 

        OrderEvent& ev   = it->second;
        ev.cancel_us     = cancel_us;
        sig.lifetime_us  = cancel_us - ev.submit_us;
        sig.depth_level  = ev.depth_level;
        sig.price        = ev.price;
        sig.quantity     = ev.quantity;
        sig.filled       = ev.filled;

        sig.is_spoof = (!ev.filled)
                    && (ev.depth_level >= 0 && ev.depth_level <= SPOOF_MAX_DEPTH_LEVEL)
                    && (sig.lifetime_us <= SPOOF_MAX_LIFETIME_US);

        recent_cancel_vol_stats_.push(static_cast<double>(submit_count_per_window_));
        submit_count_per_window_ = 0;

        double z = recent_cancel_vol_stats_.z_score(
            static_cast<double>(cancel_count_));
        sig.is_stuffing = (z >= STUFFING_Z_THRESHOLD) && (fill_count_ == 0);

        int same_side = 0;
        for (const auto& [id, o] : active_) {
            if (o.is_bid == ev.is_bid && !o.filled)
                same_side++;
        }
        sig.is_layering = (same_side >= LAYERING_MIN_LEVELS) && sig.is_spoof;

        completed_.push_back(ev);
        active_.erase(it);

        if ((submit_count_ + cancel_count_) % 100 == 0) {
            fill_count_    = 0;
            cancel_count_  = 0;
        }

        return sig;
    }

    [[nodiscard]] double order_to_trade_ratio() const {
        if (fill_count_ == 0) return static_cast<double>(submit_count_);
        return static_cast<double>(submit_count_) / static_cast<double>(fill_count_);
    }

    [[nodiscard]] double cancel_to_fill_ratio() const {
        if (fill_count_ == 0) return static_cast<double>(cancel_count_);
        return static_cast<double>(cancel_count_) / static_cast<double>(fill_count_);
    }

    [[nodiscard]] int64_t active_orders()    const { return static_cast<int64_t>(active_.size()); }
    [[nodiscard]] int64_t completed_orders() const { return static_cast<int64_t>(completed_.size()); }
    [[nodiscard]] int64_t submit_count()     const { return submit_count_; }
    [[nodiscard]] int64_t fill_count()       const { return fill_count_; }
    [[nodiscard]] int64_t cancel_count()     const { return cancel_count_; }
    [[nodiscard]] const std::string& symbol() const { return symbol_; }

    [[nodiscard]] const std::vector<OrderEvent>& completed_events() const {
        return completed_;
    }

    [[nodiscard]] std::vector<RiskSignal> flush_signals() {
        auto out = std::move(signal_buffer_);
        signal_buffer_.clear();
        return out;
    }

    void reset_window() {
        submit_count_per_window_ = 0;
        fill_count_              = 0;
        cancel_count_            = 0;
    }

private:
    std::string symbol_;

    std::unordered_map<std::string, OrderEvent> active_;
    std::vector<OrderEvent>                      completed_;
    std::vector<RiskSignal>                      signal_buffer_;

    int64_t submit_count_             = 0;
    int64_t fill_count_               = 0;
    int64_t cancel_count_             = 0;
    int64_t submit_count_per_window_  = 0;

    RollingStats recent_cancel_vol_stats_;

    [[nodiscard]] static int64_t now_us() noexcept {
        using namespace std::chrono;
        return duration_cast<microseconds>(
            system_clock::now().time_since_epoch()).count();
    }
};
