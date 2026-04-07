# 專案戰情室 (Project State)

## 📌 當前狀態
- **環境**: Streamlit Cloud + GitHub
- **進度**: PR #13 待 Merge（含所有最新修復）
- **分支**: claude/analyze-test-coverage-070Kf → main

## 🛠️ 檔案結構與核心組件
- `CLAUDE.md`: 核心開發與治理協議 v2.0
- `STATE.md`: 專案熱資料與進度追蹤
- `app.py`: Streamlit 主程式（台股 AI 戰情室，~5480行）
- `etf_dashboard.py`: ETF 分析儀表板（~1876行）
- `market_strategy.py`: 大盤判讀與市場策略
- `data_loader.py`: 資料抓取（yfinance/.TW/.TWO、FinMind、TWSE T86 fallback）
- `chart_plotter.py`: K線+法人圖表（無資料時顯示 ⏰ 提示）
- `scoring_engine.py`: 多因子評分引擎
- `stock_names.py`: 股票名稱查詢（靜態~100支 + yfinance動態備援）
- `daily_checklist.py`: 每日清單與欄位定義
- `requirements.txt`: 依賴清單

## ✅ 已完成並 Merged（PR #11 + #12）
- 汰弱留強明細：hide_index + reset_index + 明確欄位順序（名稱置前）
- 上櫃股票 `.TWO` fallback
- Tab3 AI 分析條件修正（results_t3 有資料即顯示）
- stock_names.py 擴充 + yfinance 動態備援
- chart_plotter.py 法人子圖無資料時顯示 ⏰ 提示
- Tab2 底部真正的 AI 分析按鈕（gemini_call）
- 外資現貨 _ov_inst fallback 至 _last_inst

## 🔄 PR #13 待 Merge（4個 commits）
1. **現價錯誤根治**: `threading.Lock()` 保護 FinMind dl + cache prefix `t3v2` 清除污染
2. **stock_names 清理**: 移除重複 key（2408/3706/3661/6770）+ 新增債券ETF（00982A等15支）
3. **TWSE T86 fallback**: FinMind 無授權時自動用 TWSE 免費 API 補充個股法人歷史資料
4. **STATE.md 更新**

## 🐞 待驗證（PR #13 Merge 後）
- [ ] 批次分析各股現價應各自正確（非全部 54.00）
- [ ] 6770/6239/00982A 名稱應正確顯示
- [ ] 個股技術線圖外資/投信子圖應顯示 T86 資料（最近10日）

## 🐞 長期已知限制
- 外資現貨總量僅收盤後 15:30 更新（TWSE BFI82U 限制）
- TWSE T86 每次查詢僅能取特定日期，10日資料需查10次（已優化為倒序最多查20天取10筆）
