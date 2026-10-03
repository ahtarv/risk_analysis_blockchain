#pragma once

#include <map>
#include <span>
#include <vector>
#include <concepts>
#include <stdexcept>
#include <algorithm>
#include <functional>
#include <string>
#include <chrono>
#include <cstdint>

template <typename T>
concept Numeric = std::is_arithmetic_v<T>;

template <typename T>
concept PriceLevel = requires(T t) {
    { t.price }  -> std::convertible_to<double>;
    { t.volume } -> std::convertible_to<double>;
};

struct L2Level {
    double price;
    double volume;
};

struct BookSnapshot {
    double best_bid   = 0.0;
    double best_ask   = 0.0;
    double best_bid_vol = 0.0;
    double best_ask_vol = 0.0;

    std::vector<std::pair<double,double>> top_bids; 
    std::vector<std::pair<double,double>> top_asks; 

    int64_t timestamp_us = 0; 
};

class OrderBook20 {
public:
    explicit OrderBook20(std::string symbol, std::size_t depth_levels = 20)
        : symbol_(std::move(symbol)), depth_levels_(depth_levels) {}

    template <PriceLevel P>
    void apply_snapshot(std::span<const P> bids, std::span<const P> asks) {
        bids_.clear();
        asks_.clear();
        for (const auto& lvl : bids) {
            if (lvl.volume > 0.0)
                bids_[lvl.price] = lvl.volume;
        }
        for (const auto& lvl : asks) {
            if (lvl.volume > 0.0)
                asks_[lvl.price] = lvl.volume;
        }
        stamp_now();
    }

    void apply_snapshot_raw(const std::vector<L2Level>& bids,
                            const std::vector<L2Level>& asks) {
        apply_snapshot<L2Level>(
            std::span<const L2Level>(bids),
            std::span<const L2Level>(asks)
        );
    }

    void update_level(bool is_bid, double price, double volume) {
        if (is_bid) {
            if (volume <= 0.0) bids_.erase(price);
            else               bids_[price] = volume;
        } else {
            if (volume <= 0.0) asks_.erase(price);
            else               asks_[price] = volume;
        }
        stamp_now();
    }

    [[nodiscard]] BookSnapshot snapshot(std::size_t top_n = 5) const {
        BookSnapshot s;
        s.timestamp_us = last_update_us_;

        if (!bids_.empty()) {
            s.best_bid     = bids_.begin()->first;
            s.best_bid_vol = bids_.begin()->second;
        }
        if (!asks_.empty()) {
            s.best_ask     = asks_.begin()->first;
            s.best_ask_vol = asks_.begin()->second;
        }

        s.top_bids.reserve(top_n);
        std::size_t cnt = 0;
        for (const auto& [p, v] : bids_) {
            if (cnt++ >= top_n) break;
            s.top_bids.emplace_back(p, v);
        }

        s.top_asks.reserve(top_n);
        cnt = 0;
        for (const auto& [p, v] : asks_) {
            if (cnt++ >= top_n) break;
            s.top_asks.emplace_back(p, v);
        }

        return s;
    }

    [[nodiscard]] const std::string& symbol()   const noexcept { return symbol_; }
    [[nodiscard]] std::size_t bid_levels()      const noexcept { return bids_.size(); }
    [[nodiscard]] std::size_t ask_levels()      const noexcept { return asks_.size(); }
    [[nodiscard]] bool        is_valid()        const noexcept {
        return !bids_.empty() && !asks_.empty() &&
               bids_.begin()->first < asks_.begin()->first;
    }

    template <Numeric T>
    [[nodiscard]] T best_bid() const {
        if (bids_.empty()) return T{0};
        return static_cast<T>(bids_.begin()->first);
    }

    template <Numeric T>
    [[nodiscard]] T best_ask() const {
        if (asks_.empty()) return T{0};
        return static_cast<T>(asks_.begin()->first);
    }

private:
    std::string symbol_;
    std::size_t depth_levels_;
    int64_t     last_update_us_ = 0;

    std::map<double, double, std::greater<double>> bids_;

    std::map<double, double>                       asks_;

    void stamp_now() {
        using namespace std::chrono;
        last_update_us_ = duration_cast<microseconds>(
            system_clock::now().time_since_epoch()).count();
    }
};
