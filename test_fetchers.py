#!/usr/bin/env python3
"""
test_fetchers.py — 獨立驗證腳本（v2）
Part A: 離線單元測試（date column + CL extraction 邏輯）
Part B: 線上整合測試（需 Streamlit Cloud / proxy 環境）
目標: Part A 全通過；Part B 印出日期必須是 2025+ 年
"""
import os, sys, datetime, warnings
warnings.filterwarnings('ignore')
import pandas as pd
import numpy as np

PASS, FAIL = '✅', '❌'

# ════════════════════════════════════════════
# Part A: 離線單元測試
# ════════════════════════════════════════════
print('=' * 60)
print('PART A: 離線單元測試（不需網路）')
print('=' * 60)

# A1: 季末 date 欄位計算
print('\n[A1] 季末 date 欄位計算')
_QTR_END = {1: '03-31', 2: '06-30', 3: '09-30', 4: '12-31'}

def make_qtr_date(年度, 季度):
    return f'{int(年度)}-{_QTR_END[int(季度)]}'

test_cases = [
    (2025, 4, '2025-12-31'),
    (2025, 3, '2025-09-30'),
    (2025, 2, '2025-06-30'),
    (2025, 1, '2025-03-31'),
    (2026, 1, '2026-03-31'),
]
all_ok = True
for y, q, expected in test_cases:
    got = make_qtr_date(y, q)
    ok = got == expected
    if not ok: all_ok = False
    print(f'  {PASS if ok else FAIL} {y}Q{q} → {got} (期望:{expected})')

# Simulate get_quarterly_data output with date column
df_sim = pd.DataFrame({'年度': [2025, 2025, 2025, 2025],
                        '季度': [1, 2, 3, 4],
                        '季度標籤': ['2025Q1','2025Q2','2025Q3','2025Q4'],
                        '營收': [100, 110, 120, 130]})
df_sim = df_sim.sort_values(['年度', '季度'])
df_sim['date'] = df_sim['年度'].astype(int).astype(str) + '-' + df_sim['季度'].astype(int).map(_QTR_END)

latest_date = df_sim['date'].iloc[-1]
ok_latest = latest_date == '2025-12-31'
print(f'  {PASS if ok_latest else FAIL} 最新季 date={latest_date} (期望:2025-12-31)')
print(f'  {"✅ A1 通過" if all_ok and ok_latest else "❌ A1 有失敗"}')

# A2: 合約負債 str.contains 提取
print('\n[A2] 合約負債 str.contains 提取')
mock_bs_rows = [
    {'date': '2025-12-31', 'type': '合約負債-流動',    'origin_name': '合約負債─流動',    'value': '1500000'},
    {'date': '2025-12-31', 'type': '合約負債-非流動', 'origin_name': '合約負債─非流動', 'value': '300000'},
    {'date': '2025-12-31', 'type': '應收帳款',          'origin_name': '應收帳款',          'value': '5000000'},
    {'date': '2025-12-31', 'type': '存貨',              'origin_name': '存貨',              'value': '8000000'},
    {'date': '2025-09-30', 'type': '合約負債',          'origin_name': '合約負債',          'value': '1700000'},
    {'date': '2025-09-30', 'type': '應收帳款',          'origin_name': '應收帳款',          'value': '4800000'},
]
bs_df = pd.DataFrame(mock_bs_rows)
bs_df = bs_df.sort_values('date', ascending=False)

def extract_cl(bs_df, date):
    cl_rows = bs_df[(bs_df['date'] == date) & bs_df['type'].str.contains('合約負債', na=False)]
    if len(cl_rows) == 0:
        return float('nan')
    cl_vals = pd.to_numeric(cl_rows['value'].astype(str).str.replace(',', '', regex=False),
                            errors='coerce').abs()
    cl_vals = cl_vals[cl_vals > 0]
    return float(cl_vals.sum()) if len(cl_vals) > 0 else float('nan')

cl_dec = extract_cl(bs_df, '2025-12-31')
cl_sep = extract_cl(bs_df, '2025-09-30')
ok_dec = abs(cl_dec - 1800000) < 1
ok_sep = abs(cl_sep - 1700000) < 1
print(f'  {PASS if ok_dec else FAIL} 2025Q4 CL={cl_dec:,.0f} (期望:1,800,000 = 1500000+300000)')
print(f'  {PASS if ok_sep else FAIL} 2025Q3 CL={cl_sep:,.0f} (期望:1,700,000)')
a2_ok = ok_dec and ok_sep

# Test with fullwidth dash variant
mock_bs2 = [
    {'date': '2025-12-31', 'type': '合約負債－流動',    'origin_name': '',  'value': '2000000'},
    {'date': '2025-12-31', 'type': '合約負債－非流動', 'origin_name': '', 'value': '500000'},
]
bs_df2 = pd.DataFrame(mock_bs2)
cl2 = extract_cl(bs_df2, '2025-12-31')
ok_fw = abs(cl2 - 2500000) < 1
print(f'  {PASS if ok_fw else FAIL} 全形連字符 CL={cl2:,.0f} (期望:2,500,000)')
print(f'  {"✅ A2 通過" if a2_ok and ok_fw else "❌ A2 有失敗"}')

# A3: NDC indicator exact match logic
print('\n[A3] NDC indicator 精確比對邏輯')
mock_ndc_rows = [
    {'date': '2026-01-01', 'indicator': '景氣對策信號(分)', 'value': '28'},
    {'date': '2025-12-01', 'indicator': '景氣對策信號(分)', 'value': '24'},
    {'date': '2026-01-01', 'indicator': '景氣領先指標', 'value': '101.5'},
    {'date': '2026-01-01', 'indicator': '景氣同時指標', 'value': '99.8'},
]
df_ndc = pd.DataFrame(mock_ndc_rows)
# Exact match
sub_exact = df_ndc[df_ndc['indicator'] == '景氣對策信號(分)'].copy()
sub_exact = sub_exact.sort_values('date')
sub_exact['_v'] = pd.to_numeric(sub_exact['value'], errors='coerce')
last = sub_exact.iloc[-1]
ok_ndc = (float(last['_v']) == 28.0 and str(last['date'])[:4] == '2026')
print(f'  {PASS if ok_ndc else FAIL} 精確比對: score={float(last["_v"])} date={last["date"]}')
# Contains fallback (when exact fails)
sub_contains = df_ndc[df_ndc['indicator'].str.contains('景氣對策信號', na=False)].copy()
ok_fb = len(sub_contains) == 2
print(f'  {PASS if ok_fb else FAIL} contains 備援: 找到 {len(sub_contains)} 筆 (期望:2)')
print(f'  {"✅ A3 通過" if ok_ndc and ok_fb else "❌ A3 有失敗"}')

a_total = all_ok and ok_latest and a2_ok and ok_fw and ok_ndc and ok_fb
print(f'\n{"✅ PART A 全部通過" if a_total else "❌ PART A 有失敗，請修復上述邏輯"}')

# ════════════════════════════════════════════
# Part B: 線上整合測試（需 proxy / 網路）
# ════════════════════════════════════════════
print()
print('=' * 60)
print('PART B: 線上整合測試（需 Streamlit Cloud 或 proxy）')
print('=' * 60)

import requests as _rq

# 偵測是否有網路
def _has_net():
    try:
        r = _rq.get('https://api.finmindtrade.com/api/v4/info', timeout=5)
        return r.status_code < 500
    except Exception:
        return False

_net = _has_net()
if not _net:
    print('⚠️ 無網路連線，跳過 Part B（請在 Streamlit Cloud 環境執行）')
else:
    _px = (os.environ.get('PROXY_URL') or os.environ.get('HTTPS_PROXY') or '')
    if _px:
        for _k in ('HTTPS_PROXY','HTTP_PROXY','https_proxy','http_proxy'):
            os.environ[_k] = _px
        print(f'[Proxy] {_px[:40]}...')

    def _mk_s():
        s = _rq.Session()
        s.verify = False
        s.headers.update({'User-Agent': 'Mozilla/5.0'})
        return s

    _tok = os.environ.get('FINMIND_TOKEN', '')

    print('\n[B1] CPI via pandas_datareader FRED')
    try:
        import pandas_datareader.data as web
        end = datetime.date.today()
        df_c = web.DataReader('CPIAUCSL', 'fred', end.replace(year=end.year-3), end).dropna()
        if len(df_c) >= 13:
            vals = df_c['CPIAUCSL'].values
            yoy = round((vals[-1]/vals[-13]-1)*100, 2)
            date_c = str(df_c.index[-1])[:10]
            ok = date_c[:4] >= '2025'
            print(f'  {PASS if ok else FAIL} YoY={yoy:.2f}%  date={date_c}')
        else:
            print(f'  {FAIL} 資料不足: {len(df_c)} 筆')
    except Exception as e:
        print(f'  {FAIL} {e}')

    print('\n[B2] NDC via FinMind TaiwanMacroEconomics')
    try:
        s_n = _mk_s()
        start_n = (datetime.date.today()-datetime.timedelta(days=365*3)).strftime('%Y-%m-%d')
        p_n = {'dataset':'TaiwanMacroEconomics','start_date':start_n}
        if _tok: p_n['token'] = _tok
        j_n = s_n.get('https://api.finmindtrade.com/api/v4/data', params=p_n,
                       headers={'Authorization':f'Bearer {_tok}'} if _tok else {},
                       timeout=15).json()
        print(f'  status={j_n.get("status")} rows={len(j_n.get("data",[]))}')
        if j_n.get('status')==200 and j_n.get('data'):
            df_n = pd.DataFrame(j_n['data'])
            inds = list(df_n['indicator'].unique()) if 'indicator' in df_n.columns else []
            print(f'  Indicators sample: {inds[:10]}')
            sub = df_n[df_n['indicator']=='景氣對策信號(分)'].copy()
            if len(sub)==0:
                sub = df_n[df_n['indicator'].str.contains('景氣對策信號',na=False)].copy()
            if len(sub)>0:
                sub = sub.sort_values('date')
                sub['_v'] = pd.to_numeric(sub['value'], errors='coerce')
                last_n = sub.dropna(subset=['_v']).iloc[-1]
                score = float(last_n['_v']); date_n = str(last_n['date'])[:10]
                ok = date_n[:4] >= '2025' and 9 <= score <= 45
                print(f'  {PASS if ok else FAIL} score={score}  date={date_n}')
            else:
                print(f'  {FAIL} 找不到景氣對策信號')
        else:
            print(f'  {FAIL} {j_n.get("msg","")}')
    except Exception as e:
        print(f'  {FAIL} {e}')

    print('\n[B3] 2330 季報日期')
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from data_loader import StockDataLoader
        loader = StockDataLoader()
        qtr, err = loader.get_quarterly_data('2330')
        if err:
            print(f'  {FAIL} {err}')
        else:
            latest_lbl = qtr['季度標籤'].iloc[-1]
            latest_d   = qtr['date'].iloc[-1] if 'date' in qtr.columns else 'N/A'
            ok = str(latest_d)[:4] >= '2025'
            print(f'  {PASS if ok else FAIL} 最新季={latest_lbl}  date={latest_d}')
    except Exception as e:
        print(f'  {FAIL} {e}')

    print('\n[B4] 2330 合約負債')
    try:
        from data_loader import StockDataLoader
        loader2 = StockDataLoader()
        extra, err2 = loader2.get_quarterly_bs_cf('2330')
        if err2:
            print(f'  {FAIL} {err2}')
        else:
            cl_notna = extra[extra['合約負債'].notna() & (extra['合約負債']>0)]
            if len(cl_notna)>0:
                last_cl = cl_notna.iloc[-1]
                ok = float(last_cl['合約負債']) > 0
                print(f'  {PASS if ok else FAIL} CL={last_cl["合約負債"]:,.0f}  季度={last_cl["季度標籤"]}')
            else:
                print(f'  {FAIL} 合約負債全部 NaN')
    except Exception as e:
        print(f'  {FAIL} {e}')

print()
print('=' * 60)
print('測試完成')
print('=' * 60)
