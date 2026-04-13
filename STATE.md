# 專案戰情室 (Project State)

## 📌 當前狀態
- **專案**: 台股 AI 戰情室（Streamlit Cloud + GitHub，Python 3.14）
- **版本**: v5.7 | main `pending` | dev `pending`
- **最新異動**: ETF AI 存股決策模組 + etf_dashboard.py 棄用警告排毒

## 🛠️ 核心檔案
| 檔案 | 職責 |
|------|------|
| `app.py` | Streamlit 主程式（10 個 Section，~4700 行）|
| `daily_checklist.py` | 國際/台股/技術指標抓取 + section_header/kpi UI 元件 |
| `data_loader.py` | FinMind HTTP API 資料抓取 |
| `scoring_engine.py` | 多因子健康評分引擎 |
| `chart_plotter.py` | K線 + 法人子圖 |
| `leading_indicators.py` | 外資期貨/PCR/ADL 先行指標 |
| `etf_dashboard.py` | ETF 診斷/組合/回測/AI 四子頁 |
| `ai_engine.py` | 個股 Gemini AI 分析 |

## ✅ 已上線功能（截至 v5.3）
- Section 一：國際市場（SOX×DXY 四象限、10Y殖利率三區間）
- Section 二：台股大盤（股匯四象限、ADL廣度）
- Section 三：籌碼（外資100億門檻、融資2800/3400億）
- Section 四：期現貨（期貨口數絕對門檻）
- Section 五/六：法人技術 + 個股先行指標 D2
- Section 七：M1B-M2 Gap + 年線乖離率 BIAS240
- Section 八：總經拼圖 v4.0（VIX時序圖、NDC代理、外銷訂單、CPI、OECD CLI）
- Section 九：總經 AI 五維度規則分析（位階/配置/貨幣流向/美股/結論）
- Section 十：AI 總經戰情總結（Gemini LLM × RSS 新聞 × 8欄 JSON）

## 🔒 長期已知限制（持續中）
- TWSE BFI82U / 融資 IP 封鎖 → FinMind 備援正常
- NDC data.gov.tw 3個resourceID 全404 → OECD CLI代理正常
- st.dataframe / st.button 的 `use_container_width` 待 Streamlit 官方明確後再處理
- ETF AI 存股決策：BIAS240 需 ≥240 日資料，新掛牌 ETF 會顯示 N/A

## ✅ 已修復（v5.4–v5.7）
- `calc_fundamental_score` list/hasattr 防呆（`5b314c8`）
- duplicate `_li_log()` 死碼 7 行清除（`2ca50e2`）
- SyntaxError L4604：f-string 混用隱式/顯式串接（`21c80f2`）
- ADL `_ui/_di` index-0 falsy bug → `is not None`（`205b4a7`）
- app.py `use_container_width` → `width='stretch'` 18處（`7125bcd`）
- etf_dashboard.py `use_container_width` → `width='stretch'` 7處（排毒）
- ETF Tab⑥ AI 存股決策總結模組（BIAS240＋KD＋Gemini）（`a28fc34`）

## ✅ Cloud log 驗證確認
- M1B=7.12% / M2=5.38% ✓
- NDC data.gov.tw 全404 → OECD CLI代理=19分 ✓
- Export=31.82% ✓

## 🔒 長期已知限制
- TWSE IP 封鎖 → 全部走 FinMind/openapi 備援
- FinMind 免費帳號：每小時 600 次
- 董監持股 I6：FinMind 免費版無資料（顯示 N/A）
- NDC 景氣燈號：主站 Angular SPA 封鎖 → OECD CLI 代理

## 🔑 環境變數（Streamlit Secrets）
- `FINMIND_TOKEN`: FinMind API
- `GEMINI_API_KEY`: Gemini AI（全站共用）
