# 專案戰情室 (Project State)

## 📌 當前狀態
- **專案**: 台股 AI 戰情室（Streamlit Cloud + GitHub，Python 3.14）
- **版本**: v5.3 | main `5e0fb48` | dev `claude/analyze-test-coverage-070Kf`
- **最新異動**: calc_fundamental_score list防呆根治 + STATE重建

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

## 🐞 待驗證（需 Cloud log 確認）
- [ ] M1B=7.12% / M2=5.38%：pct_cols[-4][-2] 確認（`54ce45f`）
- [ ] NDC data.gov.tw 3個resourceID 是否命中，或退回 OECD CLI 代理
- [ ] 孫慶龍「有基之彈」：Export=31.82% 確認觸發（`e400ef7`）

## 🔒 長期已知限制
- TWSE IP 封鎖 → 全部走 FinMind/openapi 備援
- FinMind 免費帳號：每小時 600 次
- 董監持股 I6：FinMind 免費版無資料（顯示 N/A）
- NDC 景氣燈號：主站 Angular SPA 封鎖 → OECD CLI 代理

## 🔑 環境變數（Streamlit Secrets）
- `FINMIND_TOKEN`: FinMind API
- `GEMINI_API_KEY`: Gemini AI（全站共用）
