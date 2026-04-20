# 專案戰情室 (Project State)

## 📌 當前狀態
- **專案**: 台股 AI 戰情室（Streamlit Cloud + GitHub，Python 3.14）
- **版本**: v9.5 | main `66fb06b`
- **最新異動**: Bug Fix — 財報體檢 AI 失效降級 + token 缺失警告

## ✅ 已完成任務：Bug Fix 財報體檢 N/A + AI 失效（v9.5，commit 66fb06b）

| 項目 | 內容 |
|------|------|
| `financial_health_engine.py` | 新增 `_derive_basic_from_fin_data()`：AI 失效時直接從 fin_data 計算基礎指標 |
| AI 失效降級 | `analyze_financial_health()` exception 路徑改為回傳基礎計算（不帶 `error:True`），避免 tab2/tab3 整個體檢區塊空白 |
| `app.py` Tab3 | 批次體檢前置 token 檢查：未設定 FINMIND_TOKEN/GEMINI_API_KEY 時顯示明確 warning |
| `data_loader.py` | FinMind 非 200 回應加印 status+msg，便於 debug N/A 原因 |
| Bug 根因 | FINMIND_TOKEN 失效 → FinMind 返回非200 → empty data → `{"error":...}` → FAIL_SAFE |

## ✅ 已完成任務：MJ 財報體檢 Part 6 綜合診斷模組（v9.4，commit 4aa2157）

| 項目 | 內容 |
|------|------|
| `financial_health_engine.py` | `_ADVANCED_DIAGNOSTIC_PROMPT` + `analyze_advanced_diagnostic_module()` |
| 盈餘品質 | OCF/淨利 >100%=真金白銀 / <100%=紙上富貴；淨利≤0→N/A |
| 杜邦分析 | ROE+負債比交叉判定「槓桿膨脹警報」vs「健康成長」 |
| 雙高危機 | AR增長率 AND 存貨增長率 同時>營收增長率 → 地雷警報 |
| 企業 DNA | OCF/ICF/籌資CF正負號矩陣（A+印鈔機/成長/瀕死型等） |
| `app.py` Tab2+Tab3 | 3欄診斷卡 + DNA全寬Banner |

## ✅ 已完成任務：MJ 財報體檢 Part 5 償債能力模組（v9.3，commit 101d2d7）

| 項目 | 內容 |
|------|------|
| `data_loader.py` | 新增 `流動資產(千)` + `營業成本(千)` |
| `financial_health_engine.py` | `_SOLVENCY_PROMPT` + `analyze_solvency_module()` |
| 指標1 | 流動比率 > 300% Pass（MJ 嚴格標準） |
| 指標2 | 速動比率 > 150% Pass（MJ 嚴格標準） |
| 保命符 | 條件A:現金>25% / 條件B:DSO<15天 / 條件C:完整週期<50天 → Exception_Pass |
| `app.py` Tab2+Tab3 | 最終裁決 Banner + 兩比率卡片 + 交叉驗證保命符提示 |

## ✅ 已完成任務：MJ 財報體檢 Part 4 財務結構模組（v9.2，commit d38789c）

| 項目 | 內容 |
|------|------|
| `data_loader.py` | 新增 `非流動負債(千)` = 總負債 - 流動負債 |
| `financial_health_engine.py` | `_FINANCIAL_STRUCTURE_PROMPT` + `analyze_financial_structure_module()` |
| 指標1 | 負債比 < 60% Pass / 60-70% Warning / > 70% Fail；金融業 N/A |
| 指標2 | 以長支長 (股東權益+非流動負債)/固定資產 > 100% Pass；輕資產自動 Pass |
| `app.py` Tab2+Tab3 | 2欄大字卡片（三色負債比 + 以長支長通過/致命紅燈）|

## ✅ 已完成任務：MJ 財報體檢 Part 3 獲利能力模組（v9.1，commit 5e84615）

| 項目 | 內容 |
|------|------|
| `data_loader.py` | 新增 `oper_income`（營業利益）+ `equity`（股東權益）欄位 |
| `financial_health_engine.py` | `_PROFITABILITY_PROMPT` + `analyze_profitability_module()` |
| 5大指標 | 毛利率(>20%好生意)、營業利益率(本業虧損淘汰)、安全邊際(>60%)、稅後淨利率、ROE(槓桿防呆) |
| `app.py` Tab2+Tab3 | 5欄獲利卡片（綠=Pass/紅=Fail/黃=Warning）|

## ✅ 已完成任務：v4.0 三階段升級（commit 731f104）

| 階段 | 項目 | 內容 |
|------|------|------|
| Phase 1 | `daily_checklist.py` | 新增 `evaluate_market_status_v4_final()`，解耦趨勢×位階，共同基金導向 |
| Phase 1 | `app.py` 5分鐘清單 | 改用 v4 引擎 Signal/Action_Advice/Suggested_Holding；融資水位→融資維持率 |
| Phase 2 | `daily_checklist.py` | 新增 `fetch_margin_maintenance_ratio()`，從 TWSE MI_MARGN 抓「維持率」欄位 |
| Phase 2 | `app.py` 資料管線 | 新增 `_job_margin_ratio` 並發任務，cl_data 加入 `margin_ratio` |
| Phase 3 | `daily_checklist.py` 圖表 | `bar_chart_institutional()` 改 `textposition='outside'` + `cliponaxis=False` |

## ✅ 已完成任務：MJ 經營能力模組（v8.1，commit 57d651c）

| 項目 | 內容 |
|------|------|
| `financial_health_engine.py` | `_OPERATING_PROMPT` + `analyze_operating_module()` 計算 DSO/DIO/DPO/CCC/Asset Turnover/OPM護城河 |
| `app.py` Tab2 | 個股健檢頁新增存活能力 + 經營能力雙模組卡片 |
| `app.py` Tab3 | 批次健檢 expander 同步加入經營能力模組渲染 |
| Commit | `60d604e` |

## ✅ 已完成任務：MJ 存活能力精細模組（v8.0，PR #37）

| 項目 | 內容 |
|------|------|
| `financial_health_engine.py` | `_SURVIVAL_PROMPT`（氣長/DSO/100-100-10）+ `analyze_survival_module()` + 整合進 `analyze_financial_health()` |
| `data_loader.py` | 補充流動負債/存貨/現金股利/固定資產/長期投資欄位 |
| `app.py` | 個股 expander 新增 3 欄存活能力精細診斷卡（含 Final_Survival_Verdict） |
| Commit | `b11fd52` |

## ✅ 已完成任務：Tab1 市場總覽同步化（v7.9.4，PR #35）

| 項目 | 內容 |
|------|------|
| 根因 | 資料過期時交通燈顯示⏳，但今日市場總覽卡片和5分鐘清單仍從舊 session_state 顯示，三者不同步 |
| 修復 | 兩個 section 加入 `_cache_fresh and` 條件，資料過期時全部隱藏，更新後同步顯示 |
| Commit | `e9805eb` |

## ✅ 已完成任務：Tab3 健檢移至 AI 結論上方（v7.9.3，PR #34）

| 項目 | 內容 |
|------|------|
| 變更 | 對調兩個區塊：體檢摘要比較表 + 個股詳細體檢報告 移至 AI 投資組合綜合判讀上方 |
| Commit | `424ca08` |

## ✅ 已完成任務：Tab1 交通燈結論統一（v7.9.2，PR #32）

| 項目 | 內容 |
|------|------|
| 根因 | `_calc_traffic_light()` health<40 觸發「空頭防禦」，但下方卡片直接讀 raw regime 顯示「震盪」，兩個矛盾結論並存 |
| 修復 | 新增 `_tl_eff_reg`（從 icon 推導）；今日市場狀態卡 + 今日作戰室 + 5分鐘清單皆改用統一 regime；bear mode 自動顯示 ≤20% 持股 |
| Commit | `d4aa95e` |

## ✅ 已完成任務：資料診斷 Section 1-3 DataFrame 修復（v7.9.1，PR #30）

| 項目 | 內容 |
|------|------|
| 根因 | `cl_data['intl'/'tw'/'tech']` 值為 yfinance DataFrame，`if not _v:` 觸發 pandas ValueError |
| 修復 | 新增 `from daily_checklist import calc_stats`；三段迴圈改為 `_s = calc_stats(_df)` 後再讀 last/pct/status |
| Commit | `7ae2e4e` |

## ✅ 已完成任務：資料診斷 Tab 全面擴展（v7.9）

| 項目 | 內容 |
|------|------|
| `render_data_health()` 全面改寫 | 從 6 項 session_state 擴展為 17 個展開區塊，顯示所有資料實際數值 |
| Section 1-12 | 國際市場/台股大盤/科技股/法人籌碼/融資餘額/ADL/先行指標/M1B-M2/乖離率/總經快照/旌旗評估/AI裁決報告 |
| Section 13 個股分析 | t2_data 技術指標表（Price/RSI/KD/VCP/月營收/季財報）+ MJ財報體檢 |
| Section 14 ETF 單支診斷 | etf_single_data：殖利率/溢折價/追蹤誤差/市場環境 |
| Section 15 ETF 組合配置 | etf_portfolio_data：持倉明細表 + 總值/虧損比/再平衡日 |
| Section 16 ETF 回測績效 | etf_backtest_data：CAGR/Sharpe/MDD/波動度 |
| Section 17 財經新聞 RSS | 4 個 RSS 來源即時驗證按鈕 |
| Commit | `f5b9d20` (Section 13-16)、`9eb69b3` (Section 1-12) |

## ✅ 已完成任務：總經 Tab AI 裁決改版（v7.8.1）

| 項目 | 內容 |
|------|------|
| AI 裁決 Fail-safe 修復 | 改用 `lock_system_state_only()` 寫入 Python 規則狀態，`gemini_call()` 輸出 Markdown 報告 |
| 清除報告按鈕 | 新增「🗑️ 清除報告」按鈕，清除 session_state `_macro_ai_report/ts` |
| `st.rerun()` | 在 `if _do_verdict:` 區塊尾端加 `st.rerun()`，確保頂部方塊更新 |
| Commit | `2814ed0` |

## ✅ 已完成任務：Tab3 財報體檢 N/A + 排序修復（v7.8，PR #27）

| 項目 | 內容 |
|------|------|
| Token bug | `_gk3/_fk3` 改用全域 `api_key`/`FINMIND_TOKEN`（含 os.environ fallback） |
| df_cmp 排序 | 加 `健康度` 為次要鍵，避免舊評分同分時順序任意 |
| 體檢摘要表 | 加 `sort_values('雷達均分')` 降序，高分排前 |

## ✅ 已完成任務：Tab1 頂部看板資料延遲顯示修復（v7.7，PR #25）

| 項目 | 內容 |
|------|------|
| 根因 | Streamlit top-to-bottom 單次執行：頂部「今日市場總覽」在資料抓取前就已渲染，點擊更新後顯示舊快取 |
| 修復 | `if do_refresh` 區塊尾端加 `st.rerun()`，資料寫入 session_state 後觸發第二次完整渲染 |

## ✅ 已完成任務：Tab3 NameError 修復（v7.6，PR #23）

| 項目 | 內容 |
|------|------|
| 根因 | `results_t3` 僅在 `if t3_data:` 內定義，line 7094 在區塊外引用 → Streamlit Cloud 首次渲染崩潰 |
| 修復 | `if t3_data:` 前加 `results_t3 = []` 安全初始值 |

## ✅ 已完成任務：Tab1 總經 AI 改版（v7.5）

| 項目 | 內容 |
|------|------|
| `macro_state_locker.py` | 新版 Prompt「台股AI戰情室：總體經濟與大盤判讀提示語」4段輸出格式 |
| `execute_and_lock()` | 新增 `macro_context` 參數（原始量化數據字串），新增儲存 `traffic_light/market_level/data_deep_dive/risk_warning/strategy` |
| `app.py` if _do_verdict | 組裝豐富 `_v_macro_ctx`（外資/投信/自營/融資/韭菜指數/PCR/ADR/期貨）並傳入 locker |
| `app.py` UI 渲染 | 4段戰情卡片（🚦燈號/🔍深度解析/🛡️風險預警/💼戰略建議），`traffic_light` 存在時才顯示 |
| 所有 36 個測試 | ✅ 全部通過 |

## ✅ 已完成任務：個股分析四大群組化 + AI首席顧問總結（`6abaca7`）

| 項目 | 內容 |
|------|------|
| 💰 建議價格（橘） | section 0：停利停損、風報比、倉位計算、進場條件 |
| 📈 技術面（藍） | A健康度 → E VCP → F K線圖 → G規則引擎（重排連貫）|
| 📊 基本面（綠） | B 357評價 → C財報領先 → D月營收 → D2六大指標 |
| 🏥 體檢表（紫） | H MJ林明樟財報體檢 |
| 🤖 AI首席顧問（青） | 新版 Prompt：五維雷達+洞察摘要+深度解析+具體戰術+警示針 |
| 資料收集 | 技術/籌碼(三大法人10日)/基本面/MJ體檢結果 全部來自頁面上方 |

## ✅ 已完成任務：AI 財報體檢戰情室 v1.0（`a53b8c8`）

| 項目 | 內容 |
|------|------|
| `financial_health_engine.py` | MJ 4力1棒子+現金流矩陣 Prompt + `analyze_financial_health()` + `_FAIL_SAFE` |
| `data_loader.py` | 新增 `fetch_financial_statements()`，抓 FinMind BS+CF+IS，計算現金比/負債比/OCF/AR天數/AP天數 |
| `app.py` Tab 2 Section H | 生死燈號 × 3 + 五力雷達圖（range=[0,100]）+ 企業DNA + OPM護城河 + AI白話診斷 + 紅旗警示 |
| Tab 3 批次體檢 | `2ace67d` ✅ ThreadPoolExecutor 並行 + 摘要表 + 個股 expander 卡片 |

## ✅ 已完成任務：v5.2 物理鎖三大紅線（`46a8457`）

| 項目 | 內容 |
|------|------|
| 紅線一 | 薩姆規則觸發 → 曝險上限 20% |
| 紅線二 | PMI 連兩月 <48 → 曝險上限 40%（跨次執行用 session_state 追蹤前月值）|
| 紅線三 | 外資期貨淨空 >35000 口 + 破 MA5 → 曝險上限 30% |
| 公式修正 | BIAS240 改雙重共振、MA120 改5日斜率、chip_score 加 foreign_5d_net、MA5 新增至 mkt_info |
| AI Prompt | 加第4條：禁止在 analysis_summary 輸出持股百分比數字 |
| 測試 | 36 passed（+5 紅線測試）|

## ✅ 已完成任務：AI 決策引擎 v2.0（理科/文科分工）

**目標**：拆分「運算邏輯（理科）」與「解讀邏輯（文科）」，消除 AI 自行決定倉位的幻覺風險。
Python rule-based 計算 `exposure_limit_pct`，AI 僅輸出 `analysis_summary` 解讀文字。

| 步驟 | 內容 | 狀態 |
|------|------|------|
| Step 1 | `macro_state_locker.py`：新增 `calculate_system_state()`（VIX/PMI/M1B-M2/BIAS240/PCR 五因子）| ✅ |
| Step 2 | 輕量化 Prompt：AI role 改為「解讀師」，輸出從 4 欄位縮為 1 欄位（`analysis_summary`）| ✅ |
| Step 3 | `execute_and_lock()` 改接收 `system_state dict`，合併 Python + AI 後原子寫入 | ✅ |
| Step 4 | `app.py`：呼叫 `calculate_system_state()` 後傳入 `execute_and_lock()`；渲染層改讀新欄位 | ✅ |
| Step 5 | `macro_state.json`：欄位更新（`exposure_limit_pct` + `analysis_summary` + `Macro_Phase`）| ✅ |
| Step 6 | `tests/test_macro_state_locker.py`：31 tests（+8），新增 `TestCalculateSystemState`（7 cases）| ✅ |

## ✅ 已完成任務：AI 總裁決實體狀態鎖 v1.0（前版基礎）

| 步驟 | 內容 | 狀態 |
|------|------|------|
| Step 1 | `macro_state_locker.py`：`MacroStateLocker` 類別 + `load_macro_state()` + 原子寫入 + Fail-safe | ✅ |
| Step 2 | `app.py`：Section 十改為唯讀裁決卡片 + 「執行 AI 裁決」觸發按鈕；移除舊 IF-ELSE 邏輯 | ✅ |
| Step 3 | `tests/test_macro_state_locker.py`：23 tests，0 failures，無 HTTP 呼叫 | ✅ |

## ✅ 已完成任務：總經數據自動警示模組 `macro_alert.py`（main `20bad40`）

**目標**：新增 L3 策略層模組，監控 VIX / CPI / 10Y 殖利率 / DXY / PCR 等總經指標，
閾值觸發時自動在 Section 8 頂端發出 🔴🟡🟢 分級警示橫幅。

| 步驟 | 內容 | Commit | 狀態 |
|------|------|--------|------|
| Step 1 | 規則引擎：`config.py` MACRO_ALERT_RULES + `check_macro_alerts()` 純函式 | `6aef067` | ✅ |
| Step 2 | 資料擷取：`fetch_macro_snapshot()`，session_state 優先 + yfinance 補抓 | `92086c6` | ✅ |
| Step 3 | UI 元件：`render_macro_alerts()`，badge 條 + 展開詳情，純資料驅動 | `e293fe7` | ✅ |
| Step 4 | app.py 整合：Section 8 頂端注入，`session_state['macro_alerts']` 供全站共用 | `5e56112` | ✅ |
| Step 5 | 單元測試：`tests/test_macro_alert.py` 62 tests，0 failures，無 API 呼叫 | `20bad40` | ✅ |

## ✅ 已完成任務：ARCHITECTURE.md 技術規格書

| 步驟 | 內容 | 狀態 |
|------|------|------|
| Step 1 | **目錄結構**：檔案樹 + 每檔一行職責說明 | ✅ 完成 (`bc2f200`) |
| Step 2 | **系統架構概覽**：分層設計（5層）+ ASCII 架構圖 | ✅ 完成 (`079a589`) |
| Step 3 | **資料流向**：3大主流程（個股/ETF/每日總覽）的資料流圖 | ✅ 完成 (`c7cb28d`) |
| Step 4 | **核心函式 I/O**：按模組分組，列出 signature + 輸入/輸出說明 | ✅ 完成 (`22d29ec`) |
| Step 5 | **組裝 + commit**：合併 Step 1-4 成完整 ARCHITECTURE.md，push + 更新 STATE.md | ✅ 完成 |

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

## ✅ 新增功能（v6.5）
- v4.0 四大引擎升級（`fff28cf`）：
  - **Engine 1** `market_strategy.py`：`market_regime()` 加入宏爺 M1B-M2 資金活水評分（選填，向後相容），max_score 升至 6
  - **Engine 3** `v4_strategy_engine.py`：`detect_vcp_breakout()`（春哥三階段波幅收縮 + 蔡森等幅測距目標價）+ `detect_false_breakout_v4()`（天量黑K逃命訊號）
  - **Engine 4** `portfolio_manager.py`（新建）：`CoreSatelliteManager` 核心/衛星動態配比 + 超標 10% 再平衡警報
  - 妮可地緣籌碼加權（1.5x）：資料源不支援，暫不實作

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
