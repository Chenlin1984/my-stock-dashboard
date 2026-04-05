# STATE.md — 台股 AI 戰情室

> 上次更新：2026-04-05（7 項策略升級完成，184 tests pass，覆蓋率 91%）| 分支：`claude/analyze-test-coverage-070Kf`

---

## 核心檔案摘要

| 檔案 | 一句話簡介 |
|---|---|
| `app.py` | 主 Streamlit UI，11 個 Tab（①~⑤股票 + ⑥~⑨ETF + ⑩資料健診 + ⑪熱力圖），共 5627 行 |
| `etf_dashboard.py` | ETF AI 儀表板（1319行）：Tab⑥~⑨ ETF分析 + Tab⑩資料健診 + Tab⑪產業熱力圖 |
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

### 已完成（本輪）
- **資料健診 + 產業熱力圖（2026-04-05）**：
  - Tab ⑩ 資料健診：掃描 session_state 快取（6項）+ yfinance ETF 抓取狀態（價格/配息/info）+ 快取清除工具
  - Tab ⑪ 產業熱力圖：美股 GICS 11大類（XLK/XLF...）+ 台股主要類股，Plotly Treemap 紅跌綠漲，支援1日/5日/1月切換
- **ETF Dashboard 新增（2026-04-05）**：
  - `etf_dashboard.py`（942行）：4 個 render 函式 + 全部計算/快取層
  - Tab ⑥ ETF 單支診斷：郭俊宏/孫慶龍/春哥三大策略 + 折溢價 + 追蹤誤差
  - Tab ⑦ ETF 組合配置：再平衡引擎 + 相關係數矩陣 + 壓力測試 + 總經連動
  - Tab ⑧ ETF 回測：資金成長曲線 + CAGR/Sharpe/MDD + 個別績效
  - Tab ⑨ ETF AI 綜合：跨 Tab 彙整 + 自由提問區 + 總經配置建議連動
  - `app.py`：修正全形分號語法錯誤 + 加入 4 個新 ETF Tab
- **184 個單元測試**：`tests/test_risk_control.py` (59) + `tests/test_scoring_engine.py` (125)，全數通過
- **覆蓋率提升**：`scoring_engine.py` 81% → 93%，`risk_control.py` 94% → 95%
- **新增測試類別**：
  - `TestRsSlope`：rs_slope 函式（先跌後彈、too-short、bool 型別）
  - `TestCheckRelativeStrength`：有/無大盤基準強弱判斷（6 cases）
  - `TestCalcRsScore` 擴充：含大盤基準的 RS 計算（2 cases）
  - `TestCheckStopLossCompat`：check_stop_loss 舊版相容包裝（2 cases）
  - `TestAdditionalCoverage`：ATR fallback、中波動率 elif、量增價漲路徑、grade 欄位、position_size 極端案例
- **`.gitignore` 補強**：新增 `.coverage` / `htmlcov/` / `coverage.xml`
- **CLAUDE.md**：建立含 §1~§6 六大治理協議
- **STATE.md**：本檔案，追蹤開發狀態
- **Bug 修復批次（已 push）**：
  - `data_loader.py:592`：修正 `list-1` TypeError，季財報資料可正常解析
  - `app.py` Tab1 §3：inst/margin fallback 到 `_last_inst`/`_last_margin` session_state 快取
  - `app.py` Tab1 §4：`df_li_show` 數值欄 `ffill()` 補齊 NaN
  - `leading_indicators.py`：正值→藍色(#58a6ff)，負值→紅色(#f85149)
  - `app.py` Tab2 §D：rev/qtr fallback 到 `_last_rev_{sid}`/`_last_qtr_{sid}` session_state 快取
  - `app.py` Tab2 §C：`fetch_financials()` non-200 HTTP 狀態記錄至 `fetch_errors`，修正無 Token 時誤顯「金融/保險不適用」的 false positive
  - `app.py`：FINMIND_TOKEN 未設定時顯示紅色 error 含 Streamlit Cloud Secrets 設定步驟
  - `data_loader.py`：Goodinfo 月營收新增第二備援 URL + 放寬欄位過濾

---

## 策略升級（7 項，2026-04-05 完成）

| # | 位置 | 項目 | 狀態 |
|---|---|---|---|
| ① | `etf_dashboard.py` `_render_bias()` | BIAS 乖離率 MA20/60/120 + 60日Bar圖 | ✅ 完成 |
| ② | `config.py` `WEIGHT_TABLES` + `scoring_engine.py` `stock_score()` | 動態因子權重（bull進攻/bear防禦） | ✅ 完成 |
| ③ | `scoring_engine.py` `check_vcp_atr_filter()` | VCP ATR5 < ATR20×0.8 收縮確認 | ✅ 完成 |
| ④ | `etf_dashboard.py` Tab⑧ `TAX_FACTOR=0.95` | 配息稅費磨損（二代健保 ×0.95） | ✅ 完成 |
| ⑤ | `etf_dashboard.py` `_check_sector_exposure()` | GICS 產業曝險上限 ≤30% | ✅ 完成 |
| ⑥ | `scoring_engine.py` `calc_short_squeeze_bonus()` | 券資比>30%+法人連買≥3天 → +5分 | ✅ 完成 |
| ⑦ | `etf_dashboard.py` `_render_monte_carlo()` | 蒙地卡羅 10,000 路徑，P10/50/90 | ✅ 完成 |

## 測試狀態（2026-04-05）

| 項目 | 結果 |
|---|---|
| `tests/test_scoring_engine.py` | ✅ 123 passed |
| `tests/test_risk_control.py` | ✅ 61 passed |
| 全部測試 | ✅ 184 passed，0 failed |
| `scoring_engine.py` 覆蓋率 | 91%（未覆蓋行：11-15, 98, 180, 204, 239-245, 298-299, 318, 361, 418, 432-433…） |

## 待辦事項

| 優先 | 項目 |
|---|---|
| 低 | 補充 `check_vcp_atr_filter` / `calc_short_squeeze_bonus` 單元測試，覆蓋率可升至 93%+ |
| 低 | 建立 PR（如需要請告知） |

## 待修復 Bug 清單

| 優先 | 位置 | 問題描述 |
|---|---|---|
| ✅ 已修 | `data_loader.py:592` | list-1 TypeError 導致季財報永遠無法解析 |
| ✅ 已修 | `app.py` Tab1 §3 | 三大法人＋融資 API 失敗時無 fallback |
| ✅ 已修 | `app.py` Tab1 §4 | 外資先行指標部分欄位 NaN，無 ffill |
| ✅ 已修 | `leading_indicators.py` | 正/負值顏色配置錯誤 |
| ✅ 已修 | `app.py` Tab2 §D | 月營收/季財報無 fallback 快取 |
| ✅ 已修 | `stop-hook-git-check.sh` | `no_pr_reminder` 重複文字已清除 |
