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

        print(f"[FinHealth] ✅ {stock_id} DNA={result.get('business_model_dna','?')}")
        return result

    except Exception as _e:
        print(f"[FinHealth] ❌ {stock_id}: {_e}")
        fs = _FAIL_SAFE.copy()
        fs["ai_insight"] = f"體檢分析失敗：{_e}"
        return fs
