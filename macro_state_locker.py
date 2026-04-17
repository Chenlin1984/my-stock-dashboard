"""
macro_state_locker.py — L3 策略層：AI 解讀引擎 + 實體狀態鎖 v2.0
------------------------------------------------------------------
架構分工（理科 / 文科）：
  calculate_system_state(macro_numbers) → dict   [理科：Python 算曝險]
  MacroStateLocker.execute_and_lock(system_state, news_list)
    → 呼叫 Gemini AI（只輸出 analysis_summary）
    → 合併 system_state + AI 解讀 → 原子寫入 macro_state.json

前端 (app.py) 只需呼叫 load_macro_state() 唯讀讀取。
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Callable


# ── 預設 Fail-safe 狀態 ─────────────────────────────────────
_DEFAULT_STATE: dict = {
    "market_regime": "系統異常",
    "systemic_risk_level": "危險",
    "exposure_limit_pct": 0,
    "Macro_Phase": "系統異常",
    "analysis_summary": (
        "系統防護機制啟動：無法取得有效的總經與新聞數據，"
        "強制將風險部位降至零。請執行 AI 裁決後更新。"
    ),
    "timestamp": "",
}

# ── AI 核心 Prompt 模板（輕量化 v2.0）───────────────────────
_PROMPT_TEMPLATE = """\
# Role
你是「台股戰情室首席總經分析師」。你的任務是將系統底層已經計算出的「總經燈號與曝險上限」，結合「近期新聞」，轉化為一段專業、精煉的給投資人的解讀報告。

# Absolute Constraint (絕對約束)
1. 資訊隔離：【絕對禁止】腦補或使用預訓練知識。你的解讀【必須 100% 基於】下方 <System_Calculated_State> 與 <News> 的內容。
2. 絕對服從：你必須絕對服從系統給出的「最高持股上限 (exposure_limit_pct)」。若系統給出 30%，代表底層風控已啟動，你的解讀必須偏向防禦與風險提示；若為 80%，則可偏向樂觀。禁止在文字中給出違背系統上限的買賣建議。
3. 標的限制：禁止在解讀中建議配置 ETF 或任何非股票型基金的資產。

# Input Data
<System_Calculated_State>
{system_state_json}
</System_Calculated_State>

<News>
{news_string}
</News>

# Output Protocol
請直接輸出符合以下格式的 JSON，禁止包含任何 Markdown 標記（如 ```json）或解釋性前言/結語：
{{
  "analysis_summary": "結合系統燈號與新聞的專業解讀，說明目前的市場結構與風險，以及為何對應此曝險水位。(限 100 字內，語氣需冷靜客觀)"
}}"""


def _default_gemini_call(prompt: str) -> str:
    """內建 Gemini API 呼叫，自動 fallback 多模型。"""
    _key = os.environ.get("GEMINI_API_KEY", "")
    if not _key:
        return "⚠️ 缺少 GEMINI_API_KEY"
    _models = [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ]
    import requests  # 延遲 import，測試環境可 mock

    for _model in _models:
        try:
            _r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{_model}:generateContent",
                params={"key": _key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 600},
                },
                timeout=120,
            )
            if _r.status_code == 200:
                _d = _r.json()
                _cands = _d.get("candidates", [])
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
            print(f"[MacroStateLocker/{_model}] {type(_e).__name__}: {_e}")
            time.sleep(1)
    return "⚠️ AI 服務暫時無法使用（已嘗試所有模型）"


class MacroStateLocker:
    """
    AI 總裁決引擎。

    Parameters
    ----------
    llm_client : callable, optional
        接受 (prompt: str) → str 的可呼叫物件。
        預設使用內建 _default_gemini_call（直接呼叫 Gemini REST API）。
        測試時可傳入 mock，避免 HTTP 呼叫。
    state_file_path : str
        實體狀態鎖檔案路徑，預設 macro_state.json。
    """

    def __init__(
        self,
        llm_client: Callable[[str], str] | None = None,
        state_file_path: str = "macro_state.json",
    ) -> None:
        self._llm = llm_client or _default_gemini_call
        self.state_file_path = state_file_path
        self.default_state = _DEFAULT_STATE.copy()

    # ── 公開入口 ────────────────────────────────────────────
    def execute_and_lock(
        self,
        system_state: dict,
        news_list: list[str],
    ) -> bool:
        """
        接收 Python 預算好的 system_state（理科），呼叫 AI 生成 analysis_summary（文科），
        合併後原子寫入 macro_state.json。

        Returns True on success, False on failure (fail-safe written).
        """
        news_str = (
            "\n".join(f"- {n}" for n in news_list)
            if news_list
            else "無重大異常新聞"
        )
        state_json_str = json.dumps(system_state, ensure_ascii=False, indent=2)
        prompt = self._build_prompt(state_json_str, news_str)

        try:
            raw_response = self._llm(prompt)
            if raw_response.startswith("⚠️"):
                raise ValueError(raw_response)

            ai_out = self._extract_json(raw_response)
            final = {
                **system_state,
                "exposure_limit_pct": max(
                    0, min(100, int(system_state.get("exposure_limit_pct", 0)))
                ),
                "analysis_summary": str(ai_out.get("analysis_summary", "")),
                "timestamp": _now_str(),
            }
            self._write_state_lock(final)
            print(f"[MacroStateLocker] ✅ {final.get('market_regime')} / "
                  f"曝險上限 {final['exposure_limit_pct']}%")
            return True

        except Exception as _e:
            print(f"[MacroStateLocker] ❌ {_e}，啟動 Fail-safe")
            _fs = self.default_state.copy()
            _fs["timestamp"] = _now_str()
            self._write_state_lock(_fs)
            return False

    # ── 內部方法 ────────────────────────────────────────────
    def _build_prompt(self, state_json_str: str, news_str: str) -> str:
        return _PROMPT_TEMPLATE.format(
            system_state_json=state_json_str,
            news_string=news_str,
        )

    def _extract_json(self, raw_text: str) -> dict:
        """清洗 LLM 輸出，強制取出 JSON。"""
        text = re.sub(r"```json|```", "", raw_text).strip()
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"LLM 回傳無法解析為 JSON：{raw_text[:120]}")

    def _write_state_lock(self, state_dict: dict) -> None:
        """原子寫入，防止 Streamlit 讀取到寫入一半的殘缺 JSON。"""
        temp_path = self.state_file_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(state_dict, f, ensure_ascii=False, indent=4)
        os.replace(temp_path, self.state_file_path)


# ── 前端唯讀工具函式 ────────────────────────────────────────
def load_macro_state(state_file_path: str = "macro_state.json") -> dict:
    """
    Streamlit 前端唯讀讀取實體狀態鎖。
    讀取失敗時回傳 default_state，確保 UI 不崩潰。
    """
    try:
        with open(state_file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["exposure_limit_pct"] = int(data.get("exposure_limit_pct", 0))
        return data
    except Exception:
        return _DEFAULT_STATE.copy()


# ── 理科引擎：Python 規則計算總經狀態 ─────────────────────
def calculate_system_state(macro_numbers: dict) -> dict:
    """
    Rule-based quantitative engine (理科 brain).
    輸入原始指標 dict，輸出 market_regime / systemic_risk_level /
    exposure_limit_pct / Macro_Phase，供 AI 解讀引擎使用。
    """
    def _f(key, default):
        v = macro_numbers.get(key)
        try:
            return float(v) if v is not None else default
        except (ValueError, TypeError):
            return default

    vix     = _f("VIX_Index", 20.0)
    pmi     = _f("ISM_PMI_or_OECD_CLI", 50.0)
    m1b_yoy = _f("M1B_YoY_pct", 0.0)
    m2_yoy  = _f("M2_YoY_pct", 0.0)
    bias240 = _f("BIAS240_pct", 0.0)
    pcr     = _f("PCR", 1.0)

    score = 60  # 中性基準

    # VIX 恐慌指數
    if vix >= 35:    score -= 30
    elif vix >= 28:  score -= 20
    elif vix >= 22:  score -= 10
    elif vix <= 14:  score += 10

    # PMI 經濟動能
    if pmi < 46:     score -= 20
    elif pmi < 50:   score -= 10
    elif pmi > 55:   score += 10
    elif pmi > 52:   score += 5

    # M1B-M2 資金流動
    spread = m1b_yoy - m2_yoy
    if spread > 3:    score += 15
    elif spread > 0:  score += 5
    elif spread < -3: score -= 10

    # BIAS240 長期均線偏離
    if bias240 > 15:    score -= 15
    elif bias240 < -10: score += 10

    # PCR 期權恐慌比
    if pcr > 1.5:   score -= 10
    elif pcr < 0.7: score += 5

    exposure = max(0, min(100, round(score / 10) * 10))

    if exposure >= 70:   risk_level, regime = "安全", "多頭"
    elif exposure >= 40: risk_level, regime = "警告", "震盪"
    else:                risk_level, regime = "危險", "空頭"

    labels = []
    if pmi < 50:      labels.append(f"PMI收縮({pmi:.1f})")
    if vix > 25:      labels.append(f"VIX高波動({vix:.1f})")
    if spread < 0:    labels.append("資金緊縮")
    if bias240 > 15:  labels.append("均線過熱")
    macro_phase = "、".join(labels) if labels else "環境正常"

    return {
        "market_regime": regime,
        "systemic_risk_level": risk_level,
        "exposure_limit_pct": exposure,
        "Macro_Phase": macro_phase,
    }


# ── 工具 ────────────────────────────────────────────────────
def _now_str() -> str:
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
