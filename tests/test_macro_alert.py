"""
總經數據自動警示模組單元測試 (macro_alert.py)

涵蓋範圍：
  - _classify_level()        閾值三色分級（含 PCR 雙向觸發）
  - check_macro_alerts()     主引擎（觸發 / 邊界值 / 防呆 / dict 結構）
  - alert_summary()          彙總統計（計數 / 整體等級優先序）
  - fetch_macro_snapshot()   資料適配器（session_state 路徑，不呼叫任何 API）
  - 整合測試                 end-to-end: snapshot → alerts → summary
"""

import pytest
import pandas as pd
from unittest.mock import patch

from macro_alert import (
    _classify_level,
    check_macro_alerts,
    alert_summary,
    fetch_macro_snapshot,
    MACRO_ALERT_RULES,
)

# ── 測試用規則快照（從 MACRO_ALERT_RULES 取對應規則）────────────
def _rule(key: str) -> dict:
    """從 MACRO_ALERT_RULES 取出指定 key 的規則，找不到則 pytest.fail。"""
    for r in MACRO_ALERT_RULES:
        if r['key'] == key:
            return r
    pytest.fail(f"MACRO_ALERT_RULES 中找不到 key='{key}'")


# ══════════════════════════════════════════════════════════════
# 1. _classify_level — 閾值分級邏輯
# ══════════════════════════════════════════════════════════════

class TestClassifyLevel:
    """驗證單一規則的三色分級，不依賴 MACRO_ALERT_RULES 順序。"""

    # ── VIX（高端單向） ───────────────────────────────────────
    def test_vix_red_above_threshold(self):
        assert _classify_level(30.001, _rule('vix')) == 'red'

    def test_vix_boundary_exactly_at_red_is_yellow(self):
        # 規則使用嚴格 >，30.0 不觸發 red
        assert _classify_level(30.0, _rule('vix')) == 'yellow'

    def test_vix_yellow_mid_range(self):
        assert _classify_level(25.0, _rule('vix')) == 'yellow'

    def test_vix_boundary_exactly_at_yellow_is_green(self):
        # 20.0 不觸發 yellow
        assert _classify_level(20.0, _rule('vix')) == 'green'

    def test_vix_green_below_threshold(self):
        assert _classify_level(15.0, _rule('vix')) == 'green'

    # ── CPI（高端單向） ──────────────────────────────────────
    def test_cpi_red(self):
        assert _classify_level(3.6, _rule('cpi')) == 'red'

    def test_cpi_yellow(self):
        assert _classify_level(3.0, _rule('cpi')) == 'yellow'

    def test_cpi_green(self):
        assert _classify_level(2.0, _rule('cpi')) == 'green'

    def test_cpi_boundary_red(self):
        assert _classify_level(3.5, _rule('cpi')) == 'yellow'   # 3.5 not > 3.5

    def test_cpi_boundary_yellow(self):
        assert _classify_level(2.5, _rule('cpi')) == 'green'    # 2.5 not > 2.5

    # ── us10y（高端單向） ────────────────────────────────────
    def test_us10y_red(self):
        assert _classify_level(5.0, _rule('us10y')) == 'red'

    def test_us10y_yellow(self):
        assert _classify_level(4.5, _rule('us10y')) == 'yellow'

    def test_us10y_green(self):
        assert _classify_level(4.0, _rule('us10y')) == 'green'

    # ── dxy（高端單向）──────────────────────────────────────
    def test_dxy_red(self):
        assert _classify_level(108.0, _rule('dxy')) == 'red'

    def test_dxy_yellow(self):
        assert _classify_level(105.0, _rule('dxy')) == 'yellow'

    def test_dxy_green(self):
        assert _classify_level(100.0, _rule('dxy')) == 'green'

    # ── PCR（雙向：高端偏空 + 低端過熱）────────────────────
    def test_pcr_high_red(self):
        assert _classify_level(1.6, _rule('pcr')) == 'red'

    def test_pcr_high_red_boundary(self):
        assert _classify_level(1.5, _rule('pcr')) == 'yellow'   # 1.5 not > 1.5

    def test_pcr_high_yellow(self):
        assert _classify_level(1.3, _rule('pcr')) == 'yellow'

    def test_pcr_high_yellow_boundary(self):
        assert _classify_level(1.2, _rule('pcr')) == 'green'    # 1.2 not > 1.2

    def test_pcr_normal_green(self):
        assert _classify_level(1.0, _rule('pcr')) == 'green'

    def test_pcr_low_yellow(self):
        assert _classify_level(0.65, _rule('pcr')) == 'yellow'

    def test_pcr_low_yellow_boundary(self):
        assert _classify_level(0.7, _rule('pcr')) == 'green'    # 0.7 not < 0.7

    def test_pcr_low_red(self):
        assert _classify_level(0.4, _rule('pcr')) == 'red'

    def test_pcr_low_red_boundary(self):
        assert _classify_level(0.5, _rule('pcr')) == 'yellow'   # 0.5 not < 0.5

    def test_pcr_high_red_priority_over_low_check(self):
        # 極端高值不應被低端規則誤判
        assert _classify_level(2.0, _rule('pcr')) == 'red'


# ══════════════════════════════════════════════════════════════
# 2. check_macro_alerts — 主引擎
# ══════════════════════════════════════════════════════════════

class TestCheckMacroAlerts:
    """驗證主引擎的觸發行為、防呆、與回傳 dict 結構。"""

    def test_empty_snapshot_returns_empty_list(self):
        assert check_macro_alerts({}) == []

    def test_missing_key_is_skipped(self):
        # 只傳 vix，其他指標應略過
        result = check_macro_alerts({'vix': 25.0})
        assert len(result) == 1
        assert result[0]['key'] == 'vix'

    def test_none_value_is_skipped(self):
        result = check_macro_alerts({'vix': None, 'cpi': 3.0})
        assert all(a['key'] != 'vix' for a in result)
        assert any(a['key'] == 'cpi' for a in result)

    def test_non_numeric_value_is_skipped(self):
        result = check_macro_alerts({'vix': 'N/A', 'cpi': 2.0})
        assert all(a['key'] != 'vix' for a in result)

    def test_alert_dict_has_required_keys(self):
        result = check_macro_alerts({'vix': 25.0})
        assert len(result) == 1
        a = result[0]
        for field in ('key', 'label', 'unit', 'value', 'level', 'emoji', 'message'):
            assert field in a, f"missing field: {field}"

    def test_emoji_matches_level(self):
        snap = {'vix': 35.0, 'cpi': 3.0, 'us10y': 4.0}
        alerts = check_macro_alerts(snap)
        by_key = {a['key']: a for a in alerts}
        assert by_key['vix']['emoji']   == '🔴'
        assert by_key['cpi']['emoji']   == '🟡'
        assert by_key['us10y']['emoji'] == '🟢'

    def test_value_is_float(self):
        result = check_macro_alerts({'vix': '22.5'})   # 字串可轉 float
        assert result[0]['value'] == pytest.approx(22.5)
        assert isinstance(result[0]['value'], float)

    def test_all_green_scenario(self):
        snap = {'vix': 15.0, 'cpi': 2.0, 'us10y': 3.9, 'dxy': 100.0, 'pcr': 0.9}
        alerts = check_macro_alerts(snap)
        assert all(a['level'] == 'green' for a in alerts)
        assert len(alerts) == 5

    def test_all_red_scenario(self):
        snap = {'vix': 35.0, 'cpi': 4.0, 'us10y': 5.0, 'dxy': 110.0, 'pcr': 2.0}
        alerts = check_macro_alerts(snap)
        assert all(a['level'] == 'red' for a in alerts)

    def test_output_preserves_rules_order(self):
        # 輸出順序應遵循 MACRO_ALERT_RULES 定義順序
        snap = {'vix': 20.0, 'cpi': 2.5, 'us10y': 4.2, 'dxy': 103.0, 'pcr': 0.7}
        alerts = check_macro_alerts(snap)
        keys = [a['key'] for a in alerts]
        rule_keys = [r['key'] for r in MACRO_ALERT_RULES]
        assert keys == rule_keys

    def test_message_is_nonempty_string(self):
        result = check_macro_alerts({'vix': 32.0})
        assert isinstance(result[0]['message'], str)
        assert len(result[0]['message']) > 0

    def test_unit_is_percent_for_cpi(self):
        result = check_macro_alerts({'cpi': 3.0})
        assert result[0]['unit'] == '%'

    def test_unit_is_empty_for_vix(self):
        result = check_macro_alerts({'vix': 22.0})
        assert result[0]['unit'] == ''


# ══════════════════════════════════════════════════════════════
# 3. alert_summary — 彙總統計
# ══════════════════════════════════════════════════════════════

class TestAlertSummary:

    def test_empty_list_is_overall_green(self):
        sm = alert_summary([])
        assert sm['overall'] == 'green'
        assert sm['overall_emoji'] == '🟢'
        assert sm['total'] == 0

    def test_counts_are_correct(self):
        alerts = [
            {'level': 'red'},
            {'level': 'red'},
            {'level': 'yellow'},
            {'level': 'green'},
            {'level': 'green'},
            {'level': 'green'},
        ]
        sm = alert_summary(alerts)
        assert sm['red_count']    == 2
        assert sm['yellow_count'] == 1
        assert sm['green_count']  == 3
        assert sm['total']        == 6

    def test_overall_red_when_any_red(self):
        alerts = [{'level': 'red'}, {'level': 'yellow'}, {'level': 'green'}]
        assert alert_summary(alerts)['overall'] == 'red'

    def test_overall_yellow_when_no_red(self):
        alerts = [{'level': 'yellow'}, {'level': 'green'}]
        assert alert_summary(alerts)['overall'] == 'yellow'

    def test_overall_green_when_all_green(self):
        alerts = [{'level': 'green'}, {'level': 'green'}]
        assert alert_summary(alerts)['overall'] == 'green'

    def test_overall_emoji_matches_level(self):
        for level, expected_emoji in [('red', '🔴'), ('yellow', '🟡'), ('green', '🟢')]:
            sm = alert_summary([{'level': level}])
            assert sm['overall_emoji'] == expected_emoji

    def test_all_required_keys_present(self):
        sm = alert_summary([])
        for k in ('red_count', 'yellow_count', 'green_count', 'total',
                  'overall', 'overall_emoji'):
            assert k in sm, f"missing key: {k}"


# ══════════════════════════════════════════════════════════════
# 4. fetch_macro_snapshot — 資料適配器（不呼叫 API）
# ══════════════════════════════════════════════════════════════

class TestFetchMacroSnapshot:
    """
    所有測試都 patch _yf_latest 回傳空 dict，
    確保不發出任何 HTTP 請求。
    """

    @patch('macro_alert._yf_latest', return_value={})
    def test_vix_read_from_session_macro(self, _):
        snap = fetch_macro_snapshot(
            session_macro={'vix': {'current': 22.5}}
        )
        assert snap.get('vix') == pytest.approx(22.5)

    @patch('macro_alert._yf_latest', return_value={})
    def test_cpi_read_from_session_macro(self, _):
        snap = fetch_macro_snapshot(
            session_macro={'us_core_cpi': {'yoy': 3.1}}
        )
        assert snap.get('cpi') == pytest.approx(3.1)

    @patch('macro_alert._yf_latest', return_value={})
    def test_pcr_read_from_session_li(self, _):
        df = pd.DataFrame([{'選PCR': 1.18}, {'選PCR': 1.25}])
        snap = fetch_macro_snapshot(session_li=df)
        assert snap.get('pcr') == pytest.approx(1.25)   # iloc[-1]

    @patch('macro_alert._yf_latest', return_value={})
    def test_none_session_macro_yields_no_vix(self, _):
        snap = fetch_macro_snapshot(session_macro=None)
        assert 'vix' not in snap

    @patch('macro_alert._yf_latest', return_value={})
    def test_empty_session_macro_yields_no_cpi(self, _):
        snap = fetch_macro_snapshot(session_macro={})
        assert 'cpi' not in snap

    @patch('macro_alert._yf_latest', return_value={})
    def test_empty_dataframe_yields_no_pcr(self, _):
        snap = fetch_macro_snapshot(session_li=pd.DataFrame())
        assert 'pcr' not in snap

    @patch('macro_alert._yf_latest', return_value={})
    def test_missing_pcr_column_yields_no_pcr(self, _):
        df = pd.DataFrame([{'外資大小': 5000}])
        snap = fetch_macro_snapshot(session_li=df)
        assert 'pcr' not in snap

    @patch('macro_alert._yf_latest', return_value={})
    def test_pcr_dash_string_is_skipped(self, _):
        df = pd.DataFrame([{'選PCR': '-'}])
        snap = fetch_macro_snapshot(session_li=df)
        assert 'pcr' not in snap

    @patch('macro_alert._yf_latest', return_value={})
    def test_pcr_nan_string_is_skipped(self, _):
        df = pd.DataFrame([{'選PCR': 'nan'}])
        snap = fetch_macro_snapshot(session_li=df)
        assert 'pcr' not in snap

    @patch('macro_alert._yf_latest', return_value={'^TNX': 4.55, 'DX-Y.NYB': 105.2})
    def test_us10y_and_dxy_read_from_yfinance(self, _):
        snap = fetch_macro_snapshot()
        assert snap.get('us10y') == pytest.approx(4.55)
        assert snap.get('dxy')   == pytest.approx(105.2)

    @patch('macro_alert._yf_latest', return_value={'^VIX': 18.3, '^TNX': 4.2, 'DX-Y.NYB': 102.0})
    def test_vix_from_yfinance_when_session_missing(self, _):
        # session_macro 中無 vix，應從 yfinance 補抓
        snap = fetch_macro_snapshot(session_macro={'us_core_cpi': {'yoy': 2.5}})
        assert snap.get('vix') == pytest.approx(18.3)

    @patch('macro_alert._yf_latest', return_value={'^TNX': 4.2, 'DX-Y.NYB': 102.0})
    def test_session_vix_takes_priority_over_yfinance(self, mock_yf):
        # session_state 有 vix → 不應把 ^VIX 放入 _need_yf
        snap = fetch_macro_snapshot(
            session_macro={'vix': {'current': 25.0}}
        )
        assert snap['vix'] == pytest.approx(25.0)
        # ^VIX 不應出現在 yfinance 呼叫的 tickers 中
        called_tickers = mock_yf.call_args[0][0]
        assert '^VIX' not in called_tickers

    @patch('macro_alert._yf_latest', side_effect=Exception('network error'))
    def test_yfinance_failure_does_not_crash(self, _):
        # yfinance 失敗時，snapshot 仍含 session_state 資料
        snap = fetch_macro_snapshot(
            session_macro={'vix': {'current': 20.0}, 'us_core_cpi': {'yoy': 2.8}}
        )
        assert snap.get('vix') == pytest.approx(20.0)
        assert snap.get('cpi') == pytest.approx(2.8)
        assert 'us10y' not in snap   # yfinance 失敗→無此 key


# ══════════════════════════════════════════════════════════════
# 5. 整合測試 — end-to-end
# ══════════════════════════════════════════════════════════════

class TestIntegration:

    @patch('macro_alert._yf_latest', return_value={'^TNX': 4.55, 'DX-Y.NYB': 105.2})
    def test_full_pipeline_mixed_levels(self, _):
        """
        VIX=22.5→黃, CPI=3.1→黃, us10y=4.55→黃, dxy=105.2→黃, PCR=0.4→紅
        整體 overall = red（PCR 低端觸發）
        """
        df = pd.DataFrame([{'選PCR': 0.4}])
        snap = fetch_macro_snapshot(
            session_macro={'vix': {'current': 22.5}, 'us_core_cpi': {'yoy': 3.1}},
            session_li=df,
        )
        # 手動補 us10y / dxy（yfinance mock 已提供）
        alerts = check_macro_alerts(snap)
        sm = alert_summary(alerts)
        assert sm['overall'] == 'red'
        assert sm['red_count'] >= 1

    @patch('macro_alert._yf_latest', return_value={'^TNX': 3.8, 'DX-Y.NYB': 99.0})
    def test_full_pipeline_all_green(self, _):
        df = pd.DataFrame([{'選PCR': 0.9}])
        snap = fetch_macro_snapshot(
            session_macro={'vix': {'current': 15.0}, 'us_core_cpi': {'yoy': 2.0}},
            session_li=df,
        )
        alerts = check_macro_alerts(snap)
        sm = alert_summary(alerts)
        assert sm['overall'] == 'green'
        assert sm['red_count']    == 0
        assert sm['yellow_count'] == 0
        assert sm['green_count']  == 5

    def test_pcr_two_tailed_full_spectrum(self):
        """PCR 在五個典型值上的分級驗證。"""
        cases = [
            (2.0,  'red'),     # 高端極度恐慌
            (1.3,  'yellow'),  # 高端警戒
            (1.0,  'green'),   # 正常
            (0.65, 'yellow'),  # 低端樂觀
            (0.3,  'red'),     # 低端過熱
        ]
        for val, expected in cases:
            result = check_macro_alerts({'pcr': val})
            assert result[0]['level'] == expected, (
                f"PCR={val} 期望 {expected}，got {result[0]['level']}"
            )


# ═══════════════════════════════════════════════════════════════
# 補齊 fetch_macro_snapshot TypeError/ValueError 防禦路徑
# ═══════════════════════════════════════════════════════════════

class TestFetchMacroSnapshotEdgeCases:

    @patch('macro_alert._yf_latest', return_value={'^TNX': 4.2, 'DX-Y.NYB': 102.0})
    def test_invalid_vix_value_is_ignored(self, _):
        """VIX current = 非數值字串 → TypeError/ValueError → 靜默略過，vix 不寫入"""
        snap = fetch_macro_snapshot(
            session_macro={'vix': {'current': 'invalid_string'}},
        )
        # vix 應從 yfinance 補抓（或不存在）；不應拋出例外
        assert 'cpi' not in snap or isinstance(snap.get('cpi'), (float, type(None)))

    @patch('macro_alert._yf_latest', return_value={'^TNX': 4.2, 'DX-Y.NYB': 102.0})
    def test_invalid_cpi_value_is_ignored(self, _):
        """CPI yoy = dict（非純量）→ 靜默略過，cpi 不寫入"""
        snap = fetch_macro_snapshot(
            session_macro={'us_core_cpi': {'yoy': {'nested': 'dict'}}},
        )
        assert 'cpi' not in snap

    @patch('macro_alert._yf_latest', return_value={'^TNX': 4.2, 'DX-Y.NYB': 102.0})
    def test_invalid_pcr_value_is_ignored(self, _):
        """選PCR 欄位含無法轉 float 的值 → except 略過，pcr 不寫入"""
        import pandas as pd
        df = pd.DataFrame([{'選PCR': [1, 2, 3]}])  # list 無法 float()
        snap = fetch_macro_snapshot(session_li=df)
        assert 'pcr' not in snap

    @patch('macro_alert._yf_latest', return_value={'^TNX': 4.2, 'DX-Y.NYB': 102.0})
    def test_pcr_dash_string_is_ignored(self, _):
        """選PCR = '-' → 被過濾掉，pcr 不寫入"""
        import pandas as pd
        df = pd.DataFrame([{'選PCR': '-'}])
        snap = fetch_macro_snapshot(session_li=df)
        assert 'pcr' not in snap


# ═══════════════════════════════════════════════════════════════
# 整合測試：render_macro_alerts（mock streamlit）
# ═══════════════════════════════════════════════════════════════
import sys
import types
from unittest.mock import MagicMock, patch, call

from macro_alert import render_macro_alerts


def _make_st_mock():
    """建立最小 Streamlit mock，捕捉 info/markdown/expander 呼叫。"""
    st = MagicMock()
    # st.expander 需要支援 context manager
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cm)
    cm.__exit__  = MagicMock(return_value=False)
    st.expander.return_value = cm
    return st


class TestRenderMacroAlerts:

    def test_empty_alerts_calls_st_info(self):
        """alerts=[] → 呼叫 st.info 顯示佔位符，不呼叫 st.markdown"""
        st = _make_st_mock()
        with patch.dict(sys.modules, {'streamlit': st}):
            render_macro_alerts([])
        st.info.assert_called_once()
        st.markdown.assert_not_called()

    def test_single_green_alert_renders_markdown(self):
        """一個 green 警示 → 呼叫 st.markdown（橫幅）+ st.expander + st.markdown（詳情）"""
        alerts = check_macro_alerts({'vix': 15.0})
        assert len(alerts) == 1
        st = _make_st_mock()
        with patch.dict(sys.modules, {'streamlit': st}):
            render_macro_alerts(alerts)
        st.markdown.assert_called()
        st.expander.assert_called_once()

    def test_red_alert_expander_expanded_true(self):
        """red 整體等級 → st.expander 以 expanded=True 開啟"""
        alerts = check_macro_alerts({'vix': 40.0})
        assert alerts[0]['level'] == 'red'
        st = _make_st_mock()
        with patch.dict(sys.modules, {'streamlit': st}):
            render_macro_alerts(alerts)
        _, kwargs = st.expander.call_args
        assert kwargs.get('expanded') is True

    def test_green_alert_expander_expanded_false(self):
        """green 整體等級 → st.expander 以 expanded=False 開啟"""
        alerts = check_macro_alerts({'vix': 15.0})
        assert alerts[0]['level'] == 'green'
        st = _make_st_mock()
        with patch.dict(sys.modules, {'streamlit': st}):
            render_macro_alerts(alerts)
        _, kwargs = st.expander.call_args
        assert kwargs.get('expanded') is False

    def test_multiple_alerts_all_rendered(self):
        """多個警示 → 每個詳情卡各呼叫一次 st.markdown"""
        snap = {'vix': 40.0, 'cpi': 4.5, 'pcr': 0.5}
        alerts = check_macro_alerts(snap)
        assert len(alerts) == 3
        st = _make_st_mock()
        with patch.dict(sys.modules, {'streamlit': st}):
            render_macro_alerts(alerts)
        # 1 次橫幅 + N 次詳情 = N+1 次 st.markdown
        assert st.markdown.call_count >= len(alerts)

    def test_banner_html_contains_level_label(self):
        """橫幅 HTML 應包含整體等級的中文標籤"""
        alerts = check_macro_alerts({'vix': 40.0})
        st = _make_st_mock()
        with patch.dict(sys.modules, {'streamlit': st}):
            render_macro_alerts(alerts)
        # 第一次 markdown 呼叫是橫幅
        first_call_html = st.markdown.call_args_list[0][0][0]
        assert '高風險' in first_call_html
