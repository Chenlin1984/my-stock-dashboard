"""
macro_alert.py — 總經數據自動警示模組 v1.0
L3 策略層：監控 VIX / CPI / 10Y 殖利率 / DXY / PCR 等總經指標
閾值觸發時產生三色分級警示（🔴 紅 / 🟡 黃 / 🟢 綠）

Step 1：規則引擎（純函式，零外部依賴）
Step 2：資料擷取 fetch_macro_snapshot()
Step 3：UI 渲染 render_macro_alerts()
"""
from __future__ import annotations

try:
    from config import MACRO_ALERT_RULES
except ImportError:
    MACRO_ALERT_RULES = []   # fallback，允許不依賴 config 獨立測試


# ── Streamlit 快取工具（非 Streamlit 環境自動退化為無快取）──────────
def _safe_cache(**kwargs):
    """
    在 Streamlit 環境回傳 st.cache_data 裝飾器；
    pytest / CLI 環境回傳恆等函式，讓測試不依賴 streamlit。
    """
    try:
        import streamlit as st
        return st.cache_data(**kwargs)
    except Exception:
        return lambda f: f


# ══════════════════════════════════════════════════════════════
# 內部工具函式（無副作用）
# ══════════════════════════════════════════════════════════════

def _classify_level(value: float, rule: dict) -> str:
    """
    依規則判定指標嚴重等級。

    支援雙向閾值：
      - red_above / yellow_above  高值危險（VIX / CPI / 殖利率 / DXY）
      - red_below / yellow_below  低值危險（PCR 過度樂觀端）
    高危門檻優先於黃色門檻，高端門檻優先於低端門檻。

    Returns
    -------
    'red' | 'yellow' | 'green'
    """
    red_above    = rule.get('red_above')
    yellow_above = rule.get('yellow_above')
    red_below    = rule.get('red_below')
    yellow_below = rule.get('yellow_below')

    if red_above is not None and value > red_above:
        return 'red'
    if red_below is not None and value < red_below:
        return 'red'
    if yellow_above is not None and value > yellow_above:
        return 'yellow'
    if yellow_below is not None and value < yellow_below:
        return 'yellow'
    return 'green'


def _format_message(value: float, rule: dict, level: str) -> str:
    """
    組合人可讀的警示說明文字。
    """
    label        = rule['label']
    unit         = rule.get('unit', '')
    val_str      = f"{value:.2f}{unit}"
    red_above    = rule.get('red_above')
    yellow_above = rule.get('yellow_above')
    red_below    = rule.get('red_below')
    yellow_below = rule.get('yellow_below')

    if level == 'red':
        if red_above is not None and value > red_above:
            return (f"{label} {val_str} 突破警戒上限（> {red_above}{unit}），"
                    f"高風險，建議降低部位")
        if red_below is not None and value < red_below:
            return (f"{label} {val_str} 跌破警戒下限（< {red_below}{unit}），"
                    f"市場過度樂觀，注意反轉風險")
    elif level == 'yellow':
        if yellow_above is not None and value > yellow_above:
            return (f"{label} {val_str} 進入觀察區（> {yellow_above}{unit}），"
                    f"謹慎持倉")
        if yellow_below is not None and value < yellow_below:
            return (f"{label} {val_str} 偏低（< {yellow_below}{unit}），"
                    f"情緒偏樂觀，持續觀察")
    else:
        return f"{label} {val_str} 位於正常區間"

    return f"{label} {val_str}"   # 防禦性 fallback


# ══════════════════════════════════════════════════════════════
# 公開 API — Step 1 純函式
# ══════════════════════════════════════════════════════════════

def check_macro_alerts(snapshot: dict) -> list[dict]:
    """
    總經指標閾值警示引擎（純函式）。

    Parameters
    ----------
    snapshot : dict
        各指標當前值，key 對應 MACRO_ALERT_RULES 中的 'key' 欄位。
        例：
            {
                'vix':   28.3,
                'cpi':   3.1,
                'us10y': 4.5,
                'dxy':   104.2,
                'pcr':   1.1,
            }
        值為 None 或 key 缺失代表資料不可用，略過該指標（不納入輸出）。

    Returns
    -------
    list[dict]
        每個有效指標對應一筆 alert dict（含 green 狀態，讓 UI 可顯示完整看板）：
        {
            'key'    : str   — 指標識別符（例 'vix'）
            'label'  : str   — 顯示名稱（例 'VIX 恐慌指數'）
            'unit'   : str   — 單位（'%' 或 ''）
            'value'  : float — 當前數值
            'level'  : str   — 'red' | 'yellow' | 'green'
            'emoji'  : str   — '🔴' | '🟡' | '🟢'
            'message': str   — 完整警示說明（供 UI tooltip 或展開詳情使用）
        }
    """
    _EMOJI = {'red': '🔴', 'yellow': '🟡', 'green': '🟢'}
    alerts: list[dict] = []

    for rule in MACRO_ALERT_RULES:
        key = rule['key']
        raw = snapshot.get(key)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue

        level = _classify_level(value, rule)
        alerts.append({
            'key':     key,
            'label':   rule['label'],
            'unit':    rule.get('unit', ''),
            'value':   value,
            'level':   level,
            'emoji':   _EMOJI[level],
            'message': _format_message(value, rule, level),
        })

    return alerts


def alert_summary(alerts: list[dict]) -> dict:
    """
    彙總警示清單，計算紅/黃/綠數量與整體最高風險等級。

    Parameters
    ----------
    alerts : list[dict]
        check_macro_alerts() 的回傳值。

    Returns
    -------
    dict
        {
            'red_count'     : int,
            'yellow_count'  : int,
            'green_count'   : int,
            'total'         : int,
            'overall'       : 'red' | 'yellow' | 'green',
            'overall_emoji' : str,
        }
    """
    _EMOJI = {'red': '🔴', 'yellow': '🟡', 'green': '🟢'}
    red    = sum(1 for a in alerts if a['level'] == 'red')
    yellow = sum(1 for a in alerts if a['level'] == 'yellow')
    green  = sum(1 for a in alerts if a['level'] == 'green')
    overall = 'red' if red > 0 else ('yellow' if yellow > 0 else 'green')
    return {
        'red_count':    red,
        'yellow_count': yellow,
        'green_count':  green,
        'total':        red + yellow + green,
        'overall':      overall,
        'overall_emoji': _EMOJI[overall],
    }


# ══════════════════════════════════════════════════════════════
# Step 2 — 資料擷取適配器
# ══════════════════════════════════════════════════════════════

@_safe_cache(ttl=1800, show_spinner=False)
def _yf_latest(tickers: tuple) -> dict:
    """
    從 yfinance 抓指定 tickers 的最新收盤價（快取 30 分鐘）。

    Parameters
    ----------
    tickers : tuple of str
        Yahoo Finance 代碼，使用 tuple 以支援 st.cache_data 雜湊。
        例：('^TNX', 'DX-Y.NYB', '^VIX')

    Returns
    -------
    dict  { ticker: float | None }
        取不到資料的 ticker 值為 None。
    """
    import yfinance as yf
    result: dict = {}
    for t in tickers:
        try:
            hist = yf.Ticker(t).history(period='5d')
            result[t] = round(float(hist['Close'].iloc[-1]), 4) if not hist.empty else None
        except Exception as e:
            print(f'[MacroAlert/yf] {t} 失敗: {e}')
            result[t] = None
    return result


def fetch_macro_snapshot(
    session_macro: dict | None = None,
    session_li=None,
    session_m1b2: dict | None = None,
) -> dict:
    """
    整合 session_state 快取資料與 yfinance，組建各指標當前快照。

    優先順序：session_state 已計算值 > yfinance 即時抓取
    （避免重複呼叫 API；僅補抓 session_state 尚未涵蓋的 us10y / dxy）

    Parameters
    ----------
    session_macro : dict | None
        st.session_state.get('macro_info')
        含 vix={'current': float, ...} 與 us_core_cpi={'yoy': float}
    session_li : pd.DataFrame | None
        st.session_state.get('li_latest')
        含 '選PCR' 欄位（台指選擇權 Put/Call Ratio）
    session_m1b2 : dict | None
        st.session_state.get('m1b_m2_info')
        含 m1b_yoy / m2_yoy（保留供未來擴充，當前不映射至 snapshot）

    Returns
    -------
    dict
        {
            'vix'  : float | None  — VIX 恐慌指數
            'cpi'  : float | None  — US Core CPI YoY (%)
            'us10y': float | None  — 美債 10Y 殖利率 (%)
            'dxy'  : float | None  — 美元指數
            'pcr'  : float | None  — 台指選擇權 Put/Call Ratio
        }
        值為 None 代表該指標資料不可用（不影響其他指標的警示計算）。
    """
    snap: dict = {}

    # ── ① VIX：優先讀 session_state['macro_info']['vix']['current'] ──
    _vix_ss = (session_macro or {}).get('vix') or {}
    if _vix_ss.get('current') is not None:
        try:
            snap['vix'] = float(_vix_ss['current'])
        except (TypeError, ValueError):
            pass

    # ── ② CPI YoY：session_state['macro_info']['us_core_cpi']['yoy'] ──
    _cpi_ss = (session_macro or {}).get('us_core_cpi') or {}
    if _cpi_ss.get('yoy') is not None:
        try:
            snap['cpi'] = float(_cpi_ss['yoy'])
        except (TypeError, ValueError):
            pass

    # ── ③ PCR：session_state['li_latest'].iloc[-1]['選PCR'] ──────────
    if session_li is not None:
        try:
            if not session_li.empty and '選PCR' in session_li.columns:
                _pcr_raw = session_li.iloc[-1].get('選PCR')
                if _pcr_raw is not None and str(_pcr_raw) not in ('', 'nan', '-'):
                    snap['pcr'] = float(_pcr_raw)
        except Exception:
            pass

    # ── ④ yfinance：us10y / dxy 必抓；vix 若 ①未命中則補抓 ──────────
    _need_yf: list[str] = ['^TNX', 'DX-Y.NYB']
    if 'vix' not in snap:
        _need_yf.append('^VIX')

    try:
        _yf_data = _yf_latest(tuple(_need_yf))
        if _yf_data.get('^TNX') is not None:
            snap['us10y'] = _yf_data['^TNX']
        if _yf_data.get('DX-Y.NYB') is not None:
            snap['dxy'] = _yf_data['DX-Y.NYB']
        if 'vix' not in snap and _yf_data.get('^VIX') is not None:
            snap['vix'] = _yf_data['^VIX']
    except Exception as e:
        print(f'[MacroAlert] yfinance 批次抓取失敗: {e}')

    return snap


# ══════════════════════════════════════════════════════════════
# Step 3 — UI 渲染元件（純資料驅動，不自行抓取資料）
# ══════════════════════════════════════════════════════════════

# 三色對應：背景色、文字色、邊框色
_LEVEL_STYLE: dict[str, dict] = {
    'red':    {'bg': '#2d1b1b', 'text': '#f85149', 'border': '#f85149', 'badge_bg': '#3d1f1f'},
    'yellow': {'bg': '#2d2208', 'text': '#d29922', 'border': '#d29922', 'badge_bg': '#3a2c0a'},
    'green':  {'bg': '#0d2318', 'text': '#3fb950', 'border': '#3fb950', 'badge_bg': '#142d1e'},
}


def render_macro_alerts(alerts: list[dict]) -> None:
    """
    渲染總經數據三色警示看板（純資料驅動）。

    版面分兩區：
    1. **警示橫幅**：顯示整體風險等級 + 各指標 badge（一行 pill 條）
    2. **展開詳情**：st.expander，以表格列出各指標當前值與警示說明

    Parameters
    ----------
    alerts : list[dict]
        check_macro_alerts() 的回傳值。空清單時顯示「資料載入中」佔位符。

    Returns
    -------
    None  （直接渲染至 Streamlit，無回傳值）
    """
    import streamlit as st

    # ── 資料不可用時的佔位符 ─────────────────────────────────────
    if not alerts:
        st.info('⏳ 總經警示資料載入中，請點擊「🔄 更新全部總經數據」', icon='📡')
        return

    sm = alert_summary(alerts)
    overall = sm['overall']
    _os = _LEVEL_STYLE[overall]

    # ── ① 警示橫幅 ───────────────────────────────────────────────
    # 各指標 badge（pill 形式）
    _badge_parts: list[str] = []
    for a in alerts:
        _s     = _LEVEL_STYLE[a['level']]
        _unit  = a.get('unit', '')
        _val   = f"{a['value']:.2f}{_unit}"
        _badge_parts.append(
            f'<span style="'
            f'background:{_s["badge_bg"]};'
            f'border:1px solid {_s["border"]};'
            f'border-radius:20px;'
            f'padding:3px 10px;'
            f'font-size:12px;'
            f'color:{_s["text"]};'
            f'white-space:nowrap;'
            f'margin-right:4px;'
            f'">'
            f'{a["emoji"]} {a["label"]} <b>{_val}</b>'
            f'</span>'
        )
    _badges_html = ''.join(_badge_parts)

    # 整體狀態標籤
    _overall_labels = {
        'red':    '⚠️ 高風險 — 建議降低部位',
        'yellow': '⚡ 觀察中 — 謹慎持倉',
        'green':  '✅ 正常 — 總經環境無異常',
    }
    _overall_counts = (
        f'<span style="font-size:11px;color:#8b949e;margin-left:8px;">'
        f'🔴×{sm["red_count"]} &nbsp;🟡×{sm["yellow_count"]} &nbsp;🟢×{sm["green_count"]}'
        f'</span>'
    )

    st.markdown(
        f'<div style="'
        f'background:{_os["bg"]};'
        f'border-left:4px solid {_os["border"]};'
        f'border-radius:0 8px 8px 0;'
        f'padding:10px 16px;'
        f'margin-bottom:6px;'
        f'">'
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        f'<span style="font-size:14px;font-weight:700;color:{_os["text"]};">'
        f'{_overall_labels[overall]}</span>'
        f'{_overall_counts}'
        f'</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:4px;">'
        f'{_badges_html}'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── ② 展開詳情 ──────────────────────────────────────────────
    _red_alerts    = [a for a in alerts if a['level'] == 'red']
    _yellow_alerts = [a for a in alerts if a['level'] == 'yellow']
    _green_alerts  = [a for a in alerts if a['level'] == 'green']

    _expander_label = (
        f'🔍 總經警示詳情（'
        + (f'🔴×{sm["red_count"]} ' if sm['red_count'] else '')
        + (f'🟡×{sm["yellow_count"]} ' if sm['yellow_count'] else '')
        + f'🟢×{sm["green_count"]}）'
    )
    with st.expander(_expander_label, expanded=(overall == 'red')):
        _all_ordered = _red_alerts + _yellow_alerts + _green_alerts
        for a in _all_ordered:
            _s    = _LEVEL_STYLE[a['level']]
            _unit = a.get('unit', '')
            _val  = f"{a['value']:.2f}{_unit}"
            st.markdown(
                f'<div style="'
                f'background:{_s["badge_bg"]};'
                f'border-radius:6px;'
                f'padding:8px 14px;'
                f'margin-bottom:6px;'
                f'border-left:3px solid {_s["border"]};'
                f'">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<span style="font-size:13px;font-weight:600;color:{_s["text"]};">'
                f'{a["emoji"]} {a["label"]}</span>'
                f'<span style="font-size:15px;font-weight:700;color:{_s["text"]};">'
                f'{_val}</span>'
                f'</div>'
                f'<div style="font-size:12px;color:#8b949e;margin-top:3px;">'
                f'{a["message"]}'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
