# 專案戰情室 (Project State)

## 📌 當前狀態
- **環境**: Streamlit Cloud + GitHub
- **進度**: 系統排毒、協議 2.0 (Level 5 + Anti-Drift) 部署完成
- **分支**: claude/analyze-test-coverage-070Kf

## 🛠️ 檔案結構與核心組件
- `CLAUDE.md`: 核心開發與治理協議
- `STATE.md`: 專案熱資料與進度追蹤
- `app.py`: Streamlit 主程式入口 (~5440行)
- `etf_dashboard.py`: ETF分析儀表板 (~1876行)
- `market_strategy.py`: 市場策略與大盤判讀
- `data_loader.py`: 資料抓取與快取
- `scoring_engine.py`: 多因子評分引擎
- `stock_names.py`: 股票名稱查詢
- `daily_checklist.py`: 每日清單與欄位定義
- `requirements.txt`: 依賴清單

## 🐞 待辦與已知 Bug
- [ ] 汰弱留強明細：現價顯示錯誤、名稱欄消失、排名從0開始
- [ ] 非內建代碼（無.TW後綴）抓不到資料（0筆）
- [ ] 所有Tab下方沒有最終AI分析顯示
- [ ] 建立 `Requirements.md` 確立專案目標錨點
