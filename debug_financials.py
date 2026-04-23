"""
debug_financials.py — 探勘 FinMind API 對 2330 真實回傳的欄位名稱
執行：python debug_financials.py
"""
import os, sys, requests, json
from pprint import pprint

STOCK_ID = "2330"
TOKEN = os.environ.get("FINMIND_TOKEN", "")
BASE = "https://api.finmindtrade.com/api/v4/data"

def fm_get(dataset: str, stock_id: str = STOCK_ID, extra: dict | None = None) -> list[dict]:
    params = {"dataset": dataset, "stock_id": stock_id, "token": TOKEN}
    if extra:
        params.update(extra)
    try:
        r = requests.get(BASE, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("status") == 200:
            return data.get("data", [])
        print(f"  ⚠️  {dataset} status={data.get('status')} msg={data.get('msg','')}")
    except Exception as e:
        print(f"  ❌ {dataset}: {e}")
    return []


def show_types(rows: list[dict], label: str, value_field: str = "value"):
    """印出所有 type（科目名稱）及對應的最新值"""
    if not rows:
        print(f"  [空資料]\n")
        return
    # 取最新日期
    dates = sorted({r.get("date", "") for r in rows}, reverse=True)
    latest = dates[0]
    print(f"  最新期間: {latest}  (共 {len(dates)} 個期間)\n")
    latest_rows = [r for r in rows if r.get("date") == latest]
    print(f"  {'科目名稱 (type)':<50} {'數值':>20}")
    print(f"  {'-'*50} {'-'*20}")
    for r in sorted(latest_rows, key=lambda x: x.get("type", "")):
        t = r.get("type", "")
        v = r.get(value_field, "")
        print(f"  {t:<50} {str(v):>20}")
    print()


# ── 1. 資產負債表 ──────────────────────────────────────────────
print("=" * 70)
print("【資產負債表】TaiwanStockBalanceSheet")
print("=" * 70)
bs_rows = fm_get("TaiwanStockBalanceSheet")
show_types(bs_rows, "BS")

# 搜尋關鍵字
keywords = ["應收", "負債", "資產"]
print("  >> 含關鍵字的科目：")
if bs_rows:
    dates = sorted({r.get("date","") for r in bs_rows}, reverse=True)
    latest = dates[0]
    for kw in keywords:
        matched = [r for r in bs_rows if r.get("date") == latest and kw in r.get("type","")]
        if matched:
            print(f"\n  [{kw}]")
            for r in matched:
                print(f"    type={r['type']!r:55} value={r.get('value',''):>20}")
print()

# ── 2. 現金流量表 ──────────────────────────────────────────────
print("=" * 70)
print("【現金流量表】TaiwanStockCashFlowsStatement")
print("=" * 70)
cf_rows = fm_get("TaiwanStockCashFlowsStatement")
show_types(cf_rows, "CF")

# 搜尋 OCF 相關
ocf_keywords = ["營業", "現金流", "Operating"]
print("  >> 含 OCF 關鍵字的科目：")
if cf_rows:
    dates = sorted({r.get("date","") for r in cf_rows}, reverse=True)
    latest = dates[0]
    for kw in ocf_keywords:
        matched = [r for r in cf_rows if r.get("date") == latest and kw in r.get("type","")]
        if matched:
            print(f"\n  [{kw}]")
            for r in matched:
                print(f"    type={r['type']!r:55} value={r.get('value',''):>20}")
print()

# ── 3. 損益表 ──────────────────────────────────────────────────
print("=" * 70)
print("【損益表】TaiwanStockFinancialStatements")
print("=" * 70)
is_rows = fm_get("TaiwanStockFinancialStatements")
show_types(is_rows, "IS")

# ── 4. 結論摘要 ────────────────────────────────────────────────
print("=" * 70)
print("【結論：目標欄位確認】")
print("=" * 70)
if bs_rows:
    dates = sorted({r.get("date","") for r in bs_rows}, reverse=True)
    latest = dates[0]
    bmap = {r["type"]: r.get("value") for r in bs_rows if r.get("date") == latest}
    targets = [
        "應收帳款及票據", "應收帳款淨額", "應收帳款", "應收票據",
        "應收帳款及票據淨額", "應收票據及應收帳款",
        "負債總計", "負債總額", "負債合計",
        "資產總計", "資產總額", "資產合計",
    ]
    for t in targets:
        v = bmap.get(t)
        hit = "✅" if v is not None else "❌"
        print(f"  {hit} BS[{t!r}] = {v}")

if cf_rows:
    dates = sorted({r.get("date","") for r in cf_rows}, reverse=True)
    latest = dates[0]
    cmap = {r["type"]: r.get("value") for r in cf_rows if r.get("date") == latest}
    cf_targets = [
        "CashFlowsFromOperatingActivities",
        "營業活動之淨現金流入（流出）",
        "來自營業活動之現金流量",
        "本期營業活動之現金流量",
    ]
    print()
    for t in cf_targets:
        v = cmap.get(t)
        hit = "✅" if v is not None else "❌"
        unit_hint = ""
        if v is not None:
            try:
                fv = float(v)
                unit_hint = f"  → ÷1e5={fv/1e5:.1f}億  ÷1e8={fv/1e8:.1f}億"
            except Exception:
                pass
        print(f"  {hit} CF[{t!r}] = {v}{unit_hint}")
