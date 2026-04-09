# 專案戰情室 (Project State)

## 📌 當前狀態
- **環境**: Streamlit Cloud + GitHub (Python 3.14)
- **進度**: 持續修復中
- **分支**: main（最新）
- **最新 commit**: `a2bbcba` — 成交量/殖利率X軸/yfinance volume

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
| 待推送 | **技術線圖法人子圖**: FinMind API 加 end_date + 日期型別正規化 + 零值改顯示提示訊息 |

## 🐞 已確認根本原因
- **Python 3.14 SSL**: `www.twse.com.tw` 憑證缺少 Subject Key Identifier → 全面 SSL 驗證失敗
  - 修正：三個檔案加入 `Session(verify=False)` + `urllib3 warnings off`
- **TWSE IP 封鎖**: Streamlit Cloud IP 被 TWSE 擋 `頁面無法執行` → BFI82U/T86/FMTQIK 全部走備援
- **finmind 1.3.0**: `FinMind.data` → `finmind.data`（小寫）模組路徑改變

## 🔄 待驗證項目
- [x] 先行指標成交量：roc_to_ymd 7位民國格式已修正 ✅
- [x] 先行指標顏色：正數藍色/負數紅色 ✅
- [ ] BFI82U 外資方向：TWSE 主動封鎖，需 FinMind 備援
- [ ] 技術線圖外資/投信/主力：已修正 FinMind API 呼叫（加 end_date + 日期正規化）；若仍空白看 [DBG-INST] log 確認 FinMind status/data_rows
- [ ] 毛利率：token 修正已 push，待 Streamlit Cloud 驗證
- [ ] debug checkpoints（DBG-VOL/INST/GP）：確認資料正常後可移除

## 🐞 長期已知限制
- TWSE 直接 API 被 Streamlit Cloud IP 封鎖（`頁面無法執行`）→ 全部依賴 FinMind/openapi 備援
- FinMind 免費帳號：每小時 600 次；finmind 1.3.0 SDK 路徑已改
- 前五大留倉/前十大留倉永遠 `-`：FinMind 免費版無此資料
