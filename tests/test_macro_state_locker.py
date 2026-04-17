"""
tests/test_macro_state_locker.py
---------------------------------
MacroStateLocker 單元測試（無 HTTP、無 Streamlit）
"""
import json
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

# 確保 project root 在 sys.path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from macro_state_locker import MacroStateLocker, load_macro_state, _DEFAULT_STATE


# ═══════════════════════════════════════════════════════════════
# 輔助工廠
# ═══════════════════════════════════════════════════════════════
def _locker(mock_llm=None, tmp_path=None) -> MacroStateLocker:
    """建立測試用 MacroStateLocker，不呼叫真實 Gemini API。"""
    path = tmp_path or tempfile.mktemp(suffix=".json")
    return MacroStateLocker(llm_client=mock_llm, state_file_path=path)


_VALID_JSON_RESP = json.dumps({
    "market_regime": "多頭",
    "systemic_risk_level": "安全",
    "equity_fund_exposure_pct": 70,
    "final_verdict": "量化指標樂觀，建議維持高曝險。",
})

_MARKDOWN_WRAPPED = f"```json\n{_VALID_JSON_RESP}\n```"


# ═══════════════════════════════════════════════════════════════
# TestExtractJson — _extract_json 清洗邏輯
# ═══════════════════════════════════════════════════════════════
class TestExtractJson:
    def test_plain_json(self):
        locker = _locker()
        result = locker._extract_json(_VALID_JSON_RESP)
        assert result["market_regime"] == "多頭"
        assert result["equity_fund_exposure_pct"] == 70

    def test_markdown_wrapped(self):
        locker = _locker()
        result = locker._extract_json(_MARKDOWN_WRAPPED)
        assert result["systemic_risk_level"] == "安全"

    def test_trailing_text(self):
        """LLM 在 JSON 後加說明文字仍可解析。"""
        raw = _VALID_JSON_RESP + "\n\n以上為本次分析結論。"
        result = _locker()._extract_json(raw)
        assert result["final_verdict"] != ""

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
        locker = _locker(tmp_path=path)
        locker._write_state_lock({"market_regime": "震盪", "equity_fund_exposure_pct": 40})
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["market_regime"] == "震盪"

    def test_no_tmp_file_remains(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(tmp_path=path)
        locker._write_state_lock({"x": 1})
        assert not os.path.exists(path + ".tmp")

    def test_unicode_persisted(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(tmp_path=path)
        locker._write_state_lock({"final_verdict": "繁體中文測試內容"})
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "繁體中文" in data["final_verdict"]

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
        locker = _locker(mock_llm=lambda p: _VALID_JSON_RESP, tmp_path=path)
        ok = locker.execute_and_lock({"VIX_Index": 18.0}, ["市場平穩"])
        assert ok is True
        data = json.load(open(path, encoding="utf-8"))
        assert data["market_regime"] == "多頭"
        assert data["equity_fund_exposure_pct"] == 70

    def test_exposure_clamped_to_100(self, tmp_path):
        path = str(tmp_path / "state.json")
        raw = json.dumps({
            "market_regime": "多頭",
            "systemic_risk_level": "安全",
            "equity_fund_exposure_pct": 150,
            "final_verdict": "test",
        })
        locker = _locker(mock_llm=lambda p: raw, tmp_path=path)
        locker.execute_and_lock({}, [])
        data = json.load(open(path, encoding="utf-8"))
        assert data["equity_fund_exposure_pct"] == 100

    def test_exposure_clamped_to_0(self, tmp_path):
        path = str(tmp_path / "state.json")
        raw = json.dumps({
            "market_regime": "空頭",
            "systemic_risk_level": "危險",
            "equity_fund_exposure_pct": -10,
            "final_verdict": "test",
        })
        locker = _locker(mock_llm=lambda p: raw, tmp_path=path)
        locker.execute_and_lock({}, [])
        data = json.load(open(path, encoding="utf-8"))
        assert data["equity_fund_exposure_pct"] == 0

    def test_timestamp_written(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(mock_llm=lambda p: _VALID_JSON_RESP, tmp_path=path)
        locker.execute_and_lock({}, [])
        data = json.load(open(path, encoding="utf-8"))
        assert data.get("timestamp", "") != ""

    def test_llm_error_triggers_failsafe(self, tmp_path):
        path = str(tmp_path / "state.json")
        def bad_llm(p): raise RuntimeError("API down")
        locker = _locker(mock_llm=bad_llm, tmp_path=path)
        ok = locker.execute_and_lock({}, [])
        assert ok is False
        data = json.load(open(path, encoding="utf-8"))
        assert data["equity_fund_exposure_pct"] == 0
        assert data["systemic_risk_level"] == "危險"

    def test_llm_warning_prefix_triggers_failsafe(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(mock_llm=lambda p: "⚠️ API Key 無效", tmp_path=path)
        ok = locker.execute_and_lock({}, [])
        assert ok is False
        data = json.load(open(path, encoding="utf-8"))
        assert data["equity_fund_exposure_pct"] == 0

    def test_invalid_json_triggers_failsafe(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(mock_llm=lambda p: "不是 JSON", tmp_path=path)
        ok = locker.execute_and_lock({}, [])
        assert ok is False

    def test_empty_news_list(self, tmp_path):
        path = str(tmp_path / "state.json")
        locker = _locker(mock_llm=lambda p: _VALID_JSON_RESP, tmp_path=path)
        ok = locker.execute_and_lock({"VIX_Index": 25}, [])
        assert ok is True

    def test_prompt_contains_macro_numbers(self, tmp_path):
        path = str(tmp_path / "state.json")
        received = []
        def capture_llm(p): received.append(p); return _VALID_JSON_RESP
        locker = _locker(mock_llm=capture_llm, tmp_path=path)
        locker.execute_and_lock({"VIX_Index": 99.9}, ["headline"])
        assert "99.9" in received[0]

    def test_prompt_contains_news(self, tmp_path):
        path = str(tmp_path / "state.json")
        received = []
        def capture_llm(p): received.append(p); return _VALID_JSON_RESP
        locker = _locker(mock_llm=capture_llm, tmp_path=path)
        locker.execute_and_lock({}, ["Fed 升息 50bps"])
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
            "equity_fund_exposure_pct": 10,
            "final_verdict": "謹慎",
            "timestamp": "2026-04-17 09:00:00",
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        data = load_macro_state(path)
        assert data["market_regime"] == "空頭"
        assert data["equity_fund_exposure_pct"] == 10

    def test_missing_file_returns_default(self, tmp_path):
        path = str(tmp_path / "nonexistent.json")
        data = load_macro_state(path)
        assert data["equity_fund_exposure_pct"] == 0
        assert data["systemic_risk_level"] == "危險"

    def test_corrupt_file_returns_default(self, tmp_path):
        path = str(tmp_path / "bad.json")
        with open(path, "w") as f:
            f.write("{ broken json ::::")
        data = load_macro_state(path)
        assert data["equity_fund_exposure_pct"] == 0

    def test_exposure_coerced_to_int(self, tmp_path):
        path = str(tmp_path / "s.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"equity_fund_exposure_pct": "60"}, f)
        data = load_macro_state(path)
        assert isinstance(data["equity_fund_exposure_pct"], int)
        assert data["equity_fund_exposure_pct"] == 60
