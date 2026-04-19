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

# ── AI 核心 Prompt 模板（台股AI戰情室 v3.0）──────────────────
_PROMPT_TEMPLATE = """\
# 台股 AI 戰情室：總體經濟與大盤判讀提示語

## Role（角色定義）
你是「台股 AI 戰情室」首席總經分析師，擁有 20 年台股與全球宏觀研究經驗。
你的任務是整合量化指標、籌碼數據與財經新聞，輸出一份精確、可直接指導操作的大盤戰情判讀報告。

## Absolute Constraints（絕對約束）
1. 資訊隔離：【絕對禁止】腦補或使用預訓練知識中的具體數字。解讀必須 100% 基於下方 Data 標籤內的內容。
2. 絕對服從：你必須絕對服從系統計算出的「曝險上限 (exposure_limit_pct)」。曝險 ≤30% → 解讀必須偏向防禦；曝險 ≥70% → 可偏向樂觀。
3. 標的禁令：【絕對禁止】在報告中建議任何個股、ETF 或特定標的。
4. 百分比禁令：analysis_summary 中不得出現任何持股百分比數字（如「60%」「持股七成」）。

## Input Data
<System_State>
{system_state_json}
</System_State>

<Macro_Quantitative_Data>
{macro_data_str}
</Macro_Quantitative_Data>

<News_Headlines>
{news_string}
</News_Headlines>

## Output Protocol（輸出協議）
請直接輸出符合以下格式的 JSON（禁止包含任何 ```json 標記或說明文字）：
{{
  "traffic_light": "🟢 多頭市場|🟡 震盪整理|🔴 空頭防禦（三選一，須與 exposure_limit_pct 一致）",
  "market_level": "大盤位階與 BIAS240 評價（25 字以內）",
  "data_deep_dive": "資金國際連動、法人散戶博弈、潛在背離隱患的深度解析（80 字以內）",
  "risk_warning": "具體系統性風險警示，最多 3 點以頓號分隔（50 字以內，無重大風險則輸出「暫無重大風險」）",
  "strategy": "大盤戰略方向與操作建議（45 字以內，不可含持股百分比數字）",
  "analysis_summary": "精煉一句話總結，語氣冷靜客觀（25 字以內，不可含百分比數字）"
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
        macro_context: str = "",
    ) -> bool:
        """
        接收 Python 預算好的 system_state（理科），呼叫 AI 生成 4 段判讀報告（文科），
        合併後原子寫入 macro_state.json。

        Returns True on success, False on failure (fail-safe written).
        """
        news_str = (
            "\n".join(f"- {n}" for n in news_list)
            if news_list
            else "無重大異常新聞"
        )
        state_json_str = json.dumps(system_state, ensure_ascii=False, indent=2)
        prompt = self._build_prompt(state_json_str, news_str, macro_context)

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
                "traffic_light":   str(ai_out.get("traffic_light", "")),
                "market_level":    str(ai_out.get("market_level", "")),
                "data_deep_dive":  str(ai_out.get("data_deep_dive", "")),
                "risk_warning":    str(ai_out.get("risk_warning", "")),
                "strategy":        str(ai_out.get("strategy", "")),
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

    def lock_system_state_only(self, system_state: dict) -> None:
        """Write rule-based system_state to the state lock without calling AI."""
        final = {
            **system_state,
            "exposure_limit_pct": max(0, min(100, int(system_state.get("exposure_limit_pct", 0)))),
            "analysis_summary": f"曝險上限 {system_state.get('exposure_limit_pct', 0)}%（Python 規則引擎計算）",
            "timestamp": _now_str(),
        }
        self._write_state_lock(final)

    # ── 內部方法 ────────────────────────────────────────────
    def _build_prompt(self, state_json_str: str, news_str: str, macro_context: str = "") -> str:
        return _PROMPT_TEMPLATE.format(
            system_state_json=state_json_str,
            macro_data_str=macro_context or "（量化數據未提供）",
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
    包含三大硬否決紅線（Physical Lock），覆蓋分數計算結果。
    新增輸入：Sahm_Rule_Triggered / PMI_Prev_Month / Futures_Net_Short / Index_Below_MA5
    """
    def _b(key):
        v = macro_numbers.get(key)
        if isinstance(v, bool): return v
        return str(v).lower() in ('true', '1', 'yes') if v is not None else False

    def _f(key, default):
        v = macro_numbers.get(key)
        try:
            return float(v) if v is not None else default
        except (ValueError, TypeError):
            return default

    vix         = _f("VIX_Index", 20.0)
    pmi         = _f("ISM_PMI_or_OECD_CLI", 50.0)
    pmi_prev    = _f("PMI_Prev_Month", 50.0)
    m1b_yoy     = _f("M1B_YoY_pct", 0.0)
    m2_yoy      = _f("M2_YoY_pct", 0.0)
    bias240     = _f("BIAS240_pct", 0.0)
    pcr         = _f("PCR", 1.0)
    futures_net = _f("Futures_Net_Short", 0.0)  # 負值 = 淨空單
    sahm        = _b("Sahm_Rule_Triggered")
    below_ma5   = _b("Index_Below_MA5")

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

    # BIAS240 雙重共振才扣分：高乖離需同時伴隨 VIX 偏高或 PMI 收縮
    if bias240 > 15 and (vix >= 22 or pmi < 50):
        score -= 15
    elif bias240 < -10:
        score += 10

    # PCR 期權恐慌比
    if pcr > 1.5:   score -= 10
    elif pcr < 0.7: score += 5

    # ── 初始曝險（分數計算結果）─────────────────────────────
    exposure = max(0, min(100, round(score / 10) * 10))

    # ── 三大硬否決紅線 (Hard Veto Physical Lock) ────────────
    veto_labels: list[str] = []

    # 紅線一：薩姆規則（美國衰退警報）→ 強制上限 20%
    if sahm:
        exposure = min(exposure, 20)
        veto_labels.append("🚨薩姆規則觸發")

    # 紅線二：ISM PMI 連兩月 <48 → 強制上限 40%
    if pmi < 48 and pmi_prev < 48:
        exposure = min(exposure, 40)
        veto_labels.append(f"⚠️PMI連兩月收縮({pmi_prev:.1f}→{pmi:.1f})")

    # 紅線三：外資期貨淨空 >35000 口 + 指數跌破 MA5 → 強制上限 30%
    if futures_net < -35000 and below_ma5:
        exposure = min(exposure, 30)
        veto_labels.append(f"🚨期貨淨空{abs(futures_net):.0f}口+破MA5")

    # ── 依硬否決後的曝險重新評定等級 ────────────────────────
    if exposure >= 70:   risk_level, regime = "安全", "多頭"
    elif exposure >= 40: risk_level, regime = "警告", "震盪"
    else:                risk_level, regime = "危險", "空頭"

    labels = veto_labels.copy()
    if pmi < 50 and not any("PMI" in l for l in labels):
        labels.append(f"PMI收縮({pmi:.1f})")
    if vix > 25:
        labels.append(f"VIX高波動({vix:.1f})")
    if spread < 0:
        labels.append("資金緊縮")
    if bias240 > 15 and (vix >= 22 or pmi < 50):
        labels.append("均線過熱")
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
