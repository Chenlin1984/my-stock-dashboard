# 專案戰情室 (Project State)

## 📌 當前狀態
- **環境**: Streamlit Cloud + GitHub
- **進度**: ✅ 所有修復已部署至 main（直接推送）
- **分支**: main（最新）
- **最新 commit**: 待本次 commit

## 🛠️ 檔案結構與核心組件
- `app.py`: Streamlit 主程式（台股 AI 戰情室，~5500行）
- `data_loader.py`: 資料抓取（TWSE T86 + TPEx 法人備援、FinMind、yfinance）
- `chart_plotter.py`: K線+法人圖表
- `scoring_engine.py`: 多因子評分引擎
- `stock_names.py`: 股票名稱查詢（動態TWSE/TPEx + 靜態備援）
- `leading_indicators.py`: 先行指標（外資期貨/PCR/成交量/三大法人）
- `daily_checklist.py`: 每日清單
- `etf_dashboard.py`: ETF 診斷/組合/回測

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
| 本次 | pandas 3.0 `groupby(axis=1)` 相容性修正 |

## 🔄 驗證清單
- [ ] 外資方向：從「未知」變回有效數值
- [ ] 先行指標成交量：顯示億數（yfinance ^TWII 備援）
- [ ] 技術線圖：外資/投信/主力子圖有資料（rename_dict 修正）
- [ ] 毛利率：非金融股顯示數值（yfinance quarterly_financials）
- [ ] ETF 組合配置表：顯示中文名稱欄
- [ ] 熱力板塊：漲=紅，跌=綠

## 🐞 長期已知限制（非程式 Bug）
- 合約負債顯示 `-`：只有預收款業務公司才有此科目，屬正常
- TWSE 直接 API（FMTQIK/MI_INDEX/BFI82U）在 Streamlit Cloud 可能被 rate-limit
- FinMind 免費帳號：每小時 600 次限制
- 外資現貨總量：僅收盤後 15:30 更新（TWSE BFI82U 限制）
