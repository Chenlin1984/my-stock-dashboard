# 專案戰情室 (Project State)

## 📌 當前狀態
- **環境**: Streamlit Cloud + GitHub
- **進度**: ✅ 所有修復已部署至 main
- **分支**: main（最新）
- **最新 commit**: `ccc3892` — fix: 五項顯示問題修正

## 🛠️ 檔案結構與核心組件
- `app.py`: Streamlit 主程式（台股 AI 戰情室，~5500行）
- `data_loader.py`: 資料抓取（TWSE T86 + TPEx 法人備援、FinMind、yfinance）
- `chart_plotter.py`: K線+法人圖表
- `scoring_engine.py`: 多因子評分引擎
- `stock_names.py`: 股票名稱查詢（動態TWSE/TPEx + 靜態備援）
- `leading_indicators.py`: 先行指標（外資期貨/PCR/成交量/三大法人）
- `daily_checklist.py`: 每日清單（外資方向 FinMind 四層備援）
- `etf_dashboard.py`: ETF 診斷/組合/回測（折溢價 FinMind NAV）

## ✅ 已部署修復清單（main 最新）

### PR #17 以前（主要功能修復）
| Commit | 內容 |
|--------|------|
| `5ff5164` | T86 欄位名稱修正（買賣超非淨）+ 股票名稱 truthy bug × 3 |
| `646abfd` | get_quarterly_data 新增 EPS 欄位提取 |
| `e02c06c` | TPEx 上櫃股法人備援 |
| `b39bf54` | 毛利率備援（Goodinfo 季損益 step 5c）|
| `1da2ffd` | 股名快取 TTL 保護 + TPEx 欄位驗證 |
| `b4f221d` | 成交量補強（三 URL + OpenAPI + row[2]/row[1]）|
| `a6cf5c1` | roc_to_ymd 支援 YYYYMMDD 西元格式 |

### PR #17 後（直接推 main）
| Commit | 內容 |
|--------|------|
| `fb2a513` | twse_volume_daily 加 cache + sleep 優化 |
| `8464148` | 熱力板塊漲紅跌綠 + BFI82U rwd/zh 備援 + 流程圖更新 + 結論收合 |
| `6363dc3` | **5項根治**：BFI82U `r.json()` bug / FinMind法人rename / yfinance^TWII成交量 / yfinance毛利率 / ETF名稱 |
| `78217fd` | pandas 3.0 `groupby(axis=1)` 相容 + FinMind法人EN/ZH雙名稱 + yfinance MultiIndex成交量 |
| `3a48fc1` | data_loader: `_normalize_inst_pivot` + `_fetch_finmind_inst_raw` 四層備援法人資料 |
| `ccc3892` | **五項修正**：五步流程移除 / OpenAPI FMTQIK日期參數 / quarterly_income_stmt毛利率 / ETF折溢價NAV公式+歷史表格 |

## 🔄 驗證清單
- [ ] 外資方向：每日清單顯示有效數值（非「未知」）
- [ ] 先行指標成交量：FMTQIK OpenAPI 日期修正後顯示億數
- [ ] 技術線圖：外資/投信/主力子圖有資料（`_normalize_inst_pivot` 四層備援）
- [ ] 毛利率：非金融股顯示數值（quarterly_income_stmt 優先）
- [ ] ETF 折溢價：FinMind NAV 來源 + 正確公式 `(市價-淨值)/淨值×100`
- [ ] ETF 折溢價：歷史 NAV 表格顯示於折溢價率下方

## 🐞 長期已知限制（非程式 Bug）
- TWSE 直接 API（FMTQIK/MI_INDEX/BFI82U/T86）在 Streamlit Cloud 可能被 rate-limit → 以 FinMind 為雲端安全備援
- FinMind 免費帳號：每小時 600 次限制；無 token 時部分 dataset 可能拒絕
- FinMind `TaiwanETFNetAssetValue` 更新頻率：T+1（收盤後隔日）
- 前五大留倉/前十大留倉永遠顯示 `-`：FinMind 免費版無此資料，屬正常
- 合約負債顯示 `-`：只有預收款業務公司才有此科目，屬正常
- 外資現貨總量：僅收盤後 15:30 更新（TWSE BFI82U 限制）
