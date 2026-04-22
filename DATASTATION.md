# 📡 數據中轉站：my-stock-dashboard 模組使用說明

本專案（my-stock-dashboard）作為台股數據後端，提供
總經狀態、個股評分、AI 分析、風控四大數據流。
以下為各模組的函式簽名與回傳結構，可直接 import 使用。

---

## ⚙️ 環境需求

```python
# requirements: streamlit, requests, pandas, numpy, plotly,
#               yfinance, beautifulsoup4, lxml, finmind
# 金鑰：FINMIND_TOKEN、GEMINI_API_KEY（st.secrets 或 os.environ）
# 可選：PROXY_HOST / PROXY_PORT / PROXY_USER / PROXY_PASS（NAS Proxy）
```

---

## 1️⃣ 總經狀態層 — `macro_state_locker.py` + `market_strategy.py`

```python
from macro_state_locker import (
    calculate_system_state_bias240,  # 規則引擎：計算總經狀態
    lock_system_state,               # 寫入 macro_state.json（不呼叫 AI）
    load_macro_state,                # 讀取實體狀態鎖
    MacroStateLocker,                # 完整流程（含 AI 判讀 + 原子寫入）
)
from market_strategy import (
    market_regime,                   # 大盤狀態判斷 v4.0
    get_market_assessment,           # 整合版市場評估（含 regime + score）
    portfolio_exposure,              # bull→80% / neutral→50% / bear→20%
)

# 規則引擎（不呼叫 AI，純 Python 計算）
macro_numbers = {
    "bias240": 12.5,       # 加權指數與 240MA 乖離率(%)
    "vix": 18.0,
    "pmi": 51.2,
    "m1b_m2_spread": -0.5, # M1B-M2 利差(pp)
}
system_state = calculate_system_state_bias240(macro_numbers)
# → {
#     "market_regime":         "bull" / "neutral" / "bear",
#     "systemic_risk_level":   "low" / "medium" / "high",
#     "exposure_limit_pct":    80,    # 建議最高曝險(%)
#     "Macro_Phase":           "擴張" / "趨緩" / "衰退" / "復甦",
#   }

# 直寫鎖（不呼叫 AI）
lock_system_state(system_state)

# 完整 AI 流程（AI 生成判讀報告 + 原子寫入）
locker = MacroStateLocker(llm_client=default_gemini_call)
locker.execute_and_lock(
    system_state=system_state,
    news_list=["聯準會暗示降息", "台積電法說優於預期"],
    macro_context="PMI 連續 3 個月擴張",
)

# 讀回狀態鎖
state = load_macro_state("macro_state.json")
# → {"market_regime": "bull", "exposure_limit_pct": 80,
#    "ai_verdict": str, "locked_at": "2025-04-22T08:00:00", ...}

# 大盤狀態判斷（需已取得指數 df）
assessment = get_market_assessment(
    df_index=df_taiex,          # 含 close/volume 欄位
    foreign_net=50000,          # 外資單日淨買超（張）
    m1b_m2_gap=-0.5,            # 本月 M1B-M2 利差
    m1b_m2_prev=-0.3,           # 上月 M1B-M2 利差
)
# → {"regime": "bull", "score": 7, "max_score": 10,
#    "exposure": 0.80, "label": "多頭", "index_close": 21500, ...}
```

---

## 2️⃣ 先行指標層 — `leading_indicators.py`

```python
from leading_indicators import (
    build_leading_fast,   # 主入口：純 FinMind，無 TAIFEX 爬蟲
    finmind_get,          # FinMind API v4 單次查詢
    taifex_pcr,           # 選擇權 PCR 批量查詢
    build_ai_data_table,  # DataFrame → AI 純文字表格
)

df_leading = build_leading_fast(days=7, token=FINMIND_TOKEN)
# → DataFrame，columns:
#   日期 / 成交量 / 外資淨買超 / 投信淨買超 / 自營淨買超
#   外資大小單 / 前五大留倉 / 前十大留倉
#   選PCR / 外(選)未平倉 / 韭菜指數

ai_table = build_ai_data_table(df_leading)   # → str（tab-separated）
```

---

## 3️⃣ 個股數據層 — `data_loader.py` + `tw_stock_data_fetcher.py`

```python
from data_loader import StockDataLoader, fetch_financial_statements
from tw_stock_data_fetcher import fetch_tw_financials  # Proxy 備援

loader = StockDataLoader()

# 價格 + 籌碼 + 融資 完整資料
df, err, stock_name = loader.get_combined_data(
    stock_id="2330",
    days=400,
    use_adjusted=True,
)
# df columns: open/high/low/close/volume/MA5/MA20/MA60/MA120
#             外資買超/投信買超/自營買超/融資餘額/融資使用率

# 月營收
df_rev, err = loader.get_monthly_revenue("2330")
# df_rev columns: date / revenue / yoy_pct / mom_pct

# 季財報（3年）
df_fin, err = loader.get_quarterly_data("2330")
# df_fin columns: date / revenue / gross_margin / 毛利率 / 是否金融股 ...

# 最新一季財務指標（MJ 體系）
fd = fetch_financial_statements("2330", token=FINMIND_TOKEN)
# → {
#     "現金佔總資產(%)":   float,
#     "應收帳款天數":       float,
#     "OCF(千)":           float,
#     "流動負債(千)":      float,
#     "存貨(千)":          float,
#     "應收帳款(千)":      float,
#     "總資產(千)":        float,
#     "總負債(千)":        float,
#     "股東權益(千)":      float,
#     "非流動負債(千)":    float,
#     "固定資產(千)":      float,
#     "長期投資(千)":      float,
#     "流動資產(千)":      float,
#     "現金(千)":          float,
#     "毛利率(%)":         float,
#     "負債比率(%)":       float,
#     "ROE(%)":            float,
#     "資本支出(千)":      float,
#     "現金股利(千)":      float,
#     "營業收入(千)":      float,
#     "稅後淨利(千)":      float,
#     "存貨前期(千)":      float,
#     "is_finance":        bool,   # 金融特許行業旗標
#   }
# 失敗時回傳 {"error": "..."}

# Proxy 備援（Goodinfo + MOPS，格式相容 fetch_financial_statements）
fd_proxy = fetch_tw_financials("2330", is_finance=False)
```

---

## 4️⃣ AI 分析層 — `ai_engine.py`

```python
from ai_engine import (
    analyze_stock_trend,        # 個股深度分析（5章節完整報告）
    fetch_news_summary,         # 即時新聞摘要（Gemini + Google Search）
    analyze_leading_indicators, # 先行指標 AI 判讀
    generate_daily_report,      # 每日戰情摘要
    generate_quick_summary,     # 快速收盤摘要（1段文字）
)

# 個股完整分析
report = analyze_stock_trend(
    api_key=GEMINI_KEY,
    stock_id="2330",
    stock_name="台積電",
    df=df,                               # get_combined_data 的 df
    fundamental_summary="毛利率53%，連3季成長",  # 可選
)
# → str：K線型態 / 均線架構 / 籌碼分析 / 產業定位 / 操作策略

# 即時新聞
news = fetch_news_summary(GEMINI_KEY, "2330", "台積電")  # → str

# 先行指標判讀
lead_text = analyze_leading_indicators(GEMINI_KEY, df_leading)  # → str

# 每日戰情
daily = generate_daily_report(
    api_key=GEMINI_KEY,
    market_info=assessment,         # get_market_assessment 的結果
    top_stocks=[{"id": "2330", "score": 82}, ...],
    risk_alerts=["VIX 急升"],
)
# → str：大盤判讀 / 個股建議 / 風險提醒
```

---

## 5️⃣ 量化評分層 — `scoring_engine.py`

```python
from scoring_engine import (
    score_single_stock,              # 主入口：全維度評分
    calc_trend_score,                # 均線多頭排列評分
    calc_chip_score,                 # 籌碼評分（外資/投信/自營）
    calc_momentum_score,             # 動能評分（RSI/Sharpe/ATR）
    calc_fundamental_score,          # 月營收 YoY 基本面評分
    calc_quality_score,              # 季財報品質評分
    calc_forward_momentum_score,     # 前瞻動能評分（FGMS）
    calc_leading_indicators_detail,  # 6大先行指標評分明細
    check_vcp_atr_filter,            # VCP 波動收縮確認
    calc_atr_stop,                   # ATR 動態停損計算
    calc_rr_ratio,                   # 盈虧比計算
    calculate_position_size,         # 動態倉位計算
)

# 完整個股評分（主入口）
result = score_single_stock(
    df=df,
    stock_id="2330",
    stock_name="台積電",
    foreign_buy=50000,    # 張，單日外資淨買超
    trust_buy=10000,
    dealer_buy=2000,
    short_ratio=0.35,     # 融資使用率
    inst_consec_buy=5,    # 法人連續買超天數
    regime="bull",        # market_regime 的輸出
    revenue_df=df_rev,    # get_monthly_revenue 的輸出（可選）
    quarterly_df=df_fin,  # get_quarterly_data 的輸出（可選）
)
# → {
#     "total":           float,  # 0-100 加權總分
#     "trend":           float,  # 均線評分
#     "momentum":        float,  # 動能評分
#     "chip":            float,  # 籌碼評分
#     "volume":          float,  # 量能評分
#     "risk":            float,  # 風險評分（越高越安全）
#     "fundamental":     float,  # 月營收基本面評分
#     "grade":           str,    # "A" / "B" / "C"
#     "momentum_signal": str,    # 動能訊號描述
#     "VCP_ATR_pass":    bool,   # VCP 確認
#   }

# 前瞻動能（FGMS，需季財報）
fgms = calc_forward_momentum_score(
    quarterly_df=df_fin,
    bs_cf_df=fd,          # fetch_financial_statements 的輸出
    is_finance=fd.get("is_finance", False),
)
# → {"fgms": float, "fgms_label": str, "cl_score": float,
#    "inv_divergence": float, "capex_score": float, ...}

# 6大先行指標明細
indicators_detail = calc_leading_indicators_detail(
    rev_df=df_rev,
    qtr_df=df_fin,
    bs_cf_df=fd,
)
# → list of 6 dicts:
#   [{"id":"I1","module":"月營收","name":"月營收加速",
#     "signal":"🟢","value":str,"detail":str}, ...]

# ATR 停損
atr_stop = calc_atr_stop(df, entry_price=850.0, multiplier=1.5)
# → {"stop_loss": 823.5, "atr": 17.7, "stop_pct": -3.1, "method": "ATR×1.5"}

# 盈虧比
rr = calc_rr_ratio(entry_price=850, stop_loss=823.5, target_price=950)
# → {"rr": 3.8, "pass": True, "target": 950, "risk_amt": 26.5, "label": "良好"}

# 倉位大小
pos = calculate_position_size(
    total_capital_twd=1_000_000,
    entry_price=850.0,
    atr_value=17.7,
    max_risk_pct=0.015,    # 單筆最大虧損 1.5%
)
# → {"stop_loss": 823.5, "position_sh": 849, "position_lot": 8,
#    "cost": 721_650, "rr_ratio": 3.8, "target_price": 956}
```

---

## 6️⃣ 風控層 — `risk_control.py`

```python
from risk_control import (
    RiskController,
    trailing_stop_trigger,
    stop_loss_trigger,
)

rc = RiskController(portfolio_value=1_000_000, regime="bull")

# 倉位分配
alloc = rc.position_size(price=850.0, weight=None)
# → {"allocated": 80_000, "shares": 94, "lots": 0, "actual_cost": 79_900}

# 停損 / 移動停利檢查
exit_info = rc.check_exit(
    stock_id="2330",
    buy_price=800.0,
    current_price=750.0,
)
# → {"exit_type": "stop_loss" / "trailing" / "hold",
#    "action": "賣出" / "持有", "pnl_pct": -6.25,
#    "stop_price": 736.0, "peak_price": 800.0}

# 移動停利（獨立函式）
triggered = trailing_stop_trigger(
    buy_price=800, peak_price=920, current_price=860,
    trail_pct=0.08, min_profit_pct=0.03,
)  # → bool

# 帳戶回撤監控
dd = rc.update_drawdown(current_value=940_000)
# → {"peak_value": 1_000_000, "drawdown_pct": -6.0,
#    "trading_suspended": False, "status": "正常"}

# 全倉報告
report = rc.full_report(positions=[
    {"stock_id": "2330", "buy_price": 800, "current_price": 850, "shares": 100},
])
# → {"total_value": float, "unrealized_pnl": float,
#    "positions": list, "drawdown": dict, "cash_check": dict}
```

---

## 7️⃣ Proxy / Secrets 設定

```toml
# .streamlit/secrets.toml
FINMIND_TOKEN  = "your_finmind_token"
GEMINI_API_KEY = "your_gemini_key"

# 以下為可選 NAS Proxy（無則自動直連）
PROXY_HOST = "192.168.1.x"
PROXY_PORT = "3128"
PROXY_USER = ""          # 無驗證時留空
PROXY_PASS = ""
```

---

## 🔗 完整使用範例（最小可執行版）

```python
import os
from data_loader        import StockDataLoader, fetch_financial_statements
from market_strategy    import get_market_assessment
from scoring_engine     import score_single_stock, calc_leading_indicators_detail
from risk_control       import RiskController, calc_atr_stop
from ai_engine          import analyze_stock_trend
from leading_indicators import build_leading_fast
from macro_state_locker import load_macro_state

FINMIND_TOKEN = os.environ["FINMIND_TOKEN"]
GEMINI_KEY    = os.environ["GEMINI_API_KEY"]
STOCK_ID      = "2330"

# Step 1: 總經狀態（讀已鎖定的裁決）
state  = load_macro_state()
regime = state.get("market_regime", "neutral")

# Step 2: 先行指標
df_leading = build_leading_fast(days=7, token=FINMIND_TOKEN)

# Step 3: 個股數據
loader = StockDataLoader()
df, err, name = loader.get_combined_data(STOCK_ID, days=400)
df_rev, _     = loader.get_monthly_revenue(STOCK_ID)
df_fin, _     = loader.get_quarterly_data(STOCK_ID)
fd            = fetch_financial_statements(STOCK_ID, token=FINMIND_TOKEN)
if "error" in fd:
    raise RuntimeError(fd["error"])

# Step 4: 評分
result     = score_single_stock(
    df=df, stock_id=STOCK_ID, stock_name=name,
    regime=regime, revenue_df=df_rev, quarterly_df=df_fin,
)
indicators = calc_leading_indicators_detail(df_rev, df_fin, fd)

# Step 5: 停損 + 風控
entry    = df["close"].iloc[-1]
atr_stop = calc_atr_stop(df, entry_price=entry)
rc       = RiskController(portfolio_value=1_000_000, regime=regime)
alloc    = rc.position_size(price=entry)

# Step 6: AI 分析
report = analyze_stock_trend(GEMINI_KEY, STOCK_ID, name, df)

print(f"[{name}] 總分={result['total']} 等級={result['grade']}")
print(f"停損={atr_stop['stop_loss']} 分配={alloc['allocated']:,}元")
print(report)
```

---

## 重點說明（貼到其他專案時附上）

- `df` 欄位：`open/high/low/close/volume` + `MA5/MA20/MA60/MA120` + `外資/投信/自營買超`
- `fd`（`fetch_financial_statements`）失敗時回傳 `{"error": "..."}` 需上層檢查
- `fetch_tw_financials()` 為 Proxy 備援，與 `fd` 格式相容，可直接互換
- `@st.cache_data` 已套在 `StockDataLoader` 主要方法，Streamlit 環境自動快取
- 非 Streamlit 環境直接 import，Proxy 自動降級直連（不需改程式碼）
- `is_finance=True` 代表金融特許行業（銀行/保險），評分引擎與體檢引擎均已適配
- `calc_leading_indicators_detail` 回傳 `list[dict]`，`signal` 欄位為 🟢/🟡/🔴/⚪
