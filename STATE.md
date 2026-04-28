# 專案戰情室 (Project State)

## 📌 當前狀態
- **專案**: 台股 AI 戰情室（Streamlit Cloud + GitHub，Python 3.x）
- **版本**: v10.36 | branch `claude/analyze-test-coverage-070Kf`
- **部署**: Streamlit Cloud，需設定 `FINMIND_TOKEN` + `GEMINI_API_KEY` + `PROXY_URL`
- **✅ PR #76 已 merge**（2026-04-28）— 新鮮度容忍升級 + UI來源名稱全面更新 + 殘餘dbnomics清理

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

## ✅ 最新異動（v10.36，commit `640c869`，PR #76）

### 新鮮度容忍升級 + UI來源名稱全面更新 + 殘餘dbnomics清理

| 項目 | 修復內容 |
|------|---------|
| **_freshness() yearly** | 有資料即 🟢（股利 848天前正確顯示，消除誤判🔴） |
| **_freshness() quarterly** | 90天→**150**天為 🟢（覆蓋 Q3→Q4 四個月財報空窗；117天前 = 🟢） |
| **_freshness() monthly** | 45天→**60**天為 🟢（覆蓋次月底延遲公佈） |
| **_freshness() daily** | 3天→**5**天為 🟢（覆蓋連假） |
| **UI 來源名稱清理** | `render_data_health_raw()` / macro info table / KPI卡片 / LLM context 全面移除 dbnomics / IMF / OECD CLI / data.gov.tw / TaiwanExportImport 字眼，統一顯示 FRED / FinMind Macro |
| **_fetch_pmi 殘餘dbnomics** | 方案2 dbnomics OECD PMI block 完整刪除（PR#74 漏刪） |
| **_fetch_export 殘餘dbnomics** | 方案3 dbnomics OECD/IMF block 完整刪除 |
| **test_fetch.py** | 新增 FRED CPI + FinMind NDC 快速驗證腳本 |

## ✅ 最新異動（v10.35，commit `75194a3`，PR #74）

### 破解快取陷阱 + NDC精確比對 + 合約負債DataFrame提取（app.py + data_loader.py + daily_checklist.py）

| 項目 | 修復內容 |
|------|---------|
| **快取強制清除** | `app.py` session 首次執行 `st.cache_data.clear()`（`_cache_cleared_v10_35` 旗標防重複）；`fetch_quarterly` `_ver` 3→4；`fetch_quarterly_extra` 新增 `_ver=2` |
| **TTL 統一** | `fetch_quarterly` ttl 1800→3600 |
| **NDC 精確比對** | `_fetch_ndc` 改用 `indicator=='景氣對策信號(分)'` 精確比對，備援 `str.contains('景氣對策信號')`；新增 debug 印出 FinMind 所有 indicator 清單 |
| **CPI 清理** | 移除 dbnomics IMF 備援路徑（保留 FRED 主路徑 + BLS 次路徑） |
| **PMI 清理** | 移除 dbnomics OECD PMI + CLI 所有備援路徑（FRED 唯一路徑） |
| **融資維持率** | `daily_checklist` 新增方案 3：TWSE MI_MARGN CSV + regex 提取 |
| **合約負債 DataFrame 提取** | `get_quarterly_bs_cf` 先建 `_bs_df_raw`（sort 降冪）；以 `type.str.contains('合約負債')` 加總（涵蓋 ASCII/全形/em dash 所有變體）；失敗才降級 `_val()` + dict fuzzy |
| **test_fetchers.py** | 新增離線單元測試（Part A 全通過：A1 date欄位 / A2 CL提取 / A3 NDC比對）+ 線上整合測試（Part B，供 Streamlit Cloud 環境） |

## ✅ 最新異動（v10.34，commit `54a7132`，PR #73）

### 修復失效的總經/籌碼/個股財報 API 管線（app.py + data_loader.py + daily_checklist.py）

| 項目 | 修復內容 |
|------|---------|
| **CPI** | 新增 pandas_datareader FRED `CPIAUCSL` 主路徑（proxy env 注入）；BLS/dbnomics 降為備援 |
| **PMI** | 新增 FRED `NAPM`→`MANEMP`→`INDPRO` 主路徑；dbnomics OECD 降為備援 |
| **NDC 景氣燈號** | 新增 FinMind TaiwanMacroEconomics 主路徑；data.gov.tw 降為備援 |
| **台灣出口 YoY** | 新增 FinMind TaiwanMacroEconomics 主路徑；TaiwanExportImportTotal/dbnomics 降為備援 |
| **融資維持率** | MI_MARGN 新增搜尋 totalData+notes；加 TWSE TWT93U 備援端點 |
| **季報 date 欄位** | qtr/qtr_extra 加 end-of-quarter date 欄（2025Q4→2025-12-31）供診斷正確讀取 |
| **合約負債模糊加總** | _CL_KEYS 擴充含-流動/-非流動；精確 match 失敗時 contains 加總所有子科目 |
| **requirements.txt** | 新增 `pandas-datareader>=0.10.0` |

## ✅ 最新異動（v10.33，commit `7dee262`，PR #72）

### 資料診斷 macro_info key 修正（etf_dashboard.py）

| 項目 | 說明 |
|------|------|
| **CPI key 修正** | `'cpi'` → `'us_core_cpi'`（BLS/dbnomics 實際回傳 key） |
| **PMI key 修正** | `'pmi'` → `'ism_pmi'`（OECD CLI 實際 key） |
| **NDC key 修正** | `'ndc'` → `'ndc_signal'`（NDC/OECD CLI 代理實際 key） |
| **M1B date 修正** | `m1b_m2_info` 無 `date` 欄位，改以 `cl_ts` 作為時間代理 |
| **margin_ratio 判斷修正** | 數值 `0` 會被 `if val` 誤判缺失，改為 `is not None` |

## ✅ 最新異動（v10.32，commit `a5e3eca`，PR #71）

### Phase 2 UI 重構：平坦 8-Tab + 資料診斷 Raw-only + 教學 Markdown（app.py + etf_dashboard.py）

| 項目 | 說明 |
|------|------|
| **平坦 8-Tab 結構** | `總經 / 產業熱力圖 / 個股 / 個股組合 / ETF / ETF組合 / 資料診斷 / 教學`，移除舊的巢狀 Tab 包裝層 |
| **ETF組合子 Tab** | 內建 3 子頁：`組合配置 / 歷史回測 / ETF AI`（`_tab_etf_port/_tab_etf_bt/_tab_etf_ai`） |
| **資料診斷 Raw-only** | 新 `render_data_health_raw()` 函式：5 個 expander（總經/大盤籌碼/先行指標/個股/ETF），每列 3 欄（資料名稱/最後更新/狀態燈號），嚴格排除所有計算值（RSI/MA/KD 等） |
| **教學 Markdown** | 靜態 `st.expander` 4 師：孫慶龍（合約負債/資本支出/EPS框架）、蔡森（破底翻/頭肩底）、春哥 VCP（4大條件/ASCII圖）、宏爺（M1B-M2/四象限矩陣） |
| **舊內容清理** | 移除 ~550 行舊巢狀 Tab 結構與 placeholder 手冊重複內容（9336→8793 行） |
| **舊變數替換** | `tab_etf1~4/tab_health/tab4_masters` → `tab_etf/_tab_etf_port/_tab_etf_bt/_tab_etf_ai/tab_diag/tab_edu` |

## ✅ 最新異動（v10.31，commits `0f34d0a`–`5da3870`）

### 全面 Proxy 修復 + 資料新鮮度改善（app.py / daily_checklist.py / data_loader.py / leading_indicators.py）

| 問題 | 根本原因 | 修正 |
|------|---------|------|
| **yfinance `proxy=` TypeError** | 新版 yfinance 不接受 `proxy=` 關鍵字參數 | 改用 `os.environ` 注入 `HTTPS_PROXY`/`HTTP_PROXY`，try/finally 還原 |
| **TWSE SSLCertVerificationError** | `build_proxy_session()` 回傳 `verify=True`；Missing Subject Key Identifier | 所有 `_bps()`/`_bps_dl()` 建立 session 後強制 `s.verify = False` |
| **FRED CPI 超時浪費 30s** | Streamlit Cloud 封鎖 FRED，每次 15s×2=30s 白費 | 完整移除 FRED CPI 直連；dbnomics IMF 備援已可正常運作 |
| **大盤指標 40→1 項** | `fetch_single()` 裸呼叫 yfinance 無 proxy；DataRegistry 在抓取失敗時不重建大盤項目 | `fetch_single()` 加 `os.environ` 注入；Registry Patch 補建大盤區塊 |
| **NDC 景氣 878天** | `dbnomics.fetch_series()` 不走 proxy；Series ID 格式錯誤 | 改用 `_dbn_px()`；ID 修正為 `OECD/MEI_CLI/TWN.LOLITOAA.ST.M` |
| **出口 391天** | OECD 資料有 12 個月延遲 | 新增 FinMind `TaiwanExportImportTotal`/`TaiwanExportByIndustry` 為優先來源（1 個月延遲） |
| **個股資料完全失敗** | `data_loader.py` 中多處裸 `yf.download()`/`requests.get()` 無 proxy | 新增 `_yf_dl()` helper（env 注入）；所有 `requests.get()` 改為 `_bps_dl().get()` |
| **SyntaxWarning `\>`** | `app.py:8476` raw string 中使用 `\>` | 修正為 `>` |
| **ADL timeout** | timeout 30s 不夠 | 調升至 55s；錯誤訊息更新 |

**關鍵程式碼模式：**
```python
# yfinance proxy 注入（相容新舊版本）
_ek = ('HTTPS_PROXY', 'HTTP_PROXY', 'https_proxy', 'http_proxy')
_bak = {k: os.environ.get(k) for k in _ek}
if _px_url:
    for k in _ek: os.environ[k] = _px_url
try:
    return yf.download(symbol, **kwargs)  # 或 yf.Ticker().history()
finally:
    for k, v in _bak.items():
        if v is None: os.environ.pop(k, None)
        else: os.environ[k] = v

# requests session（verify=False 強制）
def _bps():
    try:
        from tw_stock_data_fetcher import build_proxy_session as _b
        s = _b()
    except Exception:
        s = requests.Session()
    s.verify = False  # ← 必須，TWSE SSL 問題
    return s
```

## ✅ 最新異動（v10.30，commit `3d8bf30`）

### 總經 Macro Job 超時根因修復（app.py）— 移除確認永遠失敗的 API

| 問題 | 根本原因 | 修正 |
|------|---------|------|
| **Export 永遠 422** | FinMind `TaiwanExportStatistics` 資料集不存在，每次浪費 15s | 完整移除此區塊；OECD dbnomics 升格為主要 Export 來源 |
| **GOV 探測 ProxyError** | `api.mof.gov.tw` 在 Streamlit Cloud 透過 Proxy 連線失敗（500），且從未成功設定 `tw_export`，浪費 10s | 整個 GOV debug 區塊移除 |
| **Macro Job 超時 >80s** | FRED 15s×3 + FinMind 15s + MOF 10s 疊加 → 超過限制 → `_macro_res=None` | 合計省下 ~25s；配合 PR #61 的 FRED 5s/NDC CKAN v3，總耗時降至 ~35-45s |

**PR #61（已 merge 2026-04-26）收錄：**
- FRED PMI timeout: 15s → 5s；新增 freshness 檢查（>60天跳過舊 FRED series）
- NDC: CKAN v3 端點優先（`/api/3/action/datastore_search`）；sort key 補 `period`/`期間`
- BLS CPI: 過濾 `value='&#39;`（未公布月份）
- `build_proxy_session()` 套用至 macro + financials 請求
- `PROXY_URL` 單一 key 支援（Streamlit Cloud 格式）

## ✅ 最新異動（v10.29，commit `a3548cb`）

### 總經資料過期根因修復（app.py）
| 問題 | 根本原因 | 修正 |
|------|---------|------|
| **PMI 877天** | FRED `MFPMI01USM657S` 授權於 2023-10 終止，fetch 成功但資料是舊的，所有備援永遠無法觸發 | 加入 freshness 檢查（>60天自動跳過）；新增 `BSCICP03USM665S`、`PMDILK03USM665S` 備援系列；讓 dbnomics OECD PMI 備援得以生效 |
| **NDC 877天** | data.gov.tw resource_id 已過期 | 加入動態搜尋 API（`package_search`）預先取得最新 resource_id；sort key 補上 `period`/`期間` 欄位 |
| **Export 390天** | FinMind 422 + MOF ProxyError，從未成功取得資料 | v10.30 正式移除（詳上） |
| **Timeout** | 40s 不夠（含 Proxy 延遲） | 調升至 80s |

## ✅ 最新異動（v10.28，commit `4c76307`）

### 資料診斷全動態化：無限制類別擴充（app.py + etf_dashboard.py + test_registry.py）
| 項目 | 說明 |
|------|------|
| **欄位重命名** | `app.py` registry：`freq` → `frequency`、`latest_date` → `last_updated`（`_reg_add` / `_reg_missing` 及全部 10+ 呼叫點同步更新） |
| **動態 Tab 生成** | `etf_dashboard.py §0`：移除硬寫的 `st.tabs(['大盤','個股','ETF'])`；改為掃描 registry 中實際存在的 `category` 值動態生成；新增任意類別不需改 UI 代碼 |
| **`_disp_name()`** | 統一 registry key → 顯示名稱轉換（去 `[先行指標]` / `[ETF]` / `[個股]` 前綴，`| ` 後取細項名） |
| **`_freshness()` 參數** | 參數從 `freq` 改為 `frequency`，與 registry 欄位名一致 |
| **`_build_table()` 欄位** | 讀 `frequency`（非 `freq`）、`last_updated`（非 `latest_date`） |
| **`_CAT_ICON` 可擴充** | 替換 `_CAT_LBL` 固定字典，未登錄類別自動顯示 `📁 {cat}` |
| **全域 Banner 修復** | 摘要計算同步使用 `last_updated` / `frequency` 欄位 |
| **`test_registry.py`（新增）** | 12 個 mock 案例（日/月/季 × 最新/略舊/過期/缺失 + 跨月/跨年邊界），全部通過 ✅ |

## ✅ 最新異動（v10.27）

### 資料診斷重構：純時間戳 + 三維嚴格分類（app.py + etf_dashboard.py）
| 項目 | 說明 |
|------|------|
| **`category` + `freq` 欄位** | `_reg_add(name, df, category, freq)` — 每筆資料在登錄時即標記類別（大盤/個股/ETF）與更新頻率（daily/monthly/quarterly） |
| **移除 df 儲存** | registry 不再儲存 DataFrame 本體，僅保留 `latest_date` / `rows` / `category` / `freq`，節省記憶體且移除 df.head() 顯示 |
| **純 freq 判定新鮮度** | `_freshness(date_str, freq)` 依 freq 欄位套用門檻，不再用名稱猜測；日≤3天🟢、月≤45天🟢、季≤90天🟢 |
| **5 欄標準表** | `資料項目 / 所屬類別 / 更新頻率 / 最新資料時間 / 狀態（🟢最新/🟡略舊/🔴過期/⚫缺失）` |
| **嚴格過濾** | 依 `category` 欄位分流，大盤/個股/ETF 三 Tab 互不干擾（驗證：三域交叉過濾均為 False） |
| **移除快照 df.head()** | 刪除實體數值顯示，診斷頁僅呈現時間戳元資料 |

## ✅ 最新異動（v10.26）

### 資料診斷重構：三域分組 + Tab 切換（etf_dashboard.py）
| 項目 | 說明 |
|------|------|
| **三域 Tab** | `st.tabs(['📊 總經 & 市場', '🔬 個股', '🏦 ETF'])` |
| **總經子分組** | 🇹🇼 台股市場 / 🌐 國際指數 / 💰 固定收益 / 📈 先行指標（5細項） |
| **個股 Tab** | 強制顯示 5 細項，缺失標 ⚫；顯示股號名稱作為標題 |
| **ETF Tab** | 只在完成 ETF 診斷後出現資料 |
| **_render_group()** | 共用渲染 helper，自動計算缺/舊數量並顯示 badge |
| **全域 Banner** | 跨三域統計 ⚫缺失 / ⚠️過期總數 |
| **快照摺疊** | 改為 `st.expander` 預設收合，減少頁面長度 |

## ✅ 最新異動（v10.25）

### 個股缺失資料明確標示（app.py + etf_dashboard.py）
| 項目 | 說明 |
|------|------|
| **強制顯示 5 細項** | `t2_data` 的 df/rev/qtr/cl/cx 全部登錄；有資料正常顯示，無資料標 `missing=True` |
| **⚫ 缺失欄** | `etf_dashboard` 表格：`missing=True` → 燈號 `⚫`、新鮮度「缺失（API未回傳）」，讓合約負債/現金流量缺失一眼可見 |
| **快照過濾** | 資料抽查快照的選項排除 missing 項目，避免選到空 DataFrame |
| **Banner 分類** | 缺失數與過期數分開統計顯示（⚫ N筆缺失 / ⚠️ N筆過期） |

## ✅ 最新異動（v10.24）

### 先行指標拆細項（app.py）
| 細項 | 來源欄位 | 資料來源 |
|------|---------|---------|
| `[先行指標] 三大法人現貨` | 外資、投信、自營 | FinMind TaiwanStockTotalInstitutionalInvestors |
| `[先行指標] 外資期貨留倉` | 外資大小 | FinMind TaiwanFuturesInstitutionalInvestors |
| `[先行指標] 選擇權PCR` | 選PCR、外(選) | FinMind TaiwanOptionInstitutionalInvestors |
| `[先行指標] 成交量（TWSE）` | 成交量 | TWSE MI_INDEX |
| `[先行指標] 未平倉/韭菜指數` | 前五大留倉、前十大留倉、未平倉口數、韭菜指數 | TAIFEX（免費版多為 null） |
- 各細項排除「整列均為 null / '-'」的日期，最新日期反映該來源最後有效資料

## ✅ 最新異動（v10.23）

### Data Registry 頻率感知新鮮度（etf_dashboard.py）
| 項目 | 說明 |
|------|------|
| **_freshness(date_str, name)** | 新增 `name` 參數，依資料名稱關鍵字自動判斷更新頻率並套用對應門檻 |
| **日更新（預設）** | 🟢 0-3天（含週末）、🟡 4-5天、🔴 >5天；0=今天、1=昨天 顯示文字 |
| **月更新（月營收）** | 🟢 ≤45天、🟡 ≤75天、🔴 >75天 |
| **季更新（季財報/現金流量/資產負債）** | 🟢 ≤90天（最新一季）、🟡 ≤180天（落後一季）、🔴 >180天 |
| **新欄位「更新頻率」** | 健康總表新增欄位，顯示 📈日/📅月/📊季 |
| **警告訊息更新** | Banner 同步說明各頻率的過期標準 |

## ✅ 最新異動（v10.22）

### Data Registry 修復 + 個股/ETF 細項掃描（app.py + etf_dashboard.py）
| 項目 | 說明 |
|------|------|
| **先行指標 NaT 修復** | `_reg_add()` 優先搜尋 `_date` 欄（YYYYMMDD 格式），以 `format='%Y%m%d'` 解析；舊的 `日期` 欄（`4月23日`，無年份）不再導致 NaT |
| **NaN 安全判斷** | `_ls` 賦值加入 `pd.isna()` 防呆，避免 `NaT` 被格式化成錯誤字串 |
| **個股細項自動登錄** | 掃描 `t2_data` 的 `df/rev/qtr/cl/cx`，以 `[個股] {sid} {name} \| {類型}` 格式寫入 registry |
| **ETF 細項自動登錄** | `etf_single_data` 新增 `price_df` 欄位；registry 掃描後以 `[ETF] {ticker} {name} \| 價格走勢` 登錄 |

## ✅ 最新異動（v10.21）

### 全域資料診斷中心（app.py + etf_dashboard.py）
| 項目 | 說明 |
|------|------|
| **Data Registry** | `app.py` 在 `st.rerun()` 前呼叫 `_reg_add()`，掃描 `cl_data.intl/tw/tech`、ADL、先行指標，寫入 `st.session_state['data_registry']` |
| **自動降冪排序** | `_reg_add()` 對 DatetimeIndex 型 DF 呼叫 `sort_index(ascending=False)`；date 欄型呼叫 `sort_values(dcol, ascending=False)` |
| **無綁定標的** | Registry 完全動態，不寫死任何股票代號 |
| **全域健康總表** | `etf_dashboard.render_data_health()` 最前加入「📋 全域資料健康總表」：讀 `data_registry`，顯示名稱/最新日期/新鮮度(🟢≤5天/🟡≤14天/🔴過舊)/筆數/欄數 |
| **快照檢視器** | `st.selectbox` 選項由 registry 動態生成；選中後顯示該 DF `.head(5)` |
| **過舊偵測** | 超過 14 天顯示 ⚠️，並在底部顯示警告 banner |

## ✅ 最新異動（v10.20）

### 6770 DSO + 負債比 N/A 修復（data_loader.py）
| 項目 | 說明 |
|------|------|
| **AR L1 vsum 新增** | 括號格式：`應收帳款（非關係人）`、`（關係人）`、`淨額`後綴、`應收票據（非關係人）/（關係人）`、短橫線格式（涵蓋 IFRS 關係人拆分揭露） |
| **AR L2 vsum 新增** | `應收帳款（含稅）`、`應收帳款淨額（含稅）`（部分公司含稅列示） |
| **AR L3 v 新增** | `應收帳款（非關係人）`、`應收帳款（關係人）` 加入備援路徑 |
| **ar_p 前期 AR 擴充** | 由 3 個 alias 擴充至 9 個，補齊括號格式與含稅格式 |
| **fuzzy 排除修正** | `["稅"]` → `["所得稅", "退稅"]`：舊排除會誤殺 `應收帳款（含稅）` 等欄位 |
| **liab 新增** | `Liabilities`（英文 type）、`負債合計（千元）`、`負債總額（千元）` |
| **驗證** | `test_6770_fields.py` 三情境（括號格式/含稅/fuzzy 修復）全部通過 |

## ✅ 最新異動（v10.19，commit `3d2049a`）

### MA120 誤判根因修復（app.py + market_strategy.py）
| 項目 | 說明 |
|------|------|
| **根本原因** | `app.py:1987` 的 `fetch_single('^TWII', period='90d')` 只回傳 ~64 交易日，不足 MA120 所需 120 筆；舊程式碼用 `current_price` 填補導致 `index_close == ma120` 判定跌破 |
| **資料長度修正** | `_job_tw()` 改為 `period='9mo'`（≈195 交易日），確保 `rolling(120)` 有效運算 |
| **新鮮度守門** | `get_market_assessment` 加入 7 天有效期檢查：末筆資料超過 7 天 → `return None` + 警告 log，防止陳舊資料產生誤判 |

## ✅ 最新異動（v10.18，commit `93d811f`）

### MA120 趨勢濾網全面升級（market_strategy.py）
| 項目 | 說明 |
|------|------|
| **歷史長度修正** | `period='300d'` → `'9mo'`（≈195 交易日），確保 `rolling(120)` 有足夠有效 bars |
| **NaN 防呆** | MA120 為 NaN 時直接 `return None`，不再以 `current_price` 填補（消除「index_close == ma120」誤判跌破）|
| **三日確認法則** | 向量化比對最近 3 日收盤 vs MA120：`ma120_above_3d` / `ma120_below_3d` |
| **均線斜率** | 今日 MA120 vs 5 日前 MA120：`ma120_rising` / `ma120_falling` |
| **狀態機重構** | 🟢 晴天 = above_3d + rising；🔴 雨天 = below_3d + falling；🟡 多雲 = 所有過渡狀態（取代原分數門檻）|
| **Label 更新** | `'🟢 多頭'` → `'🟢 多頭（晴天）'`；`'🟡 中性'` → `'🟡 震盪（多雲）'`；`'🔴 空頭'` → `'🔴 空頭防禦（雨天）'` |

## ✅ 最新異動（v10.17）

### MJ 體檢表 uncaught exception 修復（app.py）
| 項目 | 說明 |
|------|------|
| **問題根因** | `fetch_financial_statements` / `analyze_financial_health` 沒有外層 try/except；若任一函式拋出例外，session state 永遠不被寫入，expander 內容崩潰且每次 rerun 重試再崩潰 |
| **修復** | `app.py:6478` 在 `st.spinner` 內加外層 `try/except Exception as _fh_exc`；捕獲後寫入 `{'error': True, 'ai_insight': f'財報體檢發生例外：{_fh_exc}'}` |
| **效果** | 即使 FinMind API 或 AI 引擎拋例外，MJ 體檢表 expander 仍會顯示（改為紅色錯誤訊息而非空白崩潰） |

## ✅ 最新異動（v10.16，branch `f688401`）

### AI 語氣升級：股海老船長 v2（commit `f688401`）
| 項目 | 說明 |
|------|------|
| **角色升級** | 台灣資深投資顧問 → 股海老船長（多次牛熊歷練、一針見血） |
| **新增守則** | 拒絕券商官腔（禁用震盪整理/逢低承接）、籌碼翻譯蒟蒻、總經翻譯對照 |
| **輸出格式** | 核心洞察 50 字以內、兄弟帶入感、條列直擊要害 |

## ✅ 最新異動（v10.15，branch `c6011fc`）

### 全站 AI 白話文語氣注入（commit `c6011fc`）
| 項目 | 說明 |
|------|------|
| **新增 `persona.py`** | 統一定義 `TAIWAN_ADVISOR_PERSONA` 常數（台灣資深投資顧問語氣） |
| **注入方式** | Gemini REST API `systemInstruction` 欄位（等效 SDK `system_instruction=`） |
| **涵蓋範圍** | `financial_health_engine._gemini_call`、`app.gemini_call`、`macro_state_locker._default_gemini_call`、`ai_engine`（3 處 payload） |
| **安全機制** | 規格第 6 條：JSON 結構欄位不受風格影響，模組 JSON 輸出格式不變 |

## ✅ 最新異動（v10.14，branch `96f4ebb`）

### OCF 單位爆炸 + 翻桌率年化 + 條件A保命符（commit `96f4ebb`）
| 項目 | 修復內容 |
|------|---------|
| **OCF 單位** | 移除 >1e6 百萬中間層（台積電千元欄位 ~3e8 誤觸）→ 兩段式：>1e9 元÷1e8；否則千元÷1e5 |
| **資產翻桌率年化** | `financial_health_engine._no_ai_operating`：分子改為 `rev×4` |
| **條件A保命符** | Tab2/Tab3 均新增 `_is_cash_exception`；現金充足時流動比率門檻放寬至 >100%；顯示 💰 Banner |

## ✅ 最新異動（v10.13，main `23b76a2`）

### 財報計算年化 + OCF 單位 + AR 別名修復（commit `23b76a2`）
| 項目 | 修復內容 |
|------|---------|
| **ROE 年化** | `_no_ai_profitability` + `_no_ai_advanced_diagnostic`：`(NI × 4) / equity` |
| **DIO 年化** | `_no_ai_operating`：分母 `cogs × 4`，天數統一 360 |
| **DSO/DPO 年化** | `data_loader`：分母 `rev/cogs × 4`，365天→360天 |
| **OCF 單位防呆** | 三段式自動偵測：>1e9 → 元（÷1e8）；>1e6 → 百萬（÷100）；其他 → 千元（÷1e5） |
| **AR 別名** | L2 _vsum 補入 `應收帳款及票據`、`應收帳款及票據淨額` |

### 新增 fetch_goodinfo_metrics()（commit `44cd2af`）
| 項目 | 說明 |
|------|------|
| **模組** | `tw_stock_data_fetcher.py` §12.6 |
| **URL** | `BS_M_QUAR`（資產總額/負債總額/應收帳款及票據）+ `IS_M_QUAR`（營業收入） |
| **格式** | `@st.cache_data(ttl=3天)`；proxies 參數相容 Streamlit Secrets |
| **計算** | `debt_ratio = 負債/資產×100`；`DSO = 360/(rev×4/ar)` |

## ✅ 最新異動（v10.11，main `d546216`）

### 財報 N/A 與 OPM 護城河誤渲染修復（3 commits `ef7a9bf` → `d546216`）
| commit | 項目 | 內容 |
|--------|------|------|
| `ef7a9bf` | **短期償債能力保命符邏輯脫鉤** | Banner 改讀 `Final_Solvency_Verdict` 字串精確比對「條件B：天天收現」；流動比率保命符啟動時閾值 300%→150%，顏色/標籤連動 |
| `9810cd4` | **ARCHITECTURE.md v6.5 + STATE.md** | 更新版本日期；STATE.md 補記 v10.8 |
| `d546216` | **AR/負債 N/A + OPM 護城河誤觸** | AR 兩段式加總（L1拆開+L2合計行）；補全 FIELD_ALIASES（資產總額/負債總額）；OPM 雙重驗證（CCC 必須是實質負數） |

### 財報判定 3 大 UI Bug 修復（commit `d4cc9ee`）
| Bug | 修復 |
|-----|------|
| ROE 負值誤判真實獲利 | 解析數值，`ROE<=0` → ❌ 本業虧損 |
| OPM N/A 誤觸護城河 | 移除 `_p_days>_r_days` 旁路 |
| N/A 誤標「特許行業」 | 按 Value 字串區分 🏦/⚪ |

## ✅ 最新異動（v10.8，main `d4cc9ee`）

### `app.py` UI 層 3 個狀態判定 Bug 修復（commit `d4cc9ee`）
| Bug | 位置 | 修復內容 |
|-----|------|---------|
| **ROE 負值誤判真實獲利** | Tab2/Tab3 ROE 卡片 | 新增數值解析，`ROE <= 0` → `❌ 本業虧損`（紅燈） |
| **OPM 護城河被 DSO=0 誤觸** | Tab2 OPM 商業話語權 | 移除 `_p_days > _r_days` 旁路；`_r_days==0` → info 缺漏提示 |
| **N/A 誤標「特許行業」** | Tab2/Tab3 負債比率卡片 | `else "特許行業"` → 按 Value 字串區分「🏦 特許行業 / ⚪ 資料缺漏」 |

### `ARCHITECTURE.md` 技術規格書完成（v6.5）
| 章節 | 說明 |
|------|------|
| §1 目錄結構 | 專案根目錄樹、各層職責、程式碼規模（1.4） |
| §2 分層架構 | L0–L5 六層設計、跨層依賴矩陣、環境變數 |
| §3 資料流向 | Session State 架構、個股/ETF/市場三大流程、資料新鮮度 |
| §4 核心函式 I/O | 8 模組 30+ 函式輸入/輸出/副作用表格（L1–L5 + app.py） |

## ✅ 最新異動（v10.7，main `769f945`）

### `financial_health_engine.py` N/A 連鎖誤判修復（commit `769f945`）
| Bug | 位置 | 修復內容 |
|-----|------|---------|
| **OPM 護城河誤判** | `_derive_basic_from_fin_data` + `_no_ai_operating` | DSO=0(N/A) 時：`advantage=False`、雷達得 -999（最低）、`OPM_Strategy="N/A (DSO缺失)"` |
| **負債比 0% 亮綠燈** | `_derive_basic_from_fin_data` | `debt_pct` 改用 `None` 預設；缺漏 → `⚪` 灰燈；雷達「財務結構」同給 -999 |
| **OCF 單位錯誤** | `_derive_basic_from_fin_data` | `÷1e6` → `÷1e5`，顯示由 `XB` 改為 `X億` |

## ✅ 最新異動（v10.6，main `6e197ef`）

### `financial_health_engine.py` 3 大邏輯 Bug 修復（commit `6e197ef`）
| Bug | 位置 | 修復內容 |
|-----|------|---------|
| **Bug 1：ROE 負值顯示綠色** | `_no_ai_advanced_diagnostic` dupont 判斷 | 新增 `roe <= 0` 分支 → `"⚠️ ROE 為負，本業虧損"` |
| **Bug 2：天天收現防呆漏洞** | `_no_ai_solvency` 條件B | `ar_days < 15` → `0 < ar_days <= 15`，DSO 為 N/A (0) 時不觸發 |
| **Bug 3：盈餘含金量公式錯誤** | `_no_ai_advanced_diagnostic` 盈餘含金量 | NI≤0 → `"N/A (本業虧損，不適用此指標)"`；NI>0 → 標準 OCF/NI |

## ✅ 最新異動（v10.5，main `5f98874`）

### 移除執行期暫存檔（commit `5f98874`）
| 項目 | 說明 |
|------|------|
| **`macro_state.json`** | `git rm --cached` 移出追蹤；`.gitignore` 補上規則，往後不再進 repo |
| **原因** | 該檔由 `macro_state_locker.py` 執行時寫入，屬執行期狀態，非原始碼 |

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
