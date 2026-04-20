"""
financial_health_engine.py — MJ 林明樟財報體檢 AI 引擎
--------------------------------------------------------
analyze_financial_health(api_key, stock_id, fin_data) -> dict
  fin_data: fetch_financial_statements() 的輸出
  回傳標準化 8 欄 JSON 供 Streamlit 前端渲染
"""
from __future__ import annotations

import json
import re
import time

import requests


# ── Survival Module Prompt（存活能力：3大生死指標）──────────
_SURVIVAL_PROMPT = """\
# Role & Task
你是一個執行「超級數字力（MJ老師）」財務邏輯的嚴格量化 AI。你的任務是審查企業的【存活能力 (Survival)】。這攸關公司是否會面臨黑字破產或資金斷鏈，判定標準極度嚴格。

# Constraint: Exception Handling
- 若遇財報欄位缺失，輸出 "N/A"，絕對禁止自行推算或腦補。
- 若遇分母為 0（如流動負債=0），視為無短期債務壓力，該指標直接判定為 "Pass"。

# Evaluation Logic (存活能力 3 大生死指標)

## 1. 氣長不長 (Cash Ratio)
- 計算：現金與約當現金 / 總資產 * 100%
- 判斷標準：
  - Pass (綠燈)：>= 25%
  - Acceptable (黃燈)：10% ~ 24%
  - Fail (紅燈)：< 10%

## 2. 收現速度 (Days Sales Outstanding, DSO)
- 判斷公司是不是天天收現金的好生意。
- 判斷標準：
  - Pass (綠燈)：< 15天
  - Acceptable (黃燈)：15 ~ 90天
  - Fail (紅燈)：> 90天

## 3. 現金流自給自足 (100 / 100 / 10 法則)
必須同時檢驗以下三個條件：
- [條件 A] 現金流量比率：(營業活動淨現金流 / 流動負債) * 100% -> 必須 > 100%
- [條件 B] 現金流量允當比率：(近5年營業現金流 / 近5年[資本支出+存貨增加+現金股利]) * 100% -> 必須 > 100%（資料不足5年時輸出 "N/A"）
- [條件 C] 現金再投資比率：([營業現金流 - 現金股利] / 固定與長期資產等) * 100% -> 必須 > 10%
- 判斷標準：
  - Pass (綠燈)：三項全數達標（N/A 項不計入失敗）
  - Fail (紅燈)：任一項未達標

# Input Data
<Financial_Data>
{financial_data_json}
</Financial_Data>

# Output Protocol (Strict JSON)
直接輸出以下 JSON（禁止 Markdown 包裝）：
{{
  "Survival_Module": {{
    "Cash_Ratio": {{
      "Value": "XX.X%",
      "Status": "Pass | Acceptable | Fail",
      "Insight": "一句話短評"
    }},
    "DSO_Speed": {{
      "Value": "XX 天",
      "Status": "Pass | Acceptable | Fail",
      "Insight": "一句話短評"
    }},
    "Rule_100_100_10": {{
      "Cash_Flow_Ratio": "XX.X% 或 N/A",
      "Cash_Flow_Adequacy": "XX.X% 或 N/A",
      "Cash_Reinvestment": "XX.X% 或 N/A",
      "Status": "Pass | Fail",
      "Insight": "一句話短評"
    }},
    "Final_Survival_Verdict": "總結存活能力防禦力等級（高/中/低），並標示是否通過生死關。"
  }}
}}"""

# ── Operating Module Prompt（經營能力：周轉效率 + 資金壓力）──
_OPERATING_PROMPT = """\
# Role: 超級數字力經營能力分析官

# Core Rules
1. 一年以 360 天計算。
2. 直接使用期末值，不使用平均值。

# Analysis Process

## 模組 A：周轉效率檢驗
- [DSO] 應收帳款天數 = 360 / (營收 / 應收帳款)
- [DIO] 存貨在手天數 = 360 / (成本 / 存貨)
- [DPO] 應付帳款天數 = 360 / (成本 / 應付帳款)

## 模組 B：資金壓力檢驗 (做生意的週期)
1. 做生意的完整週期 = DIO + DSO
   - 判定：> 150 天為笨重生意；< 50 天為極速周轉。
2. 缺錢的天數 (CCC) = 完整週期 - DPO
   - 判定：若 < 0 天，標註具備「OPM 護城河」(拿別人的錢做生意)。

## 模組 C：總資產翻桌率
- 計算：營收 / 總資產
- 判定：
  - > 1.0 : 通過。
  - < 1.0 : 檢查是否滿足 (現金佔比 > 25% OR ROE 連續三年 > 20%)。若不滿足，判定為高風險燒錢行業。

# Constraint
- 若財報欄位缺失或分母為 0，該指標輸出 "N/A"，禁止腦補。

# Input Data
<Financial_Data>
{financial_data_json}
</Financial_Data>

# Output Protocol (Strict JSON)
直接輸出以下 JSON（禁止 Markdown 包裝）：
{{
  "Operating_Module": {{
    "DSO": "XX.X 天",
    "DIO": "XX.X 天 或 N/A",
    "DPO": "XX.X 天",
    "Complete_Cycle": "XX.X 天",
    "Cash_Gap_Days": "XX.X 天",
    "OPM_Strategy": "Yes | No",
    "Asset_Turnover": "X.XX 趟",
    "Verdict": "綜合評價做生意的本事（50字以內）"
  }}
}}"""

# ── Profitability Module Prompt（獲利能力：5大指標 + 槓桿防呆）──
_PROFITABILITY_PROMPT = """\
# Role: 超級數字力獲利分析官

# Core Rules
1. 嚴格區分「本業獲利」與「業外獲利」，本業虧損即視為劣質企業。
2. 看到高 ROE 必須聯動檢查「財務結構（負債比）」，排除槓桿作弊。

# Evaluation Logic (獲利能力 5 大指標)

## 1. 營業毛利率 (Gross Margin)
- 計算：毛利(千) / 營業收入(千)
- 判定：> 20% (Good)；≤ 20% (Hard Work)。

## 2. 營業利益率 (Operating Margin)
- 計算：營業利益(千) / 營業收入(千)
- 判定：> 10% (Excellent)；0%~10% (Moderate)；< 0% (FAIL — 本業虧損)。
- Core_Business_Profitable = "Yes" if 營業利益 > 0 else "No"

## 3. 經營安全邊際 (Margin of Safety)
- 計算：營業利益(千) / 毛利(千)
- 判定：> 60% (Strong)；≤ 60% (Weak)。

## 4. 稅後淨利率 (Net Margin)
- 計算：稅後淨利(千) / 營業收入(千)
- 判定：> 10% (Pass)；2%~10% (Thin Profit)；< 2% (Fail)。

## 5. 股東權益報酬率 (ROE)
- 計算：稅後淨利(千) / 股東權益(千)
- 判定：> 20% (Top Tier)；10%~20% (Good)；< 10% (Weak)。
- 防呆：若 ROE > 15%，強制檢查負債比率(%)。
  - 負債比 > 60% → Leverage_Warning = "High Debt Ratio (>60%)"
  - 其他 → Leverage_Warning = "None"

# Input Data
<Financial_Data>
{financial_data_json}
</Financial_Data>

# Output Protocol
直接輸出以下 JSON（禁止 Markdown 包裝）：
{{
  "Profitability_Module": {{
    "Gross_Margin": {{"Value": "XX.X%", "Status": "Good | Hard Work"}},
    "Operating_Margin": {{"Value": "XX.X%", "Core_Business_Profitable": "Yes | No"}},
    "Margin_Of_Safety": {{"Value": "XX.X%", "Status": "Strong | Weak"}},
    "Net_Margin": {{"Value": "XX.X%", "Status": "Pass | Thin Profit | Fail"}},
    "ROE": {{"Value": "XX.X%", "Leverage_Warning": "None | High Debt Ratio (>60%)"}},
    "Final_Insight": "綜合短評（50字以內，點出最關鍵的獲利品質特徵）"
  }}
}}"""

# ── MJ 財報體檢 Prompt ──────────────────────────────────────
_PROMPT_TEMPLATE = """\
# Role
你是「MJ 林明樟財報分析師 AI」。依據「4力1棒子＋現金流矩陣」邏輯，\
對下方台灣上市公司財務數據進行標準化健診，輸出精準的 JSON 報告。

# Absolute Constraint
1. 所有判斷【必須 100% 基於】<Financial_Data> 的數值，禁止使用預訓練記憶或猜測。
2. 禁止在輸出中推薦任何買賣操作或 ETF 標的。
3. 輸出僅限 JSON，禁止任何 Markdown 包裝、前言或結語。

# Financial Health Framework (MJ 體系)

## 第一關：生死關
- 現金佔總資產比率：>25% 安全（🟢）| 10~25% 注意（🟡）| <10% 危險（🔴）
- 營業活動現金流（OCF）：>0 真實獲利（🟢）| ≤0 黑字破產警戒（🔴）
- 負債比率（總負債/總資產）：<40% 優秀（🟢）| 40~60% 正常（🟡）| >60% 危險（🔴）
  注意：金融/租賃業負債高屬正常，請考量行業特性

## 第二關：五力分析（各 0~100 分）
- 存活能力：現金水位 + OCF 穩定性
- 經營能力：應付帳款天數 vs 應收帳款天數（話語權）+ 資產周轉
- 獲利能力：毛利率趨勢 + OCF 佔淨利比（盈餘品質）
- 財務結構：負債結構健康度 + 流動比率
- 償債能力：自由現金流（FCF = OCF - CAPEX）

## 第三關：企業 DNA（現金流矩陣）
依 OCF / ICF / 籌資CF 正負號判斷企業類型：
- (+, -, -) = A+ 穩健印鈔機（本業強，積極擴張）
- (+, -, +) = A 成熟收割機（本業強，不擴張，向外融資/分紅）
- (+, +, ?) = B 資產出清型（賣廠換現金，需警戒）
- (-, -, +) = C+ 成長燒錢型（新創/擴張初期，可接受）
- (-, -, -) = D 資金黑洞（危險）

## OPM 護城河
應付帳款天數 > 應收帳款天數 → 具備議價優勢（向上下游收錢慢、付錢慢）

# Input Data
<Financial_Data>
{financial_data_json}
</Financial_Data>

# Output Protocol
直接輸出以下 JSON（禁止 Markdown 包裝）：
{{
  "cash_ratio_status": "🟢 或 🟡 或 🔴",
  "cash_ratio_value": "XX.X%",
  "ocf_status": "🟢 或 🔴",
  "ocf_value": "XXX億",
  "debt_ratio_status": "🟢 或 🟡 或 🔴",
  "debt_ratio_value": "XX.X%",
  "radar_scores": {{
    "存活能力": 0到100的整數,
    "經營能力": 0到100的整數,
    "獲利能力": 0到100的整數,
    "財務結構": 0到100的整數,
    "償債能力": 0到100的整數
  }},
  "business_model_dna": "A+ 穩健印鈔機 (+, -, -)",
  "opm_data": {{
    "payable_days": 數字,
    "receivable_days": 數字,
    "advantage": true或false
  }},
  "ai_insight": "結合DuPont+盈餘品質的150字白話診斷，說明現況與潛在風險（語氣冷靜客觀）",
  "red_flags": "若有①應收帳款增速>營收增速②存貨大增③OCF持續負④負債急升，請說明。若無異常填 None"
}}"""


# ── Gemini 呼叫（多模型 fallback）──────────────────────────
def _gemini_call(prompt: str, api_key: str) -> str:
    _models = [
        "gemini-2.5-flash-lite", "gemini-2.5-flash",
        "gemini-2.0-flash", "gemini-2.0-flash-lite",
    ]
    for _m in _models:
        try:
            _r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{_m}:generateContent",
                params={"key": api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200},
                },
                timeout=120,
            )
            if _r.status_code == 200:
                _cands = _r.json().get("candidates", [])
                if _cands:
                    _parts = _cands[0].get("content", {}).get("parts", [])
                    if _parts and _parts[0].get("text"):
                        return _parts[0]["text"]
                    if _cands[0].get("finishReason") == "SAFETY":
                        continue
            elif _r.status_code in (404, 400):
                continue
            elif _r.status_code == 429:
                time.sleep(5)
                continue
        except Exception as _e:
            print(f"[FinHealth/{_m}] {type(_e).__name__}: {_e}")
            time.sleep(1)
    return "⚠️ AI 服務暫時無法使用"


def _extract_json(raw: str) -> dict:
    text = re.sub(r"```json|```", "", raw).strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return json.loads(m.group(0))
    raise ValueError(f"無法解析 JSON：{raw[:120]}")


# ── Fail-safe 預設值 ────────────────────────────────────────
_FAIL_SAFE: dict = {
    "cash_ratio_status": "🔴",
    "cash_ratio_value": "N/A",
    "ocf_status": "🔴",
    "ocf_value": "N/A",
    "debt_ratio_status": "🔴",
    "debt_ratio_value": "N/A",
    "radar_scores": {
        "存活能力": 0, "經營能力": 0, "獲利能力": 0,
        "財務結構": 0, "償債能力": 0,
    },
    "business_model_dna": "無法判斷（資料不足）",
    "opm_data": {"payable_days": 0, "receivable_days": 0, "advantage": False},
    "ai_insight": "財報資料載入失敗，無法進行體檢分析。請確認 FINMIND_TOKEN 已設定。",
    "red_flags": "None",
    "error": True,
}


# ── Survival Module 入口 ────────────────────────────────────
def analyze_survival_module(api_key: str, stock_id: str, fin_data: dict) -> dict:
    """
    執行存活能力 3 大生死指標分析（氣長/DSO/100-100-10）。
    失敗時回傳 {"error": True, "Survival_Module": {...fail-safe...}}。
    """
    _fs_survival = {
        "Survival_Module": {
            "Cash_Ratio":       {"Value": "N/A", "Status": "Fail", "Insight": "資料載入失敗"},
            "DSO_Speed":        {"Value": "N/A", "Status": "Fail", "Insight": "資料載入失敗"},
            "Rule_100_100_10":  {
                "Cash_Flow_Ratio": "N/A", "Cash_Flow_Adequacy": "N/A",
                "Cash_Reinvestment": "N/A", "Status": "Fail", "Insight": "資料載入失敗",
            },
            "Final_Survival_Verdict": "無法判斷（資料不足）",
        },
        "error": True,
    }
    if not api_key or not fin_data or fin_data.get("error"):
        return _fs_survival
    try:
        fin_str = json.dumps(fin_data, ensure_ascii=False, indent=2)
        prompt = _SURVIVAL_PROMPT.format(financial_data_json=fin_str)
        raw = _gemini_call(prompt, api_key)
        if raw.startswith("⚠️"):
            raise ValueError(raw)
        result = _extract_json(raw)
        print(f"[Survival] ✅ {stock_id} verdict={result.get('Survival_Module',{}).get('Final_Survival_Verdict','?')[:20]}")
        return result
    except Exception as _e:
        print(f"[Survival] ❌ {stock_id}: {_e}")
        fs = _fs_survival.copy()
        fs["Survival_Module"]["Final_Survival_Verdict"] = f"分析失敗：{_e}"
        return fs


def analyze_operating_module(api_key: str, stock_id: str, fin_data: dict) -> dict:
    """
    執行經營能力模組：DSO/DIO/DPO 周轉效率 + CCC 資金壓力 + 總資產翻桌率。
    """
    _fs_op = {
        "Operating_Module": {
            "DSO": "N/A", "DIO": "N/A", "DPO": "N/A",
            "Complete_Cycle": "N/A", "Cash_Gap_Days": "N/A",
            "OPM_Strategy": "No", "Asset_Turnover": "N/A",
            "Verdict": "資料載入失敗，無法分析。",
        },
        "error": True,
    }
    if not api_key or not fin_data or fin_data.get("error"):
        return _fs_op
    try:
        fin_str = json.dumps(fin_data, ensure_ascii=False, indent=2)
        prompt = _OPERATING_PROMPT.format(financial_data_json=fin_str)
        raw = _gemini_call(prompt, api_key)
        if raw.startswith("⚠️"):
            raise ValueError(raw)
        result = _extract_json(raw)
        opm = result.get("Operating_Module", {})
        print(f"[Operating] ✅ {stock_id} CCC={opm.get('Cash_Gap_Days','?')} turnover={opm.get('Asset_Turnover','?')}")
        return result
    except Exception as _e:
        print(f"[Operating] ❌ {stock_id}: {_e}")
        fs = _fs_op.copy()
        fs["Operating_Module"]["Verdict"] = f"分析失敗：{_e}"
        return fs


def analyze_profitability_module(api_key: str, stock_id: str, fin_data: dict) -> dict:
    """Part 3 獲利能力模組：5大指標 + 槓桿防呆。"""
    _fs_pr = {"Profitability_Module": {
        "Gross_Margin":      {"Value": "N/A", "Status": "N/A"},
        "Operating_Margin":  {"Value": "N/A", "Core_Business_Profitable": "N/A"},
        "Margin_Of_Safety":  {"Value": "N/A", "Status": "N/A"},
        "Net_Margin":        {"Value": "N/A", "Status": "N/A"},
        "ROE":               {"Value": "N/A", "Leverage_Warning": "N/A"},
        "Final_Insight":     "分析資料不足",
    }}
    try:
        fin_str = json.dumps(fin_data, ensure_ascii=False, indent=2)
        prompt = _PROFITABILITY_PROMPT.format(financial_data_json=fin_str)
        raw = _gemini_call(prompt, api_key)
        if raw.startswith("⚠️"):
            raise ValueError(raw)
        result = _extract_json(raw)
        print(f"[Profitability] ✅ {stock_id}")
        return result
    except Exception as _e:
        print(f"[Profitability] ❌ {stock_id}: {_e}")
        _fs_pr["Profitability_Module"]["Final_Insight"] = f"分析失敗：{_e}"
        return _fs_pr


# ── Financial Structure Module Prompt（財務結構：那根棒子 + 以長支長）──
_FINANCIAL_STRUCTURE_PROMPT = """\
# Role: 超級數字力財務結構分析官

# Core Rules
1. 此關卡負責檢驗「財務結構」，也就是資產負債表上的「那根棒子」與「資金配置」。
2. 未通過代表公司有極高的突發性倒閉風險。

# Edge Case Handling
- 【金融業例外】：若股票代號屬金融保險業（銀行、金控、壽險），
  「負債佔資產比率」直接標記為 "N/A (特許行業)"，Status = "N/A"。
- 【除以零防呆】：若「固定資產(千)」為 0（如純軟體業），
  「以長支長比率」直接標記為 "Pass (輕資產)"，Value = "N/A (輕資產)"。

# Evaluation Logic

## 1. 負債佔資產比率 (Debt to Asset Ratio)
- 計算：(總負債(千) / 總資產(千)) * 100%
- 判定：< 60% → Pass；60%~70% → Warning；> 70% → Fail。

## 2. 以長支長比率 (Long-Term Funds to Fixed Assets)
- 計算：(股東權益(千) + 非流動負債(千)) / 固定資產(千) * 100%
- 判定：> 100% → Pass；< 100% → Fail（短債長投，資金鏈隨時斷裂）。

# Input Data
<Financial_Data>
{financial_data_json}
</Financial_Data>

# Output Protocol
直接輸出以下 JSON（禁止 Markdown 包裝）：
{{
  "Financial_Structure_Module": {{
    "Debt_Ratio": {{"Value": "XX.X%", "Status": "Pass | Warning | Fail | N/A"}},
    "Long_Term_Funding_Ratio": {{"Value": "XX.X% | N/A (輕資產)", "Status": "Pass | Fail"}},
    "Final_Insight": "綜合短評（50字以內，點出財務結構最關鍵的風險或優勢）"
  }}
}}"""


def analyze_financial_structure_module(api_key: str, stock_id: str, fin_data: dict) -> dict:
    """Part 4 財務結構模組：負債比 + 以長支長比率。"""
    _fs_st = {"Financial_Structure_Module": {
        "Debt_Ratio":              {"Value": "N/A", "Status": "N/A"},
        "Long_Term_Funding_Ratio": {"Value": "N/A", "Status": "N/A"},
        "Final_Insight":           "分析資料不足",
    }}
    try:
        fin_str = json.dumps(fin_data, ensure_ascii=False, indent=2)
        prompt = _FINANCIAL_STRUCTURE_PROMPT.format(financial_data_json=fin_str)
        raw = _gemini_call(prompt, api_key)
        if raw.startswith("⚠️"):
            raise ValueError(raw)
        result = _extract_json(raw)
        print(f"[FinStructure] ✅ {stock_id}")
        return result
    except Exception as _e:
        print(f"[FinStructure] ❌ {stock_id}: {_e}")
        _fs_st["Financial_Structure_Module"]["Final_Insight"] = f"分析失敗：{_e}"
        return _fs_st


# ── Solvency Module Prompt（償債能力：流動/速動比率 + 收現豁免）──
_SOLVENCY_PROMPT = """\
# Role: 超級數字力短期償債分析官

# Core Rules
1. 採用 MJ 老師極度嚴格標準 (300/150)。
2. 備有「收現行業」豁免條款，確保不誤殺優質流通業。

# Edge Case Handling
- 【無債一身輕】：若「流動負債(千)」= 0，所有指標直接標記 Status = "Pass (無短期債務)"，
  Cross_Validation_Applied = "No"，Final_Solvency_Verdict = "Pass"。

# Evaluation Logic

## 1. 流動比率 (Current Ratio)
- 計算：流動資產(千) / 流動負債(千) * 100%
- 嚴格標準：> 300% → Pass；≤ 300% → Fail_Initial。

## 2. 速動比率 (Quick Ratio)
- 計算：(流動資產(千) - 存貨(千)) / 流動負債(千) * 100%
  （預付費用不在資料中，以存貨作為主要扣減項）
- 嚴格標準：> 150% → Pass；≤ 150% → Fail_Initial。

## 3. 交叉驗證保命符 (Cross-Validation)
若任一項為 Fail_Initial，Cross_Validation_Applied = "Yes"，
依序檢查三個條件（滿足任一即豁免）：
- [條件 A] 現金佔總資產(%) > 25%
- [條件 B] 應收帳款天數 < 15 天（天天收現金行業）
- [條件 C] DSO + DIO - DPO（做生意完整週期）< 50 天
  DIO = 存貨(千) / 營業成本(千) * 360（若營業成本=0則用營業收入(千)代替）
  DPO = 應付帳款天數
  若上述任一條件成立 → Final_Solvency_Verdict = "Exception_Pass (條件X：說明)"
  若均不符合 → Final_Solvency_Verdict = "Fail"

# Input Data
<Financial_Data>
{financial_data_json}
</Financial_Data>

# Output Protocol
直接輸出以下 JSON（禁止 Markdown 包裝）：
{{
  "Solvency_Module": {{
    "Current_Ratio": {{"Value": "XX.X%", "Status": "Pass | Fail_Initial"}},
    "Quick_Ratio": {{"Value": "XX.X%", "Status": "Pass | Fail_Initial"}},
    "Cross_Validation_Applied": "Yes | No",
    "Final_Solvency_Verdict": "Pass | Exception_Pass (說明) | Fail",
    "Final_Insight": "綜合短評（50字以內，說明短期償債能力關鍵結論）"
  }}
}}"""


def analyze_solvency_module(api_key: str, stock_id: str, fin_data: dict) -> dict:
    """Part 5 償債能力模組：流動/速動比率 + 收現行業豁免。"""
    _fs_sv = {"Solvency_Module": {
        "Current_Ratio":            {"Value": "N/A", "Status": "N/A"},
        "Quick_Ratio":              {"Value": "N/A", "Status": "N/A"},
        "Cross_Validation_Applied": "N/A",
        "Final_Solvency_Verdict":   "N/A",
        "Final_Insight":            "分析資料不足",
    }}
    try:
        fin_str = json.dumps(fin_data, ensure_ascii=False, indent=2)
        prompt = _SOLVENCY_PROMPT.format(financial_data_json=fin_str)
        raw = _gemini_call(prompt, api_key)
        if raw.startswith("⚠️"):
            raise ValueError(raw)
        result = _extract_json(raw)
        print(f"[Solvency] ✅ {stock_id}")
        return result
    except Exception as _e:
        print(f"[Solvency] ❌ {stock_id}: {_e}")
        _fs_sv["Solvency_Module"]["Final_Insight"] = f"分析失敗：{_e}"
        return _fs_sv


# ── Advanced Diagnostic Module Prompt（綜合診斷：跨表勾稽 + 地雷偵測）──
_ADVANCED_DIAGNOSTIC_PROMPT = """\
# Role: 超級數字力綜合診斷與避雷官

# Core Rules
1. 看透高獲利背後的真相，執行跨表勾稽與地雷偵測。
2. 盈餘品質防呆：若「稅後淨利(千)」<= 0，直接輸出 "N/A (淨利為負)"。

# Evaluation Logic

## 1. 盈餘品質 (Earnings Quality)
- 計算：OCF(千) / 稅後淨利(千) * 100%
- 判定：> 100% → Pass（真金白銀）；< 100% → Fail（紙上富貴）。

## 2. 杜邦分析 (DuPont Health)
- ROE = 稅後淨利(千) / 股東權益(千) * 100%
- 若 ROE > 15% 且 負債比率(%) > 65% → "槓桿膨脹警報"
- 若 ROE > 15% 且 負債比率(%) ≤ 65% → "健康成長"
- 若 ROE ≤ 15% → "ROE 偏低，成長動能不足"

## 3. 雙高危機 (Double High Warning)
- 應收帳款增長率 = 應收帳款季增率(%)（已在資料中）
- 存貨增長率 = (存貨(千) - 存貨前期(千)) / |存貨前期(千)| * 100%
- 條件：應收帳款增長率 > 營收季增率(%) 且 存貨增長率 > 營收季增率(%)
  同時滿足 → "Triggered (危險)"；否則 → "Clear (安全)"
  若增長率數值為 null/0 → 標記 "N/A (資料不足)"

## 4. 企業 DNA (Cash Flow Matrix)
- 依 [OCF符號, ICF符號, 籌資CF符號] 判斷：
  (+, -, -) → "A+ 穩健印鈔機"
  (+, -, +) → "成長擴張型"
  (+, +, -) → "變賣祖產型（⚠️ 請確認原因）"
  (-, -, +) → "燒錢新創型（需觀察現金消耗速度）"
  (-, +, -) → "瀕死型（🔴 極度危險）"
  其他 → "特殊組合（需個案分析）"

# Input Data
<Financial_Data>
{financial_data_json}
</Financial_Data>

# Output Protocol
直接輸出以下 JSON（禁止 Markdown 包裝）：
{{
  "Advanced_Diagnostic_Module": {{
    "Earnings_Quality": {{"Value": "XX.X% | N/A", "Status": "Pass | Fail | N/A"}},
    "DuPont_Health": "健康成長 | 槓桿膨脹警報 | ROE 偏低，成長動能不足",
    "Double_High_Warning": "Triggered (危險) | Clear (安全) | N/A (資料不足)",
    "Business_DNA": "標籤名稱 (+/-/- 組合)",
    "Final_Verdict": "綜合短評（60字以內，點出最關鍵的地雷或亮點）"
  }}
}}"""


def analyze_advanced_diagnostic_module(api_key: str, stock_id: str, fin_data: dict) -> dict:
    """Part 6 綜合診斷模組：盈餘品質+杜邦+雙高危機+企業DNA。"""
    _fs_ad = {"Advanced_Diagnostic_Module": {
        "Earnings_Quality":    {"Value": "N/A", "Status": "N/A"},
        "DuPont_Health":       "N/A",
        "Double_High_Warning": "N/A",
        "Business_DNA":        "N/A",
        "Final_Verdict":       "分析資料不足",
    }}
    try:
        fin_str = json.dumps(fin_data, ensure_ascii=False, indent=2)
        prompt = _ADVANCED_DIAGNOSTIC_PROMPT.format(financial_data_json=fin_str)
        raw = _gemini_call(prompt, api_key)
        if raw.startswith("⚠️"):
            raise ValueError(raw)
        result = _extract_json(raw)
        print(f"[AdvDiag] ✅ {stock_id}")
        return result
    except Exception as _e:
        print(f"[AdvDiag] ❌ {stock_id}: {_e}")
        _fs_ad["Advanced_Diagnostic_Module"]["Final_Verdict"] = f"分析失敗：{_e}"
        return _fs_ad


# ── 公開入口 ────────────────────────────────────────────────
def analyze_financial_health(api_key: str, stock_id: str, fin_data: dict) -> dict:
    """
    輸入財報原始指標 dict（由 fetch_financial_statements 產出），
    呼叫 Gemini AI，回傳標準化 8 欄 JSON。
    失敗時回傳 _FAIL_SAFE，確保前端不崩潰。
    """
    if not api_key:
        fs = _FAIL_SAFE.copy()
        fs["ai_insight"] = "缺少 GEMINI_API_KEY，無法執行 AI 財報體檢。"
        return fs
    if not fin_data or fin_data.get("error"):
        fs = _FAIL_SAFE.copy()
        fs["ai_insight"] = fin_data.get("error", "財報資料為空") if fin_data else "財報資料為空"
        return fs

    try:
        fin_str = json.dumps(fin_data, ensure_ascii=False, indent=2)
        prompt = _PROMPT_TEMPLATE.format(financial_data_json=fin_str)
        raw = _gemini_call(prompt, api_key)
        if raw.startswith("⚠️"):
            raise ValueError(raw)

        result = _extract_json(raw)

        # 強制保護雷達圖值域 [0, 100]
        if "radar_scores" in result and isinstance(result["radar_scores"], dict):
            result["radar_scores"] = {
                k: max(0, min(100, int(v)))
                for k, v in result["radar_scores"].items()
            }
        # 確保 opm_data 存在且型別正確
        if "opm_data" not in result or not isinstance(result["opm_data"], dict):
            result["opm_data"] = {"payable_days": 0, "receivable_days": 0, "advantage": False}
        else:
            result["opm_data"]["advantage"] = bool(result["opm_data"].get("advantage", False))

        # 同步執行 Survival Module（存活能力精細版）
        _surv = analyze_survival_module(api_key, stock_id, fin_data)
        result["survival_module"] = _surv.get("Survival_Module", {})

        # 同步執行 Operating Module（經營能力：周轉效率+資金壓力）
        _oper = analyze_operating_module(api_key, stock_id, fin_data)
        result["operating_module"] = _oper.get("Operating_Module", {})

        # 同步執行 Profitability Module（獲利能力：5大指標+槓桿防呆）
        _prof = analyze_profitability_module(api_key, stock_id, fin_data)
        result["profitability_module"] = _prof.get("Profitability_Module", {})

        # 同步執行 Financial Structure Module（財務結構：負債比+以長支長）
        _fstr = analyze_financial_structure_module(api_key, stock_id, fin_data)
        result["financial_structure_module"] = _fstr.get("Financial_Structure_Module", {})

        # 同步執行 Solvency Module（償債能力：流動/速動比率+收現豁免）
        _solv = analyze_solvency_module(api_key, stock_id, fin_data)
        result["solvency_module"] = _solv.get("Solvency_Module", {})

        # 同步執行 Advanced Diagnostic Module（綜合診斷：盈餘品質+杜邦+雙高+DNA）
        _adv = analyze_advanced_diagnostic_module(api_key, stock_id, fin_data)
        result["advanced_diagnostic_module"] = _adv.get("Advanced_Diagnostic_Module", {})

        print(f"[FinHealth] ✅ {stock_id} DNA={result.get('business_model_dna','?')}")
        return result

    except Exception as _e:
        print(f"[FinHealth] ❌ {stock_id}: {_e}")
        fs = _FAIL_SAFE.copy()
        fs["ai_insight"] = f"體檢分析失敗：{_e}"
        return fs
