# 專案戰情室 (Project State)

## 📌 當前狀態
- **環境**: Streamlit Cloud + GitHub
- **進度**: 最新修復已推送，待 PR Merge
- **分支**: claude/analyze-test-coverage-070Kf → main
- **最新 commits**: e02c06c（TPEx法人）← 646abfd（EPS修復）← 5ff5164（5項Bug修復）

## 🛠️ 檔案結構與核心組件
- `CLAUDE.md`: 核心開發與治理協議 v2.0
- `STATE.md`: 專案熱資料與進度追蹤
- `app.py`: Streamlit 主程式（台股 AI 戰情室，~5500行）
- `etf_dashboard.py`: ETF 分析儀表板
- `market_strategy.py`: 大盤判讀與市場策略
- `data_loader.py`: 資料抓取（yfinance/.TW/.TWO、FinMind、TWSE T86、TPEx 法人備援）
- `chart_plotter.py`: K線+法人圖表（無資料時顯示 ⏰ 提示）
- `scoring_engine.py`: 多因子評分引擎
- `stock_names.py`: 股票名稱查詢（動態TWSE/TPEx爬蟲 + 靜態備援 + yfinance）
- `daily_checklist.py`: 每日清單與欄位定義
- `requirements.txt`: 依賴清單

## ✅ 已推送修復（branch claude/analyze-test-coverage-070Kf）

### commit 5ff5164 — 5項Bug修復
| Bug | 根本原因 | 修復 |
|-----|---------|------|
| 外資/投信圖表空白 | T86 API 欄位是「買賣超」非「淨」，f_idx/t_idx/d_idx 全 None | `data_loader.py`：改用 `買賣超` 匹配 |
| 多因子排行無名稱 | `name4_full or name4`：代碼是 truthy，後備不觸發 | 加 `name4_full != sid4` 判斷 |
| 批次分析名稱錯誤 | `_name4 or sid4` 同上問題 | `_fetch_single_t3` 改同樣判斷 |
| Tab2 個股無名稱 | `name2 or sid2`：代碼是 truthy | 加 `_gsn2` 二次查詢 |
| 技術線圖不完整 | 同外資/投信問題 | 同上修復 |

### commit 646abfd — EPS 欄位修復
| Bug | 根本原因 | 修復 |
|-----|---------|------|
| 近4季EPS 永遠 `-` | `get_quarterly_data` 未提取 EPS 欄位 | `data_loader.py`：step 5b 加入 EPS 提取；`app.py`：搜尋加入 `每股盈餘` |

### commit e02c06c — TPEx 上櫃股法人資料
| 新功能 | 說明 |
|--------|------|
| `_TPEX_DAY_CACHE` | 進程級快取，多股共用 |
| `_get_tpex_day(ds)` | TPEx 三大法人 API（民國年格式），row[4]/row[7]/row[10] |
| `_fetch_tpex_inst_fallback()` | 上櫃股備援，查最近10個交易日 |
| fallback 邏輯 | TWSE T86（上市）→ 若無資料 → TPEx（上櫃） |

## 🔄 待辦（PR Merge 後驗證）
- [ ] 上市股外資/投信子圖顯示 TWSE T86 最近10日資料
- [ ] 上櫃股（6770等）外資/投信子圖顯示 TPEx 最近10日資料
- [ ] 多因子排行顯示正確股票名稱（非代碼）
- [ ] Tab2 個股顯示正確名稱
- [ ] 批次分析「近4季EPS」顯示數值（非 `-`）

## 🐞 長期已知限制
- 外資現貨總量僅收盤後 15:30 更新（TWSE BFI82U 限制）
- 合約負債（CurrentContractLiabilities）：非所有股票都有此科目，顯示 `-` 屬正常
- 毛利率：FinMind 需有成本/毛利欄位，部分股票財報格式不同可能仍為 `-`
- TPEx API 欄位索引若 TPEx 改版需重新確認（目前 row[4]/[7]/[10]）
