# 專案戰情室 (Project State)

## 📌 當前狀態
- **環境**: Streamlit Cloud + GitHub
- **進度**: 系統排毒、協議 2.0 初始化完成；PR #11 待 Merge
- **分支**: claude/analyze-test-coverage-070Kf → main

## 🛠️ 檔案結構與核心組件
- `CLAUDE.md`: 核心開發與治理協議 v2.0
- `STATE.md`: 專案熱資料與進度追蹤
- `app.py`: Streamlit 主程式（台股 AI 戰情室，~5450行）
- `etf_dashboard.py`: ETF 分析儀表板（~1876行）
- `market_strategy.py`: 大盤判讀與市場策略
- `data_loader.py`: 資料抓取（yfinance/.TW/.TWO、FinMind）
- `scoring_engine.py`: 多因子評分引擎
- `stock_names.py`: 股票名稱查詢
- `daily_checklist.py`: 每日清單與欄位定義（INTL_UNIT/TW_UNIT/TECH_MAP）
- `requirements.txt`: 依賴清單

## 🐞 待辦與已知 Bug
- [ ] PR #11 merge 後驗證：汰弱留強名稱欄、排名索引、AI分析按鈕
- [ ] 現價顯示異常（54.00）疑似舊 cache，建議清除 /tmp/st_cache/
- [ ] 建立 `Requirements.md` 確立專案目標錨點
