# 專案戰情室 (Project State)

## 📌 當前狀態
- **專案**: 台股 AI 戰情室（Streamlit Cloud + GitHub，Python 3.14）
- **版本**: v6.4 | main `5b715ec` | branch `716eed1`
- **最新異動**: 紅綠燈 + 市場概覽合併為單一看板 ✅

## 🔨 進行中任務：ARCHITECTURE.md 技術規格書

**目標**：產出 `ARCHITECTURE.md`，內容含目錄結構、資料流向、核心函式 I/O 定義

| 步驟 | 內容 | 狀態 |
|------|------|------|
| Step 1 | **目錄結構**：檔案樹 + 每檔一行職責說明 | ✅ 完成 (`bc2f200`) |
| Step 2 | **系統架構概覽**：分層設計（5層）+ ASCII 架構圖 | ✅ 完成 (`079a589`) |
| Step 3 | **資料流向**：3大主流程（個股/ETF/每日總覽）的資料流圖 | ⏳ 待執行 |
| Step 4 | **核心函式 I/O**：按模組分組，列出 signature + 輸入/輸出說明 | ⏳ 待執行 |
| Step 5 | **組裝 + commit**：合併 Step 1-4 成完整 ARCHITECTURE.md，push + 更新 STATE.md | ⏳ 待執行 |

> 請回覆「執行步驟 X」繼續。每次只實作一個步驟。


| 檔案 | 職責 |
|------|------|
| `app.py` | Streamlit 主程式（10 個 Section，~4700 行）|
| `daily_checklist.py` | 國際/台股/技術指標抓取 + section_header/kpi UI 元件 |
| `data_loader.py` | FinMind HTTP API 資料抓取 |
| `scoring_engine.py` | 多因子健康評分引擎 |
| `chart_plotter.py` | K線 + 法人子圖 |
| `leading_indicators.py` | 外資期貨/PCR/ADL 先行指標 |
| `etf_dashboard.py` | ETF 診斷/組合/回測/AI 四子頁 |
| `ai_engine.py` | 個股 Gemini AI 分析 |
| `unified_decision.py` | 統一投資決策分析模組（stock/etf/portfolio 三模式 3-Card UI）|

## ✅ 已上線功能（截至 v5.3）
- Section 一：國際市場（SOX×DXY 四象限、10Y殖利率三區間）
- Section 二：台股大盤（股匯四象限、ADL廣度）
- Section 三：籌碼（外資100億門檻、融資2800/3400億）
- Section 四：期現貨（期貨口數絕對門檻）
- Section 五/六：法人技術 + 個股先行指標 D2
- Section 七：M1B-M2 Gap + 年線乖離率 BIAS240
- Section 八：總經拼圖 v4.0（VIX時序圖、NDC代理、外銷訂單、CPI、OECD CLI）
- Section 九：總經 AI 五維度規則分析（位階/配置/貨幣流向/美股/結論）
- Section 十：AI 總經戰情總結（Gemini LLM × RSS 新聞 × 8欄 JSON）

## 🔒 長期已知限制（持續中）
- TWSE BFI82U / 融資 IP 封鎖 → FinMind 備援正常
- NDC data.gov.tw 3個resourceID 全404 → OECD CLI代理正常
- st.dataframe / st.button 的 `use_container_width` 待 Streamlit 官方明確後再處理
- ETF AI 存股決策：BIAS240 需 ≥240 日資料，新掛牌 ETF 會顯示 N/A

## ✅ 已修復（v6.4）
- 紅綠燈 + 市場概覽合併為單一看板（`716eed1`）：
  - `_render_traffic_light()` 新增 `mkt_info` 參數，整合市場評分、指數、建議持股、信號 badges、更新時間
  - 原 `render_market_overview()` 卡片抑制（`_mkt_placeholder.empty()`），資訊不重複
  - 保守優先：defense/health<40 可降級 regime → 兩者不再矛盾

## ✅ 已修復（v6.3）
- 紅綠燈標示與 Regime 對齊（`18f4b0c`）：
  - `_calc_traffic_light()` 改以 `regime` 為主要驅動（原為 `_health` 獨立計算）
  - regime='bull' → 🟢 多頭市場｜積極操作
  - regime='neutral' → 🟡 震盪整理｜謹慎觀望
  - regime='caution'/'bear' → 🔴 保守防禦｜縮減部位
  - `_defense` 或 `_health<40` 仍可強制覆蓋為紅燈（緊急防禦）
  - 回傳 dict 新增 `'regime'` key

## ✅ 代碼淨化與收尾完成（v6.2）
- 自動掃描 6 個核心 .py，選出最高污染目標（`ce2d34a`）：
  - `etf_dashboard.py`: 2300 → 2263 行（-37 超空行）
  - `scoring_engine.py`: 1224 → 1201 行（-23 超空行）
- 所有 print() 確認為生產 logging（Cloud log 依賴），保留
- .bak 備份已建立，語法驗證 4 檔全通過

## ✅ 已修復（v6.1）
- 個股 Tab 重複 AI 區塊整合（`2bf14a0`）：
  - 刪除舊 `_t2_ai_key` 區塊（33 行）
  - `unified_decision.py` 個股模式對齊 ①②③④ 四面向
  - Card1=①技術面評價 / Card2=②進場③停損 / Card3=④風控

## ✅ 新增功能（v6.0）
- `unified_decision.py` 統一投資決策分析模組（`731b384`）：
  - 萬用 LLM Prompt：自動路由 stock / etf / portfolio 三套分析邏輯
  - JSON 輸出：`summary`（戰情總結）+ `action_advice`（具體建議）+ `precautions`（風險警示）
  - 3-Card UI：全寬戰情總結（多空自動變色）+ 並排建議/風險卡片
  - session_state 持久化 + 清除按鈕，每個 context_id 獨立
  - 注入 4 個 Tab：個股 Tab2 / ETF 單支 / ETF 組合 / ETF 回測

## ✅ 已修復（v5.9）
- ETF AI 全面修復（`90cc198`）：
  - `render_etf_single`：`etf_s_active` session_state gate（ticker 變更自動重置）
  - `render_etf_portfolio`：`etf_p_active` session_state gate
  - `render_etf_backtest`：`etf_bt_active` session_state gate
  - `_etf_ai_portfolio`：`etf_ai_p_result` 持久化 + 清除按鈕
  - `_etf_ai_backtest`：`etf_ai_bt_result` 持久化 + 清除按鈕

## ✅ 已修復（v5.8）
- ETF Tab⑥ 重複 AI 區塊：移除 `_etf_ai_single`（結果不持久），保留 `_etf_ai_hokei`（`a50bcf6`）

## ✅ 已修復（v5.4–v5.7）
- `calc_fundamental_score` list/hasattr 防呆（`5b314c8`）
- duplicate `_li_log()` 死碼 7 行清除（`2ca50e2`）
- SyntaxError L4604：f-string 混用隱式/顯式串接（`21c80f2`）
- ADL `_ui/_di` index-0 falsy bug → `is not None`（`205b4a7`）
- app.py `use_container_width` → `width='stretch'` 18處（`7125bcd`）
- etf_dashboard.py `use_container_width` → `width='stretch'` 7處（排毒）
- ETF Tab⑥ AI 存股決策總結模組（BIAS240＋KD＋Gemini）（`a28fc34`）

## ✅ Cloud log 驗證確認
- M1B=7.12% / M2=5.38% ✓
- NDC data.gov.tw 全404 → OECD CLI代理=19分 ✓
- Export=31.82% ✓

## 🔒 長期已知限制
- TWSE IP 封鎖 → 全部走 FinMind/openapi 備援
- FinMind 免費帳號：每小時 600 次
- 董監持股 I6：FinMind 免費版無資料（顯示 N/A）
- NDC 景氣燈號：主站 Angular SPA 封鎖 → OECD CLI 代理

## 🔑 環境變數（Streamlit Secrets）
- `FINMIND_TOKEN`: FinMind API
- `GEMINI_API_KEY`: Gemini AI（全站共用）
