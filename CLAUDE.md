# 核心開發與治理協議 (Core Protocol v2.0)

## §1 狀態與記憶管理 (State & Memory)
- **冷熱資料分離**：專案維持極簡 `STATE.md`（含檔案簡介、進度、Bug）。每次新任務**僅限讀取此檔**。絕對禁止無故讀取完整 JSONL，僅允許用 `grep/tail` 抽樣。
- **防幻覺機制 (Anti-Hallucination)**：若單一任務對話超過 10 輪，修改程式碼前**必須重新讀取目標檔**，嚴禁依賴記憶盲寫。
- **主動壓縮 (Context Compact)**：階段任務完成時，主動提醒我執行 `/compact` 指令，清理無用推理鏈，保留核心記憶。

## §2 精準讀寫與檢索 (Precision I/O)
- **動工前大掃除**：重構或開發前，優先清理 Dead code 與 Unused imports，極大化釋放 Token 空間。
- **防截斷讀取**：讀取超過 500 行的檔案，強制使用 `offset` 與 `limit` 分段讀取；永遠預設搜尋結果可能被截斷，必須用 `grep` 進行二次驗證。
- **局部編輯**：閉嘴寫扣 (No-Yapping)。嚴禁無意義的整檔讀取與整檔覆蓋，針對特定函數局部替換。

## §3 規劃與多線程 (Plan & Parallel Execute)
- **嚴格三步法**：面對複雜任務，先以 Explore Agent（唯讀探索）釐清架構 -> 提出 Plan（3 句話實作藍圖）與我確認 -> 獲准後才 Execute（動手改 code）。
- **並行處理優勢**：若任務牽涉超過 5 個檔案（如全域重構），主動拆分成子任務並行處理，極致利用 API Context Cache 共享快取。

## §4 鋼鐵自省與交付 (Audit & Delivery)
- **強制驗證機制**：不准說 Done 就跑。修改後必須通過 Type check 與 Lint，確認無誤後輸出簡短報告：[邏輯]、[邊界]、[效能]、[Debug]。
- **環境與效能**：限用 `.py` 腳本（禁 `.ipynb`），維護 `requirements.txt`。妥善運用 `st.cache_data` 及 `.clear()` 處理 UI 數據同步。
- **PR 規範**：修改後使用 `gh pr create` 建立請求，並提供一鍵 Merge 指令 `gh pr merge <PR號碼> --merge --delete-branch` 供使用者操作。嚴禁自動 Merge。

## §5 卡關救援 (Anti-Loop Protocol)
- 針對同一個報錯，若連續重試 2 次未果，**嚴禁繼續盲目猜測**。
- 立即停機並輸出「外部 AI 諮詢清單」（精煉列出問題核心、終端機錯誤 Log 與相關代碼片段），交由我詢問其他 AI。
