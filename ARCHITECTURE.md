# 台股 AI 戰情室 — 技術規格書

> **版本**：v6.4　|　**最後更新**：2026-04-15　|　**狀態**：完成 ✅
>
> 本文件為系統架構師視角的唯讀規格書，不含任何實作程式碼。

---

## 目錄

1. [目錄結構](#1-目錄結構)
2. [分層架構](#2-分層架構)
3. [資料流向](#3-資料流向)
4. [核心函式 IO 定義](#4-核心函式-io-定義)

---

## 1. 目錄結構

### 1.1 專案根目錄

```
my-stock-dashboard/
│
├── 🔵 應用層 (Application)
│   └── app.py
│
├── 🟢 資料層 (Data Layer)
│   ├── data_loader.py
│   ├── daily_checklist.py
│   └── leading_indicators.py
│
├── 🟡 評分層 (Scoring Layer)
│   ├── scoring_engine.py
│   ├── v4_strategy_engine.py
│   └── v5_modules.py
│
├── 🟠 策略層 (Strategy Layer)
│   ├── market_strategy.py
│   ├── risk_control.py
│   └── backtest_engine.py
│
├── 🟣 視覺化層 (Visualization Layer)
│   ├── chart_plotter.py
│   └── etf_dashboard.py
│
├── 🔴 AI 層 (AI Layer)
│   ├── ai_engine.py
│   └── unified_decision.py
│
├── ⚙️ 基礎設施 (Infrastructure)
│   ├── config.py
│   ├── stock_names.py
│   └── financial_debug_helper.py
│
└── 📁 支援檔案 (Support Files)
    ├── .streamlit/config.toml
    ├── requirements.txt
    ├── pytest.ini
    ├── STATE.md
    └── CLAUDE.md
```

### 1.2 各檔案職責說明

#### 應用層

| 檔案 | 行數 | 職責 |
|------|-----:|------|
| `app.py` | ~7,300 | Streamlit 主程式；協調所有模組、渲染 10 個分析 Section 與 6 個主頁籤；管理 session_state 生命週期 |

#### 資料層

| 檔案 | 行數 | 職責 |
|------|-----:|------|
| `data_loader.py` | ~1,435 | 從 TWSE T86/TPEx、FinMind API 抓取個股 OHLCV 與三大法人進出明細；含 process-level cache 與備援邏輯 |
| `daily_checklist.py` | ~733 | 每日市場總覽資料抓取（三大法人、融資、ADL、yfinance 國際指數）；同時提供 `section_header`、`kpi` 等共用 UI 元件 |
| `leading_indicators.py` | ~1,173 | 抓取 TAIFEX 期貨/選擇權/PCR、FinMind 未平倉量、TWSE 成交量、組建先行指標 DataFrame |

#### 評分層

| 檔案 | 行數 | 職責 |
|------|-----:|------|
| `scoring_engine.py` | ~1,201 | 多因子健康評分（趨勢 25% + 動能 20% + 籌碼 20% + 量價 15% + 風險 10% + 基本面 10%）；VCP/ATR/Bollinger 訊號偵測 |
| `v4_strategy_engine.py` | ~371 | v4 相對籌碼計算（外資/投信佔流通股比）與總體否決訊號（VIX + 外資期貨 → 紅黃綠燈限倉） |
| `v5_modules.py` | ~443 | v5 進階模組：基本面領先指標、RS 相對強度 Z-Score、估值區間（P/E + P/B）、Bollinger 突破、股息殖利率情境 |

#### 策略層

| 檔案 | 行數 | 職責 |
|------|-----:|------|
| `market_strategy.py` | ~213 | 市場多空判斷（5 分制評分 → bull / neutral / caution / bear）與對應建議持股比例 |
| `risk_control.py` | ~221 | 固定停損 (-8%)、追蹤停利 (-7%)、ATR 動態停損、投資組合層級風控（最大回撤 / 現金下限） |
| `backtest_engine.py` | ~264 | MA 交叉與 MA+RSI 策略回測；Walk-Forward Test（3 年訓練 / 12 個月測試滾動窗口）|

#### 視覺化層

| 檔案 | 行數 | 職責 |
|------|-----:|------|
| `chart_plotter.py` | ~574 | Plotly 5 子圖（K 線 + 成交量 + 外資 + 投信 + 自營/融資）、月營收趨勢圖、季度財務圖 |
| `etf_dashboard.py` | ~2,263 | ETF 四子頁（診斷/組合/回測/AI）；NAV 折溢價、年線乖離率、VCP、追蹤誤差、蒙地卡羅模擬、板塊熱力圖 |

#### AI 層

| 檔案 | 行數 | 職責 |
|------|-----:|------|
| `ai_engine.py` | ~734 | Gemini 2.5-Flash 個股趨勢分析、新聞摘要（Google Search Grounding）、每日市場摘要、先行指標解讀 |
| `unified_decision.py` | ~231 | 統一投資決策模組；自動路由 stock / ETF / portfolio 三套 Prompt；輸出結構化 JSON → 3-Card UI |

#### 基礎設施

| 檔案 | 行數 | 職責 |
|------|-----:|------|
| `config.py` | ~83 | 全域常數：均線週期、因子權重表、停損參數、回測手續費、市場曝險比例等 |
| `stock_names.py` | ~174 | 台股代號 ↔ 中文名稱靜態映射表 |
| `financial_debug_helper.py` | ~504 | FinMind 財務欄位別名對應、資料有效性驗證、財務科目分類邏輯 |

### 1.3 支援檔案說明

| 檔案 | 用途 |
|------|------|
| `.streamlit/config.toml` | 暗色主題（base `#0e1117`）、主色 `#1f6feb`、關閉遙測與 CORS |
| `requirements.txt` | 17 個生產依賴（streamlit / pandas / plotly / yfinance / FinMind / google-generativeai 等） |
| `pytest.ini` | 測試探索路徑 `tests/test_*.py`、pythonpath 設定 |
| `STATE.md` | 專案戰情室；版本號、異動紀錄、已知限制（由 CLAUDE.md 規範必讀） |
| `CLAUDE.md` | Claude Code 開發協議 v2.0；規範探索→計劃→執行三步法、防幻覺機制、Anti-Loop 上限 |

### 1.4 程式碼規模概覽

| 分類 | 檔案數 | 總行數 |
|------|-------:|-------:|
| 應用層 | 1 | ~7,300 |
| 資料層 | 3 | ~3,341 |
| 評分層 | 3 | ~2,015 |
| 策略層 | 3 | ~698 |
| 視覺化層 | 2 | ~2,837 |
| AI 層 | 2 | ~965 |
| 基礎設施 | 3 | ~761 |
| **合計** | **17** | **~17,917** |

---

## 2. 分層架構

### 2.1 整體架構圖

```
╔══════════════════════════════════════════════════════════════════════╗
║                    台股 AI 戰情室 v4.0 Pro                            ║
║              Streamlit Cloud  ·  Python 3.14  ·  GitHub              ║
╚══════════════════════════════════════════════════════════════════════╝
                              │
                    ┌─────────▼─────────┐
                    │   app.py (L0)      │  ← 唯一入口；協調所有層
                    │   Streamlit 主程式  │    session_state 管理
                    └─────┬──────┬──────┘
          ┌───────────────┘      └───────────────┐
          ▼                                       ▼
┌─────────────────┐                   ┌─────────────────────┐
│  L5 · AI 層     │                   │  L4 · 視覺化層       │
│  ai_engine.py   │                   │  chart_plotter.py    │
│  unified_       │                   │  etf_dashboard.py    │
│  decision.py    │                   │  daily_checklist.py  │
│  ↕ Gemini API   │                   │  (UI 元件)           │
└────────┬────────┘                   └──────────┬──────────┘
         │                                        │
         └──────────────┬─────────────────────────┘
                        ▼
          ┌─────────────────────────┐
          │  L3 · 策略層             │
          │  market_strategy.py     │  ← 多空判斷 / 倉位比例
          │  risk_control.py        │  ← 停損 / 追蹤停利
          │  backtest_engine.py     │  ← 策略回測 / WFT
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │  L2 · 評分層             │
          │  scoring_engine.py      │  ← 多因子評分 (0-100)
          │  v4_strategy_engine.py  │  ← 相對籌碼 / 總體否決
          │  v5_modules.py          │  ← RS 強度 / 估值區間
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │  L1 · 資料層             │
          │  data_loader.py         │  ← 個股 OHLCV + 法人
          │  daily_checklist.py     │  ← 大盤 / 外資 / ADL
          │  leading_indicators.py  │  ← 期貨 / PCR / 先行
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │  L0 · 基礎設施           │
          │  config.py              │  ← 全域常數
          │  stock_names.py         │  ← 代號映射
          │  financial_debug_       │
          │  helper.py              │  ← 欄位別名
          └─────────────────────────┘

外部服務（唯讀，不屬於任何層）：
  TWSE / TPEx API  ·  TAIFEX POST  ·  FinMind API
  yfinance (Yahoo)  ·  Gemini 2.5-Flash API  ·  dbnomics
```

---

### 2.2 各層職責與設計原則

#### L0 — 基礎設施層（Infrastructure）

| 模組 | 類型 | 設計原則 |
|------|------|---------|
| `config.py` | 純常數（無邏輯） | 所有閾值集中在此，其他層只讀不寫 |
| `stock_names.py` | 靜態映射表 | 不依賴任何外部 API；冷資料 |
| `financial_debug_helper.py` | 工具函式 | 欄位別名標準化，隔離 API 格式變動 |

**設計原則**：零外部依賴；任何層可自由引用；變更只影響此層。

---

#### L1 — 資料層（Data Layer）

| 模組 | 主要外部源 | 快取策略 |
|------|-----------|---------|
| `data_loader.py` | TWSE T86、TPEx、FinMind | `@st.cache_data(ttl=3600)` + process-level dict |
| `daily_checklist.py` | TWSE BFI82U、yfinance、FinMind ADL | `@st.cache_data(ttl=1800)` |
| `leading_indicators.py` | TAIFEX POST、FinMind 未平倉、TWSE 成交量 | `@st.cache_data(ttl=3600)` |

**設計原則**：
- 每個函式只抓一種資料源（單一職責）
- 所有 HTTP 呼叫有 retry + fallback（TWSE IP 封鎖 → FinMind 備援）
- 回傳純 `pd.DataFrame` 或 `dict`，不含任何 UI 邏輯

---

#### L2 — 評分層（Scoring Layer）

| 模組 | 輸入來源 | 輸出格式 |
|------|---------|---------|
| `scoring_engine.py` | L1 DataFrame | `dict`（各因子分數 + 總分 + 訊號） |
| `v4_strategy_engine.py` | L1 DataFrame + L3 市場狀態 | `dict`（相對籌碼比 + 限倉燈號） |
| `v5_modules.py` | L1 DataFrame + 財務數據 | `dict`（RS Z-Score / 估值標籤 / 突破訊號） |

**設計原則**：
- 純函式（Pure Functions）—— 相同輸入永遠相同輸出
- 不呼叫任何 API；不依賴 `st.session_state`
- 評分結果以 0–100 正規化，便於跨模組比較

**因子權重表（依市場狀態動態切換）**：

```
              趨勢    動能    籌碼    量價    風險    基本面
bull（多頭）  30%     25%     20%     15%      5%      5%
neutral（中性）25%    20%     20%     15%     10%     10%
bear（空頭）  15%     10%     15%     15%     25%     20%
```

---

#### L3 — 策略層（Strategy Layer）

| 模組 | 核心判斷邏輯 | 輸出給 |
|------|------------|--------|
| `market_strategy.py` | 5 分制評分 → regime（bull/neutral/caution/bear） | L4 UI、L5 AI、`session_state` |
| `risk_control.py` | 固定停損 / 追蹤停利 / ATR 動態停損 / 最大回撤 | L4 UI |
| `backtest_engine.py` | MA 交叉 / MA+RSI 策略 + Walk-Forward Test | L4 視覺化 |

**設計原則**：
- 策略邏輯與 UI 完全分離
- `market_strategy.regime` 的結果寫入 `session_state['mkt_info']`，供全站各 Tab 共用
- `risk_control.RiskController` 為有狀態類別，封裝單一交易週期的風控計算

---

#### L4 — 視覺化層（Visualization Layer）

| 模組 | 渲染目標 | 依賴層 |
|------|---------|--------|
| `chart_plotter.py` | 個股 K 線 5 子圖、月營收、季度財務 | L1、L2 |
| `etf_dashboard.py` | ETF 四子頁（診斷/組合/回測/AI） | L1、L2、L3、L5 |
| `daily_checklist.py` (UI 部分) | 共用 UI 元件（`section_header`、`kpi`、`sparkline`） | L1 |

**設計原則**：
- 所有 `render_*` 函式接受純資料 dict，不自行抓取資料
- Plotly 圖表以 `st.plotly_chart` 渲染，支援互動縮放
- `st.session_state` gate pattern：大按鈕（開始診斷/計算組合）觸發後持久化狀態，避免 AI 按鈕 rerun 時閘門失效

---

#### L5 — AI 層（AI Layer）

| 模組 | 呼叫方式 | Prompt 架構 |
|------|---------|------------|
| `ai_engine.py` | 直接呼叫 Gemini REST API | 個股分析 / 新聞摘要 / 每日摘要（各自獨立 Prompt） |
| `unified_decision.py` | 透過 `gemini_fn` 回呼（Callback） | `_BASE_RULES` + 型別路由（stock/etf/portfolio） → JSON 輸出 |

**設計原則**：
- AI 層**不依賴**任何評分或策略計算——只接收已整理的資料 dict
- Gemini 回傳強制為 JSON 格式，`re.search` 提取後 `json.loads` 解析
- 結果以 `session_state[_sess_key]` 持久化，跨 rerun 不消失
- Fallback 模型順序：`gemini-2.5-flash-lite` → `gemini-2.5-flash` → `gemini-2.0-flash` → `gemini-2.0-flash-lite`

---

### 2.3 跨層依賴矩陣

```
           L0   L1   L2   L3   L4   L5
L0 基礎     ─    ✗    ✗    ✗    ✗    ✗
L1 資料     ✓    ─    ✗    ✗    ✗    ✗
L2 評分     ✓    ✓    ─    ✗    ✗    ✗
L3 策略     ✓    ✓    ✓    ─    ✗    ✗
L4 視覺     ✓    ✓    ✓    ✓    ─    ✗
L5 AI       ✓    ✗    ✗    ✗    ✗    ─
app.py      ✓    ✓    ✓    ✓    ✓    ✓

✓ = 可引用上層  ✗ = 禁止反向依賴（無循環）
```

> **關鍵約束**：資料永遠向上流（L1 → L2 → L3）；AI 層（L5）直接由 app.py 驅動，繞過評分與策略層，避免增加 LLM 呼叫延遲。

---

### 2.4 環境變數與 Secrets

| 變數名 | 作用範圍 | 用途 |
|--------|---------|------|
| `GEMINI_API_KEY` | L5（ai_engine、unified_decision） | Gemini 2.5-Flash API 金鑰 |
| `FINMIND_TOKEN` | L1（data_loader、leading_indicators） | FinMind 免費帳號（每小時 600 次） |

兩者皆儲存於 Streamlit Secrets（`st.secrets`），部署時不進版控。

---

## 3. 資料流向

### 3.1 全域 Session State 架構

`st.session_state` 是全站各 Tab 的共用記憶體，所有資料載入後寫入此處，避免重複抓取。

```
                       st.session_state（全站共用）
  ┌────────────────────────────────────────────────────────────┐
  │  mkt_info          市場多空評分 dict（regime / score / signals）│
  │  jingqi_info       旌旗均值（有幾% 股票站在均線上）            │
  │  cl_data           每日總覽資料（inst / margin / adl / tw / intl）│
  │  cl_ts             上次更新時間戳（判斷快取是否新鮮）           │
  │  li_latest         先行指標 DataFrame（期貨/PCR/韭菜指數）      │
  │  m1b_m2_info       M1B-M2 Gap + 趨勢方向                      │
  │  bias_info         年線乖離率 BIAS240                          │
  │  defense_mode      bool（全站 AI 衛星訊號是否鎖定）             │
  │  warroom_summary   戰情總結 dict（供 Section 10 AI 總結使用）    │
  │  total_capital_twd 使用者設定的總資金（NT$）                    │
  │  satellite_used    衛星資金已使用量                             │
  └────────────────────────────────────────────────────────────┘
```

---

### 3.2 流程一：個股分析

**觸發**：使用者在「🔬 台股」Tab 輸入股票代號並點擊查詢。

```
使用者輸入
  股票代號 (sid)
  分析週期 (days)
       │
       ▼
┌──────────────────────────────────┐
│  L1 · data_loader                │
│  StockDataLoader.fetch()         │
│  ├─ yfinance：OHLCV 日K線        │
│  ├─ TWSE T86 / TPEx：三大法人     │
│  └─ FinMind：法人備援             │
│                                  │
│  輸出：df_price (DataFrame)       │
│        df_inst  (DataFrame)       │
└──────────┬───────────────────────┘
           │
    ┌──────▼──────┐    ┌──────────────────────────────────────┐
    │ L2·scoring  │    │  L2 · v4_strategy_engine              │
    │  engine     │    │  V4StrategyEngine(df, df_macro, shares)│
    │             │    │  ├─ check_macro_veto()                 │
    │ calc_*()    │    │  │   VIX + 外資期貨 → 紅黃綠燈限倉      │
    │ 趨勢/動能/   │    │  └─ calc_relative_chips()             │
    │ 籌碼/量價/   │    │      外資佔流通股比 / 投信佔流通股比     │
    │ 風險/基本面  │    └──────────────────────────────────────┘
    │             │
    │  輸出：      │    ┌──────────────────────────────────────┐
    │  score dict │    │  L2 · v5_modules                      │
    │  (0~100)    │    │  ├─ calc_relative_strength()  RS Z-Score│
    └──────┬──────┘    │  ├─ calc_valuation_zone()    估值區間   │
           │           │  └─ detect_bollinger_breakout() 突破訊號 │
           │           └──────────────────────────────────────┘
           │                        │
           └────────────┬───────────┘
                        ▼
          ┌─────────────────────────┐
          │  L3 · market_strategy   │
          │  market_regime()        │
          │                         │
          │  輸入：指數/均線/外資/廣度│
          │  輸出：regime dict       │
          │   ├─ regime: bull/neutral│
          │   │          caution/bear│
          │   ├─ score: 0~5         │
          │   └─ exposure_pct       │
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │  L4 · chart_plotter     │
          │  plot_combined_chart()  │
          │  ├─ K 線 + 均線         │
          │  ├─ 成交量              │
          │  ├─ 外資/投信/自營子圖   │
          │  └─ 融資餘額            │
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │  L5 · ai_engine         │
          │  analyze_stock_trend()  │
          │  fetch_news_summary()   │
          │                         │
          │  + unified_decision     │
          │  render_unified_        │
          │  decision()             │
          │  → 3-Card JSON UI       │
          │  (①技術②進場③停損④風控) │
          └─────────────────────────┘

最終輸出：個股分析頁（K線圖 + 評分雷達 + AI 決策三卡）
```

**關鍵資料轉換節點**：

| 節點 | 輸入型別 | 輸出型別 | 備註 |
|------|---------|---------|------|
| `StockDataLoader.fetch()` | `str`（代號）, `int`（天數） | `DataFrame` | yfinance + TWSE/FinMind 合併 |
| `score_single_stock()` | `DataFrame`, 法人資料 | `dict`（各因子分數） | 所有分數正規化至 0–100 |
| `market_regime()` | 指數價/均線/外資/ADL | `dict`（regime + score） | 寫入 `session_state['mkt_info']` |
| `_build_prompt()` | context `dict` | `str`（完整 Prompt） | 路由至 `_STOCK_LOGIC` |

---

### 3.3 流程二：ETF 分析

**觸發**：使用者在「🏦 ETF」Tab 輸入代號並點擊「開始診斷」。

```
使用者輸入
  ETF 代號 (ticker)
       │
       ▼
┌──────────────────────────────────────────────┐
│  L4 · etf_dashboard · render_etf_single()    │
│                                              │
│  並行抓取（ThreadPoolExecutor）：              │
│  ├─ fetch_etf_price()     ← yfinance 日K      │
│  ├─ fetch_etf_nav_history() ← 基金公司 API     │
│  ├─ fetch_etf_dividends()  ← 歷史配息紀錄      │
│  └─ fetch_etf_info()       ← 基本資料/規模      │
│                                              │
│  輸出：price_df / nav_df / div_df / info_dict │
└─────────────────┬────────────────────────────┘
                  │
    ┌─────────────▼──────────────────────────────────┐
    │  指標計算層（純函式，無外部 I/O）                  │
    │                                                │
    │  calc_current_yield()    現金殖利率              │
    │  calc_avg_yield()        近 3 年平均殖利率        │
    │  calc_premium_discount() 折溢價率（市價/NAV-1）   │
    │  calc_tracking_error()   追蹤誤差（vs 指數）      │
    │  calc_mdd()              最大回撤                │
    │  calc_cagr()             年化報酬率              │
    │  calc_sharpe()           Sharpe Ratio           │
    │  check_vcp_signal()      VCP 波動收縮訊號         │
    │  _render_bias()          BIAS240 年線乖離率       │
    └─────────────┬──────────────────────────────────┘
                  │
    ┌─────────────▼──────────────────────────────────┐
    │  AI 決策（選用）                                 │
    │                                                │
    │  unified_decision · render_unified_decision()  │
    │  context type = 'etf'                          │
    │  data = { 殖利率 / BIAS240 / KD / 折溢價 / 大盤 }│
    │                                                │
    │  → Gemini Prompt（_ETF_LOGIC 左側交易鐵血紀律）  │
    │  → JSON → 3-Card UI                            │
    └────────────────────────────────────────────────┘

ETF 組合子頁（render_etf_portfolio）額外流程：
  使用者輸入多支 ETF + 持倉比例
       │
       ├─ 相關係數矩陣計算 → 熱力圖
       ├─ 組合績效回測（CAGR / Sharpe / MDD）
       ├─ _render_monte_carlo()：蒙地卡羅模擬（1000 次路徑）
       └─ _etf_ai_portfolio()：組合 AI 評斷

ETF 回測子頁（render_etf_backtest）額外流程：
  使用者選擇策略 + 時間範圍
       │
       └─ backtest_engine · run_backtest()
            └─ walk_forward_test() → 績效統計 → _etf_ai_backtest()
```

---

### 3.4 流程三：每日市場總覽

**觸發**：使用者點擊「🔄 更新全部總經數據」。

```
點擊更新按鈕
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│  並發任務（ThreadPoolExecutor，6 個 worker）               │
│                                                          │
│  _job_intl()   yfinance 國際指數（SOX/DJI/DXY/10Y）        │
│  _job_tw()     yfinance 台股指數（^TWII/匯率）              │
│  _job_tech()   yfinance 科技股（NVDA/TSMC/AAPL…）          │
│  _job_inst()   daily_checklist · fetch_institutional()    │
│                  └─ TWSE BFI82U → FinMind 備援             │
│  _job_margin() daily_checklist · fetch_margin_balance()   │
│                  └─ TWSE MI_MARGN                         │
│  _job_adl()    daily_checklist · fetch_adl()              │
│                  └─ FinMind TaiwanStockMarketValue         │
└──────────────────────┬───────────────────────────────────┘
                       │（全部完成後合併）
                       ▼
         ┌─────────────────────────┐
         │  leading_indicators     │
         │  build_leading_fast()   │
         │  ├─ TAIFEX 外資期貨淨部位 │
         │  ├─ 選擇權 PCR           │
         │  └─ 韭菜指數             │
         └────────────┬────────────┘
                      │
         ┌────────────▼────────────┐
         │  market_strategy        │
         │  market_regime()        │
         │                         │
         │  輸入（5 個評分維度）：   │
         │  ① 指數 vs MA60/MA120   │
         │  ② 外資現貨淨買賣        │
         │  ③ ADL 廣度指標          │
         │  ④ 均線斜率方向          │
         │  ⑤ 成交量 vs 20日均量    │
         │                         │
         │  輸出：mkt_info dict     │
         │   regime / score /       │
         │   label / exposure_pct  │
         └────────────┬────────────┘
                      │
         ┌────────────▼────────────┐
         │  app.py                 │
         │  _calc_traffic_light()  │
         │                         │
         │  主要驅動：regime        │
         │  緊急覆蓋：defense /     │
         │           health < 40   │
         │                         │
         │  輸出：tl dict           │
         │   icon / label /         │
         │   color / action / sub  │
         │   health / conf          │
         └────────────┬────────────┘
                      │
         ┌────────────▼────────────┐
         │  _render_traffic_light()│
         │  + mkt_info（合併看板）  │
         │                         │
         │  渲染：                  │
         │  ① 主燈號 + 操作建議     │
         │  ② 市場評分/指數/持股%   │
         │  ③ 信號 badges           │
         │  ④ 核心/衛星資金看板     │
         │  ⑤ 衛星資金使用進度條    │
         └─────────────────────────┘
                      │
                      ▼
          後續 Section 渲染（順序執行）：
          Section 一  國際市場（SOX×DXY 四象限）
          Section 二  台股大盤（股匯四象限/ADL）
          Section 三  籌碼（外資/融資門檻）
          Section 四  期現貨（期貨口數）
          Section 七  M1B-M2 Gap + BIAS240
          Section 八  總經拼圖（VIX/NDC/CPI/OECD CLI）
          Section 九  總經 AI 五維度規則分析
          Section 十  AI 總結（Gemini × RSS 新聞）
```

---

### 3.5 資料新鮮度管理

| 快取機制 | 適用資料 | 有效期 | 過期策略 |
|---------|---------|-------|---------|
| `@st.cache_data(ttl=3600)` | 個股 OHLCV、法人、先行指標 | 60 分鐘 | Streamlit 自動失效，重新抓取 |
| `@st.cache_data(ttl=1800)` | 每日大盤資料（BFI82U / ADL） | 30 分鐘 | 同上 |
| `session_state['cl_ts']` | 最後更新時間戳 | 30 分鐘 | 超過後燈號顯示「等待中」，拒絕渲染過期數據 |
| `session_state['_last_inst']` | 三大法人備援快取 | 當次 session | 頁面重新整理後清除 |
| process-level `dict` | TWSE T86 / TPEx 當日資料 | 程序生命週期 | 僅限同一 Python 程序，Cloud 重啟後清除 |

> **防誤判設計**：燈號渲染前先比對 `cl_ts` 與當前時間。若快取超過 30 分鐘，`_tl_placeholder` 顯示「燈號等待中（已過期）」，不渲染過時的多空訊號，避免誤導投資決策。

---

## 4. 核心函式 I/O 定義

> 本節按分層列出各模組的核心公開函式。格式統一為：函式簽名（無實作）、輸入參數、回傳值、副作用。

---

### 4.1 L1 資料層

#### `data_loader.py`

---

**`_get_t86_day(ds)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `ds: str` — 日期字串，格式 `YYYYMMDD` |
| 輸出 | `dict` — `{ '外資': int, '投信': int, '自營商': int }`（單位：仟元），抓取失敗回傳 `{}` |
| 副作用 | 無；結果寫入 process-level `_t86_cache` dict |
| 備援 | TWSE T86 失敗時由 `_fetch_finmind_inst_raw()` 接手 |

---

**`StockDataLoader.fetch(stock_id, days)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `stock_id: str` — 台股代號（如 `'2330'`）；`days: int` — 回溯天數 |
| 輸出 | `tuple[DataFrame, DataFrame]` — `(df_price, df_inst)` |
| `df_price` | 欄位：`Date / Open / High / Low / Close / Volume`（日頻，按日期升序） |
| `df_inst` | 欄位：`Date / 外資 / 投信 / 自營商`（單位：張，正買負賣） |
| 副作用 | `@st.cache_data(ttl=3600)` 快取；TWSE/TPEx → FinMind 備援自動切換 |

---

**`fetch_institutional(date_str)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `date_str: str` — 查詢日期 `YYYYMMDD`（預設當日） |
| 輸出 | `tuple[dict, str]` — `(inst_dict, source_label)` |
| `inst_dict` | `{ '外資及陸資(不含外資自營商)': { 'buy': int, 'sell': int, 'net': int }, ... }` |
| `source_label` | 資料來源標籤（`'TWSE BFI82U'` 或 `'FinMind'`） |
| 副作用 | 無 |

---

**`fetch_margin_balance(date_str)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `date_str: str` — 查詢日期 |
| 輸出 | `tuple[float|None, str]` — `(margin_billion, source_label)` |
| `margin_billion` | 全市場融資餘額（單位：億元）；無資料時回傳 `None` |
| 副作用 | 無 |

---

#### `leading_indicators.py`

---

**`build_leading_fast(days, token)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `days: int` — 回溯天數（建議 7–14）；`token: str` — FinMind API Token |
| 輸出 | `DataFrame \| None` — 欄位：`Date / 外資大小 / PCR / 韭菜指數 / ...`；無資料時回傳 `None` |
| 副作用 | `@st.cache_data(ttl=3600)` 快取；結果存入 `session_state['li_latest']` |
| 用途 | 每日總覽快速版；ETF 多空判斷輸入來源 |

---

**`finmind_get(dataset, data_id, start_ymd, end_ymd, token)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `dataset: str` — FinMind 資料集代號；`data_id: str` — 標的代號；`start/end_ymd: str` — 日期範圍 `YYYYMMDD` |
| 輸出 | `DataFrame` — 原始 FinMind JSON 轉換結果；失敗回傳空 DataFrame |
| 副作用 | 無；HTTP 錯誤時 `print('[FinMind] ❌ ...')` 至 Cloud log |

---

**`taifex_pcr(start_ymd, end_ymd)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `start_ymd, end_ymd: str` — 日期範圍 `YYYYMMDD` |
| 輸出 | `DataFrame` — 欄位：`Date / PCR_OI / PCR_Volume`（Put/Call 比） |
| 副作用 | TAIFEX POST 請求；失敗時回傳空 DataFrame |

---

### 4.2 L2 評分層

#### `scoring_engine.py`

---

**`score_single_stock(df, stock_id, stock_name, **kwargs)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `df: DataFrame` — 個股 OHLCV；`stock_id / stock_name: str`；`kwargs`：`foreign_buy / trust_buy / dealer_buy: int`、`revenue_df / quarterly_df: DataFrame` |
| 輸出 | `dict` — 完整評分結果（見下表） |
| 副作用 | 無（純函式） |

輸出 dict 結構：

| 鍵 | 型別 | 說明 |
|----|------|------|
| `total` | `float` | 綜合總分 0–100 |
| `trend` | `float` | 趨勢分 0–100 |
| `momentum` | `float` | 動能分 0–100 |
| `chip` | `float` | 籌碼分 0–100 |
| `volume` | `float` | 量價分 0–100 |
| `risk` | `float` | 風險分 0–100（分越高風險越低） |
| `fundamental` | `float` | 基本面分 0–100 |
| `grade` | `str` | 評級 `'A+'/'A'/'B'/'C'/'D'` |
| `momentum_signal` | `bool` | VCP 突破訊號 |
| `vcp` | `dict` | VCP 詳細結果（見 `check_vcp_atr_filter`） |

---

**`calc_trend_score(df)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `df: DataFrame` — 需含 `Close / High / Low`（≥120 筆） |
| 輸出 | `float` — 趨勢分 0–100 |
| 邏輯摘要 | MA5>MA20>MA60>MA120 完整多頭排列=100；每跌破一條均線扣分；價格在年線上方加分 |

---

**`check_vcp_atr_filter(df)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `df: DataFrame` — 需含 `High / Low / Close / Volume`（≥60 筆） |
| 輸出 | `dict` — `{ 'signal': bool, 'stage': int, 'contraction': float, 'volume_dry': bool, 'breakout': bool, 'message': str }` |
| 說明 | `stage`：收縮次數（0–3）；`contraction`：最新波幅（越小越好）；`volume_dry`：成交量是否低於 50 日均量 50% |

---

**`calc_atr_stop(df, entry_price, multiplier)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `df: DataFrame`；`entry_price: float`；`multiplier: float`（預設 `config.ATR_MULTIPLIER=1.5`） |
| 輸出 | `dict` — `{ 'stop_price': float, 'atr': float, 'distance_pct': float }` |
| 說明 | `stop_price = entry_price - ATR × multiplier`；`distance_pct`：停損距離佔進場價百分比 |

---

#### `v4_strategy_engine.py`

---

**`V4StrategyEngine.check_macro_veto()`**

| 項目 | 說明 |
|------|------|
| 輸入 | 無（使用 `self.df_macro`：需含 `vix / futures_net / pcr`） |
| 輸出 | `dict` — `{ 'light': 'red'|'yellow'|'green', 'max_position': float, 'reason': str }` |
| 燈號邏輯 | 🔴 red（VIX>25 或外資期貨空單>20,000口）→ max_position ≤ 20%；🟡 yellow（VIX>20 或>10,000口）→ ≤ 50%；🟢 green → ≤ 100% |

---

**`V4StrategyEngine.calc_relative_chips(days)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `days: int` — 計算週期（預設 60） |
| 輸出 | `dict` — `{ 'foreign_ratio': float, 'trust_ratio': float, 'foreign_trend': str, 'trust_trend': str }` |
| 說明 | `foreign_ratio` = 外資近 N 日累積買超 ÷ 發行股數（%）；`trend`：`'accumulate'/'distribute'/'neutral'` |

---

#### `v5_modules.py`

---

**`calc_relative_strength(df_stock, df_market, periods)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `df_stock / df_market: DataFrame`（需含 `Close`）；`periods: list[int]`（預設 `[20, 60, 120]`） |
| 輸出 | `dict` — `{ 'rs_20': float, 'rs_60': float, 'rs_120': float, 'z_score': float, 'label': str }` |
| 說明 | `rs_N = 個股 N 日報酬 - 大盤 N 日報酬`；`z_score`：三週期 RS 的標準化分數；`label`：`'強勢'/'中性'/'弱勢'` |

---

**`calc_valuation_zone(price, eps_ttm, bvps, pb_target)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `price: float`；`eps_ttm: float`（近 12 月 EPS）；`bvps: float`（每股淨值）；`pb_target: float`（目標 P/B，預設 1.5） |
| 輸出 | `dict` — `{ 'pe': float, 'pb': float, 'zone': 'cheap'|'fair'|'rich', 'target_price': float }` |
| 說明 | `zone` 判斷：P/E<15 且 P/B<1 → cheap；P/E>25 或 P/B>2 → rich；其餘 → fair |

---

**`analyze_fundamental_leading(cl_now, cl_prev, capex_now, capex_prev, equity)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `cl_now / cl_prev: float` — 本季/上季合約負債；`capex_now / capex_prev: float` — 本季/上季資本支出；`equity: float` — 實收資本額 |
| 輸出 | `dict` — `{ 'cl_qoq': float, 'capex_ratio': float, 'dragon_signal': bool, 'message': str }` |
| 說明 | `cl_qoq>20% 且 capex_ratio>0.8` → `dragon_signal=True`（龍多股訊號） |

---

### 4.3 L3 策略層

#### `market_strategy.py`

---

**`market_regime(index_close, ma60, ma120, foreign_buy, ad_ratio, ma60_prev, ma120_prev, vol_today, avg_vol_20)`**

| 項目 | 說明 |
|------|------|
| 輸入 | 全部為 `float`；`foreign_buy`：外資現貨淨買超（億元，正買負賣）；`ad_ratio`：ADL 廣度（0–100%） |
| 輸出 | `dict`（mkt_info） — 見下表 |
| 副作用 | 無（純函式）；呼叫方負責寫入 `session_state['mkt_info']` |

輸出 dict 完整欄位：

| 鍵 | 型別 | 說明 |
|----|------|------|
| `regime` | `str` | `'bull' / 'neutral' / 'caution' / 'bear'` |
| `score` | `int` | 0–5（五個維度各 1 分） |
| `max_score` | `int` | 固定為 `5` |
| `label` | `str` | UI 顯示標籤（含 emoji） |
| `color` | `str` | 十六進位色碼 |
| `exposure_pct` | `str` | 建議持股比例（如 `'80%'`） |
| `signals` | `list[str]` | 觸發的加分條件文字清單 |
| `bullrun` | `bool` | 是否進入強多頭（score=5） |
| `index_price` | `float` | 傳入的大盤指數 |
| `ma60 / ma120` | `float` | 傳入的均線值 |

---

**`portfolio_exposure(regime)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `regime: str` — `'bull' / 'neutral' / 'caution' / 'bear'` |
| 輸出 | `float` — 建議股票曝險比例（`0.80 / 0.50 / 0.30 / 0.20`） |
| 副作用 | 無 |

---

#### `risk_control.py`

---

**`RiskController.position_size(price, weight)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `price: float`（股價）；`weight: float`（目標佔衛星資金比例，0–1） |
| 輸出 | `dict` — `{ 'shares': int, 'lots': int, 'cost': float, 'pct_of_portfolio': float }` |
| 限制 | 單檔不超過 `config.MAX_POSITION_PER_STOCK`（10%）；受 `RiskController.max_stock_budget` 上限約束 |

---

**`RiskController.check_exit(stock_id, buy_price, current_price)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `stock_id: str`；`buy_price / current_price: float` |
| 輸出 | `dict` — `{ 'action': 'stop_loss'|'trailing'|'hold', 'reason': str, 'pnl_pct': float }` |
| 邏輯 | 優先檢查固定停損（-8%）→ 再檢查追蹤停利（峰值回落 7%，且已獲利 3%）→ 否則 hold |

---

**`trailing_stop_trigger(buy_price, peak_price, current_price, trail_pct, min_profit_pct)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `buy_price / peak_price / current_price: float`；`trail_pct: float`（預設 `0.07`）；`min_profit_pct: float`（預設 `0.03`） |
| 輸出 | `bool` — `True` 表示觸發追蹤停利，應賣出 |
| 條件 | `current_price ≤ peak_price × (1 - trail_pct)` 且 `peak_price ≥ buy_price × (1 + min_profit_pct)` |

---

### 4.4 L5 AI 層

#### `unified_decision.py`

---

**`render_unified_decision(gemini_fn, context)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `gemini_fn: Callable[[str, int], str]` — Gemini API 回呼函式；`context: dict` — 見下表 |
| 輸出 | `None`（直接渲染至 Streamlit） |
| 副作用 | 寫入 `session_state[f'unified_{type}_{id}']`；呼叫 `st.rerun()` 觸發畫面更新 |

`context` dict 格式：

| 鍵 | 型別 | 說明 |
|----|------|------|
| `type` | `str` | `'stock' / 'etf' / 'portfolio'` |
| `id` | `str` | 唯一識別字（如 `'2330'` / `'0050'` / `'portfolio'`） |
| `data` | `dict` | 傳給 LLM 的結構化數據（自由欄位，依 type 不同而異） |

---

**`_build_prompt(context)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `context: dict`（同上） |
| 輸出 | `str` — 完整 Prompt 字串（`_BASE_RULES` + 型別路由邏輯 + JSON 化 data） |
| 路由 | `type='stock'` → `_STOCK_LOGIC`；`type='etf'` → `_ETF_LOGIC`；`type='portfolio'` → `_PORTFOLIO_LOGIC` |

---

**`_render_cards(parsed, ctx_type)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `parsed: dict` — Gemini 回傳的 JSON（需含 `summary / action_advice / precautions`）；`ctx_type: str` |
| 輸出 | `None`（渲染 3 張卡片至 Streamlit） |
| Card 1 | 全寬主卡：`summary`（依 🟢/🟡/🔴 自動變色） |
| Card 2 | 左欄：`action_advice`（股票模式標籤：②進場③停損；其他模式：具體建議） |
| Card 3 | 右欄：`precautions`（股票模式標籤：④風控；其他模式：風險警示） |

---

#### `ai_engine.py`

---

**`analyze_stock_trend(api_key, stock_id, stock_name, df, fundamental_summary)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `api_key: str`；`stock_id / stock_name: str`；`df: DataFrame`（OHLCV）；`fundamental_summary: str`（選填） |
| 輸出 | `str` — Gemini 生成的趨勢分析文字（Markdown 格式） |
| 副作用 | 無；API 失敗時回傳 `'⚠️ ...'` 開頭的錯誤訊息 |
| Fallback | `gemini-2.5-flash-lite` → `gemini-2.5-flash` → `gemini-2.0-flash` → `gemini-2.0-flash-lite` |

---

**`generate_daily_report(api_key, market_info, top_stocks, risk_alerts)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `api_key: str`；`market_info: dict`（regime/score）；`top_stocks: list[dict]`；`risk_alerts: list[str]` |
| 輸出 | `str` — 每日市場摘要（300 字內，含多空評估與今日重點） |
| 副作用 | 無 |

---

### 4.5 app.py 核心協調函式

---

**`_calc_traffic_light(mkt_info, jingqi_info, cl_data, li_latest)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `mkt_info: dict`（`market_regime()` 輸出）；`jingqi_info: dict`（旌旗均值）；`cl_data: dict`（每日總覽）；`li_latest: DataFrame \| None` |
| 輸出 | `dict \| None` — `None` 表示資料不足；否則見下表 |
| 保守優先 | `_defense=True` 或 `_health<40` → 強制紅燈（覆蓋 regime） |

輸出 dict 欄位：

| 鍵 | 型別 | 說明 |
|----|------|------|
| `regime` | `str` | 來自 `mkt_info`（bull/neutral/caution/bear） |
| `icon / color / label` | `str` | 顯示用（🔴/🟡/🟢 + 十六進位色 + 操作標籤） |
| `action / sub` | `str` | 主要操作建議與補充說明 |
| `health` | `float` | 綜合健康度 0–100（`jqavg×0.4 + score_norm×0.4 + fnet_bonus×0.2`） |
| `defense` | `bool` | Defense Mode 是否觸發 |
| `conf` | `int` | 資料信心指數 0–100%（5 個資料源各 20%） |

---

**`_render_traffic_light(placeholder, tl, mkt_info)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `placeholder: st.empty`；`tl: dict \| None`；`mkt_info: dict \| None`（選填，用於顯示評分/信號） |
| 輸出 | `None`（渲染至 placeholder） |
| 副作用 | 渲染：主燈號卡（含信號 badges + 指數 + 持股建議）→ Defense Mode 警告 → 核心/衛星資金看板 → 進度條 |
| 合併邏輯 | `mkt_info` 提供的原始 regime 資訊整合顯示，以 `tl` 的保守信號為主 |

---

**`gemini_call(prompt, max_tokens)`**

| 項目 | 說明 |
|------|------|
| 輸入 | `prompt: str`；`max_tokens: int`（預設 800） |
| 輸出 | `str` — Gemini 回傳文字；失敗時回傳 `'⚠️ ...'` |
| Fallback 順序 | `gemini-2.5-flash-lite` → `gemini-2.5-flash` → `gemini-2.0-flash` → `gemini-2.0-flash-lite` |
| 副作用 | 失敗時 `print('[AI-LLM/Gemini] ❌ ...')` 寫入 Cloud log |

---
