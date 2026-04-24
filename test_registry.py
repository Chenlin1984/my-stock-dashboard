"""Smoke-test for data_registry freshness logic (mirrors etf_dashboard.py §0)."""
import pandas as pd
from datetime import date, timedelta

TODAY = pd.Timestamp(date.today())

def _freshness(date_str: str, frequency: str = 'daily'):
    try:
        _age = (TODAY - pd.Timestamp(date_str)).days
    except Exception:
        return '⚪', '無法解析'
    if frequency == 'quarterly':
        if _age <= 90:    return '🟢', f'{_age}天前'
        elif _age <= 180: return '🟡', f'{_age}天前'
        else:             return '🔴', f'{_age}天前 ⚠️'
    elif frequency == 'monthly':
        if _age <= 45:    return '🟢', f'{_age}天前'
        elif _age <= 75:  return '🟡', f'{_age}天前'
        else:             return '🔴', f'{_age}天前 ⚠️'
    else:  # daily
        if _age == 0:     return '🟢', '今天'
        elif _age == 1:   return '🟢', '昨天'
        elif _age <= 3:   return '🟢', f'{_age}天前'
        elif _age <= 5:   return '🟡', f'{_age}天前'
        else:             return '🔴', f'{_age}天前 ⚠️'

def _d(days_ago: int) -> str:
    return str((TODAY - pd.Timedelta(days=days_ago)).date())

# ── Mock registry ────────────────────────────────────────────────
MOCK_REGISTRY = {
    '台股大盤':              {'last_updated': _d(1),   'rows': 500, 'category': '大盤', 'frequency': 'daily'},
    '美國標普500':           {'last_updated': _d(2),   'rows': 200, 'category': '大盤', 'frequency': 'daily'},
    '月營收':                {'last_updated': _d(30),  'rows': 1,   'category': '大盤', 'frequency': 'monthly'},
    '季GDP':                 {'last_updated': _d(85),  'rows': 1,   'category': '大盤', 'frequency': 'quarterly'},
    '過期日線':              {'last_updated': _d(10),  'rows': 50,  'category': '大盤', 'frequency': 'daily'},
    '過期季報':              {'last_updated': _d(200), 'rows': 1,   'category': '大盤', 'frequency': 'quarterly'},
    '[個股]2330 | 價格走勢': {'last_updated': _d(0),   'rows': 250, 'category': '個股', 'frequency': 'daily'},
    '[個股]2330 | 月營收':   {'last_updated': _d(40),  'rows': 12,  'category': '個股', 'frequency': 'monthly'},
    '[個股]2330 | 季財報':   {'last_updated': None,    'rows': 0,   'category': '個股', 'frequency': 'quarterly', 'missing': True},
    '[ETF]0050':             {'last_updated': _d(1),   'rows': 300, 'category': 'ETF',  'frequency': 'daily'},
    # Edge: cross-month boundary (day 46 for monthly → stale)
    '跨月臨界':              {'last_updated': _d(46),  'rows': 1,   'category': '大盤', 'frequency': 'monthly'},
    # Edge: cross-year (day 366 for quarterly → stale)
    '跨年季報':              {'last_updated': _d(366), 'rows': 1,   'category': '大盤', 'frequency': 'quarterly'},
}

EXPECTED = {
    '台股大盤':              '🟢',
    '美國標普500':           '🟢',
    '月營收':                '🟢',
    '季GDP':                 '🟢',
    '過期日線':              '🔴',
    '過期季報':              '🔴',
    '[個股]2330 | 價格走勢': '🟢',
    '[個股]2330 | 月營收':   '🟢',
    '[個股]2330 | 季財報':   None,   # missing
    '[ETF]0050':             '🟢',
    '跨月臨界':              '🟡',
    '跨年季報':              '🔴',
}

# ── Run ──────────────────────────────────────────────────────────
FREQ_LBL  = {'daily': '日更新', 'monthly': '月更新', 'quarterly': '季更新'}
CAT_ICON  = {'大盤': '📊', '個股': '🔬', 'ETF': '🏦'}
STATUS_LBL = {'🟢': '🟢 最新', '🟡': '🟡 略舊', '🔴': '🔴 過期'}

rows = []
fail = 0
for name, rv in MOCK_REGISTRY.items():
    cat  = rv.get('category', '未分類')
    freq = rv.get('frequency', 'daily')
    if rv.get('missing'):
        icon, lbl, status = '⚫', '—', '⚫ 缺失'
        ts_str = '—'
    else:
        icon, lbl = _freshness(rv['last_updated'], freq)
        status = STATUS_LBL.get(icon, icon)
        ts_str = f"{rv['last_updated']}（{lbl}）"

    expected = EXPECTED.get(name)
    ok = (expected is None and rv.get('missing')) or (icon == expected)
    if not ok:
        fail += 1
    rows.append({
        '資料名稱':     name,
        '類別':         f'{CAT_ICON.get(cat,"📁")} {cat}',
        '更新頻率':     FREQ_LBL.get(freq, freq),
        '最新資料時間': ts_str,
        '狀態判定':     status,
        '測試': '✅' if ok else f'❌ 期望{expected}',
    })

df = pd.DataFrame(rows)
pd.set_option('display.max_colwidth', 40)
pd.set_option('display.width', 160)
print(df.to_string(index=False))
print()
if fail:
    print(f'FAIL: {fail} case(s) did not match expected status')
    raise SystemExit(1)
else:
    print(f'PASS: all {len(rows)} cases matched')
