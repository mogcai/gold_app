"""Data layer: international spot gold + Chow Tai Fook (周大福) gold prices.

The original scraping logic (Yahoo Finance quotes and the CTF goldPrice
endpoint / Polars parsing) is kept verbatim. It has only been re-organised so
the module can be *imported safely*: no network request happens at import time
and every value is reachable through a plain function.
"""

import json

import polars as pl
import requests
import yfinance as yf

OZ_TO_GRAM = 31.1034768
GRAMS_PER_TAEL = 37.429


def get_gold_price_yahoo():
    # 1. 抓取國際金價 (USD/oz) 與 USD/HKD 匯率
    gold_price_usd = yf.Ticker("GC=F").fast_info['lastPrice']
    usd_hkd_rate = yf.Ticker("HKD=X").fast_info['lastPrice']

    # 2. 換算金額
    gold_price_hkd_oz = gold_price_usd * usd_hkd_rate
    gold_price_hkd_gram = gold_price_hkd_oz / OZ_TO_GRAM
    gold_price_hkd_tael = gold_price_hkd_gram * GRAMS_PER_TAEL

    print(f"國際金價: ${gold_price_usd:.2f} USD/oz")
    print(f"即時匯率: 1 USD = {usd_hkd_rate:.4f} HKD")
    print(f"折算每克: HK${gold_price_hkd_gram:.2f} / 克")
    print(f"折算每兩: HK${gold_price_hkd_tael:.2f} / 兩")

    return gold_price_hkd_oz, gold_price_hkd_gram, gold_price_hkd_tael


def get_gold_spot_snapshot():
    """Same conversion as `get_gold_price_yahoo`, plus the raw USD/oz and FX rate."""
    gold_price_usd = float(yf.Ticker("GC=F").fast_info['lastPrice'])
    usd_hkd_rate = float(yf.Ticker("HKD=X").fast_info['lastPrice'])

    gold_price_hkd_oz = gold_price_usd * usd_hkd_rate
    gold_price_hkd_gram = gold_price_hkd_oz / OZ_TO_GRAM
    gold_price_hkd_tael = gold_price_hkd_gram * GRAMS_PER_TAEL

    return {
        'usd_per_oz': gold_price_usd,
        'usd_hkd': usd_hkd_rate,
        'hkd_per_oz': gold_price_hkd_oz,
        'hkd_per_gram': gold_price_hkd_gram,
        'hkd_per_tael': gold_price_hkd_tael,
    }


def get_chow_tai_fook_gold_price():
    url = "https://www.chowtaifook.com/bin/servlet/ctfweb/goldPrice?region=HK"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.chowtaifook.com/zh-hant/",
        "X-Requested-With": "XMLHttpRequest"
    }

    # 使用 with 搭配 requests.Session()，結束時會自動關閉所有連線
    with requests.Session() as session:
        try:
            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            print("=== 周大福牌價抓取成功 ===")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            return data

        except requests.exceptions.RequestException as e:
            print(f"請求失敗: {e}")
        except json.JSONDecodeError:
            print("解析 JSON 失敗")

    return None


def parse_chow_tai_fook_prices(data):
    """Flatten the CTF payload into the 金粒 / 飾金 buy & sell prices (HKD per tael)."""
    ctf_gold_data = pl.DataFrame([value[0] for value in data.values()])

    gold_pellet_sell = ctf_gold_data.filter(pl.col('priceDesc') == '金粒賣出價').get_column('originGoldPrice').first()
    gold_pellet_buy = ctf_gold_data.filter(pl.col('priceDesc') == '金粒買入價').get_column('originGoldPrice').first()
    gold_9999_sell = ctf_gold_data.filter(pl.col('priceDesc') == '飾金賣出價').get_column('originGoldPrice').first()
    gold_9999_buy = ctf_gold_data.filter(pl.col('priceDesc') == '飾金買入價').get_column('originGoldPrice').first()

    prices = {
        'gold_pellet_sell': gold_pellet_sell,
        'gold_pellet_buy': gold_pellet_buy,
        'gold_9999_sell': gold_9999_sell,
        'gold_9999_buy': gold_9999_buy,
    }
    if any(value is None for value in prices.values()):
        raise ValueError("周大福牌價缺少金粒/飾金買賣價，回應格式可能已改變。")
    return {key: float(value) for key, value in prices.items()}


def get_chow_tai_fook_snapshot(spot_hkd_tael=None):
    """Fetch + parse CTF prices; premiums are added when a spot price is supplied."""
    data = get_chow_tai_fook_gold_price()
    if not data:
        raise RuntimeError("無法取得周大福牌價（請求失敗或回應非 JSON）。")

    prices = parse_chow_tai_fook_prices(data)

    if spot_hkd_tael:
        prices.update({
            'gold_pellet_sell_premium': (prices['gold_pellet_sell'] - spot_hkd_tael) / spot_hkd_tael * 100,
            'gold_pellet_buy_premium': (prices['gold_pellet_buy'] - spot_hkd_tael) / spot_hkd_tael * 100,
            'gold_9999_sell_premium': (prices['gold_9999_sell'] - spot_hkd_tael) / spot_hkd_tael * 100,
            'gold_9999_buy_premium': (prices['gold_9999_buy'] - spot_hkd_tael) / spot_hkd_tael * 100,
        })
    return prices


if __name__ == "__main__":
    # 手動測試用：只在直接執行這個檔案時才連網。
    gold_price_hkd_oz, gold_price_hkd_gram, gold_price_hkd_tael = get_gold_price_yahoo()
    print(gold_price_hkd_oz, gold_price_hkd_gram, gold_price_hkd_tael)

    snapshot = get_chow_tai_fook_snapshot(spot_hkd_tael=gold_price_hkd_tael)
    print(snapshot)
