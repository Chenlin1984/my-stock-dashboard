# 專案戰情室 (Project State)

## 📌 當前狀態
- **環境**: Streamlit Cloud + GitHub (Python 3.14)
- **進度**: v5.3 Section十 AI總經戰情總結改用 gemini_call()（移除 anthropic 依賴）
- **分支**: main `9237f0d`（已部署 Streamlit Cloud）
- **最新 commit**: `9237f0d` (dev→main) — Section十改用既有 gemini_call()，移除 anthropic 套件，GEMINI_API_KEY

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
| `b808b9a` | **移除錯誤備援**: 刪除yfinance info.navPrice備援路徑，NAV抓不到顯N/A不顯錯誤數字 |
| `fa09590` | **基本面先行指標6大指標**: calc_leading_indicators_detail() 模組一~四 + 個股頁D2區塊 |
| `6d92f72` | **Edge Case防護**: 重大資產處分偵測（處分流入/CapEx>2×）→ I4/I5暫停懲罰改標⚠️事件驅動 |
| `003547a` | **D2動態投資建議**: 6指標合成→🟢多方/🔴偏弱/🟡中性/⚠️事件驅動 + 多方因素/風險/建議行動 |
| `c2d330c` | **下載按鈕WebSocket修復**: st.download_button→Base64 data URL，行動瀏覽器不再噴錯 |
| `8295b53` | **M1B/M2+乖離率資料根治**: 乖離率改用2y TWII(MA240正確)；M1B加FM路徑+移除大盤代理誤導備援 |
| `cd992de` | **宏爺/孫慶龍公式升級+ADL Bug修復**: SOX×DXY四象限/Yield三區間公式；ADL↑誤判空頭根治 |
| `730481d` | **股匯四象限精準公式**: 股匯雙漲/股漲匯貶/股匯雙殺/股跌匯升 + 各象限持股%建議 |
| `bede66d` | **Section三籌碼公式升級**: 宏爺外資門檻100億(大戶點火/觀望/大戶倒貨) + 孫慶龍融資2800/3400億(乾淨/警戒/泡沫尾端) |
| `6a6ddb6` | **Section四ETF遺毒根除+期現貨背離矩陣**: 宏爺4象限(鎖單避險/雙殺/主升段/中性) + v5純股票%/現金%卡片(移除00679B/00720B) |
| `556b01f` | **Section四宏爺公式改版**: 改用純期貨口數絕對門檻（≤-3萬/≤-1.5萬/微空/翻多），移除期現貨矩陣，容錯率最高 |
| `33cb5a5` | **Section七根治**: 年線乖離MultiIndex展平(yfinance 1.2.x bug) + M1B FinMind判斷改data非空 + CBC多URL輪詢 |
| `1ba663b` | **M1B FRED+IMF備援**: FRED MYAGM1/M2TWA189S + IMF DataMapper MANMM101/MABMM301 |
| `c42daa6` | **Section八總經拼圖v4.0**: NDC景氣燈號/外銷訂單YoY/ISM PMI/核心CPI/VIX時間序列+v4.0總經否決權 |
| `7529317` | **DB.nomics整合**: requirements加dbnomics + IMF/IFS TW M1B/M2 + OECD CLI備援(PMI) + US CPI備援 |
| `729036b` | **三項根治+v4.0結論**: VIX競態→直接HTTP API+5~90驗證 / FinMind無效dataset停用 / 宏爺VIX否決權+孫慶龍乖離×CLI矩陣 |
| `44d96cb` | **防禦模式誤顯修正**: 點擊更新時立即覆蓋舊燈號為「載入中」，防止舊快取強制防禦旗幟在新資料抓取期間誤導用戶 |
| `72ccdab` | **CBC M1B 診斷+修正**: 加印 meta/row0 診斷 / meta-as-list 欄位提取 / 首列全字串作 header / 移除重複 cpx URL |
| `70f29b8` | **CBC M1B 根治**: EF17M01（貨幣總計數月底數）+EF01M01 雙路徑 / _parse_cbc_ds+_extract_yoy 統一解析 / 數值範圍自動偵測 YoY 欄位（0.05~35%）三層防禦 |
| `ba11c14` | **孫慶龍BIAS240邏輯修正+宏爺M1B Gap**: 孫慶龍改為純BIAS240四段門檻（≥15%史詩/≥10%紅警/≥0%多頭/≥-10%整理/<-10%黃金坑），移除CLI條件閘；Section8新增宏爺M1B-M2 Gap三段公式 |
| `df6b88f` | **四項根治**: M1B大存量偵測(median>100排序M2>M1B)根治MacroMicro不符 / 孫慶龍v4.0 BIAS240×CLI二維矩陣 / NDC景氣燈號Chrome頭+多URL / 外銷訂單改OECD MEI DB.nomics |
| `b1a3feb` | **M1B/M2根本修正**: 移除錯誤大存量偵測(EF17M01子項目最大欄≠M2) / EF01M01調為第一優先 / pct偵測改用[-3]=M1B,[-2]=M2（MacroMicro確認pct[-2]=M2=5.38%）|
| `e400ef7` | **孫慶龍v5.0+攻擊三環**: BIAS240×外銷訂單二維矩陣(有基之彈/無基之彈/長線黃金坑/景氣寒冬) / 攻擊火力分級SSS/A/B三環公式(VIX+期貨+Export+M1B-M2+外資+股匯+SOX) / NDC session暖機+空回應guard |
| `66c0a4a` | **Merge to main**: 含全部上述修正，已部署 Streamlit Cloud |
| `54ce45f` | **M1B[-4]根治+NDC略過**: EF01M01 pct_cols[-4]=M1B(7.12%),-[2]=M2(5.38%)確認 / NDC Angular SPA確認封鎖，移除所有5URL改為clean skip |
| `84f5045` | **Merge to main**: 含M1B[-4]根治+NDC略過，已部署 Streamlit Cloud |
| `11aa5be` | **NDC data.gov.tw+CLI代理+Section九AI分析**: NDC改用data.gov.tw 3個resourceID輪詢 / OECD CLI自動映射景氣燈號分數代理 / KPI卡顯示「(OECD CLI代理)」標籤 / Section九總經AI投資決策分析五維度（①總經位階 ②建議配置 ③貨幣流向 ④美股動態 ⑤結論）|
| `511dc64` | **Merge to main**: 含NDC代理+AI五維度，已部署 Streamlit Cloud |
| `65cff8e` | **Section十 AI總經戰情總結**: _fetch_macro_news(feedparser RSS 4源) + _run_llm_analysis(claude-sonnet-4-6，8欄JSON) + UI主卡片(情緒/持股%/作戰指令/風險機會) + 新聞來源expander + 說明卡；需設定ANTHROPIC_API_KEY Secrets；requirements新增feedparser+anthropic |
| `f7431fb` | **Merge to main**: 含AI總經戰情總結，已部署 Streamlit Cloud |
| `edb36fa` | **Section十改用 gemini_call()**: 移除 anthropic import/套件，_run_llm_analysis 改用既有 gemini_call() (2.5-flash-lite→2.5-flash→2.0-flash fallback)，UI提示改為 GEMINI_API_KEY |
| `9237f0d` | **Merge to main**: Section十 Gemini版，已部署 Streamlit Cloud |

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
- [x] 三率實值顯示：毛利率/營業利益率/淨利率最新季數值顯示於FGMS區塊 ✅
- [x] FGMS分數顯示：fgms/cl_momentum/inv_divergence/three_rate/capex 各維度已顯示 ✅
- [x] ETF折溢價錯誤數字：移除yfinance info備援，無法取得NAV時顯示N/A ✅
- [x] ETF NAV MoneyDJ/curl_cffi：已部署，待Cloud log確認成功路徑
- [x] 基本面先行指標D2區塊：I1~I6 6大指標計算+顯示 ✅
- [x] Edge Case賣廠誤判：I4/I5重大資產處分偵測，暫停懲罰改標⚠️事件驅動 ✅
- [x] D2動態投資建議：6指標合成多方/偏弱/中性/事件驅動 + 建議行動 ✅
- [x] 下載按鈕行動瀏覽器斷線錯誤：改用Base64 data URL ✅
- [x] 年線乖離率低估：改用2年TWII確保MA240正確計算 ✅
- [x] M1B/M2錯誤數字：加入FinMind路徑，移除大盤代理誤導備援 ✅（待Cloud log確認CBC/FM哪條路徑成功）
- [x] ADL宏爺邏輯Bug：_twii_p5=0落入else空頭分支 → 改用tw_s優先源+None判斷 ✅
- [x] 宏爺/孫慶龍公式升級：SOX×DXY四象限 + 10Y Yield三區間 ✅
- [x] 台股大盤股匯四象限：TAIEX×FX四象限精準判斷 + 持股%建議 ✅
- [x] Section三籌碼公式：宏爺外資100億門檻 + 孫慶龍融資2800/3400億門檻 ✅
- [x] Section四ETF遺毒根除：移除 00679B/00720B，v5改為純現金策略卡片 ✅
- [x] Section四宏爺期現貨背離矩陣：4象限精準公式(鎖單避險/雙殺/主升段/中性) ✅
- [x] Section四宏爺公式最終版：純期貨口數絕對門檻（≤-3萬強制防禦/≤-1.5萬收縮/微空持平/翻多積極）✅
- [x] Section七年線乖離MultiIndex：yfinance 1.2.x MultiIndex展平+寬鬆欄位查找 ✅
- [x] Section七M1B：FinMind改data非空判斷 + FRED(MYAGM1/M2TWA189S) + IMF DataMapper備援 ✅
- [x] **Section八總經拼圖v4.0**：NDC景氣燈號/外銷訂單/ISM PMI/核心CPI/VIX時間序列圖 ✅
- [x] **DB.nomics整合**：requirements.txt加入dbnomics + M1B(IMF/IFS TW) + CPI + PMI(OECD CLI)備援 ✅
- [x] v4.0 總經否決權：VIX≥30強制空手 / PMI<48無基之彈 / CPI>4%外資提款 / 藍燈危機入市 ✅
- [x] **防禦模式燈號誤顯**：點擊更新立即覆蓋舊快取燈號為載入中提示，防止強制防禦旗幟誤導 ✅
- [ ] **M1B/CBC 最終驗證(v3)**：`54ce45f` pct[-4]=M1B，待 Cloud log 確認 M1B=7.12% M2=5.38%
- [ ] **孫慶龍v5.0+攻擊火力分級**：`e400ef7` 已部署，待 Cloud log 確認 Export=31.82% 觸發「有基之彈」，攻擊分級正確顯示
- [ ] **NDC景氣燈號 data.gov.tw**：`11aa5be` 已部署，待 Cloud log 確認 data.gov.tw 是否命中（3個resourceID）或退回 OECD CLI 代理
- [x] **Section九 總經AI投資決策分析**：五維度（①總經位階 ②建議配置 ③貨幣流向 ④美股動態 ⑤結論）已部署 ✅
- [x] **Section十 AI總經戰情總結（LLM）**：RSS新聞抓取(feedparser)+Gemini分析+8欄JSON+主卡片UI 已部署 ✅
- [x] **GEMINI_API_KEY**：Section十改用既有 gemini_call()，與全站一致，無需額外設定 ✅
- [x] **calc_fundamental_score list bug**：app.py 569行入口加 isinstance(list)/hasattr 防呆，根治 AttributeError ✅
- [x] **孫慶龍 BIAS240 邏輯Bug修正**：+13.9% 原誤顯「中性」，改為純BIAS240四段門檻，現正確觸發「紅色警戒線」 ✅
- [x] **宏爺 M1B Gap 新增**：Section 8 新增 Gap≥1%=熱錢狂潮 / 0~1%=資金溫和 / <0%=資金退潮 三段公式 ✅
- [ ] calc_fundamental_score 'list' object has no attribute 'empty'：另一個潛在 bug，待追蹤
- [ ] 董監持股I6：FinMind免費版無資料，目前顯示N/A；如需啟用須升級付費版

## 🐞 長期已知限制
- TWSE 直接 API 被 Streamlit Cloud IP 封鎖（`頁面無法執行`）→ 全部依賴 FinMind/openapi 備援
- FinMind 免費帳號：每小時 600 次；finmind 1.3.0 SDK 路徑已改
- 前五大留倉/前十大留倉永遠 `-`：FinMind 免費版無此資料
