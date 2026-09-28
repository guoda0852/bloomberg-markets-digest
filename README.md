# 彭博市场速览 · Bloomberg Markets Digest

每日自动更新的金融市场速览页：市场行情看板 + 彭博社重点新闻聚合。

## 结构

- `index.html` — 网站页面（中文，深色金融看板风格）
- `data/market.json` — 行情数据（每天自动更新）
- `data/news.json` — 彭博头条（每天自动更新）
- `scripts/fetch.py` — 数据抓取脚本（仅用 Python 标准库）
- `.github/workflows/daily-update.yml` — GitHub Actions 定时任务，每天北京时间 7:00 抓取并提交

## 数据来源

- 行情：Yahoo Finance 公开接口（指数、外汇、商品、债券、加密货币）
- 新闻：Google News RSS 聚合彭博社（site:bloomberg.com）市场相关报道，标题+原文链接

注：彭博社全文有付费墙，新闻以标题摘要+原文链接形式聚合。
