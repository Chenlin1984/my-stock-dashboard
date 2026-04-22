# 專案戰情室 (Project State)

## 📌 當前狀態
- **專案**: 台股 AI 戰情室（Streamlit Cloud + GitHub，Python 3.x）
- **版本**: v10.0 | main `6592db8`
- **部署**: Streamlit Cloud，需設定 `FINMIND_TOKEN` + `GEMINI_API_KEY`

## 🏗️ 核心模組
| 檔案 | 職責 |
|------|------|
| `app.py` | Streamlit 主程式（Tab1 市場/Tab2 個股/Tab3 組合/Tab4 總經/Tab5 ETF/Tab6-9 ETF子頁） |
| `data_loader.py` | FinMind HTTP API 財報抓取（BS/CF/IS）+ yfinance/Goodinfo 備援 |
| `financial_health_engine.py` | MJ財報體檢六大模組 + `no_ai_overall_verdict()` 老師動態結論 |
| `scoring_engine.py` | 多因子健康評分引擎（技術/籌碼/基本面/VCP） |
| `daily_checklist.py` | 國際/台股/法人籌碼/融資/先行指標抓取 |
| `market_strategy.py` | market_regime() 大盤狀態判定 |
| `macro_state_locker.py` | AI 總經裁決 + 原子鎖寫入 macro_state.json |
| `macro_alert.py` | VIX/CPI/PMI/PCR 等總經警示規則引擎 |
| `etf_dashboard.py` | ETF 診斷/組合/回測/AI 四子頁 |
| `unified_decision.py` | 統一投資決策（stock/etf/portfolio 三模式 3-Card UI） |
| `leading_indicators.py` | 外資期貨/PCR/ADL 先行指標 |
| `ai_engine.py` | Gemini AI 個股分析 |
| `risk_control.py` | 停損停利/倉位控制 |

## ✅ 最新修復（v10.0，commits 8d2320b → 6592db8）
| commit | 項目 | 內容 |
|--------|------|------|
| `8d2320b` | **體檢表老師動態結論 + 資產計算修復** | `no_ai_overall_verdict()` 六模組彙整生成等級A+~F；`assets = cur_assets + non_cur_assets` 兜底 |
| `6620276` | **IFRS reverse + 模糊比對 + 盈餘含金量** | reverse IFRS 移到主邏輯層；`_fuzzy_bs()` 掃全欄位；NI<0 改顯 OCF/Rev |
| `6592db8` | **引擎層重算負債比率 + Goodinfo AR 備援** | `_no_ai_financial_structure` 直接從 `流動負債(千)` 等重算；Goodinfo 季度 BS 補 AR |

## 📐 財報健檢資料補齊策略（四層）
```
L1: FinMind 精確欄位別名（30+ 中英文變體）
L2: FinMind 組合推算（流動+非流動相加 / IFRS 雙向恆等式）
L3: 模糊比對（掃 BS 所有欄位取最大值）
L4: yfinance + Goodinfo 外部備援
L5: 引擎層重算（直接從 fin_data 已有欄位推導）← 最終防線
```

## ✅ 體檢表新功能
- **老師動態結論 Banner**：六大模組渲染完畢後，顯示等級（A+/A/B+/B/C/F）+ 標題 + 具體評語
- **盈餘含金量 NI<0**：改顯 OCF/Revenue 比率（Acceptable）或「OCF負+虧損」（Fail）
- **所有 AI 按鈕整合新聞**：個股/ETF 各自搜尋 Google News RSS

## 🔒 已知限制
- TWSE IP 封鎖 → 全部走 FinMind/openapi 備援
- FinMind 免費帳號：每小時 600 次請求限制
- NDC 景氣燈號：主站封鎖 → OECD CLI 代理
- 收現速度(DSO)：特定產業（建設/REITs/金融業）AR 欄位名稱特殊，Goodinfo 備援中

## 🔑 環境變數（Streamlit Secrets）
- `FINMIND_TOKEN`: FinMind API
- `GEMINI_API_KEY`: Gemini AI（全站共用）

| `scoring_engine.py` | 多因子健康評分引擎（技術/籌碼/基本面/VCP） |
| `daily_checklist.py` | 國際/台股/法人籌碼/融資/先行指標抓取 |
| `market_strategy.py` | market_regime() 大盤狀態判定 |
| `macro_state_locker.py` | AI 總經裁決 + 原子鎖寫入 macro_state.json |
| `macro_alert.py` | VIX/CPI/PMI/PCR 等總經警示規則引擎 |
| `etf_dashboard.py` | ETF 診斷/組合/回測/AI 四子頁 |
| `unified_decision.py` | 統一投資決策（stock/etf/portfolio 三模式 3-Card UI） |
| `leading_indicators.py` | 外資期貨/PCR/ADL 先行指標 |
| `ai_engine.py` | Gemini AI 個股分析 |
| `risk_control.py` | 停損停利/倉位控制 |

## ✅ 最新修復（v9.9，commits f23f909 → 17f36c2）
| commit | 項目 | 內容 |
|--------|------|------|
| `f23f909` | **FinMind 錯誤訊息精細化** | `_fm()` 回傳 status code；依三種情境給出精確訊息：①Token 未設定 ②HTTP 401/403 Token 無效 ③股票本身無財報資料 |
| `17f36c2` | **收現速度/負債比率 yfinance 備援** | 當 FinMind 缺少 AR/liab/assets 時：①擴充 AR 欄位別名（應收款項/ReceivablesNet 等）②yfinance `.TW`/`.TWO` 備援補值 ③備援後再次 IFRS identity 補算負債 |

## ✅ 財報健檢修復歷程（v9.7 → v9.8）
| commit | 修復項目 |
|--------|---------|
| `21aa9ba` | AR/PPE 欄位擴充；IFRS identity `assets-equity` 兜底 |
| `e6a2bb1` | DSO ar==0 顯示 N/A；以長支長 equity 異常顯示 N/A |
| `fd87779` | 負債比率全部 N/A：改用 `cur_liab + non_cur_liab` 相加（FinMind 無彙總行） |
| `c3ef0f0` | equity 理智校驗（< 0.1% of assets → 用 assets-liab 重算） |

## ✅ 已完成主要功能（截至 v9.9）
- **Tab1 市場總覽**：交通燈紅綠燈、總經警示、大盤四象限、法人籌碼、融資水位
- **Tab2 個股分析**：技術/基本面/籌碼/MJ財報體檢六模組/AI首席顧問（含個股新聞）
- **Tab3 投資組合**：批次健檢、雷達均分排序、AI 組合評估（含個股新聞）
- **Tab4 總經**：VIX/PMI/M1B-M2/ADL/PCR/Gemini AI 裁決
- **Tab5-9 ETF**：單支診斷/組合配置/回測績效/AI 存股決策（均含 ETF 新聞）
- **AI 新聞整合**：所有 AI 按鈕抓取當日 Google News RSS（個股/ETF 各自搜尋）

## 🔒 已知限制
- TWSE IP 封鎖 → 全部走 FinMind/openapi 備援
- FinMind 免費帳號：每小時 600 次請求限制
- NDC 景氣燈號：主站封鎖 → OECD CLI 代理
- ETF BIAS240：新掛牌 ETF 資料不足顯示 N/A

## 🔑 環境變數（Streamlit Secrets）
- `FINMIND_TOKEN`: FinMind API
- `GEMINI_API_KEY`: Gemini AI（全站共用）
