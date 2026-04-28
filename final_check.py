#!/usr/bin/env python3
"""
final_check.py — 系統健診終極驗證腳本
印出：CPI最新日期、2330季報最新日期、2330合約負債最新值
用法：python3 final_check.py
環境變數：FINMIND_TOKEN, PROXY_URL（選填）
"""
import os, sys, datetime, warnings, requests
warnings.filterwarnings('ignore')
import pandas as pd

_tok = os.environ.get('FINMIND_TOKEN', '')
_px  = (os.environ.get('PROXY_URL') or
        os.environ.get('HTTPS_PROXY') or
        os.environ.get('HTTP_PROXY') or '')

if _px:
    for k in ('HTTPS_PROXY', 'HTTP_PROXY', 'https_proxy', 'http_proxy'):
        os.environ[k] = _px
    print(f'[PROXY] {_px[:50]}')
else:
    print('[PROXY] 無代理（直連）')

if _tok:
    print(f'[TOKEN] FINMIND_TOKEN={_tok[:8]}...')
else:
    print('[TOKEN] 無 FINMIND_TOKEN（限速模式）')

s = requests.Session()
s.verify = False
_FM_URL = 'https://api.finmindtrade.com/api/v4/data'
_FM_HDR = {'Authorization': f'Bearer {_tok}'} if _tok else {}

print()
print('=' * 55)
print('CHECK 1: CPI 最新日期')
print('=' * 55)
_cpi_ok = False
# 方案1: FRED CSV 直連（純 requests，無需 API Key）
try:
    import io as _io_fc
    _rc = s.get('https://fred.stlouisfed.org/graph/fredgraph.csv',
                params={'id': 'CPIAUCSL'},
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
                timeout=12)
    print(f'  FRED HTTP = {_rc.status_code}')
    if _rc.status_code == 200:
        _df = pd.read_csv(_io_fc.StringIO(_rc.text), parse_dates=['DATE'], index_col='DATE').dropna()
        if len(_df) >= 2:
            _date = str(_df.index[-1])[:10]
            _age  = (datetime.date.today() - datetime.date.fromisoformat(_date)).days
            print(f'  ✅ 來源: FRED CSV（pure requests）')
            print(f'  CPI 最新日期 = {_date}（{_age}天前）')
            print(f'  狀態 = {"🟢 近期" if _age <= 60 else "🔴 過舊"}')
            _cpi_ok = True
        else:
            print(f'  ⚠️  FRED 資料不足: {len(_df)} 筆')
    else:
        print(f'  ⚠️  FRED HTTP {_rc.status_code}')
except Exception as _e:
    print(f'  ❌ FRED CSV 失敗: {type(_e).__name__}: {_e}')

# 方案2: BLS API（FRED 失敗時備援）
if not _cpi_ok:
    try:
        _r = s.post(
            'https://api.bls.gov/publicAPI/v2/timeseries/data/',
            json={'seriesid': ['CPIAUCSL'],
                  'startyear': str(datetime.date.today().year - 1),
                  'endyear':   str(datetime.date.today().year)},
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'},
            timeout=12)
        _j = _r.json()
        _obs = (_j.get('Results') or {}).get('series', [{}])[0].get('data', [])
        _valid = sorted([o for o in _obs if o.get('period', 'M13') != 'M13'],
                        key=lambda x: (x['year'], x['period']))
        if _valid:
            _last = _valid[-1]
            _date = f"{_last['year']}-{int(_last['period'][1:]):02d}-01"
            _age  = (datetime.date.today() - datetime.date.fromisoformat(_date)).days
            print(f'  ✅ 來源: BLS API')
            print(f'  CPI 最新日期 = {_date}（{_age}天前）')
            print(f'  狀態 = {"🟢 近期" if _age <= 60 else "🔴 過舊"}')
            _cpi_ok = True
        else:
            print(f'  ❌ BLS 無有效資料')
    except Exception as _e2:
        print(f'  ❌ BLS 也失敗: {type(_e2).__name__}: {_e2}')

if not _cpi_ok:
    print('  ⛔ CPI 所有方案失敗')

print()
print('=' * 55)
print('CHECK 2: 2330 季報最新日期')
print('=' * 55)
_qtr_ok = False
try:
    _start_q = (datetime.date.today() - datetime.timedelta(days=365 * 2)).strftime('%Y-%m-%d')
    _p = {'dataset': 'TaiwanStockFinancialStatement', 'stock_id': '2330', 'start_date': _start_q}
    if _tok: _p['token'] = _tok
    _r = s.get(_FM_URL, params=_p, headers=_FM_HDR, timeout=15)
    _j = _r.json()
    print(f'  HTTP = {_r.status_code}  API status = {_j.get("status")}  rows = {len(_j.get("data", []))}')
    if _j.get('status') == 200 and _j.get('data'):
        _df = pd.DataFrame(_j['data'])
        if 'date' in _df.columns:
            _date = str(_df['date'].max())[:10]
            _age  = (datetime.date.today() - datetime.date.fromisoformat(_date)).days
            print(f'  ✅ 2330 季報最新日期 = {_date}（{_age}天前）')
            print(f'  狀態 = {"🟢 近期" if _age <= 150 else "🔴 過舊"}')
            _qtr_ok = True
        else:
            print(f'  ⚠️  無 date 欄位，columns={list(_df.columns)[:8]}')
    else:
        print(f'  ❌ API error: {_j.get("msg", "")}')
except Exception as _e:
    print(f'  ❌ 失敗: {type(_e).__name__}: {_e}')

if not _qtr_ok:
    print('  ⛔ 2330 季報取得失敗')

print()
print('=' * 55)
print('CHECK 3: 2330 合約負債最新值')
print('=' * 55)
_cl_ok = False
try:
    _start_bs = (datetime.date.today() - datetime.timedelta(days=365 * 2)).strftime('%Y-%m-%d')
    _p = {'dataset': 'TaiwanStockBalanceSheet', 'stock_id': '2330', 'start_date': _start_bs}
    if _tok: _p['token'] = _tok
    _r = s.get(_FM_URL, params=_p, headers=_FM_HDR, timeout=15)
    _j = _r.json()
    print(f'  HTTP = {_r.status_code}  API status = {_j.get("status")}  rows = {len(_j.get("data", []))}')
    if _j.get('status') == 200 and _j.get('data'):
        _df = pd.DataFrame(_j['data'])
        if {'type', 'value', 'date'}.issubset(_df.columns):
            # str.contains 涵蓋所有合約負債科目變體
            _cl_df = _df[_df['type'].str.contains('合約負債', na=False)].copy()
            if len(_cl_df) > 0:
                _cl_df = _cl_df.sort_values('date', ascending=False)
                _latest_date = _cl_df['date'].max()
                _latest_cl = _cl_df[_cl_df['date'] == _latest_date]
                print(f'  ✅ 合約負債最新季度: {str(_latest_date)[:10]}')
                _total = 0.0
                for _, _row in _latest_cl.iterrows():
                    try:
                        _v = float(str(_row['value']).replace(',', ''))
                        _total += _v
                        print(f'     {_row["type"]}: {_v:,.0f} 千元 = {_v/1e5:.2f} 億')
                    except Exception:
                        print(f'     {_row["type"]}: {_row["value"]}（無法解析）')
                print(f'  合計: {_total:,.0f} 千元 = {_total/1e5:.2f} 億')
                _cl_ok = True
            else:
                print('  ❌ 找不到含「合約負債」的科目')
                _types = list(_df['type'].unique())[:25]
                print(f'  可用 type 樣本: {_types}')
        else:
            print(f'  ⚠️  缺少欄位，columns={list(_df.columns)}')
    else:
        print(f'  ❌ API error: {_j.get("msg", "")}')
except Exception as _e:
    print(f'  ❌ 失敗: {type(_e).__name__}: {_e}')

if not _cl_ok:
    print('  ⛔ 2330 合約負債取得失敗')

print()
print('=' * 55)
print('完成')
print('=' * 55)
