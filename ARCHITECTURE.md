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

<!-- Step 2, 3, 4 將於後續步驟補充 -->
