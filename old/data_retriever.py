import yfinance as yf
import requests
import json
import polars as pl
# %%

def get_gold_price_yahoo():
    # 1. 抓取國際金價 (USD/oz) 與 USD/HKD 匯率
    gold_price_usd = yf.Ticker("GC=F").fast_info['lastPrice']
    usd_hkd_rate = yf.Ticker("HKD=X").fast_info['lastPrice']

    # 2. 換算金額
    gold_price_hkd_oz = gold_price_usd * usd_hkd_rate
    gold_price_hkd_gram = gold_price_hkd_oz / 31.1034768
    gold_price_hkd_tael = gold_price_hkd_gram * 37.429

    print(f"國際金價: ${gold_price_usd:.2f} USD/oz")
    print(f"即時匯率: 1 USD = {usd_hkd_rate:.4f} HKD")
    print(f"折算每克: HK${gold_price_hkd_gram:.2f} / 克")
    print(f"折算每兩: HK${gold_price_hkd_tael:.2f} / 兩")

    return gold_price_hkd_oz, gold_price_hkd_gram, gold_price_hkd_tael

# 測試
gold_price_hkd_oz, gold_price_hkd_gram, gold_price_hkd_tael=(get_gold_price_yahoo())

# %%

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
# %%

data=get_chow_tai_fook_gold_price()


# %%
ctf_gold_data=pl.DataFrame([value[0] for value in data.values()])
gold_pellet_sell=ctf_gold_data.filter(pl.col('priceDesc')=='金粒賣出價').get_column('originGoldPrice').first()
gold_pellet_buy=ctf_gold_data.filter(pl.col('priceDesc')=='金粒買入價').get_column('originGoldPrice').first()
gold_9999_sell=ctf_gold_data.filter(pl.col('priceDesc')=='飾金賣出價').get_column('originGoldPrice').first()
gold_9999_buy=ctf_gold_data.filter(pl.col('priceDesc')=='飾金買入價').get_column('originGoldPrice').first()
gold_pellet_sell, gold_pellet_buy, gold_9999_sell, gold_9999_buy
# ctf_gold_data.filter(pl.col('priceDesc').str.contains('金粒[買賣]|飾金[買賣]'))

gold_pellet_sell_premium=(gold_pellet_sell-gold_price_hkd_tael)/gold_price_hkd_tael*100
gold_pellet_buy_premium=(gold_pellet_buy-gold_price_hkd_tael)/gold_price_hkd_tael*100
gold_9999_sell_premium=(gold_9999_sell-gold_price_hkd_tael)/gold_price_hkd_tael*100
gold_9999_buy_premium=(gold_9999_buy-gold_price_hkd_tael)/gold_price_hkd_tael*100
gold_pellet_sell_premium, gold_pellet_buy_premium, gold_9999_sell_premium, gold_9999_buy_premium
