"""
tests/test_macro_state_locker.py
---------------------------------
MacroStateLocker 單元測試（無 HTTP、無 Streamlit）
架構 v2.0：理科（calculate_system_state） / 文科（AI analysis_summary）
"""
import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from macro_state_locker import (
    MacroStateLocker,
    load_macro_state,
    calculate_system_state,
    _DEFAULT_STATE,
)


# ═══════════════════════════════════════════════════════════════
# 輔助工廠
# ═══════════════════════════════════════════════════════════════
def _locker(mock_llm=None, tmp_path=None) -> MacroStateLocker:
    path = tmp_path or tempfile.mktemp(suffix=".json")
    return MacroStateLocker(llm_client=mock_llm, state_file_path=path)


# AI 只輸出 analysis_summary
_VALID_AI_RESP = json.dumps({
    "analysis_summary": "PMI 持續收縮，VIX 偏高，系統建議防禦性配置。",
})

_MARKDOWN_WRAPPED = f"```json\n{_VALID_AI_RESP}\n```"

_BASE_SYSTEM_STATE = {
    "market_regime": "震盪",
    "systemic_risk_level": "警告",
    "exposure_limit_pct": 50,
    "Macro_Phase": "PMI收縮(48.5)",
}


# ═══════════════════════════════════════════════════════════════
# TestCalculateSystemState — 理科引擎
# ═══════════════════════════════════════════════════════════════
class TestCalculateSystemState:
    def test_high_vix_reduces_exposure(self):
        result = calculate_system_state({"VIX_Index": 36, "ISM_PMI_or_OECD_CLI": 52})
        assert result["exposure_limit_pct"] <= 40
        assert result["systemic_risk_level"] in ("警告", "危險")

    def test_low_vix_pmi_expansion_bullish(self):
        result = calculate_system_state({
            "VIX_Index": 13, "ISM_PMI_or_OECD_CLI": 56,
            "M1B_YoY_pct": 5.0, "M2_YoY_pct": 2.0,
        })
        assert result["exposure_limit_pct"] >= 70
        assert result["market_regime"] == "多頭"

    def test_pmi_contraction_label_in_macro_phase(self):
        result = calculate_system_state({"ISM_PMI_or_OECD_CLI": 47})
        assert "PMI收縮" in result["Macro_Phase"]

    def test_normal_env_label(self):
        result = calculate_system_state({"VIX_Index": 18, "ISM_PMI_or_OECD_CLI": 51})
        assert result["Macro_Phase"] == "環境正常"

    def test_none_values_use_defaults(self):
        result = calculate_system_state({"VIX_Index": None, "ISM_PMI_or_OECD_CLI": None})
        assert isinstance(result["exposure_limit_pct"], int)
        assert result["market_regime"] in ("多頭", "震盪", "空頭")

    def test_output_keys_complete(self):
        result = calculate_system_state({})
        for key in ("market_regime", "systemic_risk_level", "exposure_limit_pct", "Macro_Phase"):
            assert key in result

    def test_exposure_within_bounds(self):
        for vix in (10, 20, 30, 40, 50):
            r = calculate_system_state({"VIX_Index": vix})
            assert 0 <= r["exposure_limit_pct"] <= 100

    # ── 三大硬否決紅線測試 ────────────────────────────────────
    def test_sahm_rule_caps_exposure_at_20(self):
        """薩姆規則觸發 → 無論分數多高，曝險上限 20%"""
        result = calculate_system_state({
            "VIX_Index": 14, "ISM_PMI_or_OECD_CLI": 56,
            "M1B_YoY_pct": 5.0, "M2_YoY_pct": 1.0,
            "Sahm_Rule_Triggered": True,
        })
        assert result["exposure_limit_pct"] <= 20
        assert result["systemic_risk_level"] == "危險"
        assert "薩姆規則" in result["Macro_Phase"]

    def test_pmi_consecutive_below_48_caps_at_40(self):
        """PMI 連兩月 <48 → 曝險上限 40%"""
        result = calculate_system_state({
            "VIX_Index": 18, "ISM_PMI_or_OECD_CLI": 47.0,
            "PMI_Prev_Month": 47.5,
        })
        assert result["exposure_limit_pct"] <= 40
        assert "PMI連兩月收縮" in result["Macro_Phase"]

    def test_pmi_only_one_month_no_veto(self):
        """PMI 只有本月 <48，前月正常 → 不觸發連兩月紅線"""
        result = calculate_system_state({
            "ISM_PMI_or_OECD_CLI": 47.0,
            "PMI_Prev_Month": 50.5,
        })
        assert "PMI連兩月收縮" not in result["Macro_Phase"]

    def test_futures_net_short_with_below_ma5_caps_at_30(self):
        """外資期貨淨空 >35000 + 破 MA5 → 曝險上限 30%"""
        result = calculate_system_state({
            "VIX_Index": 18, "ISM_PMI_or_OECD_CLI": 52,
            "Futures_Net_Short": -40000,
            "Index_Below_MA5": True,
        })
        assert result["exposure_limit_pct"] <= 30
        assert "期貨淨空" in result["Macro_Phase"]

    def test_futures_net_short_without_below_ma5_no_veto(self):
        """外資期貨淨空 >35000 但指數站上 MA5 → 不觸發紅線三"""
        result = calculate_system_state({
            "VIX_Index": 18, "ISM_PMI_or_OECD_CLI": 52,
            "Futures_Net_Short": -40000,
            "Index_Below_MA5": False,
        })
        assert "期貨淨空" not in result["Macro_Phase"]


# ═══════════════════════════════════════════════════════════════
# TestExtractJson — _extract_json 清洗邏輯
# ═══════════════════════════════════════════════════════════════
class TestExtractJson:
    def test_plain_json(self):
        result = _locker()._extract_json(_VALID_AI_RESP)
        assert result["analysis_summary"] != ""

    def test_markdown_wrapped(self):
        result = _locker()._extract_json(_MARKDOWN_WRAPPED)
        assert "analysis_summary" in result

    def test_trailing_text(self):
        raw = _VALID_AI_RESP + "\n\n以上為本次分析結論。"
        result = _locker()._extract_json(raw)
        assert result["analysis_summary"] != ""

    def test_invalid_raises(self):
        with pytest.raises((ValueError, json.JSONDecodeError)):
            _locker()._extract_json("這不是 JSON 格式的文字。")

    def test_empty_raises(self):
        with pytest.raises((ValueError, json.JSONDecodeError)):
            _locker()._extract_json("")


# ═══════════════════════════════════════════════════════════════
# TestWriteStateLock — 原子寫入
# ═══════════════════════════════════════════════════════════════
class TestWriteStateLock:
    def test_writes_json_file(self, tmp_path):
        path = str(tmp_path / "state.json")
        _locker(tmp_path=path)._write_state_lock({"market_regime": "震盪", "exposure_limit_pct": 40})
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["market_regime"] == "震盪"

    def test_no_tmp_file_remains(self, tmp_path):
        path = str(tmp_path / "state.json")
        _locker(tmp_path=path)._write_state_lock({"x": 1})
        assert not os.path.exists(path + ".tmp")

    def test_unicode_persisted(self, tmp_path):
        path = str(tmp_path / "state.json")
        _locker(tmp_path=path)._write_state_lock({"analysis_summary": "繁體中文測試內容"})
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "繁體中文" in data["analysis_summary"]

    def test_overwrites_existing(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(tmp_path=path)
        locker._write_state_lock({"v": 1})
        locker._write_state_lock({"v": 2})
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["v"] == 2


# ═══════════════════════════════════════════════════════════════
# TestExecuteAndLock — 主入口整合
# ═══════════════════════════════════════════════════════════════
class TestExecuteAndLock:
    def test_success_path(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(mock_llm=lambda p: _VALID_AI_RESP, tmp_path=path)
        ok = locker.execute_and_lock(_BASE_SYSTEM_STATE.copy(), ["市場平穩"])
        assert ok is True
        data = json.load(open(path, encoding="utf-8"))
        assert data["market_regime"] == "震盪"
        assert data["analysis_summary"] != ""

    def test_exposure_clamped_to_100(self, tmp_path):
        path = str(tmp_path / "state.json")
        state = {**_BASE_SYSTEM_STATE, "exposure_limit_pct": 150}
        locker = _locker(mock_llm=lambda p: _VALID_AI_RESP, tmp_path=path)
        locker.execute_and_lock(state, [])
        data = json.load(open(path, encoding="utf-8"))
        assert data["exposure_limit_pct"] == 100

    def test_exposure_clamped_to_0(self, tmp_path):
        path = str(tmp_path / "state.json")
        state = {**_BASE_SYSTEM_STATE, "exposure_limit_pct": -10}
        locker = _locker(mock_llm=lambda p: _VALID_AI_RESP, tmp_path=path)
        locker.execute_and_lock(state, [])
        data = json.load(open(path, encoding="utf-8"))
        assert data["exposure_limit_pct"] == 0

    def test_timestamp_written(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(mock_llm=lambda p: _VALID_AI_RESP, tmp_path=path)
        locker.execute_and_lock(_BASE_SYSTEM_STATE.copy(), [])
        data = json.load(open(path, encoding="utf-8"))
        assert data.get("timestamp", "") != ""

    def test_system_state_fields_preserved(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(mock_llm=lambda p: _VALID_AI_RESP, tmp_path=path)
        locker.execute_and_lock(_BASE_SYSTEM_STATE.copy(), [])
        data = json.load(open(path, encoding="utf-8"))
        assert data["Macro_Phase"] == "PMI收縮(48.5)"
        assert data["systemic_risk_level"] == "警告"

    def test_llm_error_triggers_failsafe(self, tmp_path):
        path = str(tmp_path / "state.json")
        def bad_llm(p): raise RuntimeError("API down")
        locker = _locker(mock_llm=bad_llm, tmp_path=path)
        ok = locker.execute_and_lock(_BASE_SYSTEM_STATE.copy(), [])
        assert ok is False
        data = json.load(open(path, encoding="utf-8"))
        assert data["exposure_limit_pct"] == 0
        assert data["systemic_risk_level"] == "危險"

    def test_llm_warning_prefix_triggers_failsafe(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(mock_llm=lambda p: "⚠️ API Key 無效", tmp_path=path)
        ok = locker.execute_and_lock(_BASE_SYSTEM_STATE.copy(), [])
        assert ok is False
        data = json.load(open(path, encoding="utf-8"))
        assert data["exposure_limit_pct"] == 0

    def test_invalid_json_triggers_failsafe(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(mock_llm=lambda p: "不是 JSON", tmp_path=path)
        ok = locker.execute_and_lock(_BASE_SYSTEM_STATE.copy(), [])
        assert ok is False

    def test_empty_news_list(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(mock_llm=lambda p: _VALID_AI_RESP, tmp_path=path)
        ok = locker.execute_and_lock(_BASE_SYSTEM_STATE.copy(), [])
        assert ok is True

    def test_prompt_contains_system_state(self, tmp_path):
        path = str(tmp_path / "state.json")
        received = []
        def capture_llm(p): received.append(p); return _VALID_AI_RESP
        locker = _locker(mock_llm=capture_llm, tmp_path=path)
        locker.execute_and_lock({**_BASE_SYSTEM_STATE, "exposure_limit_pct": 30}, ["headline"])
        assert "30" in received[0]
        assert "exposure_limit_pct" in received[0]

    def test_prompt_contains_news(self, tmp_path):
        path = str(tmp_path / "state.json")
        received = []
        def capture_llm(p): received.append(p); return _VALID_AI_RESP
        locker = _locker(mock_llm=capture_llm, tmp_path=path)
        locker.execute_and_lock(_BASE_SYSTEM_STATE.copy(), ["Fed 升息 50bps"])
        assert "Fed 升息 50bps" in received[0]


# ═══════════════════════════════════════════════════════════════
# TestLoadMacroState — 前端唯讀工具函式
# ═══════════════════════════════════════════════════════════════
class TestLoadMacroState:
    def test_loads_valid_file(self, tmp_path):
        path = str(tmp_path / "s.json")
        payload = {
            "market_regime": "空頭",
            "systemic_risk_level": "危險",
            "exposure_limit_pct": 10,
            "Macro_Phase": "PMI收縮(46.0)",
            "analysis_summary": "謹慎防禦",
            "timestamp": "2026-04-17 09:00:00",
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        data = load_macro_state(path)
        assert data["market_regime"] == "空頭"
        assert data["exposure_limit_pct"] == 10
        assert data["analysis_summary"] == "謹慎防禦"

    def test_missing_file_returns_default(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        data = load_macro_state(path)
        assert data["exposure_limit_pct"] == 0
        assert data["systemic_risk_level"] == "危險"

    def test_corrupt_file_returns_default(self, tmp_path):
        path = str(tmp_path / "bad.json")
        with open(path, "w") as f:
            f.write("{ broken json ::::")
        data = load_macro_state(path)
        assert data["exposure_limit_pct"] == 0

    def test_exposure_coerced_to_int(self, tmp_path):
        path = str(tmp_path / "s.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"exposure_limit_pct": "60"}, f)
        data = load_macro_state(path)
        assert isinstance(data["exposure_limit_pct"], int)
        assert data["exposure_limit_pct"] == 60


# ═══════════════════════════════════════════════════════════════
# TestDefaultGeminiCall — _default_gemini_call() HTTP paths
# ═══════════════════════════════════════════════════════════════
from macro_state_locker import _default_gemini_call


class TestDefaultGeminiCall:

    def test_no_api_key_returns_warning(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            result = _default_gemini_call("test prompt")
        assert result.startswith("⚠️ 缺少 GEMINI_API_KEY")

    def test_successful_200_returns_text(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "AI 分析結果"}]}}]
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            with patch("requests.post", return_value=mock_resp):
                result = _default_gemini_call("prompt")
        assert result == "AI 分析結果"

    def test_404_skips_to_next_model_all_fail(self):
        """所有模型都回 404 → 回傳 AI 服務暫時無法使用"""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            with patch("requests.post", return_value=mock_resp):
                result = _default_gemini_call("prompt")
        assert result.startswith("⚠️ AI 服務暫時無法使用")

    def test_safety_filter_continues_next_model(self):
        """第一個模型 SAFETY → 嘗試下一個；所有都 SAFETY → 最終失敗"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            with patch("requests.post", return_value=mock_resp):
                result = _default_gemini_call("prompt")
        assert result.startswith("⚠️ AI 服務暫時無法使用")

    def test_429_rate_limit_sleeps_and_retries(self):
        """429 → 呼叫 time.sleep(5) 後繼續嘗試下一個模型"""
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429
        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200
        mock_resp_ok.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "retry success"}]}}]
        }
        responses = [mock_resp_429, mock_resp_ok]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            with patch("requests.post", side_effect=responses):
                with patch("time.sleep"):
                    result = _default_gemini_call("prompt")
        assert result == "retry success"

    def test_request_exception_logs_and_continues(self):
        """requests 拋出異常 → 繼續嘗試下一個模型；全失敗 → 警告"""
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            with patch("requests.post", side_effect=ConnectionError("timeout")):
                with patch("time.sleep"):
                    result = _default_gemini_call("prompt")
        assert result.startswith("⚠️ AI 服務暫時無法使用")

    def test_200_empty_candidates_continues(self):
        """200 但 candidates=[] → 繼續嘗試下一個模型"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"candidates": []}
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
            with patch("requests.post", return_value=mock_resp):
                result = _default_gemini_call("prompt")
        assert result.startswith("⚠️ AI 服務暫時無法使用")


# ═══════════════════════════════════════════════════════════════
# TestLockSystemStateOnly — 規則引擎直寫（不呼叫 AI）
# ═══════════════════════════════════════════════════════════════

class TestLockSystemStateOnly:

    def test_writes_state_without_ai(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(tmp_path=path)
        locker.lock_system_state_only({
            "market_regime": "多頭",
            "systemic_risk_level": "安全",
            "exposure_limit_pct": 80,
        })
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["market_regime"] == "多頭"
        assert saved["exposure_limit_pct"] == 80

    def test_exposure_clamped_above_100(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(tmp_path=path)
        locker.lock_system_state_only({"exposure_limit_pct": 150})
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["exposure_limit_pct"] == 100

    def test_exposure_clamped_below_0(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(tmp_path=path)
        locker.lock_system_state_only({"exposure_limit_pct": -20})
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["exposure_limit_pct"] == 0

    def test_summary_contains_exposure(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(tmp_path=path)
        locker.lock_system_state_only({"exposure_limit_pct": 60})
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        assert "60" in saved["analysis_summary"]
        assert "timestamp" in saved


# ═══════════════════════════════════════════════════════════════
# TestCalculateSystemStateBias240 — BIAS240 雙重共振 & _f() 邊界
# ═══════════════════════════════════════════════════════════════

class TestCalculateSystemStateBias240:

    def test_high_bias240_with_high_vix_penalises(self):
        """BIAS240>15 且 VIX>=22 → score -15, 標記「均線過熱」"""
        result = calculate_system_state({
            "VIX_Index": 25.0,
            "ISM_PMI_or_OECD_CLI": 52.0,
            "BIAS240_pct": 18.0,
        })
        assert "均線過熱" in result["Macro_Phase"]

    def test_high_bias240_with_pmi_below_50_penalises(self):
        """BIAS240>15 且 PMI<50 → 觸發雙重共振懲罰"""
        result = calculate_system_state({
            "VIX_Index": 18.0,
            "ISM_PMI_or_OECD_CLI": 48.0,
            "BIAS240_pct": 20.0,
        })
        assert "均線過熱" in result["Macro_Phase"]

    def test_high_bias240_without_resonance_no_penalty(self):
        """BIAS240>15 但 VIX<22 且 PMI>=50 → 不觸發雙重共振（不加「均線過熱」）"""
        result = calculate_system_state({
            "VIX_Index": 16.0,
            "ISM_PMI_or_OECD_CLI": 53.0,
            "BIAS240_pct": 18.0,
        })
        assert "均線過熱" not in result["Macro_Phase"]

    def test_low_bias240_adds_score(self):
        """BIAS240 < -10 → score +10（偏空後超賣反彈空間）"""
        baseline = calculate_system_state({"VIX_Index": 20.0, "BIAS240_pct": 0.0})
        boosted  = calculate_system_state({"VIX_Index": 20.0, "BIAS240_pct": -12.0})
        assert boosted["exposure_limit_pct"] >= baseline["exposure_limit_pct"]

    def test_non_numeric_value_uses_default(self):
        """_f() 收到非數值字串 → 回傳預設值，不拋出例外"""
        result = calculate_system_state({
            "VIX_Index": "not_a_number",
            "ISM_PMI_or_OECD_CLI": "bad",
        })
        assert isinstance(result["exposure_limit_pct"], int)

    def test_negative_m1b_m2_spread_labels_tightening(self):
        """M1B YoY < M2 YoY（資金緊縮）→ Macro_Phase 含「資金緊縮」"""
        result = calculate_system_state({
            "VIX_Index": 18.0,
            "M1B_YoY_pct": 1.0,
            "M2_YoY_pct": 5.0,   # spread = -4 < 0
        })
        assert "資金緊縮" in result["Macro_Phase"]
