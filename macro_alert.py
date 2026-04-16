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
