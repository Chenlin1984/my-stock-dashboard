# 專案戰情室 (Project State)

## 📌 當前狀態
- **環境**: Streamlit Cloud + GitHub (Python 3.14)
- **進度**: 持續修復中
- **分支**: main（最新）
- **最新 commit**: `0acdf64` — ETF NAV 三修（ver快取破解 + curl_cffi + 備援log）

## 🛠️ 檔案結構與核心組件
- `app.py`: Streamlit 主程式（台股 AI 戰情室）
- `data_loader.py`: 資料抓取（FinMind HTTP API 優先）
- `chart_plotter.py`: K線+法人圖表
- `scoring_engine.py`: 多因子評分引擎
- `stock_names.py`: 股票名稱查詢
- `leading_indicators.py`: 先行指標（外資期貨/PCR/成交量/三大法人）
- `daily_checklist.py`: 每日清單
- `etf_dashboard.py`: ETF 診斷/組合/回測

## ✅ 已部署修復清單（main 最新）

| Commit | 內容 |
|--------|------|
| `efd051b` | **SSL根治**: Python 3.14 TWSE憑證問題 → Session(verify=False) × 3檔 + finmind 1.3.0 import fix |
| `8ee7b34` | **先行指標顏色**: 未平倉口數補色 + 韭菜指數全範圍著色 + 正藍負紅修正 |
| `23853db` | **毛利率修正**: FinMind季財報 token 漏傳 params + is_finance 覆蓋 NaN bug |
| `a2bbcba` | **成交量/殖利率**: roc_to_ymd補7位民國格式 + 殖利率X軸鎖定 + yfinance volume閾值 |
| `e8d4dec` | **技術線圖法人子圖**: FinMind API 加 end_date + 日期型別正規化 + 零值改顯示提示訊息 |
| `69e2cdc` | **DataLoader=None + CBC SSL + dividend import**: 跳過SDK走RawAPI / CBC verify=False / 雙路徑import |
| `c8d3c14` | **四大根本修復**: FinMind dataset名稱BuySell / TPEx SSL verify=False / scoring_engine list防護 / 現價0快取驗證 |
| `7b2cdc8` | **殖利率河流圖重寫**: 3年滾動均股利 + merge_asof動態對齊 + Y軸自動縮放 + 低股利info提示 |
| `7e6ddd6` | **殖利率河流圖 MergeError**: merge_asof→年份查表，dtype錯位根治 |
| `8738956` | **ETF折溢價率錯誤**: TWSE直讀折溢價率(%)欄位 + FinMind路徑改同日市價匹配 |
| `cdb8e31` | **清理 debug print**: data_loader.py 移除43行 DBG-INST/GP verbose print |
| `3d5a953` | **季營收圖顏色修正**: 正數→綠/負數→紅 + chart_plotter 清 debug print |
| `5781a13` | **ETF折溢價再修**: TWSE verify=False + Path B日期比對用normalize() |
| `15de029` | **ETF+毛利率雙修**: FinMind NAV>7天跳TWSE + 毛利率直接欄位/Goodinfo Session/yfinance欄位名寬鬆 |
| `45a9a82` | **ETF NAV路徑3 + 成交量月份驗證**: yfinance navPrice備援(TWSE空body) + FMTQIK返回非本月資料時改用yfinance ^TWII整月備援，修復成交量5天問題 |
| `cbd9aa6` | **三項修復**: app.py rev2結論欄名YoY%→yoy / ETF NAV path4過舊FinMind備援 / scoring_engine list明確防護 |
| `92f52e2` | **毛利率根治**: Goodinfo/yfinance fallback補充Gross Profit抓取 + FinMind無毛利時自動yfinance補充 + chart_plotter KeyError防護 |
| `e7995db` | **毛利率快取破解**: fetch_quarterly _ver=3清除舊None快取 + 排行tab tail(1)→dropna().iloc[-1]避免最新季NaN |
| `25e95c5` | **毛利率比較欄根治**: `_gc3`/`_gp_col`子字串→精確比對('毛利率名稱'誤命中bug) + ETF折溢價FinMind欄位自動偵測 + SQ獲利品質得分 |
| `29e50c8` | **三率+FGMS前瞻動能**: data_loader 新增 get_quarterly_bs_cf() + 三率(營業利益率/淨利率) + scoring_engine.calc_forward_momentum_score() 四維度加權 |
| `ef197e3` | **FGMS三率實值顯示**: 個股頁面 FGMS 區塊加入毛利率/營業利益率/淨利率最新季實際數值（方便確認抓取狀態） |
| `50ae5c7` | **FGMS debug log**: 加入 qtr_extra2/fgms/three_rate 狀態 print，供 Cloud 驗證 |
| `726c12a` | **FGMS根本修復**: scoring_engine.calc_forward_momentum_score 補 `import pandas as pd`（NameError 根治）|
| `f7084f8` | **ETF折溢價根治**: Path B舊±3天容差→同日inner join，NAV/市價日期錯位問題根除 |
| `683a411` | **ETF NAV debug**: FinMind非200補log + _ver=3快取破解 |
| `a495ce4` | **ETF NAV MoneyDJ備援**: 新增MoneyDJ爬蟲路徑(BeautifulSoup雙策略) + yfinance限速retry(2s/4s backoff) |
| `0acdf64` | **ETF NAV三修**: _ver→ver(Streamlit快取破解修正) + curl_cffi模擬Chrome繞反爬 + info備援補log |

## 🐞 已確認根本原因
- **Python 3.14 SSL**: `www.twse.com.tw` 憑證缺少 Subject Key Identifier → 全面 SSL 驗證失敗
  - 修正：三個檔案加入 `Session(verify=False)` + `urllib3 warnings off`
- **TWSE IP 封鎖**: Streamlit Cloud IP 被 TWSE 擋 `頁面無法執行` → BFI82U/T86/FMTQIK 全部走備援
- **finmind 1.3.0**: `FinMind.data` → `finmind.data`（小寫）模組路徑改變

## 🔄 待驗證項目
- [x] 先行指標成交量：roc_to_ymd 7位民國格式已修正 ✅
- [x] 先行指標顏色：正數藍色/負數紅色 ✅
- [x] FinMind法人 API 422：dataset → TaiwanStockInstitutionalInvestorsBuySell ✅
- [x] TPEx SSL：verify=False ✅
- [x] scoring_engine list崩潰：hasattr + isinstance(list) 雙重防護 ✅
- [x] 現價=0：快取驗證 + close≤0過濾 ✅
- [x] debug print 全部清除：data_loader / chart_plotter ✅
- [x] 孫慶龍結論月營收：欄位名稱 YoY%→yoy 修正，動態結論正常顯示 ✅
- [x] ETF NAV N/A：path4 過舊FinMind備援已上線，不再顯示空白 ✅
- [x] 毛利率曲線：三路徑補充Gross Profit + 快取破解(_ver=3) + tail(1)NaN修正 ✅
- [x] 毛利率比較欄根治：`'毛利率' in str(c)` → `'毛利率' in df.columns`精確比對，根除'毛利率名稱'誤命中 ✅
- [x] ETF折溢價：FinMind自動偵測 nav/base_unit_net_value 欄位 + 試兩個dataset名稱 ✅
- [x] ETF折溢價日期錯位：Path B改用same-date inner join（+1.24%→正確-0.53%）✅
- [x] SQ獲利品質得分：scoring_engine.calc_quality_score + 個股/排行tab顯示 ✅
- [x] FGMS根本錯誤修復：`import pandas as pd` 漏加導致 NameError → 726c12a 已修 ✅
- [ ] ETF NAV MoneyDJ/curl_cffi：部署後確認 log 路徑（MoneyDJ HTTP 200 成功 or 403）
- [ ] 若仍顯示 [折溢價-info備援]→代表所有路徑失敗，navPrice 過舊是根本原因需換源
- [ ] 三率實值顯示：部署後確認毛利率/營業利益率/淨利率數值是否正常出現
- [ ] FGMS分數顯示：部署後確認 fgms/cl_momentum/inv_divergence/three_rate/capex 各維度
- [ ] calc_fundamental_score 'list' object has no attribute 'empty'：另一個潛在 bug，待追蹤

## 🐞 長期已知限制
- TWSE 直接 API 被 Streamlit Cloud IP 封鎖（`頁面無法執行`）→ 全部依賴 FinMind/openapi 備援
- FinMind 免費帳號：每小時 600 次；finmind 1.3.0 SDK 路徑已改
- 前五大留倉/前十大留倉永遠 `-`：FinMind 免費版無此資料
