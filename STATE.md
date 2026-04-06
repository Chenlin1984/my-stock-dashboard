# STATE.md — 台股 AI 戰情室

> 上次更新：2026-04-06（舊Tab編號引用全數清除）| 分支：`claude/analyze-test-coverage-070Kf`

---

## 核心檔案摘要

| 檔案 | 一句話簡介 |
|---|---|
| `app.py` | 主 Streamlit UI，11 個 Tab（①~⑤股票 + ⑥~⑨ETF + ⑩資料健診 + ⑪熱力圖），共 5627 行 |
| `etf_dashboard.py` | ETF AI 儀表板：Tab⑥~⑨ ETF分析 + Tab⑩資料健診 + Tab⑪產業熱力圖 |
| `scoring_engine.py` | 多因子評分引擎（動態權重/VCP ATR/軋空加分），覆蓋率 91% |
| `risk_control.py` | 單股停損停利 + 部位計算 + 組合風控（RiskController 類別） |
| `config.py` | 全域設定：WEIGHT_TABLES（bull/neutral/bear 動態權重）+ 風控參數 |
| `backtest_engine.py` | 回測框架：MA Cross / MA+RSI 策略，CAGR/盈虧比 |
| `ai_engine.py` | Google Gemini AI 整合：新聞摘要、趨勢分析、每日報告 |
| `chart_plotter.py` | Plotly 圖表渲染：K 線、月營收、季報、合併走勢圖 |
| `leading_indicators.py` | 期貨未平倉、PCR、三大法人、ADL 等總體市場先行指標 |
| `daily_checklist.py` | 每日盤前清單：法人追蹤、融資餘額、ADL 動能掃描 |
| `market_strategy.py` | 多/空/中性市場狀態判斷 + 建議持股曝險比例 |
| `v4_strategy_engine.py` | V4.0 進階選股策略引擎（含回測能力） |
| `v5_modules.py` | 基本面領先指標、布林突破、股息殖利率等 V5 模組 |
| `data_loader.py` | 從 yfinance / FinMind 抓取股價、財報、月營收等原始資料 |
| `financial_debug_helper.py` | FinMind / GoodInfo 財務資料除錯與欄位映射工具 |
| `stock_names.py` | 台股代號與中文名稱對照查詢表 |
| `CLAUDE.md` | 核心治理協議 v2.0（5板塊：記憶/讀寫/規劃/交付/救援） |

---

## 目前開發進度

### 已完成（本輪 2026-04-05）

**7 項策略升級（全數完成）**

| # | 位置 | 項目 |
|---|---|---|
| ① | `etf_dashboard.py` `_render_bias()` | BIAS 乖離率 MA20/60/120 + 60日Bar圖 |
| ② | `config.py` `WEIGHT_TABLES` + `scoring_engine.py` | 動態因子權重（bull進攻/bear防禦自動切換） |
| ③ | `scoring_engine.py` `check_vcp_atr_filter()` | VCP ATR5 < ATR20×0.8 波動收縮確認 |
| ④ | `etf_dashboard.py` Tab⑧ `TAX_FACTOR=0.95` | 配息稅費磨損（台灣二代健保） |
| ⑤ | `etf_dashboard.py` `_check_sector_exposure()` | GICS 產業曝險上限 ≤30% 警示 |
| ⑥ | `scoring_engine.py` `calc_short_squeeze_bonus()` | 券資比>30%+法人連買≥3天→+5分 |
| ⑦ | `etf_dashboard.py` `_render_monte_carlo()` | 蒙地卡羅 10,000 路徑，P10/50/90 |

**測試狀態**
- 全部測試：✅ 184 passed，0 failed
- `scoring_engine.py` 覆蓋率：91%

---

## UI 重構進度（2026-04-06，全數完成）

| # | 項目 | 狀態 | 說明 |
|---|---|---|---|
| 1 | Tab 重組 | ✅ | 6 主 Tab：總經/熱力板塊/台股/ETF/資料診斷/策略手冊 |
| 2 | 移除交易日記 | ✅ | `tab6_journal` 整塊刪除 |
| 3 | 移除總經重複 Section 八 | ✅ | 保留保守版「今日唯一結論」 |
| 4 | 個股分析頂部趨勢儀表板 | ✅ | 現價/漲跌%/MA20/MA60/MA120/🟢🟡🔴 趨勢燈號 |
| 5 | ETF 折溢價買賣訊號 | ✅ | 5段建議彩色大卡片（折價強買→溢價嚴禁） |
| 6 | 策略手冊移至最外層 | ✅ | 從台股子Tab移出，成為第6個獨立主Tab |
| 7 | 修正舊Tab編號引用（第一輪） | ✅ | 5處「②③④①」改為Tab名稱，導覽不再錯亂 |
| 8 | 修正舊Tab編號引用（第二輪） | ✅ | 另7處殘留①②③④⑤全數清除（section header + caption） |

### 最終 Tab 結構
```
🌍 總經 | 🗺️ 熱力板塊 | 🔬 台股 | 🏦 ETF | 🔎 資料診斷 | 📚 策略手冊
台股子Tab：個股分析 | 比較×排行
ETF子Tab：ETF診斷 | ETF組合 | ETF回測 | ETF AI
```

## 待辦事項

| 優先 | 項目 |
|---|---|
| 低 | PR #6 合併至 main（已建立，待 merge） |
| 低 | 確認 資料有錯 根本原因（舊Tab編號已清除，若仍有問題需進一步診斷） |

---

## 待修復 Bug 清單

| 優先 | 位置 | 問題描述 |
|---|---|---|
| ✅ 已修 | `data_loader.py:592` | list-1 TypeError 導致季財報永遠無法解析 |
| ✅ 已修 | `app.py` Tab1 §3 | 三大法人＋融資 API 失敗時無 fallback |
| ✅ 已修 | `app.py` Tab1 §4 | 外資先行指標部分欄位 NaN，無 ffill |
| ✅ 已修 | `leading_indicators.py` | 正/負值顏色配置錯誤 |
| ✅ 已修 | `app.py` Tab2 §D | 月營收/季財報無 fallback 快取 |
| ✅ 已修 | `app.py:2671` | 全形分號語法錯誤（U+FF1B） |
