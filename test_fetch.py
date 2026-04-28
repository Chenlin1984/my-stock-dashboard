#!/usr/bin/env python3
"""
test_fetch.py — 先行驗證：FRED CPI + FinMind NDC
在終端機執行：python3 test_fetch.py
目標：印出真實日期與數值
"""
import os, sys, datetime, warnings, requests
warnings.filterwarnings('ignore')
import pandas as pd

_px = os.environ.get('PROXY_URL') or os.environ.get('HTTPS_PROXY') or ''
_tok = os.environ.get('FINMIND_TOKEN', '')

if _px:
    for k in ('HTTPS_PROXY','HTTP_PROXY','https_proxy','http_proxy'):
        os.environ[k] = _px
    print(f'[PROXY] {_px[:40]}')
else:
    print('[PROXY] 無代理')
if _tok:
    print(f'[TOKEN] FINMIND_TOKEN={_tok[:8]}...')
else:
    print('[TOKEN] 無 FINMIND_TOKEN')

print()
print('─' * 50)
print('TEST A: FRED CPIAUCSL (pandas_datareader)')
print('─' * 50)
try:
    import pandas_datareader.data as web
    end = datetime.date.today()
    start = end.replace(year=end.year - 2)
    df = web.DataReader('CPIAUCSL', 'fred', start, end).dropna()
    if len(df) >= 13:
        vals = df['CPIAUCSL'].values
        yoy = round((vals[-1] / vals[-13] - 1) * 100, 2)
        date = str(df.index[-1])[:10]
        print(f'  CPI YoY = {yoy:+.2f}%')
        print(f'  date    = {date}')
        print(f'  rows    = {len(df)}')
        print(f'  status  = {"✅ 近期資料" if date[:4] >= "2025" else "❌ 太舊 " + date}')
    else:
        print(f'  ❌ 資料不足 {len(df)} 筆')
except Exception as e:
    print(f'  ❌ FRED 失敗: {e}')
    # BLS fallback
    print('  嘗試 BLS fallback...')
    try:
        s = requests.Session(); s.verify = False
        r = s.post('https://api.bls.gov/publicAPI/v2/timeseries/data/',
                   json={'seriesid':['CPIAUCSL'],
                         'startyear':str(datetime.date.today().year-1),
                         'endyear':str(datetime.date.today().year)},
                   headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0'},
                   timeout=10)
        j = r.json()
        obs = (j.get('Results') or {}).get('series',[{}])[0].get('data',[])
        valid = sorted([o for o in obs if o.get('period','M13')!='M13'],
                       key=lambda x:(x['year'],x['period']))
        if len(valid) >= 2:
            last = valid[-1]
            date = f"{last['year']}-{int(last['period'][1:]):02d}-01"
            print(f'  BLS date = {date}')
        else:
            print(f'  BLS 資料不足: {len(valid)} 筆')
    except Exception as e2:
        print(f'  BLS 也失敗: {e2}')

print()
print('─' * 50)
print('TEST B: FinMind TaiwanMacroEconomics → 景氣對策信號(分)')
print('─' * 50)
try:
    s = requests.Session(); s.verify = False
    start_n = (datetime.date.today()-datetime.timedelta(days=365*2)).strftime('%Y-%m-%d')
    p = {'dataset':'TaiwanMacroEconomics','start_date':start_n}
    if _tok: p['token'] = _tok
    hdrs = {'Authorization':f'Bearer {_tok}'} if _tok else {}
    r = s.get('https://api.finmindtrade.com/api/v4/data', params=p, headers=hdrs, timeout=15)
    j = r.json()
    print(f'  HTTP status = {r.status_code}')
    print(f'  API status  = {j.get("status")}')
    print(f'  rows        = {len(j.get("data",[]))}')
    if j.get('status')==200 and j.get('data'):
        df = pd.DataFrame(j['data'])
        if 'indicator' in df.columns:
            inds = list(df['indicator'].unique())
            print(f'  indicators  = {inds[:15]}')
            sub = df[df['indicator']=='景氣對策信號(分)'].copy()
            if len(sub)==0:
                print('  ⚠️ 精確比對無結果，嘗試 contains...')
                sub = df[df['indicator'].str.contains('景氣對策信號',na=False)].copy()
            if len(sub)>0:
                sub = sub.sort_values('date').dropna(subset=['value'])
                sub['_v'] = pd.to_numeric(sub['value'], errors='coerce')
                last = sub.dropna(subset=['_v']).iloc[-1]
                score = float(last['_v']); date = str(last['date'])[:10]
                print(f'  score  = {score}')
                print(f'  date   = {date}')
                print(f'  status = {"✅ 近期資料" if date[:4] >= "2025" else "❌ 太舊 " + date}')
            else:
                print('  ❌ 找不到景氣對策信號欄位')
        else:
            print(f'  ❌ 無 indicator 欄位: {list(df.columns)}')
    else:
        print(f'  ❌ API error: {j.get("msg","")}')
except Exception as e:
    print(f'  ❌ FinMind 失敗: {e}')

print()
print('─' * 50)
print('完成')
print('─' * 50)
