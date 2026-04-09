# 專案戰情室 (Project State)

## 📌 當前狀態
- **環境**: Streamlit Cloud + GitHub (Python 3.14)
- **進度**: ✅ SSL 修正已部署至 main
- **分支**: main（最新）
- **最新 commit**: `efd051b` — fix: TWSE SSL 憑證錯誤

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
| `5ff5164` | T86 欄位修正 + 股票名稱 truthy bug |
| `6363dc3` | 5項根治：BFI82U/FinMind法人/yfinance成交量/毛利率/ETF名稱 |
| `78217fd` | FinMind法人EN/ZH雙名稱 + yfinance MultiIndex |
| `3a48fc1` | _normalize_inst_pivot + _fetch_finmind_inst_raw 四層備援 |
| `ccc3892` | 五步流程移除/FMTQIK日期參數/quarterly_income_stmt/ETF NAV公式 |
| `be638b8` | 法人fallback FinMind優先 + quarterly revenue fix + yfinance ^TWII |
| `d7146e6` | debug: 插入 DBG-VOL/INST/GP 檢查點（可移除） |
| `efd051b` | **SSL根治**: Python 3.14 TWSE憑證問題 → Session(verify=False) × 3檔 + finmind 1.3.0 import fix |
| `8ee7b34` | **先行指標顏色**: 未平倉口數補色 + 韭菜指數全範圍著色 + 正藍負紅修正 |

## 🐞 已確認根本原因
- **Python 3.14 SSL**: `www.twse.com.tw` 憑證缺少 Subject Key Identifier → 全面 SSL 驗證失敗
  - 修正：三個檔案加入 `Session(verify=False)` + `urllib3 warnings off`
- **finmind 1.3.0**: `FinMind.data` → `finmind.data`（小寫）模組路徑改變
  - 修正：加入小寫路徑備援 import

## 🔄 待驗證項目
- [ ] 先行指標成交量：FMTQIK SSL 修正後應恢復
- [x] 先行指標顏色：正數藍色/負數紅色 ✅ 已修正（commit 8ee7b34）
- [ ] BFI82U 外資方向：SSL 修正後應恢復
- [ ] 技術線圖外資/投信/主力：FinMind raw API 備援
- [ ] 毛利率：FinMind TaiwanStockFinancialStatement
- [ ] debug checkpoints（DBG-VOL/INST/GP）：確認資料正常後可移除

## 🐞 長期已知限制
- TWSE 直接 API 在 Python 3.14 需要 verify=False（憑證問題）
- FinMind 免費帳號：每小時 600 次；finmind 1.3.0 SDK 路徑已改
- 前五大留倉/前十大留倉永遠 `-`：FinMind 免費版無此資料
