#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/chrono.h>

#include "order_book.hpp"
#include "metrics.hpp"
#include "event_tracker.hpp"

namespace py = pybind11;

PYBIND11_MODULE(orderbook_engine, m) {
    m.doc() = "C++20 Limit Order Book engine with microstructure metrics";

    py::class_<L2Level>(m, "L2Level")
        .def(py::init<>())
        .def(py::init([](double p, double v) {
            L2Level l; l.price = p; l.volume = v; return l;
        }))
        .def_readwrite("price",  &L2Level::price)
        .def_readwrite("volume", &L2Level::volume)
        .def("__repr__", [](const L2Level& l) {
            return "L2Level(price=" + std::to_string(l.price) +
                   ", volume=" + std::to_string(l.volume) + ")";
        });

    py::class_<BookSnapshot>(m, "BookSnapshot")
        .def(py::init<>())
        .def_readwrite("best_bid",     &BookSnapshot::best_bid)
        .def_readwrite("best_ask",     &BookSnapshot::best_ask)
        .def_readwrite("best_bid_vol", &BookSnapshot::best_bid_vol)
        .def_readwrite("best_ask_vol", &BookSnapshot::best_ask_vol)
        .def_readwrite("top_bids",     &BookSnapshot::top_bids)
        .def_readwrite("top_asks",     &BookSnapshot::top_asks)
        .def_readwrite("timestamp_us", &BookSnapshot::timestamp_us)
        .def("spread", [](const BookSnapshot& s) {
            return metrics::bid_ask_spread(s);
        })
        .def("mid_price", [](const BookSnapshot& s) {
            return metrics::mid_price(s);
        })
        .def("__repr__", [](const BookSnapshot& s) {
            return "BookSnapshot(bid=" + std::to_string(s.best_bid) +
                   ", ask=" + std::to_string(s.best_ask) + ")";
        });

    py::class_<metrics::TickMetrics>(m, "TickMetrics")
        .def(py::init<>())
        .def_readwrite("timestamp_us",  &metrics::TickMetrics::timestamp_us)
        .def_readwrite("spread",        &metrics::TickMetrics::spread)
        .def_readwrite("spread_bps",    &metrics::TickMetrics::spread_bps)
        .def_readwrite("mid_price",     &metrics::TickMetrics::mid_price)
        .def_readwrite("imbalance",     &metrics::TickMetrics::imbalance)
        .def_readwrite("vwap_50k",      &metrics::TickMetrics::vwap_50k)
        .def_readwrite("slippage_bps",  &metrics::TickMetrics::slippage_bps)
        .def_readwrite("fully_filled",  &metrics::TickMetrics::fully_filled)
        .def_readwrite("is_quoting",    &metrics::TickMetrics::is_quoting)
        .def("to_dict", [](const metrics::TickMetrics& t) {
            py::dict d;
            d["timestamp_us"] = t.timestamp_us;
            d["spread"]       = t.spread;
            d["spread_bps"]   = t.spread_bps;
            d["mid_price"]    = t.mid_price;
            d["imbalance"]    = t.imbalance;
            d["vwap_50k"]     = t.vwap_50k;
            d["slippage_bps"] = t.slippage_bps;
            d["fully_filled"] = t.fully_filled;
            d["is_quoting"]   = t.is_quoting;
            return d;
        });

    py::class_<metrics::SlippageResult>(m, "SlippageResult")
        .def(py::init<>())
        .def_readwrite("vwap",         &metrics::SlippageResult::vwap)
        .def_readwrite("slippage_bps", &metrics::SlippageResult::slippage_bps)
        .def_readwrite("filled_usd",   &metrics::SlippageResult::filled_usd)
        .def_readwrite("fully_filled", &metrics::SlippageResult::fully_filled);

    py::class_<OrderBook20>(m, "OrderBook20")
        .def(py::init<std::string, std::size_t>(),
             py::arg("symbol"), py::arg("depth_levels") = 20)

        .def("apply_snapshot_raw", &OrderBook20::apply_snapshot_raw,
             py::arg("bids"), py::arg("asks"),
             "Replace full order book with a new L2 snapshot.")

        .def("update_level", &OrderBook20::update_level,
             py::arg("is_bid"), py::arg("price"), py::arg("volume"),
             "Update a single price level. volume=0 removes the level.")

        .def("snapshot", &OrderBook20::snapshot,
             py::arg("top_n") = 5,
             "Return a BookSnapshot with top-N bid/ask levels.")

        .def("best_bid",   &OrderBook20::best_bid<double>)
        .def("best_ask",   &OrderBook20::best_ask<double>)
        .def("symbol",     &OrderBook20::symbol)
        .def("bid_levels", &OrderBook20::bid_levels)
        .def("ask_levels", &OrderBook20::ask_levels)
        .def("is_valid",   &OrderBook20::is_valid)

        .def("__repr__", [](const OrderBook20& b) {
            return "OrderBook20(symbol='" + b.symbol() + "', " +
                   "bids=" + std::to_string(b.bid_levels()) + ", " +
                   "asks=" + std::to_string(b.ask_levels()) + ")";
        });

    m.def("compute_metrics", &metrics::compute_all,
          py::arg("snapshot"),
          py::arg("imbalance_levels") = 5,
          py::arg("notional_usd")     = 50'000.0,
          "Compute all microstructure metrics from a BookSnapshot in one call.");

    m.def("bid_ask_spread",  &metrics::bid_ask_spread,  py::arg("snapshot"));
    m.def("bid_ask_spread_bps", &metrics::bid_ask_spread_bps, py::arg("snapshot"));
    m.def("depth_imbalance", &metrics::depth_imbalance,
          py::arg("snapshot"), py::arg("levels") = 5);
    m.def("vwap_slippage",   &metrics::vwap_slippage,
          py::arg("snapshot"), py::arg("notional_usd") = 50'000.0);
    m.def("is_quoting",      &metrics::is_quoting,
          py::arg("snapshot"), py::arg("max_spread_bps") = 100.0);

    py::class_<OrderEvent>(m, "OrderEvent")
        .def(py::init<>())
        .def_readwrite("order_id",    &OrderEvent::order_id)
        .def_readwrite("is_bid",      &OrderEvent::is_bid)
        .def_readwrite("price",       &OrderEvent::price)
        .def_readwrite("quantity",    &OrderEvent::quantity)
        .def_readwrite("submit_us",   &OrderEvent::submit_us)
        .def_readwrite("cancel_us",   &OrderEvent::cancel_us)
        .def_readwrite("filled",      &OrderEvent::filled)
        .def_readwrite("depth_level", &OrderEvent::depth_level)
        .def("lifetime_us", [](const OrderEvent& e) {
            return e.cancel_us > 0 ? e.cancel_us - e.submit_us : 0LL;
        })
        .def("to_dict", [](const OrderEvent& e) {
            py::dict d;
            d["order_id"]    = e.order_id;
            d["is_bid"]      = e.is_bid;
            d["price"]       = e.price;
            d["quantity"]    = e.quantity;
            d["submit_us"]   = e.submit_us;
            d["cancel_us"]   = e.cancel_us;
            d["filled"]      = e.filled;
            d["depth_level"] = e.depth_level;
            d["lifetime_us"] = e.cancel_us > 0 ? e.cancel_us - e.submit_us : 0LL;
            return d;
        })
        .def("__repr__", [](const OrderEvent& e) {
            return "OrderEvent(id='" + e.order_id +
                   "', depth=" + std::to_string(e.depth_level) +
                   ", filled=" + (e.filled ? "True" : "False") + ")";
        });

    py::class_<RiskSignal>(m, "RiskSignal")
        .def(py::init<>())
        .def_readwrite("timestamp_us",  &RiskSignal::timestamp_us)
        .def_readwrite("order_id",      &RiskSignal::order_id)
        .def_readwrite("is_spoof",      &RiskSignal::is_spoof)
        .def_readwrite("is_stuffing",   &RiskSignal::is_stuffing)
        .def_readwrite("is_layering",   &RiskSignal::is_layering)
        .def_readwrite("lifetime_us",   &RiskSignal::lifetime_us)
        .def_readwrite("depth_level",   &RiskSignal::depth_level)
        .def_readwrite("price",         &RiskSignal::price)
        .def_readwrite("quantity",      &RiskSignal::quantity)
        .def_readwrite("filled",        &RiskSignal::filled)
        .def("is_anomaly", [](const RiskSignal& s) {
            return s.is_spoof || s.is_stuffing || s.is_layering;
        })
        .def("to_dict", [](const RiskSignal& s) {
            py::dict d;
            d["timestamp_us"] = s.timestamp_us;
            d["order_id"]     = s.order_id;
            d["is_spoof"]     = s.is_spoof;
            d["is_stuffing"]  = s.is_stuffing;
            d["is_layering"]  = s.is_layering;
            d["is_anomaly"]   = s.is_spoof || s.is_stuffing || s.is_layering;
            d["lifetime_us"]  = s.lifetime_us;
            d["depth_level"]  = s.depth_level;
            d["price"]        = s.price;
            d["quantity"]     = s.quantity;
            d["filled"]       = s.filled;
            return d;
        })
        .def("__repr__", [](const RiskSignal& s) {
            std::string flags;
            if (s.is_spoof)    flags += "SPOOF ";
            if (s.is_stuffing) flags += "STUFFING ";
            if (s.is_layering) flags += "LAYERING ";
            if (flags.empty()) flags = "CLEAN";
            return "RiskSignal(id='" + s.order_id + "', flags=" + flags +
                   ", lifetime=" + std::to_string(s.lifetime_us) + "us)";
        });

    py::class_<OrderEventTracker>(m, "OrderEventTracker")
        .def(py::init<std::string>(), py::arg("symbol"))

        .def("on_submit", &OrderEventTracker::on_submit,
             py::arg("order_id"), py::arg("is_bid"), py::arg("price"),
             py::arg("qty"), py::arg("depth_level"), py::arg("submit_us") = 0LL,
             "Register a new order submission.")

        .def("on_fill", &OrderEventTracker::on_fill,
             py::arg("order_id"), py::arg("filled_qty"),
             "Register a fill against an active order.")

        .def("on_cancel", &OrderEventTracker::on_cancel,
             py::arg("order_id"), py::arg("cancel_us") = 0LL,
             "Register a cancellation -> returns RiskSignal with anomaly flags.")

        .def("order_to_trade_ratio",  &OrderEventTracker::order_to_trade_ratio)
        .def("cancel_to_fill_ratio",  &OrderEventTracker::cancel_to_fill_ratio)
        .def("active_orders",         &OrderEventTracker::active_orders)
        .def("completed_orders",      &OrderEventTracker::completed_orders)
        .def("submit_count",          &OrderEventTracker::submit_count)
        .def("fill_count",            &OrderEventTracker::fill_count)
        .def("cancel_count",          &OrderEventTracker::cancel_count)
        .def("symbol",                &OrderEventTracker::symbol)
        .def("completed_events",      &OrderEventTracker::completed_events)
        .def("flush_signals",         &OrderEventTracker::flush_signals)
        .def("reset_window",          &OrderEventTracker::reset_window)
        .def("__repr__", [](const OrderEventTracker& t) {
            return "OrderEventTracker(symbol='" + t.symbol() +
                   "', active=" + std::to_string(t.active_orders()) +
                   ", OTR=" + std::to_string(t.order_to_trade_ratio()) + ")";
        });
}
