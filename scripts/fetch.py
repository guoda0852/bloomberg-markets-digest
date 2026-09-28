#!/usr/bin/env python3
"""Daily data fetcher for the Bloomberg Markets Digest site."""
import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

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
        except Exception as e:
            print(f"quote failed for {symbol}: {e}")
            continue
        if q:
            q.update({"name": name, "group": group})
            items.append(q)
    return items

def fetch_news(limit=12):
    req = urllib.request.Request(NEWS_RSS, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as resp:
        root = ET.fromstring(resp.read())
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if " - " in title:
            title, _, source = title.rpartition(" - ")
        else:
            source = "Bloomberg"
        if title and link:
            items.append({"title": title.strip(), "link": link,
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
    except Exception as e:
        print(f"news fetch failed: {e}")
        news_items = []
    if news_items:
        news = {"updated_at": now, "items": news_items}
        with open("data/news.json", "w", encoding="utf-8") as f:
            json.dump(news, f, ensure_ascii=False, indent=2)
        print(f"news: {len(news_items)} headlines")
    else:
        print("news: kept previous data/news.json")

if __name__ == "__main__":
    main()
