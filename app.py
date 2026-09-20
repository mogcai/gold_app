"""Gold Price Tracker — spot gold vs. Chow Tai Fook (周大福) price dashboard.

Data access lives in `data_retriever.py` (scraper logic untouched). This file
only handles caching, layout and the local snapshot history behind the charts.
"""

from __future__ import annotations

import inspect
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

import data_retriever as dr
import db

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
CACHE_TTL = 300  # seconds — keeps Yahoo / CTF from being hammered on every rerun
DB_STALE_AFTER = 3600  # seconds — fall back to a live fetch if the DB is older
HK_TZ = timezone(timedelta(hours=8))  # Streamlit Cloud runs in UTC; display in HKT
UNITS = {"HKD / 兩 tael": "tael", "HKD / 克 gram": "gram", "USD / oz": "usd_oz"}
# Units offered by the calculator: the same conversion codes plus HKD/oz.
CALC_UNITS = {
    "HKD / 兩 tael": "tael",
    "HKD / 克 gram": "gram",
    "HKD / 盎司 oz": "oz_hkd",
    "USD / 盎司 oz": "usd_oz",
}
CALC_STEPS = {"tael": 10.0, "gram": 1.0, "oz_hkd": 10.0, "usd_oz": 1.0}
HISTORY_COLUMNS = db.COLUMNS

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
    """Read snapshots from the committed SQLite database."""
    return db.read_history()


def append_history(snapshot: dict) -> pd.DataFrame:
    """Persist a snapshot row; reruns of the cached fetch are de-duplicated."""
    db.insert_snapshot(snapshot)
    return read_history()


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def to_unit(hkd_per_tael: float, unit: str, usd_hkd: float) -> float:
    """Convert a HKD-per-tael figure into the selected display unit."""
    if unit == "tael":
        return hkd_per_tael
    hkd_per_gram = hkd_per_tael / dr.GRAMS_PER_TAEL
    if unit == "gram":
        return hkd_per_gram
    hkd_per_oz = hkd_per_gram * dr.OZ_TO_GRAM
    if unit == "oz_hkd":
        return hkd_per_oz
    return hkd_per_oz / usd_hkd


def spot_value(spot: dict, unit: str) -> float:
    if unit == "usd_oz":
        return spot["usd_per_oz"]
    if unit == "gram":
        return spot["hkd_per_gram"]
    if unit == "oz_hkd":
        return spot["hkd_per_oz"]
    return spot["hkd_per_tael"]


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
    st.caption("DB updated by GitHub Actions every 30 min")

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
        st.rerun()

# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #
# Primary source: the committed SQLite DB (kept fresh by GitHub Actions).
history = read_history()
db_epoch = db.latest_epoch()
db_age = (time.time() - db_epoch) if db_epoch else None

# Fallback: fetch live when the DB is missing or stale.
snapshot, error = None, None
if db_age is None or db_age > DB_STALE_AFTER:
    try:
        with st.spinner("Fetching live gold prices…"):
            snapshot = load_snapshot()
        history = append_history(snapshot)
        db_epoch = snapshot["fetched_at"]
    except Exception as exc:  # network / parsing failures must not kill the page
        snapshot, error = None, exc

if db_epoch:
    updated = datetime.fromtimestamp(db_epoch, tz=HK_TZ).strftime("%Y-%m-%d %H:%M:%S")
    age_txt = f"{int(db_age)}s ago" if db_age is not None else "just now"
    st.markdown(f"**Last updated:** `{updated}` ({age_txt})")
else:
    st.markdown("**Last updated:** `unavailable`")

# COMEX 黃金期貨市場狀態（休市時報價會凍結喺最後成交價）
# 用 getattr 做防禦：若部署嘅 data_retriever 係舊版（未有 is_market_open），唔會令 app crash。
_is_market_open = getattr(dr, "is_market_open", None)
if _is_market_open is None:
    st.markdown("**Market:** ⚪ COMEX gold futures status unavailable")
elif _is_market_open():
    st.markdown("**Market:** 🟢 COMEX gold futures **open**")
else:
    st.markdown("**Market:** 🔴 COMEX gold futures **closed** — 報價為最後成交價，唔會跳動")

if error is not None:
    st.error(f"Could not refresh live prices — {type(error).__name__}: {error}")
    st.caption("Showing the last snapshots stored in `gold.db` (if any).")

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
            help="XAU spot converted with the live USD/HKD rate."
            + ("" if spot.get("market_open", True) else "（市場休市中，此為最後成交價）"),
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
# Gold price calculator
# --------------------------------------------------------------------------- #
st.subheader("🧮 金價計數機 Gold Price Calculator")
st.caption("輸入任何金價（可選重量單位），即刻計出相對國際現貨金價同周大福牌價嘅溢價。")

calc_spot = snapshot["spot"] if snapshot else None
if calc_spot is None and not history.empty:  # fall back to the last recorded snapshot
    last = history.iloc[-1]
    calc_spot = {
        "usd_per_oz": float(last["spot_usd_oz"]),
        "usd_hkd": float(last["usd_hkd"]),
        "hkd_per_oz": float(last["spot_hkd_gram"]) * dr.OZ_TO_GRAM,
        "hkd_per_gram": float(last["spot_hkd_gram"]),
        "hkd_per_tael": float(last["spot_hkd_tael"]),
    }

if calc_spot is None:
    st.info("暫時未有現貨金價，未能計算溢價 — 請先按 **Refresh Data**。")
else:
    with st.container(border=True):
        unit_col, price_col = st.columns([1, 2])

        with unit_col:
            calc_label = st.selectbox("重量單位 Unit", list(CALC_UNITS), key="calc_unit")
        calc_code = CALC_UNITS[calc_label]
        spot_unit_price = to_unit(calc_spot["hkd_per_tael"], calc_code, calc_spot["usd_hkd"])

        with price_col:
            quoted = st.number_input(
                "你輸入嘅金價 Your price",
                min_value=0.0,
                value=round(spot_unit_price, 2),
                step=CALC_STEPS[calc_code],
                key=f"calc_price_{calc_code}",
                help="金舖報價、回收價、或者其他來源嘅金價都得。",
            )

        diff = quoted - spot_unit_price
        premium = (diff / spot_unit_price * 100) if spot_unit_price else 0.0

        m1, m2, m3 = st.columns(3)
        m1.metric("國際現貨金價 Spot", money(spot_unit_price, calc_code), delta=calc_label, delta_color="off")
        m2.metric("你輸入嘅金價 Your price", money(quoted, calc_code), delta_color="off")
        m3.metric("價差 Difference", money(diff, calc_code), delta_color="off")

        if quoted <= 0:
            st.info("輸入一個金價，就會即刻計出溢價。")
        else:
            colour = "#e5484d" if premium > 0 else "#30a46c"
            stance = "貴過" if premium > 0.0001 else ("平過" if premium < -0.0001 else "等於")
            st.markdown(
                "<div style='padding:12px 16px;border-radius:12px;background:rgba(212,175,55,.10);"
                "border:1px solid rgba(212,175,55,.35);font-size:1.02rem;'>"
                f"你輸入嘅 <b>{money(quoted, calc_code)}</b> 相對國際現貨 "
                f"<b>{money(spot_unit_price, calc_code)}</b> {stance}現貨 "
                f"<span style='color:{colour};font-weight:700;font-size:1.28rem;'>{premium:+.2f}%</span>"
                f"（{money(diff, calc_code)} / {calc_label}）</div>",
                unsafe_allow_html=True,
            )

            if snapshot:
                fx = calc_spot["usd_hkd"]
                rows = []
                for name, key in (("周大福飾金賣出", "gold_9999_sell"), ("周大福金粒賣出", "gold_pellet_sell")):
                    board_price = to_unit(snapshot["ctf"][key], calc_code, fx)
                    gap = (quoted - board_price) / board_price * 100
                    rows.append(f"{name} {money(board_price, calc_code)} → **{gap:+.2f}%**")
                st.caption("對比周大福牌價： " + " ｜ ".join(rows))

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
                # 唔好由 0 開始，否則金價嘅變化會被壓扁到睇唔到。
                lo, hi = series.min().min(), series.max().max()
                pad = (hi - lo) * 0.05 or max(abs(hi) * 0.01, 1.0)
                fig.update_yaxes(range=[lo - pad, hi + pad])
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
                # 同樣唔好由 0 開始，令溢價嘅波動更明顯。
                lo, hi = premiums.min().min(), premiums.max().max()
                pad = (hi - lo) * 0.05 or max(abs(hi) * 0.01, 0.1)
                fig.update_yaxes(range=[lo - pad, hi + pad])
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
