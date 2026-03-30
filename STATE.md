# STATE.md — 台股 AI 戰情室

> 上次更新：2026-03-30 | 分支：`claude/analyze-test-coverage-070Kf`

---

## 核心檔案摘要

| 檔案 | 一句話簡介 |
|---|---|
| `app.py` | 主 Streamlit UI，含所有 Tab 頁面與使用者互動邏輯（5531 行） |
| `data_loader.py` | 從 yfinance / FinMind 抓取股價、財報、月營收等原始資料 |
| `scoring_engine.py` | 多因子評分引擎：趨勢/動能/籌碼/量價/風險/基本面加權計算 |
| `risk_control.py` | 單股停損停利 + 部位計算 + 組合風控（RiskController 類別） |
| `backtest_engine.py` | 回測框架：MA Cross / MA+RSI 策略，計算 CAGR、盈虧比 |
| `ai_engine.py` | Google Gemini AI 整合：新聞摘要、趨勢分析、每日報告生成 |
| `chart_plotter.py` | Plotly 圖表渲染：K 線、月營收、季報、合併走勢圖 |
| `leading_indicators.py` | 期貨未平倉、PCR、三大法人、ADL 等總體市場先行指標 |
| `daily_checklist.py` | 每日盤前清單：法人追蹤、融資餘額、ADL 動能掃描 |
| `market_strategy.py` | 多/空/中性市場狀態判斷 + 建議持股曝險比例 |
| `v4_strategy_engine.py` | V4.0 進階選股策略引擎（含回測能力） |
| `v5_modules.py` | 基本面領先指標、布林突破、股息殖利率等 V5 模組 |
| `financial_debug_helper.py` | FinMind / GoodInfo 財務資料除錯與欄位映射工具 |
| `config.py` | 全域設定常數（權重/風控參數/回測設定） |
| `stock_names.py` | 台股代號與中文名稱對照查詢表 |

---

## 目前開發進度

### 進行中
- **任務**：為 `scoring_engine.py` 與 `risk_control.py` 撰寫單元測試
- **已完成**：
  - `pytest.ini`（測試設定）
  - `tests/conftest.py`（共用 fixture）
  - `tests/test_risk_control.py`（45 個測試，涵蓋全部函數）
- **待完成**：
  - `tests/test_scoring_engine.py`（尚未寫入）
  - 執行測試、修正失敗項目
  - Commit & push 所有未追蹤檔案

### 已完成
- 測試覆蓋率分析報告（提交 `claude/analyze-test-coverage-070Kf` 分支）

---

## 待修復 Bug 清單

| 優先 | 位置 | 問題描述 |
|---|---|---|
| 🔴 高 | `app.py` Tab1 §4 | 外資先行指標數值未完整顯示，需改為抓最後一次有效數據（fallback to last known） |
| 🔴 高 | `app.py` Tab1 §3 | 三大法人＋融資無資料，需改為抓最後一次有效數據 |
| 🔴 高 | `app.py` Tab2 §C | 財報領先指標（財報 YoY）無法抓取，需確認 FinMind/GoodInfo API 呼叫邏輯 |
| 🔴 高 | `app.py` Tab2 §D | 月營收趨勢無法抓取，需確認 FinMind 月營收 API 呼叫邏輯 |
| 🟡 中 | `stop-hook-git-check.sh` | `no_pr_reminder` 文字與 Claude 系統提示詞重複，可清理 |
