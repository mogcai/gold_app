"""Gold Price Tracker — spot gold vs. Chow Tai Fook (周大福) price dashboard.

Data access lives in `data_retriever.py` (scraper logic untouched). This file
only handles caching, layout and the local snapshot history behind the charts.
"""

from __future__ import annotations

import inspect
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import data_retriever as dr

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
HISTORY_FILE = Path(__file__).with_name("gold_history.csv")
CACHE_TTL = 300  # seconds — keeps Yahoo / CTF from being hammered on every rerun
UNITS = {"HKD / 兩 tael": "tael", "HKD / 克 gram": "gram", "USD / oz": "usd_oz"}
HISTORY_COLUMNS = [
    "timestamp_epoch", "timestamp", "spot_usd_oz", "usd_hkd",
    "spot_hkd_gram", "spot_hkd_tael", "ctf_9999_buy", "ctf_9999_sell",
    "ctf_pellet_buy", "ctf_pellet_sell", "premium_9999_sell", "premium_pellet_sell",
]

st.set_page_config(page_title="Gold Price Tracker | 黃金價格追蹤", page_icon="🥇", layout="wide")


# --------------------------------------------------------------------------- #
# Data access (cached) + local history
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_snapshot() -> dict:
    """Fetch spot + CTF prices once per TTL window. Raises on failure."""
    spot = dr.get_gold_spot_snapshot()
    ctf = dr.get_chow_tai_fook_snapshot(spot_hkd_tael=spot["hkd_per_tael"])
    return {"fetched_at": time.time(), "spot": spot, "ctf": ctf}


def read_history() -> pd.DataFrame:
    if HISTORY_FILE.exists():
        try:
            return pd.read_csv(HISTORY_FILE)
        except Exception:
            return pd.DataFrame(columns=HISTORY_COLUMNS)
    return pd.DataFrame(columns=HISTORY_COLUMNS)


def append_history(snapshot: dict) -> pd.DataFrame:
    """Persist a snapshot row; reruns of the cached fetch are de-duplicated."""
    history = read_history()
    if not history.empty and float(history["timestamp_epoch"].iloc[-1]) == float(snapshot["fetched_at"]):
        return history

    spot, ctf = snapshot["spot"], snapshot["ctf"]
    row = {
        "timestamp_epoch": snapshot["fetched_at"],
        "timestamp": datetime.fromtimestamp(snapshot["fetched_at"]).strftime("%Y-%m-%d %H:%M:%S"),
        "spot_usd_oz": spot["usd_per_oz"],
        "usd_hkd": spot["usd_hkd"],
        "spot_hkd_gram": spot["hkd_per_gram"],
        "spot_hkd_tael": spot["hkd_per_tael"],
        "ctf_9999_buy": ctf["gold_9999_buy"],
        "ctf_9999_sell": ctf["gold_9999_sell"],
        "ctf_pellet_buy": ctf["gold_pellet_buy"],
        "ctf_pellet_sell": ctf["gold_pellet_sell"],
        "premium_9999_sell": ctf.get("gold_9999_sell_premium"),
        "premium_pellet_sell": ctf.get("gold_pellet_sell_premium"),
    }
    history = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
    history.to_csv(HISTORY_FILE, index=False)
    return history


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def to_unit(hkd_per_tael: float, unit: str, usd_hkd: float) -> float:
    """Convert a HKD-per-tael figure into the selected display unit."""
    if unit == "tael":
        return hkd_per_tael
    if unit == "gram":
        return hkd_per_tael / dr.GRAMS_PER_TAEL
    return hkd_per_tael / dr.GRAMS_PER_TAEL * dr.OZ_TO_GRAM / usd_hkd


def spot_value(spot: dict, unit: str) -> float:
    return {"tael": spot["hkd_per_tael"], "gram": spot["hkd_per_gram"]}.get(unit, spot["usd_per_oz"])


def money(value: float, unit: str) -> str:
    if unit == "usd_oz":
        return f"${value:,.2f}"
    return f"HK${value:,.2f}" if abs(value) < 1000 else f"HK${value:,.0f}"


def pct(value: float) -> str:
    return "—" if value is None else f"{value:+.2f}%"


def stretch(element) -> dict:
    """Stretch-to-width kwarg for the installed Streamlit version.

    `use_container_width` was deprecated in favour of `width="stretch"`, so pick
    whichever the running version actually supports.
    """
    try:
        return {"width": "stretch"} if "width" in inspect.signature(element).parameters else {"use_container_width": True}
    except (TypeError, ValueError):
        return {"use_container_width": True}


# --------------------------------------------------------------------------- #
# Sidebar controls
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("⚙️ Controls")
    unit_label = st.radio("Currency / Unit", list(UNITS), index=0)
    unit = UNITS[unit_label]

    st.divider()
    auto_refresh = st.checkbox("Auto-refresh", value=False)
    refresh_seconds = st.slider("Refresh interval (s)", 30, 600, CACHE_TTL, step=30, disabled=not auto_refresh)

    st.divider()
    st.caption(f"Scrapes cached for **{CACHE_TTL}s** (`st.cache_data`)")

    history_rows = len(read_history())
    st.caption(f"History rows: **{history_rows}**")
    if st.button("🗑️ Clear history", disabled=history_rows == 0, **stretch(st.button)):
        HISTORY_FILE.unlink(missing_ok=True)
        st.session_state.pop("history", None)
        st.rerun()

# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1250px;}
      div[data-testid="stMetric"] {
          background: linear-gradient(160deg, #1c1c21 0%, #292930 100%);
          border: 1px solid rgba(212,175,55,.38);
          border-radius: 14px; padding: 14px 18px;
          box-shadow: 0 2px 16px rgba(0,0,0,.20);
      }
      div[data-testid="stMetricLabel"] p {color: #d4af37; font-weight: 600; letter-spacing: .02em;}
      div[data-testid="stMetricValue"] {color: #fafafa;}
      div[data-testid="stMetricDelta"] {color: #b9b9c0;}
    </style>
    """,
    unsafe_allow_html=True,
)

title_col, button_col = st.columns([4, 1])

with title_col:
    st.title("🥇 Gold Price Tracker")
    st.caption("國際現貨金價 vs. 周大福牌價 · International spot gold vs. Chow Tai Fook (Hong Kong)")

with button_col:
    st.write("")
    if st.button("🔄 Refresh Data", type="primary", **stretch(st.button)):
        st.cache_data.clear()
        st.session_state.pop("history", None)
        st.rerun()

# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #
error = None
try:
    with st.spinner("Fetching live gold prices…"):
        snapshot = load_snapshot()
except Exception as exc:  # network / parsing failures must not kill the page
    snapshot, error = None, exc

if snapshot:
    history = append_history(snapshot)
    st.session_state["history"] = history
    updated = datetime.fromtimestamp(snapshot["fetched_at"]).strftime("%Y-%m-%d %H:%M:%S")
else:
    history = st.session_state.get("history")
    if history is None:  # a DataFrame is not truthy-testable
        history = read_history()
    updated = "unavailable"

st.markdown(f"**Last updated:** `{updated}`")

if error is not None:
    st.error(f"Could not refresh live prices — {type(error).__name__}: {error}")
    st.caption("Showing the last snapshots stored in `gold_history.csv` (if any).")

# --------------------------------------------------------------------------- #
# KPI metrics
# --------------------------------------------------------------------------- #
if snapshot:
    spot, ctf = snapshot["spot"], snapshot["ctf"]
    fx = spot["usd_hkd"]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            "International Spot Gold",
            money(spot_value(spot, unit), unit),
            delta=f"USD/HKD {fx:.4f}",
            delta_color="off",
            help="XAU spot converted with the live USD/HKD rate.",
        )
    with c2:
        st.metric(
            "CTF 飾金 Gold 9999",
            money(to_unit(ctf["gold_9999_sell"], unit, fx), unit),
            delta=f"買入 {money(to_unit(ctf['gold_9999_buy'], unit, fx), unit)}",
            delta_color="off",
            help="周大福飾金賣出價 / 買入價 (per tael, converted to the selected unit).",
        )
    with c3:
        st.metric(
            "CTF 金粒 Gold Pellet",
            money(to_unit(ctf["gold_pellet_sell"], unit, fx), unit),
            delta=f"買入 {money(to_unit(ctf['gold_pellet_buy'], unit, fx), unit)}",
            delta_color="off",
            help="周大福金粒賣出價 / 買入價 (per tael, converted to the selected unit).",
        )
    with c4:
        premium = ctf.get("gold_9999_sell_premium")
        spread = ctf["gold_9999_sell"] - spot["hkd_per_tael"]
        st.metric(
            "Premium vs. Spot",
            pct(premium),
            delta=f"價差 {money(to_unit(spread, unit, fx), unit)}",
            delta_color="off",
            help="飾金賣出價相對國際現貨金價的溢價 (per tael basis).",
        )
else:
    for col, label in zip(st.columns(4), ["International Spot Gold", "CTF 飾金 Gold 9999", "CTF 金粒 Gold Pellet", "Premium vs. Spot"]):
        col.metric(label, "—")

# --------------------------------------------------------------------------- #
# Charts & history
# --------------------------------------------------------------------------- #
st.subheader("📈 Charts & History")

if history.empty:
    st.info("No history yet — press **Refresh Data** to record the first snapshot.")
else:
    plot_df = history.copy()
    plot_df["time"] = pd.to_datetime(plot_df["timestamp"], errors="coerce")
    plot_df = plot_df.dropna(subset=["time"]).set_index("time")

    price_tab, premium_tab, table_tab = st.tabs(["價格 Price (HKD/tael)", "溢價 Premium (%)", "歷史數據 Data"])

    with price_tab:
        price_cols = [c for c in ["spot_hkd_tael", "ctf_9999_sell", "ctf_9999_buy", "ctf_pellet_sell"] if c in plot_df]
        if not price_cols:
            st.info("No price columns in history yet.")
        else:
            series = plot_df[price_cols].rename(
                columns={
                    "spot_hkd_tael": "Spot (HKD/tael)",
                    "ctf_9999_sell": "CTF 飾金賣出",
                    "ctf_9999_buy": "CTF 飾金買入",
                    "ctf_pellet_sell": "CTF 金粒賣出",
                }
            )
            try:
                import plotly.express as px

                fig = px.line(series, markers=True, labels={"value": "HKD / tael", "time": ""})
                fig.update_layout(legend_title_text="", hovermode="x unified", margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig, **stretch(st.plotly_chart))
            except ImportError:
                st.line_chart(series)

    with premium_tab:
        premium_cols = [c for c in ["premium_9999_sell", "premium_pellet_sell"] if c in plot_df]
        if not premium_cols:
            st.info("No premium data in history yet.")
        else:
            premiums = plot_df[premium_cols].rename(
                columns={"premium_9999_sell": "飾金賣出溢價 %", "premium_pellet_sell": "金粒賣出溢價 %"}
            )
            try:
                import plotly.express as px

                fig = px.line(premiums, markers=True, labels={"value": "%", "time": ""})
                fig.update_layout(legend_title_text="", hovermode="x unified", margin=dict(l=0, r=0, t=10, b=0))
                st.plotly_chart(fig, **stretch(st.plotly_chart))
            except ImportError:
                st.line_chart(premiums)

    with table_tab:
        st.dataframe(
            history.sort_values("timestamp_epoch", ascending=False).drop(columns=["timestamp_epoch"]),
            hide_index=True,
            **stretch(st.dataframe),
        )
        st.download_button(
            "⬇️ Download CSV",
            history.to_csv(index=False).encode("utf-8"),
            file_name="gold_history.csv",
            mime="text/csv",
        )

st.caption("Data sources: Yahoo Finance (GC=F, HKD=X) · chowtaifook.com 牌價 API · HK 地區")

# --------------------------------------------------------------------------- #
# Auto-refresh (re-runs the script, cache TTL still throttles real requests)
# --------------------------------------------------------------------------- #
if auto_refresh:
    time.sleep(refresh_seconds)
    st.rerun()
