"""
macro_state_locker.py — L3 策略層：AI 總裁決引擎 + 實體狀態鎖
-------------------------------------------------------------
MacroStateLocker.execute_and_lock(macro_numbers, news_list)
  → 呼叫 Gemini AI → 解析 JSON → 原子寫入 macro_state.json

前端 (app.py) 只需呼叫 load_macro_state() 唯讀讀取，
不在 Streamlit render 週期內執行任何 LLM 運算。
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
    "equity_fund_exposure_pct": 0,
    "final_verdict": (
        "系統防護機制啟動：無法取得有效的總經與新聞數據，"
        "強制將風險部位降至零。"
    ),
    "timestamp": "",
}

# ── AI 核心 Prompt 模板 ─────────────────────────────────────
_PROMPT_TEMPLATE = """\
# Role
你是「台股戰情室首席總經風險量化分析師」。你的唯一職責是輸出機器可讀的決策配置。

# Absolute Constraint（實體鎖協定）
1. 資訊隔離：【禁止】使用預訓練記憶。結論【必須 100% 基於】<Macro_Numbers> 與 <Systemic_Risk_News>。
2. 宏觀否決權：審查 <Systemic_Risk_News>，若出現「戰爭爆發、致命疫情擴散、大型金融機構倒閉」等黑天鵝，強制觸發最高風險警報。
3. 標的限制：禁止在結論中建議配置 ETF，請將資金配置建議集中於「股票型基金/個股」與「現金/防禦型資產」。

# Input Data
<Macro_Numbers>
{macro_numbers_json}
</Macro_Numbers>

<Systemic_Risk_News>
{news_string}
</Systemic_Risk_News>

# Output Protocol
請直接輸出符合以下格式的 JSON，禁止包含任何 Markdown 標記或解釋性文字：
{{
  "market_regime": "多頭 / 震盪 / 空頭",
  "systemic_risk_level": "安全 / 警告 / 危險",
  "equity_fund_exposure_pct": 50,
  "final_verdict": "結合數值與新聞的單一結論（100字內，說明為何給出此資金曝險比例）"
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
        macro_numbers: dict,
        news_list: list[str],
    ) -> bool:
        """
        執行 AI 判讀並將結果寫入實體狀態鎖。

        Returns True on success, False on failure (fail-safe written).
        """
        numbers_str = json.dumps(macro_numbers, ensure_ascii=False, indent=2)
        news_str = (
            "\n".join(f"- {n}" for n in news_list)
            if news_list
            else "無重大異常新聞"
        )
        prompt = self._build_prompt(numbers_str, news_str)

        try:
            raw_response = self._llm(prompt)
            if raw_response.startswith("⚠️"):
                raise ValueError(raw_response)

            clean = self._extract_json(raw_response)
            clean["equity_fund_exposure_pct"] = max(
                0, min(100, int(clean.get("equity_fund_exposure_pct", 0)))
            )
            clean["timestamp"] = _now_str()
            self._write_state_lock(clean)
            print(f"[MacroStateLocker] ✅ 寫入成功：{clean['market_regime']} / "
                  f"曝險 {clean['equity_fund_exposure_pct']}%")
            return True

        except Exception as _e:
            print(f"[MacroStateLocker] ❌ {_e}，啟動 Fail-safe")
            _fs = self.default_state.copy()
            _fs["timestamp"] = _now_str()
            self._write_state_lock(_fs)
            return False

    # ── 內部方法 ────────────────────────────────────────────
    def _build_prompt(self, numbers_str: str, news_str: str) -> str:
        return _PROMPT_TEMPLATE.format(
            macro_numbers_json=numbers_str,
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
        # 型別保護
        data["equity_fund_exposure_pct"] = int(
            data.get("equity_fund_exposure_pct", 0)
        )
        return data
    except Exception:
        return _DEFAULT_STATE.copy()


# ── 工具 ────────────────────────────────────────────────────
def _now_str() -> str:
    from datetime import datetime, timezone, timedelta
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
