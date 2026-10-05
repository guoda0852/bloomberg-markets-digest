#!/usr/bin/env python3
"""Daily data fetcher for the Bloomberg Markets Digest site.

Fetches:
  1. Market quotes (indices, commodities, FX, bonds, crypto) via Yahoo Finance chart API.
  2. Top Bloomberg markets headlines via Google News RSS (site:bloomberg.com).

Writes data/market.json and data/news.json. Stdlib only.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# (symbol, chinese name, group)
SYMBOLS = [
    ("^GSPC", "标普500", "美股"),
    ("^IXIC", "纳斯达克", "美股"),
    ("^DJI", "道琼斯", "美股"),
    ("^HSI", "恒生指数", "亚太"),
    ("000001.SS", "上证指数", "亚太"),
    ("^N225", "日经225", "亚太"),
    ("^GDAXI", "德国DAX", "欧洲"),
    ("^FTSE", "英国富时100", "欧洲"),
    ("GC=F", "黄金", "商品"),
    ("SI=F", "白银", "商品"),
    ("CL=F", "WTI原油", "商品"),
    ("BZ=F", "布伦特原油", "商品"),
    ("CNY=X", "美元/人民币", "外汇"),
    ("EURUSD=X", "欧元/美元", "外汇"),
    ("JPY=X", "美元/日元", "外汇"),
    ("^TNX", "美10年期国债收益率", "债券"),
    ("^VIX", "VIX恐慌指数", "债券"),
    ("BTC-USD", "比特币", "加密"),
]


# A股指数 K 线（同花顺数据源，需 HITHINK_API_KEY）
KLINE_SYMBOLS = [
    ("000001.SH", "上证指数"),
    ("399001.SZ", "深证成指"),
    ("399006.SZ", "创业板指"),
]
HITHINK_BASE = "https://fuyao.aicubes.cn"
HITHINK_KLINE_PATH = "/api/a-share-index/prices/historical"  # 指数专用端点

NEWS_RSS = (
    "https://news.google.com/rss/search"
    "?q=site%3Abloomberg.com%20markets&hl=en-US&gl=US&ceid=US%3Aen"
)


def fetch_quote(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    result = data["chart"]["result"][0]
    closes = [c for c in result["indicators"]["quote"][0]["close"] if c]
    if len(closes) < 2:
        return None
    price, prev = closes[-1], closes[-2]
    return {
        "symbol": symbol,
        "price": round(price, 2),
        "change_pct": round((price - prev) / prev * 100, 2),
        "currency": result["meta"].get("currency", ""),
    }


def fetch_market():
    items = []
    for symbol, name, group in SYMBOLS:
        try:
            q = fetch_quote(symbol)
        except Exception as e:  # noqa: BLE001 - keep going on single-symbol failure
            print(f"quote failed for {symbol}: {e}")
            continue
        if q:
            q.update({"name": name, "group": group})
            items.append(q)
    return items


def translate_en_to_zh(text):
    """Translate an English headline to Simplified Chinese.

    Tries Google's free endpoint first, falls back to MyMemory.
    Returns None when both fail; callers keep the English original.
    """
    # 1) Google translate free endpoint (unofficial, no key needed)
    try:
        q = urllib.parse.quote(text)
        url = ("https://translate.googleapis.com/translate_a/single"
               f"?client=gtx&sl=en&tl=zh-CN&dt=t&q={q}")
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        zh = "".join(seg[0] for seg in data[0] if seg and seg[0])
        if zh.strip():
            return zh.strip()
    except Exception as e:  # noqa: BLE001
        print(f"google translate failed: {e}")
    # 2) MyMemory free API (no key, ~5000 chars/day anonymous)
    try:
        q = urllib.parse.quote(text)
        url = (f"https://api.mymemory.translated.net/get"
               f"?q={q}&langpair=en|zh-CN")
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        zh = (data.get("responseData") or {}).get("translatedText", "").strip()
        if zh and "QUERY LENGTH LIMIT" not in zh and "INVALID EMAIL" not in zh:
            return zh
    except Exception as e:  # noqa: BLE001
        print(f"mymemory translate failed: {e}")
    return None



def fetch_klines(days=250):
    """从同花顺拉 A 股指数历史日K，返回 {thscode: {name, thscode, klines:[...]}}。"""
    api_key = os.environ.get("HITHINK_API_KEY", "").strip()
    if not api_key:
        print("klines: HITHINK_API_KEY 未设置，跳过")
        return {}
    out = {}
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - days * 86400 * 1000
    for thscode, name in KLINE_SYMBOLS:
        try:
            params = {"thscode": thscode, "interval": "1d",
                      "start": start_ms, "end": now_ms}
            url = HITHINK_BASE + HITHINK_KLINE_PATH + "?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers={**UA, "X-api-key": api_key})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            klines = normalize_klines(data)
            if klines:
                out[thscode] = {"name": name, "thscode": thscode, "klines": klines[-days:]}
                print(f"klines: {name} {len(klines)} bars")
            else:
                print(f"klines: {name} 无数据 (code={data.get('code')}, msg={data.get('message')})")
        except Exception as e:  # noqa: BLE001
            print(f"klines failed for {thscode}: {e}")
    return out


def normalize_klines(data):
    """把同花顺返回转成 [{date, open, high, low, close, volume}]。"""
    rows = []
    if isinstance(data, dict):
        inner = data.get("data") or {}
        if isinstance(inner, dict) and isinstance(inner.get("item"), list):
            rows = inner["item"]
        else:
            for key in ("klines", "list", "result"):
                if isinstance(data.get(key), list):
                    rows = data[key]
                    break
    elif isinstance(data, list):
        rows = data
    tz = timezone(timedelta(hours=8))
    norm = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            ms = r.get("date_ms")
            d = datetime.fromtimestamp(int(ms) / 1000, tz).strftime("%Y-%m-%d") if ms else ""
            norm.append({
                "date": d,
                "open": float(r.get("open_price", 0)),
                "high": float(r.get("high_price", 0)),
                "low": float(r.get("low_price", 0)),
                "close": float(r.get("close_price", 0)),
                "volume": float(r.get("volume") or 0),
            })
        except (TypeError, ValueError):
            continue
    return [k for k in norm if k["date"] and k["close"] > 0]


def fetch_news(limit=12):
    req = urllib.request.Request(NEWS_RSS, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        root = ET.fromstring(resp.read())
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        # Titles look like "Headline - Bloomberg.com"; split off the source.
        if " - " in title:
            title, _, source = title.rpartition(" - ")
        else:
            source = "Bloomberg"
        if title and link:
            title = title.strip()
            zh = translate_en_to_zh(title)
            time.sleep(1.5)  # be polite to the translation endpoints
            items.append({"title": title, "title_zh": zh, "link": link,
                          "pub_date": pub, "source": source.strip()})
        if len(items) >= limit:
            break
    return items


def main():
    os.makedirs("data", exist_ok=True)
    now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    market = {"updated_at": now, "items": fetch_market()}
    with open("data/market.json", "w", encoding="utf-8") as f:
        json.dump(market, f, ensure_ascii=False, indent=2)
    print(f"market: {len(market['items'])} symbols")

    try:
        news_items = fetch_news()
    except Exception as e:  # noqa: BLE001 - news failure must not kill market data
        print(f"news fetch failed: {e}")
        news_items = []
    if news_items:
        news = {"updated_at": now, "items": news_items}
        with open("data/news.json", "w", encoding="utf-8") as f:
            json.dump(news, f, ensure_ascii=False, indent=2)
        print(f"news: {len(news_items)} headlines")
    else:
        print("news: kept previous data/news.json")

    try:
        klines = fetch_klines()
    except Exception as e:  # noqa: BLE001 - klines failure must not kill market data
        print(f"klines fetch failed: {e}")
        klines = {}
    if klines:
        with open("data/klines.json", "w", encoding="utf-8") as f:
            json.dump({"updated_at": now, "symbols": klines}, f, ensure_ascii=False)
        print(f"klines: {len(klines)} symbols written")
    else:
        print("klines: kept previous data/klines.json (if any)")


if __name__ == "__main__":
    main()
