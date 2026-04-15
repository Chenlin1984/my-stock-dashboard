# 台股 AI 戰情室 — 技術規格書

> **版本**：v6.4　|　**最後更新**：2026-04-15　|　**狀態**：撰寫中（Step 1/5 完成）
>
> 本文件為系統架構師視角的唯讀規格書，不含任何實作程式碼。

---

## 目錄

1. [目錄結構](#1-目錄結構)
2. [分層架構](#2-分層架構)（Step 2）
3. [資料流向](#3-資料流向)（Step 3）
4. [核心函式 IO 定義](#4-核心函式-io-定義)（Step 4）

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

<!-- Step 3, 4 將於後續步驟補充 -->
