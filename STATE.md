# 專案戰情室 (Project State)

## 📌 當前狀態
- **環境**: Streamlit Cloud + GitHub
- **進度**: PR #12 待 Merge（5項修復已推送）
- **分支**: claude/analyze-test-coverage-070Kf → main

## 🛠️ 檔案結構與核心組件
- `CLAUDE.md`: 核心開發與治理協議 v2.0
- `STATE.md`: 專案熱資料與進度追蹤
- `app.py`: Streamlit 主程式（台股 AI 戰情室，~5470行）
- `etf_dashboard.py`: ETF 分析儀表板（~1876行）
- `market_strategy.py`: 大盤判讀與市場策略
- `data_loader.py`: 資料抓取（yfinance/.TW/.TWO fallback、FinMind）
- `chart_plotter.py`: K線+法人圖表繪製（Plotly）
- `scoring_engine.py`: 多因子評分引擎
- `stock_names.py`: 股票名稱查詢（靜態70+股 + yfinance動態備援）
- `daily_checklist.py`: 每日清單與欄位定義
- `requirements.txt`: 依賴清單

## ✅ 已完成功能（PR #11 已 Merge）
- Tab3 汰弱留強明細：`hide_index=True` + `reset_index` + 明確欄位順序
- 上櫃股票 `.TWO` fallback（data_loader.py）
- Tab3 AI 分析條件：`results_t3` 有資料即顯示按鈕

## 🔄 PR #12 待 Merge（5項修復）
- **現價全是54.00** → `_fetch_single_t3` 改呼叫 `loader_t3.get_combined_data` 直呼，修復 ThreadPoolExecutor 跨線程 cache 污染
- **名稱顯示代碼** → `stock_names.py` 擴充至 70+ 股票 + yfinance 動態備援
- **外資/投信/主力圖表空白** → chart_plotter.py 無資料時顯示 ⏰ 提示
- **Tab2 底部 AI 分析** → 移除假連結，加入真正 gemini_call 按鈕
- **外資現貨 "--"** → `_ov_inst` fallback 至 `_last_inst` session state

## 🐞 待驗證（PR #12 Merge 後）
- [ ] 現價是否恢復正確（ThreadPoolExecutor cache 問題是否根治）
- [ ] 6770/6239 名稱是否顯示「力積電/力成」
- [ ] 個股技術線圖法人子圖是否顯示提示或資料
- [ ] Tab2 底部 AI 按鈕是否可用
- [ ] 外資現貨是否顯示最後已知值

## 🐞 長期已知限制
- 三大法人個股歷史資料需 FinMind 授權（目前顯示提示）
- 外資現貨總量僅收盤後 15:30 更新（TWSE BFI82U 限制）
