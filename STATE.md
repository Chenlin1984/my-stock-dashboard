# 專案戰情室 (Project State)

## 📌 當前狀態
- **環境**: Streamlit Cloud + GitHub
- **進度**: PR #13 待 Merge（現價錯誤根治修復）
- **分支**: claude/analyze-test-coverage-070Kf → main

## 🛠️ 檔案結構與核心組件
- `CLAUDE.md`: 核心開發與治理協議 v2.0
- `STATE.md`: 專案熱資料與進度追蹤
- `app.py`: Streamlit 主程式（台股 AI 戰情室，~5480行）
- `etf_dashboard.py`: ETF 分析儀表板（~1876行）
- `market_strategy.py`: 大盤判讀與市場策略
- `data_loader.py`: 資料抓取（yfinance/.TW/.TWO fallback、FinMind）
- `chart_plotter.py`: K線+法人圖表繪製（Plotly，無資料時顯示提示）
- `scoring_engine.py`: 多因子評分引擎
- `stock_names.py`: 股票名稱查詢（靜態70+股 + yfinance動態備援）
- `daily_checklist.py`: 每日清單與欄位定義
- `requirements.txt`: 依賴清單

## ✅ 已完成並 Merged（PR #11 + #12）
- 汰弱留強明細：hide_index + reset_index + 明確欄位順序
- 上櫃股票 `.TWO` fallback
- Tab3 AI 分析條件修正
- stock_names.py 擴充至 70+ 股票 + yfinance 動態備援
- chart_plotter.py 法人子圖無資料時顯示提示
- Tab2 底部真正的 AI 分析按鈕
- 外資現貨 _ov_inst fallback 至 _last_inst

## 🔄 PR #13 待 Merge（現價錯誤根治）
- **根本原因**: FinMind DataLoader.dl 非線程安全，多 thread 並發呼叫導致所有股票回傳同一結果（54.00）
- **修復**: `threading.Lock()` 串行保護 + cache prefix `t3v2` 強制清除污染 cache + max_workers 5→3

## 🐞 待驗證（PR #13 Merge 後）
- [ ] 批次分析現價各股應各自正確
- [ ] 6770/6239 名稱應顯示「力積電/力成」
- [ ] 00982A 等 ETF 代碼應正常抓取資料

## 🐞 長期已知限制
- 三大法人個股歷史資料需 FinMind 授權（目前顯示 ⏰ 提示）
- 外資現貨總量僅收盤後 15:30 更新（TWSE BFI82U 限制）
