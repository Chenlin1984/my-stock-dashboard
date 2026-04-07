# STATE.md — 台股 AI 戰情室

> 上次更新：2026-04-07（系統排毒 + 協議 v2.0 重置）| 分支：`claude/analyze-test-coverage-070Kf`

---

## 核心檔案摘要

| 檔案 | 一句話簡介 |
|---|---|
| `app.py` | 主 Streamlit UI，6 主 Tab（總經/熱力板塊/台股/ETF/資料診斷/策略手冊），共 5439 行 |
| `etf_dashboard.py` | ETF 儀表板：診斷/組合/回測/AI/資料健診/熱力圖，共 1876 行 |
| `scoring_engine.py` | 多因子評分引擎（動態權重/VCP ATR/軋空加分），覆蓋率 91% |
| `risk_control.py` | 單股停損停利 + 部位計算 + 組合風控（RiskController） |
| `config.py` | 全域設定：WEIGHT_TABLES（bull/neutral/bear 動態權重）+ 風控參數 |
| `market_strategy.py` | 多/空/中性市場判斷 + 建議持股曝險比例 |
| `daily_checklist.py` | 三大法人/融資/ADL/先行指標抓取與顯示 |
| `leading_indicators.py` | 期貨未平倉、PCR、ADL 等先行指標 |
| `data_loader.py` | yfinance / FinMind 股價、財報、月營收抓取 |
| `ai_engine.py` | Google Gemini AI 整合 |
| `backtest_engine.py` | 回測框架：CAGR/Sharpe/MDD |
| `chart_plotter.py` | Plotly 圖表渲染（K 線、月營收、季報） |
| `CLAUDE.md` | 核心治理協議 v2.0（§1~§5） |

---

## 系統狀態

| 項目 | 狀態 |
|---|---|
| 測試 | ✅ 197 passed，0 failed |
| 覆蓋率 | `scoring_engine.py` 91% |
| 部署 | Streamlit Cloud（`main` 分支） |
| 開發分支 | `claude/analyze-test-coverage-070Kf` |

---

## Tab 結構

```
🌍 總經 | 🗺️ 熱力板塊 | 🔬 台股 | 🏦 ETF | 🔎 資料診斷 | 📚 策略手冊
台股子Tab：個股分析 | 比較×排行
ETF子Tab：ETF診斷 | ETF組合 | ETF回測 | ETF AI
```

---

## 已完成功能清單

| # | 功能 |
|---|---|
| 1 | Tab 重組（11→6 主 Tab，巢狀子 Tab） |
| 2 | 動態因子權重（bull/neutral/bear 自動切換） |
| 3 | VCP ATR 波動收縮確認濾網 |
| 4 | 軋空加分（券資比>30% + 法人連買≥3天） |
| 5 | ETF 折溢價 5 段買賣訊號大卡片 |
| 6 | GICS 產業曝險上限 ≤30% 警示 |
| 7 | 蒙地卡羅模擬 10,000 路徑（P10/50/90） |
| 8 | VaR 風險值（歷史模擬 + 參數法，95%/99%，月度√21） |
| 9 | 配息日曆 × 12 個月現金流預估圖 |
| 10 | 再平衡含具體股數（現價 × 建議張數） |
| 11 | 回測評級卡（CAGR/Sharpe/MDD ⭐評級） |
| 12 | 老師結論全站動態化（app.py 12 節 + etf_dashboard.py 8 節） |
| 13 | 比較×排行：EPS/毛利率/殖利率欄位 + 完整 AI 分析 |
| 14 | 個股分析頂部趨勢儀表板（現價/MA/燈號） |

---

## 已修復 Bug

| # | 位置 | 問題 |
|---|---|---|
| 1 | `data_loader.py` | list-1 TypeError 季財報解析失敗 |
| 2 | `app.py` Tab1 §3 | 三大法人 API 失敗無 fallback |
| 3 | `leading_indicators.py` | 顏色配置正負值錯誤 |
| 4 | `app.py` Tab2 §D | 月營收/季財報無快取 fallback |
| 5 | `app.py` | MA20/MA100 sentinel 0→None，趨勢誤算 |
| 6 | `app.py` Tab1 §一 | `ci` 未定義 NameError |
| 7 | `app.py` Tab1 §二 | `tc` 未定義 NameError |
| 8 | `market_strategy.py` | 盤中外資 0.0 誤顯為「賣超」→改為「待更新」 |

---

## 待辦

| 優先 | 項目 |
|---|---|
| 低 | PR #9 merge 至 main（請執行 `gh pr merge 9 --merge --delete-branch`） |
