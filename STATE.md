# STATE.md — 台股 AI 戰情室

> 上次更新：2026-04-07（NameError 修復 + 全站假資料審查完成）| 分支：`claude/analyze-test-coverage-070Kf`

---

## 核心檔案摘要

| 檔案 | 一句話簡介 |
|---|---|
| `app.py` | 主 Streamlit UI，6 主 Tab（總經/熱力板塊/台股/ETF/資料診斷/策略手冊），共 5394 行 |
| `etf_dashboard.py` | ETF AI 儀表板：Tab⑥~⑨ ETF分析 + Tab⑩資料健診 + Tab⑪產業熱力圖，共 1800 行 |
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
- 全部測試：✅ 197 passed，0 failed
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

## 最新完成（2026-04-07）

| # | 項目 | 狀態 | 說明 |
|---|---|---|---|
| 9 | 修正 `if True` 多餘嵌套 | ✅ | tab2 資料抓取去掉 `if True: # noqa` wrapper |
| 10 | MA sentinel 修正 | ✅ | tab3 MA20/MA100 默認值從 0 改為 None，趨勢判斷不再誤算 |
| 11 | 多因子評分排行加入 EPS/毛利率/殖利率 | ✅ | ③ 多因子排行表新增 3 欄基本面數據 |
| 12 | 最終建議卡加入基本面 | ✅ | ⑤ 建議卡顯示 EPS + 毛利率% |
| 13 | 完整AI分析恢復 | ✅ | 底部新增「🤖 完整AI投資決策分析」按鈕，呼叫 Gemini |
| 14 | 老師結論各段補充 | ✅ | 每節加入宏爺/朱家泓/孫慶龍/弘爺 teacher_conclusion 卡片 |
| 15 | 基本面數據統一預先計算 | ✅ | `_fund_map` 在顯示前統一計算，③④⑤ 共用，避免重複 API |
| 16 | **Module D** 再平衡含股數 | ✅ | `etf_dashboard.py` 再平衡指令加入現價+建議股數欄位及格式化訊息 |
| 17 | **Module B** VaR 風險值 | ✅ | 歷史模擬法+參數法 95%/99% 日VaR + 月度VaR，插入 ETF組合Tab |
| 18 | **Module C** 配息日曆 | ✅ | 依歷史月份分配年化現金流 + Plotly 12個月長條圖 |
| 20 | **老師結論全站補齊（靜態）** | ✅ | Tab1 §一二四五六 + Tab2 A-F+操作建議，共12節新增 teacher_conclusion 卡片 |
| 21 | **老師結論全面動態化** | ✅ | 所有結論改為根據當下真實數據計算：費半漲跌%、台幣升貶、外資期貨口數、ADL走向、VCP波段、357區間、YoY%、訊號共振計數 |
| 22 | **ETF dashboard 老師結論補齊** | ✅ | `etf_dashboard.py` 新增 `_teacher_conclusion()` + ETF診斷（郭俊宏/孫慶龍/春哥/宏爺×4節）、ETF組合（孫慶龍/弘爺/郭俊宏×3節）、ETF回測（春哥×1節）共 8 處動態卡片 |
| 23 | **Tab3 比較×排行結論動態化** | ✅ | ⑤最終建議、RS對比、③多因子排行、④汰弱留強、AI判讀標題全面改為根據實際評分數據計算 |
| 24 | **NameError 修復** | ✅ | Tab1 §一 teacher_conclusion 插入後導致 `ci` 未定義，補上 `ci = st.columns(len(INTL_UNIT))` |
| 25 | **全站虛假資料審查** | ✅ | 確認無假數據：v4隨機在 `__main__` 區塊（開發測試），蒙地卡羅為演算法本身，所有財務資料來源均為真實 API（FinMind/yfinance/TWSE/TAIFEX） |

## 待辦事項

| 優先 | 項目 |
|---|---|
| 低 | PR #6 合併至 main（已建立，待 merge） |

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
