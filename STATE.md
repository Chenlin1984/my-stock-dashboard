# 專案戰情室 (Project State)

## 📌 當前狀態
- **環境**: Streamlit Cloud + GitHub
- **進度**: 22 commits 待 Merge → main（所有修復尚未部署）
- **分支**: claude/analyze-test-coverage-070Kf → main
- **最新 commit**: 362c2db（STATE.md 更新）
- **⚠️ 行動項目**: 請前往 GitHub Merge PR → https://github.com/Chenlin1984/my-stock-dashboard/compare/main...claude/analyze-test-coverage-070Kf

## 🛠️ 檔案結構與核心組件
- `app.py`: Streamlit 主程式（台股 AI 戰情室，~5500行）
- `data_loader.py`: 資料抓取（TWSE T86 + TPEx 法人備援、FinMind、yfinance）
- `chart_plotter.py`: K線+法人圖表
- `scoring_engine.py`: 多因子評分引擎
- `stock_names.py`: 股票名稱查詢（動態TWSE/TPEx + 靜態備援）
- `leading_indicators.py`: 先行指標（外資期貨/PCR/成交量/三大法人）
- `daily_checklist.py`: 每日清單

## ✅ 所有已推送修復（18 commits，待 Merge）

| Commit | 內容 |
|--------|------|
| `f9ff17d` | 批次現價錯誤根治（threading.Lock + t3v2 cache）|
| `3a63f8b` | TWSE T86 法人備援（上市股）|
| `9cc82bf` | stock_names 動態爬蟲架構（TWSE/TPEx OpenAPI）|
| `60a2722` | T86 全市場日快取（多股共用）|
| `5ff5164` | **T86 欄位名稱修正**（買賣超非淨）+ 股票名稱 truthy bug × 3 |
| `646abfd` | **get_quarterly_data 新增 EPS 欄位提取** |
| `e02c06c` | **TPEx 上櫃股法人備援**（_get_tpex_day / _fetch_tpex_inst_fallback）|
| `b39bf54` | **毛利率備援**（Goodinfo 季損益 step 5c）|
| `1da2ffd` | **股名快取 TTL 保護**（API 失敗時保留舊 2600+ 筆）+ TPEx 欄位驗證 |
| `75ea74e` | **總經成交量修復**（FMTQIK 多 URL 備援 + MI_INDEX 不硬編碼 table[6]）|
| `b4f221d` | **成交量補強**（FMTQIK 三 URL + OpenAPI + row[2]/row[1] 雙索引 + MI_INDEX 搜尋所有 tables）|
| `a6cf5c1` | **roc_to_ymd 修正**（支援 YYYYMMDD 西元格式，OpenAPI 第三備援 URL 實際生效）|

## 🔄 Merge 後驗證清單
- [ ] 上市股技術線圖外資/投信子圖顯示（T86 買賣超修正）
- [ ] 上櫃股技術線圖外資/投信子圖顯示（TPEx 備援）
- [ ] 多因子排行顯示正確股票名稱
- [ ] 批次分析近4季EPS 顯示數值
- [ ] 毛利率顯示（FinMind 有資料時）
- [ ] 總經先行指標成交量欄位顯示億數

## 🐞 長期已知限制（非程式 Bug）
- 合約負債顯示 `-`：只有預收款業務公司才有此科目，屬正常
- 毛利率仍 `-`：Goodinfo rate-limit 或該股確實無資料
- TPEx API 欄位索引：需上線觀察 `idx=(4,7,10)` log 確認
- 外資現貨總量：僅收盤後 15:30 更新（TWSE BFI82U 限制）
