# 專案戰情室 (Project State)

## 📌 當前狀態
- **專案**: 台股 AI 戰情室（Streamlit Cloud + GitHub，Python 3.x）
- **版本**: v10.4 | main `213f57a`
- **部署**: Streamlit Cloud，需設定 `FINMIND_TOKEN` + `GEMINI_API_KEY`

## 🏗️ 核心模組
| 檔案 | 職責 |
|------|------|
| `app.py` | Streamlit 主程式（Tab1 市場/Tab2 個股/Tab3 組合/Tab4 總經/Tab5 ETF/Tab6-9 ETF子頁） |
| `data_loader.py` | FinMind HTTP API 財報抓取（BS/CF/IS）+ yfinance/Goodinfo 備援 |
| `financial_health_engine.py` | MJ財報體檢六大模組 + `no_ai_overall_verdict()` 老師動態結論 |
| `scoring_engine.py` | 多因子健康評分引擎（技術/籌碼/基本面/VCP） |
| `daily_checklist.py` | 國際/台股/法人籌碼/融資/先行指標抓取 |
| `market_strategy.py` | market_regime() 大盤狀態判定 |
| `macro_state_locker.py` | AI 總經裁決 + 原子鎖寫入 macro_state.json |
| `macro_alert.py` | VIX/CPI/PMI/PCR 等總經警示規則引擎 |
| `etf_dashboard.py` | ETF 診斷/組合/回測/AI 四子頁 |
| `unified_decision.py` | 統一投資決策（stock/etf/portfolio 三模式 3-Card UI） |
| `leading_indicators.py` | 外資期貨/PCR/ADL 先行指標 |
| `ai_engine.py` | Gemini AI 個股分析 |
| `risk_control.py` | 停損停利/倉位控制 |

## ✅ 最新異動（v10.4，main `213f57a`）

### `data_loader.py` NameError 修復
| 項目 | 說明 |
|------|------|
| **錯誤** | `fetch_financial_statements` line 1755 回傳 `is_finance` 但函式內從未定義 |
| **根因** | `_is_financial_stock()` 是 `StockDataLoader` 的巢狀函式，外部不可呼叫 |
| **修法** | 改用 `stock_id.startswith(('28','58'))` 保底邏輯，與原函式 fallback 一致 |

## ✅ 最新異動（v10.3，main）

### `leading_indicators.py` Bug 修復 + 測試（commits `30ea5da` → `7dee8f9`）
| 項目 | 說明 |
|------|------|
| **Bug 1 修復** | `build_dataset` 韭菜指數：`taifex_mtx_data()` 回傳 tuple，改用 `_mtx[0] if isinstance(_mtx, tuple) else _mtx` 解包 |
| **Bug 2 修復** | `render_leading_table` PCR 顏色閾值：`0.8/1.2`（小數比率）→ `80/120`（整數百分比） |
| **新增測試** | `tests/test_leading_indicators.py`：47 個測試，8 個 class，全通過 |
| **測試涵蓋** | `roc_to_ymd` / `ymd formatters` / `to_num` / `first_num` / `months_in_range` / `extract_date` / `find_data_table` / `expand_table_elem` + Bug 2 regression（PCR 邊界值 80/120） |

### Sidebar 連線狀態面板修正（commit `7438fe0`）
| 項目 | 說明 |
|------|------|
| **FinMind 端點** | `/api/v4/info`（404）→ `/api/v4/data?dataset=TaiwanStockInfo&stock_id=2330` |
| **TWSE 端點** | `twse.com.tw/rwd`（SSLError）→ `openapi.twse.com.tw/v1/opendata/t187ap03_L` |

### 總測試數
| 模組 | 測試數 |
|------|------|
| `scoring_engine.py` | 168+ |
| `macro_state_locker.py` | 18+ |
| `macro_alert.py` | 10+ |
| `financial_health_engine.py` | 17 |
| `risk_control.py` | 既有 |
| `leading_indicators.py` | **47（新增）** |
| **合計** | **≥ 473** |

## ✅ 最新異動（v10.2，main `5c94cd4`）

### Sidebar 連線狀態面板（commit `968f2bb`）
| 項目 | 說明 |
|------|------|
| **靜態徽章** | FinMind/Gemini/Proxy 三欄，根據 Secrets 是否設定顯示 ✅/❌/— |
| **Proxy 提示** | `PROXY_HOST` 有值時顯示 `🔒 host:port` |
| **測試連線按鈕** | 點擊對 FinMind / TWSE / Yahoo Finance 發送 HTTP 探測，結果存入 `session_state['_sb_conn_results']` |
| **位置** | `app.py:1125`，Defense Mode 狀態下方，警語上方 |

## ✅ 最新異動（v10.1，branch `claude/analyze-test-coverage-070Kf`）

### 財報健檢三項 N/A 修復（commits `341b1fb`）
| 項目 | 修復內容 |
|------|---------|
| **B項現金流量允當比率** | 硬編 N/A → 單季估算 `OCF/(CapEx+ΔInv+Div)×100%`，標注「1Q估」 |
| **負債比率金融特許行業** | `is_finance=True` 時跳過60/70%門檻，顯示「金融特許行業」 |
| **DSO/AR 別名擴充** | 新增 `合約資產`、`工程應收款`、`應收票據及應收帳款` 等建設業科目 |
| **data_loader 回傳欄位** | `fetch_fin_data` 加入 `is_finance` 欄位供下游模組使用 |

### 新增模組（commit `792a7e5`）
| 檔案 | 說明 |
|------|------|
| `tw_stock_data_fetcher.py` | Proxy-aware 台股財報抓取模組（Goodinfo/MOPS 備援，501行）；`fetch_tw_financials()` 公開 API，與 `data_loader.fetch_fin_data()` 格式相容 |

### PR 批次覆蓋率分析結果
| 檔案 | 變動行數 | 測試缺口 | 處置 |
|------|---------|---------|------|
| `financial_health_engine.py` | 51 | B項3路徑、is_finance 6路徑、debt fallback 6路徑 | ✅ 新增 17 tests |
| `scoring_engine.py` | 11 | 無（existing test 已覆蓋新 early-return）| ✅ 已驗證 |
| `data_loader.py` | 9 | 無（alias 擴充 + is_finance key，整合測試範疇）| ✅ 已驗證 |

### 測試覆蓋率最終結果（commit `92cbb2b` → `84a6027`）

| 模組 | 原始 | 最終 | 新增測試 |
|------|------|------|---------|
| `scoring_engine.py` | 50% | **96%** | +168 |
| `macro_state_locker.py` | 78% | **100%** | +18 |
| `macro_alert.py` | 67% | **90%** | +10 |
| `financial_health_engine.py` | 0% | **PR分支覆蓋** | +17 |
| `risk_control.py` | 95% | 95% | — |
| **整體** | **60%** | **96%+** | **+213** |

總測試數：295 → **426**（全部通過）

#### `scoring_engine.py` 新增測試類別
- `TestCalcQualityScore` — 7 情境（None/GM↑Rev↑優質/GM↓Rev↓弱/GM→Rev↑穩健）
- `TestCalcForwardMomentumScore` — FGMS 函式（None/三率維度/is_finance=True）
- `TestCalcLeadingIndicatorsDetail` + `Extended` — I1–I5 全路徑（🟢/🟡/🔴/⚪）
- `TestCalcForwardMomentumScoreExtended` — 合約負債 + 存貨維度深路徑
- `TestBollingerSqueezeBreak` — 橫盤後跳漲觸發 `is_squeeze_break=True`
- `TestVcpAtrFilterException` / `TestCalcAtrStopException` — 字串欄位觸發 `except` 路徑

#### Bug Fix
- `calc_chip_score()`: 明確傳入 `foreign_buy` 應優先於 DataFrame 欄位（修復 1 個失敗測試）

#### `macro_state_locker.py` 新增測試類別（78% → 100%）
- `TestDefaultGeminiCall` — 7 情境：無 API Key / 200 成功 / 404 / SAFETY / 429+sleep / Exception / 空 candidates
- `TestLockSystemStateOnly` — 直寫路徑（曝險上下限 clamp、summary 格式）
- `TestCalculateSystemStateBias240` — BIAS240 雙重共振（高乖離+VIX/PMI）、低乖離加分、非數值 `_f()` 防禦
- `test_negative_m1b_m2_spread_labels_tightening` — 「資金緊縮」標籤路徑

#### `macro_alert.py` 新增（67% → 71%）
- `TestFetchMacroSnapshotEdgeCases` — VIX/CPI/PCR 非數值 → TypeError/ValueError 靜默略過

## ✅ 最新修復（v10.0，main commits `8d2320b` → `e22f613`）
| commit | 項目 | 內容 |
|--------|------|------|
| `8d2320b` | **體檢表老師動態結論 + 資產計算修復** | `no_ai_overall_verdict()` 六模組彙整生成等級A+~F；`assets = cur_assets + non_cur_assets` 兜底 |
| `6620276` | **IFRS reverse + 模糊比對 + 盈餘含金量** | reverse IFRS 移到主邏輯層；`_fuzzy_bs()` 掃全欄位；NI<0 改顯 OCF/Rev |
| `6592db8` | **引擎層重算負債比率 + Goodinfo AR 備援** | `_no_ai_financial_structure` 直接從 `流動負債(千)` 等重算；Goodinfo 季度 BS 補 AR |
| `e22f613` | **STATE.md v10.0** | 記錄財報健檢四層備援策略 |

## 📐 財報健檢資料補齊策略（四層）
```
L1: FinMind 精確欄位別名（30+ 中英文變體）
L2: FinMind 組合推算（流動+非流動相加 / IFRS 雙向恆等式）
L3: 模糊比對（掃 BS 所有欄位取最大值）
L4: yfinance + Goodinfo 外部備援
L5: 引擎層重算（直接從 fin_data 已有欄位推導）← 最終防線
```

## 🔒 已知限制
- TWSE IP 封鎖 → 全部走 FinMind/openapi 備援
- FinMind 免費帳號：每小時 600 次請求限制
- NDC 景氣燈號：主站封鎖 → OECD CLI 代理
- 收現速度(DSO)：特定產業（建設/REITs/金融業）AR 欄位名稱特殊，Goodinfo 備援中
- `macro_alert.py` lines 338-421：Streamlit 渲染函式（`render_alerts()`），需 mock `st.*`，屬整合測試範疇，未納入單元測試

## 🔑 環境變數（Streamlit Secrets）
- `FINMIND_TOKEN`: FinMind API
- `GEMINI_API_KEY`: Gemini AI（全站共用）
