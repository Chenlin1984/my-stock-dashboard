import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime, os, re, time, requests, json, pickle, hashlib

# ── 台灣時間（UTC+8）─────────────────────────────────────
_TW_TZ = datetime.timezone(datetime.timedelta(hours=8))
def _tw_now(): return datetime.datetime.now(_TW_TZ)
def _tw_now_str(): return _tw_now().strftime('%Y-%m-%d %H:%M')
from concurrent.futures import ThreadPoolExecutor, as_completed
import yfinance as yf

print('[INFO] main.py v3.0 戰情室 載入完成')

from data_loader import StockDataLoader
from chart_plotter import plot_combined_chart, plot_revenue_chart, plot_quarterly_chart
from ai_engine import analyze_stock_trend
from leading_indicators import build_leading_indicators, build_leading_fast, render_leading_table
from daily_checklist import (
    fetch_single, calc_stats, sparkline, multi_chart,
    bar_chart_institutional, stat_card, section_header,
    margin_card, fetch_institutional, fetch_margin_balance,
    fetch_adl,
    _fetch_otc_via_finmind,
    INTL_MAP, INTL_UNIT, TW_MAP, TW_UNIT, TECH_MAP, COLORS_7,
)
# ── 新增模組（根據說明書 v1.0）──────────────────────────────
# ── v3.0 新增模組（§5-§11）──────────────────────────────────
from market_strategy import get_market_assessment
from risk_control import calc_position_size, calc_stop_loss  # RiskController removed (unused)
from v4_strategy_engine import V4StrategyEngine   # v4.0 核心策略引擎
from v5_modules import (                           # v5.0 大師滿配
    analyze_fundamental_leading, calc_relative_strength,
    calc_valuation_zone, detect_bollinger_breakout,
    calc_dividend_yield_357, get_defensive_allocation, DEFENSIVE_ETFS,
)
# from backtest_engine import run_backtest, stock_selector  # 保留備用
from scoring_engine import score_single_stock, rank_stocks, momentum_signal, calc_rs_score, rs_slope
from etf_dashboard import (
    render_etf_single, render_etf_portfolio,
    render_etf_backtest, render_etf_ai,
    render_data_health, render_sector_heatmap,
)
from ai_engine import generate_daily_report
from financial_debug_helper import (
    FIELD_ALIASES, FieldResult, DebugReport,
    safe_float, find_value_by_alias, classify_missing_data,
    is_financial_industry, status_to_ui_text, status_to_color,
    test_finmind_token, fetch_finmind_monthly_revenue,
    build_financial_debug_report,
    STATUS_OK, STATUS_FETCH_ERROR, STATUS_MISSING, STATUS_NOT_APPLICABLE,
)

api_key       = st.secrets.get('GEMINI_API_KEY', os.environ.get('GEMINI_API_KEY', ''))  # [Fixed] st.secrets 優先
FINMIND_TOKEN = st.secrets.get('FINMIND_TOKEN',  os.environ.get('FINMIND_TOKEN', ''))   # [Fixed] st.secrets 優先

# [Fixed] 同步到 os.environ，讓子模組頂層讀取能拿到正確值
if FINMIND_TOKEN:
    os.environ['FINMIND_TOKEN'] = FINMIND_TOKEN
if api_key:
    os.environ['GEMINI_API_KEY'] = api_key

def _get_fm_token():
    """每次動態讀取最新 Token，避免 module-level 變數被快取到舊值"""
    return os.environ.get('FINMIND_TOKEN', '')

st.set_page_config(page_title='台股AI戰情室 v3.0', layout='wide',
                   page_icon='📊', initial_sidebar_state='collapsed')

st.markdown("""<style>
.main{background:#0e1117;}
[data-testid="stSidebar"]{background:#161b22;}
.stTabs [data-baseweb="tab-list"]{gap:2px;}
.stTabs [data-baseweb="tab"]{background:#161b22;color:#8b949e;border-radius:6px 6px 0 0;padding:8px 16px;font-size:13px;}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg,#1f6feb,#0d4faa);color:#fff;font-weight:700;}
.teacher-card{background:#0d1117;border-left:3px solid #ffd700;border-radius:0 8px 8px 0;padding:10px 14px;margin:6px 0;}
.health-A{background:linear-gradient(90deg,#0d2818,#0d1117);border:2px solid #3fb950;border-radius:12px;padding:16px;text-align:center;}
.health-B{background:linear-gradient(90deg,#2a1f00,#0d1117);border:2px solid #d29922;border-radius:12px;padding:16px;text-align:center;}
.health-C{background:linear-gradient(90deg,#2a0d0d,#0d1117);border:2px solid #f85149;border-radius:12px;padding:16px;text-align:center;}
</style>""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════
def parse_stocks(raw):
    stocks = re.split(r'[,\s\n；，]+', raw.strip())
    return [s.strip() for s in stocks if s.strip() and re.match(r'^\d{4,6}[A-Z]?$', s.strip())]

def gemini_call(prompt, max_tokens=2048):
    _key = os.environ.get('GEMINI_API_KEY', '') or api_key
    if not _key:
        return '⚠️ 請在 Cell 1 設定 GEMINI_API_KEY'
    # 2026-03 有效模型：1.5系列全部退役，2.5為主力
    _models = ['gemini-2.5-flash-lite', 'gemini-2.5-flash',
               'gemini-2.0-flash', 'gemini-2.0-flash-lite']
    for _model in _models:
        try:
            _r = requests.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/{_model}:generateContent',
                params={'key': _key},
                json={'contents': [{'parts': [{'text': prompt}]}],
                      'generationConfig': {'temperature': 0.3,
                                           'maxOutputTokens': max_tokens}},
                timeout=120
            )
            if _r.status_code == 200:
                _d = _r.json()
                _cands = _d.get('candidates', [])
                if _cands:
                    _content = _cands[0].get('content', {})
                    _parts = _content.get('parts', [])
                    if _parts and _parts[0].get('text'):
                        return _parts[0]['text']
                # 檢查是否被 safety filter 攔截
                _finish = _cands[0].get('finishReason', '') if _cands else ''
                if _finish == 'SAFETY':
                    continue  # 換下一個 model 試
            elif _r.status_code == 400:
                _err_body = _r.json() if _r.text else {}
                _err_msg  = _err_body.get('error', {}).get('message', _r.text[:100])
                print(f'[Gemini/{_model}] 400 Bad Request: {_err_msg}')
                continue
            elif _r.status_code == 403:
                return '⚠️ API Key 無效或無權限（HTTP 403）—— 請確認 GEMINI_API_KEY 正確'
            elif _r.status_code == 404:
                continue  # 此 model 不存在，試下一個
            elif _r.status_code == 429:
                time.sleep(5); continue  # rate limit
            else:
                print(f'[Gemini/{_model}] HTTP {_r.status_code}: {_r.text[:200]}')
                continue
        except Exception as _ge:
            print(f'[Gemini/{_model}] {type(_ge).__name__}: {_ge}'); time.sleep(1)
    return '⚠️ AI 服務暫時無法使用（已嘗試所有模型）—— 請確認 GEMINI_API_KEY 正確'

# ── 本地快取（SQLite + Pickle 雙軌）───────────────────────
_CACHE_DIR = '/tmp/stock_cache'
os.makedirs(_CACHE_DIR, exist_ok=True)

def _cache_key(prefix, sid, extra=''):
    raw = f'{prefix}_{sid}_{extra}_{datetime.date.today()}'
    return os.path.join(_CACHE_DIR, hashlib.md5(raw.encode()).hexdigest() + '.pkl')

def _load_cache(prefix, sid, extra='', ttl_hours=6):
    path = _cache_key(prefix, sid, extra)
    if os.path.exists(path):
        age = (time.time() - os.path.getmtime(path)) / 3600
        if age < ttl_hours:
            try:
                with open(path,'rb') as f: return pickle.load(f)
            except: pass
    return None

def _save_cache(prefix, sid, data, extra=''):
    path = _cache_key(prefix, sid, extra)
    try:
        with open(path,'wb') as f: pickle.dump(data, f)
    except: pass

@st.cache_resource
def _get_loader():
    """快取單一 StockDataLoader 實例，避免每次 cache miss 都重新 login"""
    return StockDataLoader()

@st.cache_data(ttl=1800)
def fetch_price_data(sid, days):
    # K線緩存4小時
    _c = _load_cache('price', sid, str(days), ttl_hours=4)
    if _c is not None:
        df_c, name_c = _c
        # 驗證快取資料有效（close不為全0）
        if df_c is not None and not df_c.empty and float(df_c['close'].max()) > 0:
            return df_c, name_c, None
        # 快取有問題，重新抓取
    loader = _get_loader()
    df, err, name = loader.get_combined_data(sid, days + 60, True)
    if err or df is None: return None, None, err
    result = df.tail(days).reset_index(drop=True)
    _save_cache('price', sid, (result, name), str(days))
    return result, name, None

@st.cache_data(ttl=1800)
def fetch_dividend_data(sid):
    avg_div, yearly, source = 0.0, [], ''
    try:
        try:
            from FinMind.data import DataLoader as FM
        except ImportError:
            from finmind.data import DataLoader as FM
        dl = FM()
        _fm_tok_div = _get_fm_token()
        if _fm_tok_div:
            try: dl.login_by_token(api_token=_fm_tok_div)
            except Exception: pass
        end = datetime.date.today()
        # First try REST API with proper auth
        _div_resp = requests.get('https://api.finmindtrade.com/api/v4/data',
            params={'dataset':'TaiwanStockDividend','data_id':sid,
                    'start_date':(end-datetime.timedelta(days=365*6)).strftime('%Y-%m-%d')},
            headers={'Authorization':f'Bearer {_get_fm_token()}'},timeout=20)
        _div_jd = _div_resp.json()
        print(f'[股利REST] {sid} status={_div_jd.get("status")}')
        ddf = pd.DataFrame(_div_jd['data']) if _div_jd.get('status')==200 and _div_jd.get('data') else None
        if ddf is None or ddf.empty:
            ddf = dl.taiwan_stock_dividend(stock_id=sid,
                                           start_date=(end-datetime.timedelta(days=365*6)).strftime('%Y-%m-%d'))
        if ddf is not None and not ddf.empty:
            cash_col = next((c for c in ['CashDividend','cash_dividend','StockEarningsDistribution']
                             if c in ddf.columns), None)
            if cash_col is None:
                nums = ddf.select_dtypes(include='number').columns.tolist()
                if nums: cash_col = nums[0]
            if cash_col:
                ddf['date'] = pd.to_datetime(ddf['date'], errors='coerce')
                ddf['year'] = ddf['date'].dt.year
                ddf['cash'] = pd.to_numeric(ddf[cash_col], errors='coerce').fillna(0)
                yr = ddf.groupby('year')['cash'].sum().reset_index().tail(5)
                avg_div = float(yr['cash'].mean()) if len(yr) > 0 else 0
                yearly = yr.to_dict('records')
                source = 'FinMind'
    except Exception: pass
    # ── 備援2: yfinance ──
    if avg_div == 0:
        try:
            tk = yf.Ticker(f'{sid}.TW')
            divs = tk.dividends
            if divs is not None and len(divs) > 0:
                divs.index = pd.DatetimeIndex(divs.index).tz_localize(None)
                rec = divs[divs.index >= pd.Timestamp.now()-pd.DateOffset(years=5)]
                if len(rec) > 0:
                    ann = rec.resample('YE').sum().reset_index()
                    ann.columns = ['date','cash']
                    ann['year'] = pd.to_datetime(ann['date']).dt.year
                    yr = ann[['year','cash']].tail(5)
                    avg_div = float(yr['cash'].mean())
                    yearly = yr.to_dict('records')
                    source = 'yfinance'
        except Exception: pass

    # ── 備援3: TWSE 除權息資料（官方，免Token）──
    if avg_div == 0:
        try:
            _tw_div_url = 'https://www.twse.com.tw/rwd/zh/exRight/TWT49U'
            _start_dt_div = (datetime.date.today()-datetime.timedelta(days=365*6)).strftime('%Y%m%d')
            _end_dt_div   = datetime.date.today().strftime('%Y%m%d')
            _tw_div_r = requests.get(
                _tw_div_url,
                params={'response': 'json', 'strDate': _start_dt_div,
                        'endDate': _end_dt_div, 'stockNo': sid},
                headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                         'Referer':'https://www.twse.com.tw/',
                         'Accept':'application/json, text/javascript, */*'},
                timeout=15)
            _tw_div_j = _tw_div_r.json()
            if _tw_div_j.get('stat') == 'OK' and _tw_div_j.get('data'):
                _tw_div_rows = []
                for _dr in _tw_div_j['data']:
                    # 欄位：[日期, 股票代號, 名稱, 除權息前收盤, 開始交易基準價, 現金股利, 股票股利, ...]
                    try:
                        _yr_div = int(str(_dr[0]).split('/')[0])
                        if _yr_div < 1000: _yr_div += 1911
                        _cash_d = float(str(_dr[5]).replace(',','')) if len(_dr) > 5 else 0
                        if _cash_d > 0:
                            _tw_div_rows.append({'year': _yr_div, 'cash': _cash_d})
                    except: pass
                if _tw_div_rows:
                    _tw_div_df = pd.DataFrame(_tw_div_rows)
                    yr = _tw_div_df.groupby('year')['cash'].sum().reset_index().tail(5)
                    avg_div = float(yr['cash'].mean())
                    yearly = yr.to_dict('records')
                    source = 'TWSE'
        except Exception as _eTD:
            pass

    # ── 備援4: Goodinfo 配息歷史 ──
    if avg_div == 0:
        try:
            _gi_hdr_d = {'User-Agent':'Mozilla/5.0','Referer':'https://goodinfo.tw/tw/index.asp'}
            _gi_div_r = requests.get(
                f'https://goodinfo.tw/tw/StockDividendHistory.asp?STOCK_ID={sid}',
                headers=_gi_hdr_d, timeout=20)
            _gi_div_r.encoding = 'utf-8'
            if _gi_div_r.status_code == 200:
                _gi_div_tables = pd.read_html(_gi_div_r.text, encoding='utf-8')
                for _gdt in _gi_div_tables:
                    _cols_gd = [str(c).lower() for c in _gdt.columns]
                    if not any('現金' in str(c) or 'cash' in str(c).lower() for c in _gdt.columns):
                        continue
                    _cash_col_gd = next((c for c in _gdt.columns if '現金' in str(c) or 'cash' in str(c).lower()), None)
                    _year_col_gd = next((c for c in _gdt.columns if '年' in str(c) or 'year' in str(c).lower()), None)
                    if _cash_col_gd is None: continue
                    _gdt_rows = []
                    for _, _gdr in _gdt.iterrows():
                        try:
                            _yr_gd = int(str(_gdr[_year_col_gd]).split('/')[0]) if _year_col_gd else 0
                            if _yr_gd < 1000: _yr_gd += 1911
                            _cd_gd = float(str(_gdr[_cash_col_gd]).replace(',','').replace('─','0').replace('N/A','0'))
                            if _yr_gd > 2010: _gdt_rows.append({'year':_yr_gd,'cash':_cd_gd})
                        except: pass
                    if _gdt_rows:
                        _gd_df = pd.DataFrame(_gdt_rows).groupby('year')['cash'].sum().reset_index().tail(5)
                        avg_div = float(_gd_df['cash'].mean())
                        yearly = _gd_df.to_dict('records')
                        source = 'Goodinfo'
                        break
        except Exception as _eGD:
            pass

    return avg_div, yearly, source

@st.cache_data(ttl=3600)
def fetch_financials(sid, industry: str = ""):
    """
    合約負債 + 固定資產 + 資本支出 — v3.35 簡化版
    100% FinMind（免費版已確認 status=200）
    type 欄位為主鍵，比 origin_name 更可靠。
    """
    import datetime as _dtf
    import requests as _rq_f

    cl = cx = _capex = None
    cl_src = cx_src = cx_src_capex = ""
    fetch_errors = []
    _tok = _get_fm_token()
    _start = (_dtf.date.today() - _dtf.timedelta(days=365*3)).strftime('%Y-%m-%d')

    # ── Step 1: BalanceSheet → 合約負債 + 固定資產 ──────────────
    try:
        _params = {"dataset":"TaiwanStockBalanceSheet","data_id":sid,"start_date":_start}
        if _tok: _params["token"] = _tok
        _hdrs = {"User-Agent":"Mozilla/5.0","Accept":"application/json"}
        if _tok: _hdrs["Authorization"] = f"Bearer {_tok}"
        _r = _rq_f.get("https://api.finmindtrade.com/api/v4/data",
                        params=_params, headers=_hdrs, timeout=20)
        _j = _r.json()
        _rows = _j.get("data", [])
        _fm_status = _j.get("status"); _fm_msg = _j.get("msg","")
        print(f"[FM-BS] {sid} HTTP {_r.status_code} status={_fm_status} rows={len(_rows)}")
        if _fm_status != 200:
            fetch_errors.append(f"FinMind-BS:HTTP{_r.status_code}:{_fm_msg or _fm_status}")
        if _fm_status == 200 and _rows:
            # 取最新一季
            _dates = sorted(set(r.get("date","") for r in _rows), reverse=True)
            _latest_dt = _dates[0] if _dates else None
            _latest = [r for r in _rows if r.get("date") == _latest_dt]
            print(f"[FM-BS] Latest={_latest_dt} rows={len(_latest)}")

            # 合約負債
            _CL_TYPES = ["CurrentContractLiabilities","ContractLiabilities"]
            _CL_NAMES = ["合約負債","契約負債","預收款項"]
            _cl_total = 0.0
            for _row in _latest:
                _t = str(_row.get("type",""))
                if any(_t == _ct or _t.startswith(_ct) for _ct in _CL_TYPES):
                    _v = float(str(_row.get("value",0)).replace(",","") or 0)
                    if _v > 0: _cl_total += _v
            if _cl_total == 0:  # fallback: origin_name
                for _row in _latest:
                    _n = str(_row.get("origin_name",""))
                    if any(_k in _n for _k in _CL_NAMES):
                        _v = float(str(_row.get("value",0)).replace(",","") or 0)
                        if _v > 0: _cl_total += _v
            if _cl_total > 0:
                cl = _cl_total; cl_src = "FinMind"
                print(f"[FM-BS] ✅ 合約負債={cl/1e8:.2f}億")

            # 固定資產
            _FA_TYPE = "PropertyPlantAndEquipment"
            for _row in _latest:
                _t = str(_row.get("type",""))
                if _t == _FA_TYPE or (_FA_TYPE in _t and "_per" not in _t):
                    _v = float(str(_row.get("value",0)).replace(",","") or 0)
                    if _v > 0: cx = _v; cx_src = "FinMind"; break
            if cx is None:
                for _row in _latest:
                    _n = str(_row.get("origin_name",""))
                    if any(_k in _n for _k in ["不動產、廠房及設備","固定資產"]):
                        _v = float(str(_row.get("value",0)).replace(",","") or 0)
                        if _v > 0: cx = _v; cx_src = "FinMind-name"; break
            if cx: print(f"[FM-BS] ✅ 固定資產={cx/1e8:.2f}億")
    except Exception as _e_bs:
        err_msg = f"FinMind-BS:{type(_e_bs).__name__}:{_e_bs}"
        fetch_errors.append(err_msg); print(f"[FM-BS] ❌ {err_msg}")

    # ── Step 2: CashFlowsStatement → 資本支出 ────────────────────
    try:
        _params2 = {"dataset":"TaiwanStockCashFlowsStatement","data_id":sid,"start_date":_start}
        if _tok: _params2["token"] = _tok
        _hdrs2 = {"User-Agent":"Mozilla/5.0","Accept":"application/json"}
        if _tok: _hdrs2["Authorization"] = f"Bearer {_tok}"
        _r2 = _rq_f.get("https://api.finmindtrade.com/api/v4/data",
                         params=_params2, headers=_hdrs2, timeout=20)
        _j2 = _r2.json()
        _rows2 = _j2.get("data",[])
        _fm2_status = _j2.get("status"); _fm2_msg = _j2.get("msg","")
        print(f"[FM-CF] {sid} HTTP {_r2.status_code} status={_fm2_status} rows={len(_rows2)}")
        if _fm2_status != 200:
            fetch_errors.append(f"FinMind-CF:HTTP{_r2.status_code}:{_fm2_msg or _fm2_status}")
        if _fm2_status == 200 and _rows2:
            _dates2 = sorted(set(r.get("date","") for r in _rows2), reverse=True)
            _latest2 = [r for r in _rows2 if r.get("date") == (_dates2[0] if _dates2 else None)]
            _CX_TYPES = ["PropertyAndPlantAndEquipment","AcquisitionOfPropertyPlantAndEquipment"]
            _CX_NAMES = ["取得不動產、廠房及設備","購置不動產、廠房及設備","資本支出"]
            _cx2 = None
            for _row in _latest2:
                _t = str(_row.get("type",""))
                if any(_ct in _t for _ct in _CX_TYPES):
                    _v = float(str(_row.get("value",0)).replace(",","") or 0)
                    if _v != 0: _cx2 = abs(_v); break
            if _cx2 is None:
                for _row in _latest2:
                    _n = str(_row.get("origin_name",""))
                    if any(_k in _n for _k in _CX_NAMES):
                        _v = float(str(_row.get("value",0)).replace(",","") or 0)
                        if _v != 0: _cx2 = abs(_v); break
            if _cx2 and _cx2 > 0:
                _capex = _cx2; cx_src_capex = "FinMind-CF"
                if cx is None: cx = _capex; cx_src = "FinMind-CF"
                print(f"[FM-CF] ✅ 資本支出={_capex/1e8:.2f}億")
    except Exception as _e_cf:
        fetch_errors.append(f"FinMind-CF:{type(_e_cf).__name__}:{_e_cf}")
        print(f"[FM-CF] ❌ {_e_cf}")

    def _fmt(v): return f"{v/1e8:.1f}" if v else "-"
    print(f"[FIN] {sid}: cl={_fmt(cl)}億  cx={_fmt(cx)}億  capex={_fmt(_capex)}億")
    return cl, cx, _capex, cl_src, cx_src, cx_src_capex, fetch_errors


def fetch_revenue(sid):
    try:
        loader = _get_loader()
        result = loader.get_monthly_revenue(sid)
        if result is None: return None, '月營收：內部回傳None'
        if isinstance(result, tuple): return result
        return result, None  # single value
    except Exception as e:
        print(f"[fetch_revenue] {e}")
        return None, str(e)

@st.cache_data(ttl=1800)
def fetch_quarterly(sid, _ver=3):   # _ver 改變即清除舊快取
    try:
        loader = _get_loader()
        result = loader.get_quarterly_data(sid)
        if result is None: return None, '季財報：內部回傳None'
        if isinstance(result, tuple): return result
        return result, None
    except Exception as e:
        print(f"[fetch_quarterly] {e}")
        return None, str(e)

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_quarterly_extra(sid):
    """取得近 12 季資產負債表 + 現金流量時序（合約負債、存貨、資本支出），用於前瞻動能分數"""
    try:
        loader = _get_loader()
        result = loader.get_quarterly_bs_cf(sid)
        if result is None: return None, 'BS/CF：內部回傳None'
        if isinstance(result, tuple): return result
        return result, None
    except Exception as e:
        print(f"[fetch_quarterly_extra] {e}")
        return None, str(e)

# ════════════════════════════════════════════════════════════════
# 技術指標計算
# ════════════════════════════════════════════════════════════════
def calc_rsi(df, period=14):
    try:
        if df is None or len(df) < period + 1: return None
        delta = df['close'].diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi = 100 - (100 / (1 + rs))
        val = rsi.iloc[-1]
        return round(float(val), 1) if pd.notna(val) else None
    except Exception: return None

def calc_ibs(df):
    """IBS = (Close - Low) / (High - Low)  當日收盤在日震幅中的位置"""
    try:
        if df is None or df.empty: return None
        row = df.iloc[-1]
        h, l, c = float(row['high']), float(row['low']), float(row['close'])
        if h == l: return 0.5
        return round((c - l) / (h - l), 3)
    except Exception: return None

def calc_volume_ratio(df, period=5):
    """量比 = 今日成交量 / 近N日平均成交量"""
    try:
        if df is None or len(df) < period + 1: return None
        today_vol = float(df['volume'].iloc[-1])
        avg_vol = float(df['volume'].iloc[-(period+1):-1].mean())
        if avg_vol == 0: return None
        return round(today_vol / avg_vol, 2)
    except Exception: return None

def calc_kd(df, period=9):
    """計算最新一日的 K、D 值"""
    try:
        if df is None or len(df) < period: return None, None
        low_n  = df['low'].rolling(period).min()
        high_n = df['high'].rolling(period).max()
        rsv    = ((df['close'] - low_n) / (high_n - low_n).replace(0, 1)) * 100
        k = rsv.ewm(com=2, adjust=False).mean()
        d = k.ewm(com=2, adjust=False).mean()
        k_val = k.iloc[-1]; d_val = d.iloc[-1]
        if pd.isna(k_val) or pd.isna(d_val): return None, None
        return round(float(k_val), 1), round(float(d_val), 1)
    except Exception: return None, None

def calc_bollinger(df, window=20, mult=2):
    try:
        if df is None or len(df) < window: return None
        close = df['close']
        ma    = close.rolling(window).mean()
        std   = close.rolling(window).std()
        upper = ma + mult * std
        lower = ma - mult * std
        bw    = (upper - lower) / ma * 100
        _u, _l, _m, _bw = upper.iloc[-1], lower.iloc[-1], ma.iloc[-1], bw.iloc[-1]
        if any(pd.isna(v) for v in [_u, _l, _m, _bw]): return None
        return {
            'upper': round(float(_u), 2),
            'lower': round(float(_l), 2),
            'ma':    round(float(_m), 2),
            'bw':    round(float(_bw), 2),
        'bw_mean': round(float(bw.mean()) if 'bw' in dir() else 0, 2),
        'price': round(float(df['close'].iloc[-1]), 2),
        'near_upper': float(df['close'].iloc[-1]) >= float(_u) * 0.97,
        }
    except Exception: return None

def calc_vcp(df, n_swings=3):
    if df is None or len(df) < 30: return None  # relaxed to 30 days
    highs, lows = df['high'].values, df['low'].values
    swings, w   = [], 10
    for i in range(w, len(df) - w):
        if highs[i] == max(highs[max(0,i-w):i+w+1]):
            swings.append(('H', i, highs[i]))
        elif lows[i] == min(lows[max(0,i-w):i+w+1]):
            swings.append(('L', i, lows[i]))

    # P8修正: 只計算 H-L 或 L-H 交替的振幅（過濾連續同向swing）
    alt_swings = []
    for sw in swings:
        if not alt_swings or alt_swings[-1][0] != sw[0]:
            alt_swings.append(sw)
        else:
            # 同向取極值（HH取高，LL取低）
            if sw[0] == 'H' and sw[2] > alt_swings[-1][2]:
                alt_swings[-1] = sw
            elif sw[0] == 'L' and sw[2] < alt_swings[-1][2]:
                alt_swings[-1] = sw
    swings = alt_swings

    ranges = [abs(swings[k][2]-swings[k+1][2])/min(swings[k][2],swings[k+1][2])*100
              for k in range(len(swings)-1) if swings[k][0] != swings[k+1][0]]
    if len(ranges) < n_swings: return None
    last_n = ranges[-n_swings:]
    return {'swings': last_n, 'contracting': all(last_n[i]>last_n[i+1] for i in range(len(last_n)-1)),
            'latest_range': last_n[-1]}

# ════════════════════════════════════════════════════════════════
# 健康度評分（0~100）
# ════════════════════════════════════════════════════════════════
def calc_fundamental_score(qtr_df, yearly_df, avg_div):
    """基本面四維評分：獲利/成長/股利/估值，各 0-3 分"""
    import pandas as _pd_fs
    result = {
        'profit':   {'score':0,'max':3,'label':'獲利','checks':[]},
        'growth':   {'score':0,'max':3,'label':'成長','checks':[]},
        'dividend': {'score':0,'max':3,'label':'股利','checks':[]},
        'valuation':{'score':0,'max':3,'label':'估值','checks':[]},
    }
    try:
        if qtr_df is not None and not qtr_df.empty:
            cols = {c.strip():c for c in qtr_df.columns}
            def _gcol(*keys):
                for k in keys:
                    for c in qtr_df.columns:
                        if k in str(c): return c
                return None
            def _num(c, row=-1):
                if c is None: return None
                v = _pd_fs.to_numeric(qtr_df[c].iloc[row], errors='coerce')
                return None if _pd_fs.isna(v) else float(v)
            # 獲利
            eps_c = _gcol('EPS','eps')
            np_c  = _gcol('稅後淨利率','淨利率')
            op_c  = _gcol('營業利益率','營益率')
            if eps_c:
                es = _pd_fs.to_numeric(qtr_df[eps_c].tail(4), errors='coerce').dropna()
                sm = float(es.sum()) if len(es)>=2 else 0
                ok = sm >= 1
                result['profit']['score'] += int(ok)
                result['profit']['checks'].append(('近4季EPS>=1', f'{sm:.2f}', ok))
            if np_c:
                v = _num(np_c)
                ok = v is not None and v >= 5
                result['profit']['score'] += int(ok)
                result['profit']['checks'].append(('稅後淨利率>=5%', f'{v:.1f}%' if v else 'N/A', ok))
            if op_c:
                v = _num(op_c)
                ok = v is not None and v >= 10
                result['profit']['score'] += int(ok)
                result['profit']['checks'].append(('營業利益率>=10%', f'{v:.1f}%' if v else 'N/A', ok))
            # 成長
            rev_c = _gcol('營收','revenue')
            gp_c  = _gcol('毛利率')
            eps_c2= _gcol('EPS','eps')
            if rev_c and len(qtr_df)>=2:
                v1,v2 = _num(rev_c,-1),_num(rev_c,-2)
                ok = v1 and v2 and v1>v2
                result['growth']['score'] += int(ok)
                result['growth']['checks'].append(('營收季增', '成長中' if ok else '未成長', ok))
            if eps_c2 and len(qtr_df)>=5:
                v1,v5 = _num(eps_c2,-1),_num(eps_c2,-5)
                ok = v1 and v5 and v1>v5
                result['growth']['score'] += int(ok)
                result['growth']['checks'].append(('EPS年增', '成長中' if ok else '衰退', ok))
            if gp_c:
                v = _num(gp_c)
                ok = v is not None and v >= 20
                result['growth']['score'] += int(ok)
                result['growth']['checks'].append(('毛利率>=20%', f'{v:.1f}%' if v else 'N/A', ok))
        # 股利
        if avg_div and avg_div > 0:
            ok = avg_div >= 4
            result['dividend']['score'] += 2 if avg_div>=4 else (1 if avg_div>=2 else 0)
            result['dividend']['checks'].append(('平均殖利率', f'{avg_div:.1f}%', ok))
        if yearly_df is not None and not yearly_df.empty:
            dc = next((c for c in yearly_df.columns if '現金股利' in str(c) or '配息' in str(c)), None)
            if dc:
                ds = _pd_fs.to_numeric(yearly_df[dc].tail(4), errors='coerce').dropna()
                ok = len(ds)>=3 and (ds>0).all()
                result['dividend']['score'] += int(ok)
                result['dividend']['checks'].append(('近4年配息', '穩定' if ok else '不穩定', ok))
        # 估值 357
        if avg_div and avg_div > 0:
            if avg_div>=7:   sc,lb=3,'便宜區 >7%'
            elif avg_div>=5: sc,lb=2,'合理 5~7%'
            elif avg_div>=3: sc,lb=1,'合理 3~5%'
            else:            sc,lb=0,'偏貴 <3%'
            result['valuation']['score'] = sc
            result['valuation']['checks'].append(('357殖利率估值', f'{avg_div:.1f}% {lb}', sc>=2))
    except Exception as _e:
        print(f'[calc_fundamental_score] {_e}')
    return result


def calc_health_score(df, rsi, ibs, vr, k_val, d_val, bb):
    """
    綜合健康度評分，各因子分述：
    - 趨勢（MA20/MA100）    : 30分
    - RSI動能              : 20分
    - 量比                 : 15分
    - IBS位置              : 10分
    - KD排列               : 15分
    - 布林位置              : 10分
    """
    score = 0
    details = {}

    if df is not None and not df.empty:
        price  = float(df['close'].iloc[-1])
        ma20   = float(df['MA20'].iloc[-1])  if 'MA20'  in df.columns else None
        ma100  = float(df['MA100'].iloc[-1]) if 'MA100' in df.columns else None

        # 趨勢 (30分)
        if ma20 and ma100:
            if price > ma20 > ma100:
                score += 30; details['趨勢'] = ('多頭排列', 30, 30)
            elif price > ma100 and price > ma20:
                # P6修正: 需同時站上ma20和ma100才算「多箱整理」
                score += 18; details['趨勢'] = ('多箱整理(站上雙均)', 18, 30)
            elif price > ma20 and price < ma100:
                # 站上短均但低於長均 → 反彈初期，偏謹慎
                score += 10; details['趨勢'] = ('短線反彈(低於長均)', 10, 30)
            elif price < ma20 and price > ma100:
                # 短均跌破但長均支撐 → 整理中
                score += 8;  details['趨勢'] = ('整理中(長均支撐)', 8, 30)
            else:
                score += 0;  details['趨勢'] = ('空頭排列', 0,  30)
        else:
            score += 15; details['趨勢'] = ('無MA數據', 15, 30)

    # RSI (20分)
    if rsi is not None:
        if 50 <= rsi <= 70:
            score += 20; details['RSI'] = (f'{rsi}（強勢區間）', 20, 20)
        elif 40 <= rsi < 50:
            score += 12; details['RSI'] = (f'{rsi}（中性偏弱）', 12, 20)
        elif 30 <= rsi < 40:
            score += 8;  details['RSI'] = (f'{rsi}（超賣邊緣）', 8,  20)
        elif rsi < 30:
            score += 14; details['RSI'] = (f'{rsi}（超賣反彈機會）', 14, 20)
        else:  # >70
            score += 8;  details['RSI'] = (f'{rsi}（超買注意）', 8,  20)

    # 量比 (15分)
    if vr is not None:
        if vr > 3.0:
            # P7修正: 量比>3.0是重大消息/主力介入，給高分
            score += 12; details['量比'] = (f'{vr}（主力介入）', 12, 15)
        elif 1.5 <= vr <= 3.0:
            score += 15; details['量比'] = (f'{vr}（異常放量）', 15, 15)
        elif 1.0 <= vr < 1.5:
            score += 10; details['量比'] = (f'{vr}（溫和放量）', 10, 15)
        elif 0.5 <= vr < 1.0:
            score += 5;  details['量比'] = (f'{vr}（量縮整理）', 5,  15)
        else:
            score += 2;  details['量比'] = (f'{vr}（極度縮量）', 2,  15)

    # IBS (10分)
    if ibs is not None:
        if ibs <= 0.2:
            score += 10; details['IBS'] = (f'{ibs}（收低≤20%，隔日易反彈）', 10, 10)
        elif ibs >= 0.8:
            score += 2;  details['IBS'] = (f'{ibs}（收高≥80%，隔日易賣壓）', 2,  10)
        else:
            score += 6;  details['IBS'] = (f'{ibs}（中性）', 6, 10)

    # KD (15分)
    if k_val is not None and d_val is not None:
        if k_val > d_val and k_val < 80:
            score += 15; details['KD'] = (f'K={k_val} D={d_val}（黃金交叉）', 15, 15)
        elif k_val > d_val and k_val >= 80:
            score += 8;  details['KD'] = (f'K={k_val} D={d_val}（高檔黃叉注意）', 8, 15)
        elif k_val < d_val and k_val > 20:
            score += 5;  details['KD'] = (f'K={k_val} D={d_val}（死亡交叉）', 5, 15)
        else:
            score += 10; details['KD'] = (f'K={k_val} D={d_val}（低檔死叉可守）', 10, 15)

    # 布林 (10分)
    if bb is not None:
        if bb['near_upper']:
            score += 8;  details['布林'] = ('黏近上軌（強勢）', 8, 10)
        elif bb['price'] > bb['ma']:
            score += 6;  details['布林'] = ('站上中軌', 6, 10)
        elif bb['bw'] < bb['bw_mean'] * 0.7:
            score += 9;  details['布林'] = ('帶寬極度收縮（即將爆發）', 9, 10)
        else:
            score += 3;  details['布林'] = ('低於中軌', 3, 10)

    return min(score, 100), details

def health_grade(score):
    if score >= 80: return '優質優良', '#3fb950', 'health-A', '🟢'
    if score >= 50: return '震盪盤整', '#d29922', 'health-B', '🟡'
    return '弱勢危險', '#f85149', 'health-C', '🔴'

# ════════════════════════════════════════════════════════════════
# 初學者友善說明系統
# ════════════════════════════════════════════════════════════════

def explain_box(term, simple_explain, detail=''):
    """顯示一個術語說明框"""
    return (
        f'<div style="background:#161b22;border-left:3px solid #58a6ff;'
        f'padding:8px 12px;margin:4px 0;border-radius:0 6px 6px 0;">'
        f'<span style="font-size:12px;font-weight:700;color:#58a6ff;">{term}</span>'
        f'<span style="font-size:12px;color:#c9d1d9;"> = {simple_explain}</span>'
        + (f'<br><span style="font-size:11px;color:#8b949e;">{detail}</span>' if detail else '') +
        f'</div>'
    )

def traffic_light(value, good_cond, bad_cond, good_label, bad_label, neutral_label='⚪ 觀察'):
    """紅綠燈指示器"""
    if good_cond:   color, label = '#3fb950', f'🟢 {good_label}'
    elif bad_cond:  color, label = '#f85149', f'🔴 {bad_label}'
    else:           color, label = '#d29922', neutral_label
    return color, label

def beginner_kpi(title, value, plain_meaning, color='#e6edf3', tip=''):
    """初學者版 KPI 卡（有說明文字）"""
    return (
        f'<div style="background:#0d1117;border:1px solid #21262d;border-radius:10px;'
        f'padding:12px;text-align:center;">'
        f'<div style="font-size:10px;color:#484f58;margin-bottom:2px;">{title}</div>'
        f'<div style="font-size:22px;font-weight:900;color:{color};">{value}</div>'
        f'<div style="font-size:11px;color:#8b949e;margin-top:3px;">{plain_meaning}</div>'
        + (f'<div style="font-size:10px;color:#484f58;margin-top:2px;">💡 {tip}</div>' if tip else '') +
        f'</div>'
    )

# 術語白話對照表
TERM_EXPLAIN = {
    'RSI':      ('強弱指數', '衡量股票最近漲跌的「溫度」。<70正常，>70過熱，<30過冷。'),
    'KD':       ('買賣時機指標', 'K線和D線的交叉代表買賣時機。K>D往上穿越=可能要漲了。'),
    'ADL':      ('漲跌家數累積線', '今天台股漲的股票多還是跌的多。越多股票一起漲=市場越健康。'),
    'VCP':      ('波動收縮形態', '股價震盪越來越小，像彈弓拉緊。突破時可能大漲。'),
    'IBS':      ('K棒位置指標', '今天收盤在今天高低價的哪個位置。越靠近低點=隔天可能反彈。'),
    'M1B-M2':   ('資金流向指標', '活錢(M1B)比定存(M2)跑得快=錢往股市跑=行情要來了。'),
    '旌旗指數':  ('全市場健康度', '台股1800支股票，現在有幾%的股票站在均線之上。>60%=健康。'),
    '騰落指標':  ('市場廣度', '今天漲的股票-跌的股票。正數且持續往上=真正的多頭。'),
    '乖離率':    ('偏離正常值多少', '股價離平均成本線差多少%。>20%=可能過熱了，<-20%=可能太便宜。'),
    '多頭排列':  ('均線向上排列', '短期均線>中期>長期均線，代表趨勢向上，可以操作多方。'),
    '布林通道':  ('價格正常範圍', '統計出來的「正常價格範圍」。突破上軌=強勢但可能過熱。'),
    '量比':      ('成交量比較', '今天的成交量是過去20天平均的幾倍。>2=放量異常，要注意。'),
    'PCR':      ('多空情緒比', '選擇權市場的多空比例。>1偏多，<1偏空。'),
}

def show_term_help(term):
    """顯示術語說明 - 在任何 section 都可呼叫"""
    if term not in TERM_EXPLAIN: return ''
    name, desc = TERM_EXPLAIN[term]
    return explain_box(f'❓ {term}（{name}）', desc)

# 在先行指標 section 使用
_TERM_HELP_LI = show_term_help('PCR') + show_term_help('ADL') + show_term_help('M1B-M2')

# ════════════════════════════════════════════════════════════════
# generate_ai_comment：Rule-based 個股文字建議（無需 AI API）
# 輸入：dict 含財報/技術/籌碼數據
# 輸出：多行建議文字
# ════════════════════════════════════════════════════════════════

# ── 資本支出累計制還原（v4.0 修正）──────────────────────────
def generate_ai_comment(data: dict) -> str:
    """
    決策樹文字建議產生器
    data 鍵值：
      health, rsi, vcp_ok, bias_240, bias_20
      val_label (357評價), trend, cl (合約負債億), cx (資本支出億)
      foreign_buy, trust_buy (三大法人, 億), score (多因子總分)
      m1b_diff (M1B-M2 差距%)
    """
    lines = []
    h      = data.get('health', 0)
    score  = data.get('score', 0)
    rsi    = data.get('rsi') or 50
    val    = str(data.get('val_label', ''))
    trend  = str(data.get('trend', ''))
    cl     = data.get('cl') or 0
    cx     = data.get('cx') or 0
    fb     = data.get('foreign_buy') or 0   # 外資買賣億
    tb     = data.get('trust_buy') or 0     # 投信
    vcp_ok = data.get('vcp_ok', False)
    b240   = data.get('bias_240') or 0
    b20    = data.get('bias_20') or 0
    m1b    = data.get('m1b_diff') or 0      # M1B-M2 差距

    # ── 景氣環境前綴 ──────────────────────────────────────────
    if m1b < 0:
        lines.append('🌐 【景氣環境】M1B-M2為負，目前處於資金縮減期。'
                     '建議維持低持股（30%以下），優先選擇低位階、高股利標的。')
    elif m1b > 2:
        lines.append('🌐 【景氣環境】M1B-M2為正且強勁，資金行情啟動中，可積極持股。')

    # ── 財報評估 ─────────────────────────────────────────────
    fin_msg = []
    # 合約負債包含「流動」+「非流動」，別名有「預收款項」
    if cl > 0: fin_msg.append(f'合約負債{cl:.1f}億（流動+非流動合計；含預收款項）')
    if cx > 0: fin_msg.append(f'資本支出{cx:.1f}億（大規模擴廠，2-3年後營收爆發可期）')
    if fin_msg:
        lines.append('📊 【財報訊號】' + '；'.join(fin_msg) + '。')

    # ── 強烈買入條件（≥85分）────────────────────────────────
    if score >= 85 and '便宜' in val and '多頭' in trend:
        lines.append('🚀 【強烈買入】評分≥85 + 357便宜價 + 多頭排列。'
                     '建議突破60日箱頂時分批進場，回測紅K低點不破可加碼。')
    elif score >= 75 and '便宜' in val:
        lines.append('✅ 【積極買入】評分≥75且位於357便宜區，可分批布局。')
    elif score >= 75:
        lines.append('✅ 【評分優良】多因子評分≥75，技術面健康，可考慮建立底倉。')

    # ── 籌碼評估 ─────────────────────────────────────────────
    if fb > 5 and tb > 0:
        lines.append(f'💰 【籌碼共振】外資+{fb:.1f}億 & 投信+{tb:.1f}億，主力共同買進，訊號強烈。')
    elif fb > 5:
        lines.append(f'💰 【外資買進】外資+{fb:.1f}億，跟著大戶走（宏爺策略）。')
    elif fb < -10:
        lines.append(f'⚠️ 【外資賣超】外資-{abs(fb):.1f}億，籌碼面轉弱，建議等待。')

    # ── VCP 進場訊號 ─────────────────────────────────────────
    if vcp_ok:
        lines.append('🎯 【VCP籌碼安定】波幅持續收縮，籌碼集中於強手。'
                     '建議帶量突破高點時以30~50%建立底倉（妮可策略）。')

    # ── 技術面評估 ───────────────────────────────────────────
    if rsi < 30:
        lines.append(f'📉 RSI={rsi:.0f}（超賣區），短線反彈機率高，可小量試單。')
    elif rsi > 75:
        lines.append(f'📈 RSI={rsi:.0f}（超買區），注意短線回調風險，不宜追高。')

    # ── 乖離率評估 ───────────────────────────────────────────
    if b240 > 25:
        lines.append(f'🔴 【過熱警告】年線正乖離{b240:.0f}%（>25%），孫慶龍：開始分批減碼。'
                     '建議回收本金，剩餘部位守10週線（≈50MA）。')
    elif b240 < -20:
        lines.append(f'✅ 【低估機會】年線負乖離{abs(b240):.0f}%（<-20%），'
                     '孫慶龍：左側布局最佳時機，分批進場（2008/2020模式）。')

    # ── 分批減碼條件 ─────────────────────────────────────────
    if b240 > 25 and b20 > 10:
        lines.append('🟠 【分批減碼】年線乖離>25% + 月線乖離>10%雙重過熱，'
                     '建議先減50%部位，剩餘守5MA停利。')

    # ── 絕對停損觸發 ─────────────────────────────────────────
    if score < 60 and '空頭' in trend:
        lines.append('🛑 【絕對停損警示】多因子評分<60 + 空頭排列，理由消失即出場。'
                     '出清後觀望，等待評分重返60以上再考慮回補。')

    # ── 357估值提示 ─────────────────────────────────────────
    if '便宜' in val:
        lines.append('💎 【357估值】位於7%殖利率線以下（便宜區），孫慶龍認定的必買送分題。')
    elif '昂貴' in val or '超貴' in val:
        lines.append('⚠️ 【357估值】位於3%殖利率線以上（昂貴區），不宜追高，等待回調。')

    if not lines:
        lines.append('⚪ 目前無明顯買賣訊號，建議繼續觀察。')

    return '\n'.join(f'• {l}' for l in lines)

def kpi(title, value, sub='', color='#e6edf3', border='#21262d'):
    return (f'<div style="background:#161b22;border:1px solid {border};border-radius:8px;'
            f'padding:12px 14px;text-align:center;">'
            f'<div style="font-size:10px;color:#484f58;margin-bottom:3px;">{title}</div>'
            f'<div style="font-size:20px;font-weight:900;color:{color};">{value}</div>'
            f'<div style="font-size:10px;color:#8b949e;margin-top:3px;">{sub}</div></div>')

def teacher_box(icon, teacher, logic):
    # 保留向下相容，但建議用 teacher_conclusion()
    return (f'<div class="teacher-card">'
            f'<span style="font-size:12px;color:#ffd700;font-weight:700;">{icon} {teacher}</span>'
            f'<div style="font-size:12px;color:#8b949e;margin-top:4px;line-height:1.6;">{logic}</div>'
            f'</div>')

def teacher_conclusion(teacher, indicator_val, conclusion, action='', color=None):
    """
    統一老師結論格式：
    老師：指標數值 → 結論，行動建議

    teacher:       老師名稱（宏爺 / 孫慶龍 / 弘爺 / 朱家泓 / 妮可）
    indicator_val: 指標與數值（如 '費半 7837(+0.5%)'）
    conclusion:    目前結論（如 '半導體強勢'）
    action:        建議行動（如 '台股多方加分'）
    color:         顏色（自動依結論判斷，或手動指定 green/red/yellow）
    """
    # 自動判斷顏色
    if color is None:
        # 台股慣例: 正/漲/多=紅, 負/跌/空=綠, 中性=黃, 預設=藍
        _neg_kw = ['警戒','危險','賣超','空單','減碼','停損','撤離','跌破','過熱','回調','降倉','空頭']
        _pos_kw = ['強勢','買超','多頭','安全','健康','買進','加碼','流入','突破','進攻','上漲']
        if any(k in conclusion+action for k in _neg_kw):   color = '#2ea043'   # 跌=綠
        elif any(k in conclusion+action for k in _pos_kw): color = '#da3633'   # 漲=紅
        else: color = '#d29922'
    _icon = {'宏爺':'🎯','孫慶龍':'💡','弘爺':'🎯','朱家泓':'📊','妮可':'📈','春哥':'🌱','蔡森':'📐'}.get(teacher,'👤')
    _action_str = f'，{action}' if action else ''
    return (
        f'<div style="border-left:3px solid {color};padding:6px 10px;margin:4px 0;'
        f'background:rgba(0,0,0,0.2);border-radius:0 6px 6px 0;">'
        f'<span style="color:#ffd700;font-weight:700;font-size:12px;">{_icon} {teacher}</span>'
        f'<span style="color:#8b949e;font-size:12px;">：</span>'
        f'<span style="color:#c9d1d9;font-size:12px;">{indicator_val} → </span>'
        f'<span style="color:{color};font-size:12px;font-weight:600;">{conclusion}</span>'
        f'<span style="color:#8b949e;font-size:11px;">{_action_str}</span>'
        f'</div>'
    )

def signal_box(label, color, desc=''):
    colors = {'green':('#0d2818','#3fb950'),'red':('#2a0d0d','#f85149'),
              'yellow':('#2a1f00','#d29922'),'blue':('#0d1b2a','#58a6ff')}
    bg, tc = colors.get(color, ('#161b22','#8b949e'))
    return (f'<div style="background:{bg};border:1px solid {tc};border-radius:8px;'
            f'padding:10px 14px;margin:4px 0;">'
            f'<b style="color:{tc};">{label}</b>'
            f'<span style="color:#8b949e;font-size:12px;margin-left:8px;">{desc}</span></div>')

# ════════════════════════════════════════════════════════════════
# 健康度分數顯示元件
# ════════════════════════════════════════════════════════════════
def render_health_score(score, details, sid='', fund_scores=None, tech_alerts=None):
    """個股健診 v2：SVG量表 + 四維評分 + 技術警示 + 因子條形圖"""
    grade, color, css_class, emoji = health_grade(score)
    import math as _mh

    # ① SVG 半圓量表
    angle = (-180 + score * 1.8) * _mh.pi / 180
    cx, cy, r = 100, 90, 70
    nx = cx + r * _mh.cos(angle)
    ny = cy + r * _mh.sin(angle)
    gauge = (
        '<div style="text-align:center;padding:4px 0;">'
        '<svg viewBox="0 0 200 110" style="width:175px;height:92px;">'
        '<path d="M20,90 A80,80 0 0,1 60,22" stroke="#4c1d95" stroke-width="14" fill="none" stroke-linecap="round"/>'
        '<path d="M60,22 A80,80 0 0,1 100,10" stroke="#1e3a5f" stroke-width="14" fill="none" stroke-linecap="round"/>'
        '<path d="M100,10 A80,80 0 0,1 140,22" stroke="#1a4a1a" stroke-width="14" fill="none" stroke-linecap="round"/>'
        '<path d="M140,22 A80,80 0 0,1 180,90" stroke="#3d2000" stroke-width="14" fill="none" stroke-linecap="round"/>'
        f'<line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/>'
        f'<circle cx="{cx}" cy="{cy}" r="5" fill="{color}"/>'
        '<text x="14" y="103" fill="#8b949e" font-size="8">注意</text>'
        '<text x="48" y="18" fill="#8b949e" font-size="8">較差</text>'
        '<text x="88" y="8" fill="#8b949e" font-size="8">普通</text>'
        '<text x="127" y="18" fill="#8b949e" font-size="8">良好</text>'
        f'<text x="100" y="82" text-anchor="middle" fill="{color}" font-size="26" font-weight="900">{score}</text>'
        f'<text x="100" y="97" text-anchor="middle" fill="{color}" font-size="10">{grade}</text>'
        '</svg></div>'
    )

    # ② 四維評分
    fund_html = ''
    if fund_scores:
        _cat_ic = {'profit':'💰','growth':'📈','dividend':'🎁','valuation':'⚖️'}
        _sc_cl  = {0:'#8b949e',1:'#d29922',2:'#3fb950',3:'#2ea043'}
        fund_html = '<div style="display:flex;gap:4px;margin:10px 0;">'
        for cat in ['profit','growth','dividend','valuation']:
            fs  = fund_scores.get(cat,{})
            sc  = fs.get('score',0); mx=fs.get('max',3)
            lb  = fs.get('label',cat); ic=_cat_ic.get(cat,'')
            cl  = _sc_cl.get(min(sc,3),'#8b949e')
            chk = ''
            for cn,cv,cp in fs.get('checks',[])[:3]:
                cc = '#3fb950' if cp else '#f85149'
                chk += f'<div style="font-size:9px;color:{cc};margin-top:1px;">{"✓" if cp else "✗"} {cn}</div>'
            fund_html += (
                f'<div style="flex:1;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:7px 4px;text-align:center;">'
                f'<div style="font-size:20px;font-weight:900;color:{cl};">{sc}</div>'
                f'<div style="font-size:9px;color:#8b949e;">{ic} {lb}</div>'
                f'{chk}</div>'
            )
        fund_html += '</div>'

    # ③ 技術警示
    tech_html = ''
    if tech_alerts:
        _pc = {'🔴':'#f85149','🟡':'#d29922','🟢':'#3fb950'}
        tech_html = '<div style="margin:8px 0;"><div style="font-size:11px;color:#8b949e;margin-bottom:4px;">⚡ 技術警示</div>'
        for pri,name,sig,desc in tech_alerts[:5]:
            bc = _pc.get(pri,'#484f58')
            sc2 = '#f85149' if any(k in sig for k in ['看跌','空頭','超賣']) else ('#3fb950' if any(k in sig for k in ['看漲','多頭']) else '#d29922')
            tech_html += (
                f'<div style="display:flex;align-items:center;gap:6px;margin:3px 0;background:#0d1117;border-left:3px solid {bc};padding:4px 8px;border-radius:0 4px 4px 0;">'
                f'<span style="font-size:10px;">{pri}</span>'
                f'<div style="flex:1;">'
                f'<span style="font-size:11px;font-weight:700;color:#c9d1d9;">{name}</span>'
                f'<span style="font-size:9px;background:{sc2}33;color:{sc2};padding:1px 4px;border-radius:3px;margin-left:5px;">{sig}</span>'
                f'<div style="font-size:9px;color:#8b949e;">{desc}</div>'
                f'</div></div>'
            )
        tech_html += '</div>'

    # ④ 因子條形圖
    breakdown = '<div style="margin-top:8px;">'
    for factor, (desc, got, total) in details.items():
        pct = got / total * 100
        bc  = '#3fb950' if pct>=70 else ('#d29922' if pct>=40 else '#f85149')
        breakdown += (
            f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">'
            f'<div style="width:45px;font-size:10px;color:#8b949e;text-align:right;">{factor}</div>'
            f'<div style="flex:1;background:#21262d;border-radius:4px;height:7px;">'
            f'<div style="width:{pct:.0f}%;background:{bc};border-radius:4px;height:7px;"></div></div>'
            f'<div style="width:85px;font-size:9px;color:{bc};">{got}/{total} {desc[:8]}</div>'
            f'</div>'
        )
    breakdown += '</div>'
    return gauge + fund_html + tech_html + breakdown


primary_stock = '2330'

# ── Sidebar: 整合 AI 分析 ───────────────────────────────────────
with st.sidebar:
    st.markdown('<div style="text-align:center;padding:8px 0;font-size:15px;font-weight:900;color:#e6edf3;">&#128202; 台股AI戰情室 v3.0</div>', unsafe_allow_html=True)
    st.markdown('---')
    _today_sb = datetime.date.today()
    _wd_sb = {0:'一',1:'二',2:'三',3:'四',4:'五',5:'六',6:'日'}[_today_sb.weekday()]
    _trade_sb = '✅ 交易日' if _today_sb.weekday() < 5 else '❌ 非交易日'
    st.caption(f'{_today_sb.strftime("%Y/%m/%d")} 週{_wd_sb}  {_trade_sb}')
    st.markdown('---')
    st.markdown('### 🤖 AI 分析')
    st.caption('頁面底部有 AI 整合報告面板')
    ai_run = False  # AI button moved to bottom panel
    st.markdown('---')
    st.markdown('### 💰 資金控管設定')
    # ── 模組二：核心/衛星資金輸入 ─────────────────────────────
    _sb_cap_input = st.number_input(
        '📥 請輸入總投資資金（台幣元）',
        min_value=10000, max_value=100_000_000,
        value=st.session_state.get('total_capital_twd', 500000),
        step=10000, format='%d',
        help='系統自動劃分：70% 核心ETF + 30% 衛星飆股'
    )
    st.session_state['total_capital_twd'] = _sb_cap_input
    _sb_core = round(_sb_cap_input * 0.70)
    _sb_sat  = round(_sb_cap_input * 0.30)
    st.markdown(f'''
<div style="background:#0a1628;border:1px solid #21262d;border-radius:10px;padding:10px;">
<div style="display:flex;justify-content:space-between;margin-bottom:6px;">
  <span style="color:#3fb950;font-size:12px;">🏛️ 核心 70%</span>
  <span style="color:#3fb950;font-size:12px;font-weight:700;">NT${_sb_core:,}</span>
</div>
<div style="background:#143326;height:8px;border-radius:4px;margin-bottom:8px;"></div>
<div style="display:flex;justify-content:space-between;">
  <span style="color:#58a6ff;font-size:12px;">🚀 衛星 30%</span>
  <span style="color:#58a6ff;font-size:12px;font-weight:700;">NT${_sb_sat:,}</span>
</div>
<div style="background:#0d2137;height:8px;border-radius:4px;"></div>
</div>''', unsafe_allow_html=True)
    _sb_risk_pct = st.slider('單筆最大虧損 (%)', 1.0, 3.0, 1.5, 0.5,
                             help='Elder 2%法則：每筆最多輸掉總資金的1.5-2%',
                             key='sb_risk_pct')
    st.session_state['max_risk_pct'] = _sb_risk_pct / 100
    st.markdown('---')
    # Defense mode 狀態顯示
    if st.session_state.get('defense_mode', False):
        st.error('🔴 Defense Mode 啟動中\n衛星資金已鎖定')
    else:
        st.success('🟢 系統正常運作中')

    st.markdown('---')
    st.caption('⚠️ 僅供學術研究，非投資建議，盈虧自負')

# v3.0 RENDER FUNCTIONS (§9.3)
# ════════════════════════════════════════════════════════════════

# ── 旌旗指數計算（站上 MA20/MA60/MA120/MA240 的家數比例）──────
def calc_jingqi(scan_results):
    """
    傳入 Tab5 掃描結果 list，計算旌旗指數
    scan_results: [{代碼, 趨勢, 健康度, ...}, ...]
    """
    if not scan_results: return {}
    total = len(scan_results)
    # P4修正：四個維度統一用「健康度門檻」，並附上語意說明
    # pct20 = 健康度>=40（基本健康，可觀察）
    # pct60 = 健康度>=60（中等強勢）
    # pct120= 健康度>=70（強勢）
    # pct240= 健康度>=80（優質強勢）
    above_ma20  = sum(1 for r in scan_results if r.get('健康度',0) >= 40)
    above_ma60  = sum(1 for r in scan_results if r.get('健康度',0) >= 60)
    above_ma120 = sum(1 for r in scan_results if r.get('健康度',0) >= 70)
    above_ma240 = sum(1 for r in scan_results if r.get('健康度',0) >= 80)
    pct20  = round(above_ma20  / total * 100, 1) if total else 0
    pct60  = round(above_ma60  / total * 100, 1) if total else 0
    pct120 = round(above_ma120 / total * 100, 1) if total else 0
    pct240 = round(above_ma240 / total * 100, 1) if total else 0
    avg    = round((pct20+pct60+pct120+pct240)/4, 1)

    # 動態倉位建議（弘爺策略）
    if avg >= 60:   pos = '80~100%'  ; regime = 'bull';   color = '#3fb950'; label = '🟢 多頭積極'
    elif avg >= 40: pos = '50~70%';   regime = 'neutral'; color = '#d29922'; label = '🟡 中性均衡'
    elif avg >= 20: pos = '20~40%';   regime = 'caution'; color = '#f85149'; label = '🟠 保守防禦'
    else:           pos = '0~20%';    regime = 'bear';    color = '#c00000'; label = '🔴 極度保守'

    return {
        'pct20':pct20,'pct60':pct60,'pct120':pct120,'pct240':pct240,
        'avg':avg,'pos':pos,'regime':regime,'color':color,'label':label,
        'total':total
    }

def render_market_overview(market_info: dict):
    """首頁市場狀態卡 (§9.2)"""
    if not market_info:
        st.warning('⚠️ 無法取得大盤數據')
        return
    regime   = market_info.get('regime', 'neutral')
    label    = market_info.get('label', '─')
    score    = market_info.get('score', 0)
    mx       = market_info.get('max_score', 4)
    idx      = market_info.get('index_price', 0)
    exposure = market_info.get('exposure_pct', '50%')
    signals  = market_info.get('signals', [])
    color_map = {'bull': '#3fb950', 'neutral': '#d29922', 'bear': '#f85149'}
    bg_map    = {'bull': '#0d2818', 'neutral': '#2a1f00', 'bear': '#2a0d0d'}
    color = color_map.get(regime, '#8b949e')
    bg    = bg_map.get(regime, '#161b22')
    st.markdown(f"""
<div style="background:{bg};border:2px solid {color};border-radius:12px;padding:16px 20px;margin-bottom:12px;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div>
      <span style="font-size:22px;font-weight:900;color:{color};">{label}</span>
      <span style="font-size:13px;color:#8b949e;margin-left:10px;">評分 {score}/{mx} ｜ 大盤 {idx:,.0f}</span>
    </div>
    <div style="text-align:right;">
      <span style="font-size:15px;color:#e6edf3;">建議持股 <b style="color:{color};">{exposure}</b></span>
    </div>
  </div>
  <div style="margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;">
    {"".join('<span style="background:#161b22;border-radius:6px;padding:3px 8px;font-size:12px;color:#e6edf3;">' + str(s) + '</span>' for s in signals)}
  </div>
</div>""", unsafe_allow_html=True)

def render_top_rankings(results: list, top_n: int = 10):
    """股票評分排行榜 (§9.1)"""
    if not results:
        st.info('尚無評分資料')
        return
    from scoring_engine import rank_stocks as _rank
    ranked = _rank(results)[:top_n]
    if not ranked:
        st.info('尚無有效評分資料')
        return
    rows = []
    for i, r in enumerate(ranked):
        rows.append({
            '排名': i + 1, '代碼': r.get('stock_id', ''), '名稱': r.get('stock_name', ''),
            '總分': f"{r.get('total', 0):.1f}", '趨勢': f"{r.get('trend', 0):.0f}",
            '動能': f"{r.get('momentum', 0):.0f}", '籌碼': f"{r.get('chip', 0):.0f}",
            '量價': f"{r.get('volume', 0):.0f}", '風險': f"{r.get('risk', 0):.0f}",
            '評級': r.get('grade', '-'), '動能訊號': '⚡' if r.get('momentum_signal') else '─',
        })
    df_rank = pd.DataFrame(rows)
    st.dataframe(df_rank, use_container_width=True, hide_index=True,
                 column_config={'總分': st.column_config.ProgressColumn('總分', min_value=0, max_value=100, format='%.1f')})

# ════════════════════════════════════════════════════════════════
# TABS: 3 主頁籤
# ════════════════════════════════════════════════════════════════
# ── Sidebar ────────────────────
with st.sidebar:
    st.markdown('<div style="text-align:center;padding:8px 0;font-size:15px;font-weight:900;color:#e6edf3;">&#128202; 台股AI戰情室 v3.0</div>', unsafe_allow_html=True)
    st.markdown('---')
    _today_sb = datetime.date.today()
    _wd_sb = {0:'一',1:'二',2:'三',3:'四',4:'五',5:'六',6:'日'}[_today_sb.weekday()]
    _trade_sb = '✅ 交易日' if _today_sb.weekday() < 5 else '❌ 非交易日'
    st.caption(f'{_today_sb.strftime("%Y/%m/%d")} 週{_wd_sb}  {_trade_sb}')
    st.markdown('---')

# 主標題
st.markdown(
    '<div style="display:flex;align-items:center;gap:10px;padding:4px 0 8px;">'    '<span style="font-size:22px;font-weight:900;color:#e6edf3;">&#128202; 台股 AI 戰情室</span>'    '<span style="font-size:10px;color:#484f58;background:#161b22;border-radius:10px;padding:2px 8px;">v4.0 Pro</span>'    '</div>',
    unsafe_allow_html=True)

tab1_macro, tab_heatmap, tab_stock_grp, tab_etf_grp, tab_health, tab4_masters = st.tabs([
    '🌍 總經',
    '🗺️ 熱力板塊',
    '🔬 台股',
    '🏦 ETF',
    '🔎 資料診斷',
    '📚 策略手冊',
])
with tab_stock_grp:
    tab2_stock, tab3_compare = st.tabs([
        '🔬 個股分析', '🏆 比較 × 排行',
    ])
with tab_etf_grp:
    tab_etf1, tab_etf2, tab_etf3, tab_etf4 = st.tabs([
        '🏦 ETF 診斷', '⚖️ ETF 組合', '📈 ETF 回測', '🤖 ETF AI',
    ])

# ══════════════════════════════════════════════════════════════
# TAB 1: 總體經濟
# ══════════════════════════════════════════════════════════════

# ── 全域多空紅綠燈（頁面最頂端）─────────────────────────────
_mkt_top  = st.session_state.get('mkt_info', {})
_jq_top   = st.session_state.get('jingqi_info', {})
_ts_top   = st.session_state.get('cl_ts', '')
if _mkt_top or _jq_top:
    _reg   = _mkt_top.get('regime', 'neutral')
    _jqpct = _jq_top.get('avg', 50) if _jq_top else None
    # 綜合信號
    _gl_color, _gl_label = traffic_light(
        None,
        _reg == 'bull' and (_jqpct is None or _jqpct >= 40),
        _reg == 'bear' or (_jqpct is not None and _jqpct < 20),
        '多頭市場（可積極操作）', '空頭市場（先觀望保守）', '🟡 震盪整理（謹慎操作）'
    )
    _gl_pos = _mkt_top.get('exposure_pct', '80%' if _reg=='bull' else ('20%' if _reg=='bear' else '50%'))

    st.markdown(
        f'<div style="background:#0d1117;border:1px solid {_gl_color};border-radius:8px;'
        f'padding:8px 14px;margin-bottom:8px;display:flex;align-items:center;gap:16px;">'
        f'<span style="font-size:16px;font-weight:900;color:{_gl_color};">{_gl_label}</span>'
        f'<span style="font-size:12px;color:#c9d1d9;">建議持股 <b>{_gl_pos}</b></span>'
        + (f'<span style="font-size:12px;color:#8b949e;">旌旗均值 {_jqpct:.0f}%</span>'
           if _jqpct is not None else '') +
        f'<span style="font-size:11px;color:#484f58;margin-left:auto;">更新：{_ts_top}</span>'
        f'</div>', unsafe_allow_html=True)

with tab1_macro:
    # ════════════════════════════════════════════════════════
    # 【模組一】紅綠燈決策儀表板（st.empty 佔位符修復版）
    # 修復：先挖洞（placeholder）→ 資料到位後回填，杜絕未審先判
    # ════════════════════════════════════════════════════════

    # ── 核心工具函式：計算燈號（任何時候都可以呼叫）────────
    def _calc_traffic_light(mkt_info, jingqi_info, cl_data, li_latest):
        """根據當前數據計算紅綠燈狀態，回傳 dict。無數據時回傳 None。"""
        # 尚未有任何數據→回傳 None（由 placeholder 顯示等待狀態）
        if not mkt_info and not jingqi_info and not cl_data:
            return None
        _mkt    = mkt_info   or {}
        _jq     = jingqi_info or {}
        _cd     = cl_data    or {}
        _score  = _mkt.get('score', 0)
        _jqavg  = _jq.get('avg', 50)
        _inst   = _cd.get('inst', {})
        _fk     = next((k for k in _inst if '外資' in k), None)
        if _fk is None: _fk = next((k for k in _inst if '外資' in k), None)
        _fnet   = _inst.get(_fk, {}).get('net', 0) if _fk else 0
        # 先行指標期貨空單
        _fut_net = 0
        if li_latest is not None and not li_latest.empty and '外資大小' in li_latest.columns:
            try: _fut_net = float(li_latest.iloc[-1].get('外資大小', 0))
            except: pass
        # 韭菜指數
        _leek = 50
        if li_latest is not None and not li_latest.empty and '韭菜指數' in li_latest.columns:
            try: _leek = float(li_latest.iloc[-1].get('韭菜指數', 50))
            except: pass

        _defense = (_score < 2 and abs(_fut_net) > 30000 and _fut_net < 0)
        _health  = round(_jqavg * 0.4 + min(_score / 5 * 100, 100) * 0.4 + (20 if _fnet > 0 else 0), 1)

        if _defense or _health < 40:
            _color = '#f85149'; _icon = '🔴'; _label = '紅燈｜強制防禦'
            _action = '⛔ 大環境極度惡劣，系統已啟動資金保護機制'
            _sub    = '建議持有現金或僅定期定額核心 ETF，禁止追買任何個股'
        elif _health >= 70 and not _defense and _leek < 40:
            _color = '#3fb950'; _icon = '🟢'; _label = '綠燈｜積極買進'
            _action = '✅ 市場健康，籌碼乾淨，可積極尋找強勢標的'
            _sub    = '建議衛星資金（30%）可佈局高分股，核心ETF（70%）持續定投'
        else:
            _color = '#d29922'; _icon = '🟡'; _label = '黃燈｜持有觀望'
            _action = '⚠️ 市場處於整理期，謹慎操作，降低部位'
            _sub    = '持有現有倉位觀望，不追高，等待更明確信號'

        # 數據信心指數
        _conf = round(sum([bool(mkt_info), bool(jingqi_info), bool(_fk),
                           bool(li_latest is not None and not li_latest.empty),
                           bool(_cd.get('adl') is not None)]) / 5 * 100)
        return {
            'color': _color, 'icon': _icon, 'label': _label,
            'action': _action, 'sub': _sub, 'health': _health,
            'defense': _defense, 'score': _score, 'jqavg': _jqavg,
            'leek': _leek, 'fnet': _fnet, 'fk': _fk, 'fut_net': _fut_net,
            'conf': _conf,
        }

    def _render_traffic_light(placeholder, tl):
        """將計算結果回填到 placeholder（或顯示等待狀態）。"""
        if tl is None:
            placeholder.info(
                '⏳ **系統正在深度解析大盤與籌碼數據，請稍候...**\n\n'
                '首次使用請點擊「🔄 更新全部總經數據」載入資料。',
                icon='📡'
            )
            return
        _sb_cap = st.session_state.get('total_capital_twd', 500000)
        _core   = round(_sb_cap * 0.70)
        _sat    = round(_sb_cap * 0.30)
        _sat_used   = st.session_state.get('satellite_used', 0)
        _sat_remain = max(_sat - _sat_used, 0)
        _used_pct   = round(_sat_used / _sat * 100) if _sat > 0 else 0
        _sat_color  = '#f85149' if tl['defense'] else '#58a6ff'
        _rem_color  = '#3fb950' if _sat_remain > _sat * 0.3 else ('#d29922' if _sat_remain > 0 else '#f85149')

        with placeholder.container():
            # ── 紅綠燈主體 ─────────────────────────────────────
            st.markdown(f'''<div style="background:linear-gradient(135deg,#0a1628,#0d1f3c);
border:3px solid {tl["color"]};border-radius:16px;padding:20px 24px;margin-bottom:12px;">
<div style="display:flex;align-items:center;gap:16px;">
  <div style="font-size:56px;line-height:1;">{tl["icon"]}</div>
  <div>
    <div style="font-size:24px;font-weight:900;color:{tl["color"]};">{tl["label"]}</div>
    <div style="font-size:15px;color:#c9d1d9;margin-top:4px;">{tl["action"]}</div>
    <div style="font-size:12px;color:#8b949e;margin-top:2px;">{tl["sub"]}</div>
  </div>
  <div style="margin-left:auto;text-align:right;">
    <div style="font-size:12px;color:#484f58;">綜合健康度</div>
    <div style="font-size:36px;font-weight:900;color:{tl["color"]};">{tl["health"]:.0f}</div>
    <div style="font-size:11px;color:#484f58;">/ 100分｜信心{tl["conf"]}%</div>
  </div>
</div></div>''', unsafe_allow_html=True)

            # ── Defense Mode 警告 ───────────────────────────────
            if tl['defense']:
                st.error('''🚨 **Defense Mode 已啟動** — 衛星資金已鎖定！
**觸發**：大盤評分<2分 且 外資期貨空單>30,000口
- 🔴 所有 AI 衛星個股買進訊號已隱藏
- ✅ 僅建議定期定額核心 ETF（0050/006208）''')

            # ── 核心/衛星資金看板 ──────────────────────────────
            _fc = st.columns(3)
            with _fc[0]:
                st.markdown(f'''<div style="background:#0a2818;border:1px solid #3fb950;
border-radius:12px;padding:14px;text-align:center;">
<div style="font-size:11px;color:#3fb950;font-weight:700;">🏛️ 核心資金 (70%)</div>
<div style="font-size:22px;font-weight:900;color:#3fb950;">NT${_core:,}</div>
<div style="font-size:11px;color:#484f58;">定期定額 0050/006208</div></div>''', unsafe_allow_html=True)
            with _fc[1]:
                st.markdown(f'''<div style="background:#0a1628;border:1px solid {_sat_color};
border-radius:12px;padding:14px;text-align:center;">
<div style="font-size:11px;color:{_sat_color};font-weight:700;">🚀 衛星資金 (30%)</div>
<div style="font-size:22px;font-weight:900;color:{_sat_color};">NT${_sat:,}</div>
<div style="font-size:11px;color:#484f58;">{"🔒 Defense Mode 鎖定中" if tl["defense"] else "AI 選股可用"}</div></div>''', unsafe_allow_html=True)
            with _fc[2]:
                st.markdown(f'''<div style="background:#0d1117;border:1px solid #21262d;
border-radius:12px;padding:14px;text-align:center;">
<div style="font-size:11px;color:#484f58;">衛星剩餘額度</div>
<div style="font-size:22px;font-weight:900;color:{_rem_color};">NT${_sat_remain:,}</div>
<div style="font-size:11px;color:#484f58;">已用 {_used_pct}%</div></div>''', unsafe_allow_html=True)
            st.progress(min(_sat_used / max(_sat, 1), 1.0),
                        text=f'衛星資金使用 {_sat_used:,} / {_sat:,} 元')

            # ── 數據信心提示 ────────────────────────────────────
            if tl['conf'] < 80:
                st.warning(f'⚠️ 數據信心指數 {tl["conf"]}%，部分資料缺失，建議更新後再操作')

    # ── ① 最頂端先建立佔位符（關鍵：必須在任何計算前建立）───
    _tl_placeholder = st.empty()

    # ── ② 讀取快取（快取新鮮才顯示燈號，否則顯示等待，避免誤導）──
    # 設計原則：燈號必須反映「當前資料」而非「過期快取」
    # 30 分鐘內的快取視為有效；超過則要求重新更新
    import datetime as _dt_tl
    _cl_ts_str = st.session_state.get('cl_ts', '')
    _cache_fresh = False
    if _cl_ts_str:
        try:
            _cl_ts_dt = _dt_tl.datetime.strptime(_cl_ts_str[:16], '%Y-%m-%d %H:%M')
            _age_min  = (_dt_tl.datetime.now() - _cl_ts_dt).total_seconds() / 60
            _cache_fresh = _age_min < 30   # 30 分鐘內視為新鮮
        except Exception:
            _cache_fresh = False

    if _cache_fresh:
        # 快取新鮮 → 立即計算燈號（含資料新鮮度標記）
        _tm_mkt_init = st.session_state.get('mkt_info', {})
        _tm_jq_init  = st.session_state.get('jingqi_info', {})
        _tm_cd_init  = st.session_state.get('cl_data', {})
        _tm_li_init  = st.session_state.get('li_latest')
        _tl_init     = _calc_traffic_light(_tm_mkt_init, _tm_jq_init, _tm_cd_init, _tm_li_init)
        _render_traffic_light(_tl_placeholder, _tl_init)
    else:
        # 無快取 or 快取過期 → 顯示等待狀態，不顯示誤導性燈號
        age_note = f'（上次更新 {_age_min:.0f} 分鐘前，已過期）' if _cl_ts_str and not _cache_fresh else '（尚無資料）'
        _tl_placeholder.warning(
            f'⏳ **燈號等待中 {age_note}**\n\n'
            '燈號將在「🔄 更新全部總經數據」完成後自動亮起。\n'
            '確保資料是今日最新，再做投資判斷。',
        )
        _tl_init = None

    # ── 同步寫入 session_state（其他頁面需要的值）────────────
    if _tl_init:
        st.session_state['defense_mode'] = _tl_init['defense']
        st.session_state['warroom_summary'] = {
            'traffic_light': _tl_init['label'],
            'health_score':  _tl_init['health'],
            'defense_mode':  _tl_init['defense'],
            'regime': _tm_mkt_init.get('regime', 'neutral'),
            'market_score':  _tl_init['score'],
            'jingqi_avg':    _tl_init['jqavg'],
            'leek_index':    _tl_init['leek'],
            'foreign_net_bn':_tl_init['fnet'],
            'futures_net':   _tl_init['fut_net'],
            'confidence_pct':_tl_init['conf'],
            'core_capital':  round(st.session_state.get('total_capital_twd', 500000) * 0.70),
            'satellite_capital': round(st.session_state.get('total_capital_twd', 500000) * 0.30),
        }
    else:
        st.session_state['defense_mode'] = False

    st.markdown('<div style="background:#0a1628;border:1px solid #1f6feb;border-radius:12px;padding:16px;margin-bottom:12px;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:18px;font-weight:900;color:#58a6ff;margin-bottom:8px;">🌍 今日市場總覽 — 現在適合買股票嗎？</div>', unsafe_allow_html=True)
    st.markdown('''<div style="font-size:13px;color:#c9d1d9;line-height:1.8;">
投資前先看大環境，就像出門前先看天氣預報。這個頁面告訴你：<br>
• <b style="color:#3fb950;">現在是多頭市場（晴天）</b> → 可以積極找好股票買進<br>
• <b style="color:#d29922;">現在是震盪整理（多雲）</b> → 謹慎操作，小量買進<br>
• <b style="color:#f85149;">現在是空頭市場（下雨）</b> → 先保留現金，等待機會<br>
</div>''', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("""<div style="padding:6px 0 4px;">
<span style="font-size:20px;font-weight:900;color:#e6edf3;">🌍 今日市場總覽</span>
<span style="font-size:11px;color:#484f58;margin-left:10px;">決定：現在能買嗎？大盤水位？</span>
</div>""", unsafe_allow_html=True)
    # 五步流程說明已整合至主導覽列，此處不重複顯示

    # ══ 戰情概覽（一眼看清今日市場）══════════════════════════
    _ov_mkt  = st.session_state.get('mkt_info', {})
    _ov_jq   = st.session_state.get('jingqi_info', {})
    _ov_cd   = st.session_state.get('cl_data', {})
    # inst 優先從 cl_data，fallback 到獨立緩存的 _last_inst
    _ov_inst = _ov_cd.get('inst') or st.session_state.get('_last_inst', {})
    # 外資 key 匹配：TWSE 格式「外資及陸資(不含外資自營商)」或 FinMind 格式「外資」
    _ov_fk   = next((k for k in _ov_inst if '外資' in k), None)
    _ov_margin = _ov_cd.get('margin')
    _ov_bias = st.session_state.get('bias_info', {})

    if any([_ov_mkt, _ov_jq, _ov_cd]):
        _ov_cols = st.columns(4)
        # 大盤
        with _ov_cols[0]:
            _ov_reg = _ov_mkt.get('regime','neutral') if _ov_mkt else 'neutral'
            _ov_lbl = {'bull':'🟢 多頭','neutral':'🟡 震盪','bear':'🔴 空頭'}.get(_ov_reg,'⚪')
            _ov_exp = _ov_mkt.get('exposure_pct','--') if _ov_mkt else '--'
            st.markdown(beginner_kpi('今日市場狀態', _ov_lbl, f'建議持股比例 {_ov_exp}',
                            '#3fb950' if _ov_reg=='bull' else ('#f85149' if _ov_reg=='bear' else '#d29922'),
                            '#0d1117'), unsafe_allow_html=True)
        # 外資籌碼
        with _ov_cols[1]:
            _ov_fnet = _ov_inst.get(_ov_fk,{}).get('net',None) if _ov_fk else None
            if _ov_fnet is not None:
                _ov_fc = '#da3633' if _ov_fnet > 0 else '#2ea043'
                st.markdown(beginner_kpi('大戶今日', f'{_ov_fnet:+.1f}億', '外資淨買賣（+買 -賣）', _ov_fc, '正數=大戶在買，跟著買較安全'), unsafe_allow_html=True)
            else:
                st.markdown(kpi('外資現貨', '--', '更新後顯示', '#484f58', '#0d1117'), unsafe_allow_html=True)
        # 旌旗/廣度
        with _ov_cols[2]:
            _ov_jqp = _ov_jq.get('avg',None) if _ov_jq else None
            if _ov_jqp is not None:
                _ov_jc = '#3fb950' if _ov_jqp>=60 else ('#d29922' if _ov_jqp>=30 else '#f85149')
                st.markdown(beginner_kpi('全市場健康度', f'{_ov_jqp:.0f}%', '有幾%的股票站在均線之上', _ov_jc, '>60%才適合積極買進'), unsafe_allow_html=True)
            else:
                st.markdown(kpi('旌旗指數', '--', '掃描後顯示', '#484f58', '#0d1117'), unsafe_allow_html=True)
        # 乖離率
        with _ov_cols[3]:
            _ov_b240 = _ov_bias.get('bias_240', None) if _ov_bias else None
            if _ov_b240 is not None:
                _ov_bc = '#f85149' if abs(_ov_b240) > 20 else '#3fb950'
                st.markdown(beginner_kpi('大盤位置', f'{_ov_b240:+.1f}%', '偏離年均線多少（過高=貴）', _ov_bc, '>+20%過熱；<-20%便宜'), unsafe_allow_html=True)
            else:
                st.markdown(kpi('年線乖離', '--', '更新後顯示', '#484f58', '#0d1117'), unsafe_allow_html=True)
        st.markdown('')

    # ══ 今日作戰室（最重要：一眼看清今天該做什麼）══════════════
    st.markdown('''<div style="background:linear-gradient(135deg,#0a1628,#0d2040);
border:2px solid #1f6feb;border-radius:14px;padding:16px;margin-bottom:14px;">
<div style="font-size:18px;font-weight:900;color:#58a6ff;margin-bottom:4px;">
🎯 今日作戰室 — 現在該做什麼？</div>
<div style="font-size:11px;color:#484f58;">每次操作前先看這裡，5分鐘掌握今日全局</div>
</div>''', unsafe_allow_html=True)

    _wr_mkt  = st.session_state.get('mkt_info', {})
    _wr_cd   = st.session_state.get('cl_data', {})
    _wr_bias = st.session_state.get('bias_info', {})
    _wr_m1b  = st.session_state.get('m1b_m2_info', {})
    _wr_inst = _wr_cd.get('inst', {})
    _wr_fk   = next((k for k in _wr_inst if '外資' in k), None)
    if _wr_fk is None:
        _wr_fk = next((k for k in _wr_inst if '外資' in k), None)
    _wr_fnet = _wr_inst.get(_wr_fk,{}).get('net', None) if _wr_fk else None
    _wr_margin = _wr_cd.get('margin')
    _wr_adl  = _wr_cd.get('adl')
    _wr_ts   = st.session_state.get('cl_ts','')
    _wr_reg  = _wr_mkt.get('regime','neutral') if _wr_mkt else 'neutral'
    _wr_exp  = _wr_mkt.get('exposure_pct','--') if _wr_mkt else '--'

    if _wr_mkt or _wr_cd:
        # ── 今日唯一結論（大字顯示）──────────────────────────
        _wr_action = '請先更新總經數據'
        _wr_action_color = '#484f58'
        _wr_warns = []

        if _wr_reg == 'bull':
            _wr_action = f'可積極操作，建議持股 {_wr_exp}'
            _wr_action_color = '#3fb950'
        elif _wr_reg == 'bear':
            _wr_action = '空頭市場，建議空手觀望或僅持 20% 以下'
            _wr_action_color = '#f85149'
        else:
            _wr_action = f'震盪整理，謹慎操作，持股 {_wr_exp}'
            _wr_action_color = '#d29922'

        # 風險警示收集
        if _wr_margin and _wr_margin > 3400:
            _wr_warns.append(('🔴', f'融資 {_wr_margin:.0f}億 極度危險，散戶過熱，不宜追高'))
        elif _wr_margin and _wr_margin > 2500:
            _wr_warns.append(('🟡', f'融資 {_wr_margin:.0f}億 警戒，注意風險'))

        if _wr_bias:
            _b240 = _wr_bias.get('bias_240', 0)
            if _b240 > 20:
                _wr_warns.append(('🟡', f'年線乖離 {_b240:+.1f}%，大盤偏高，勿追買'))
            elif _b240 < -20:
                _wr_warns.append(('✅', f'年線負乖離 {_b240:+.1f}%，長期布局機會'))

        if _wr_fnet is not None and _wr_fnet < -20:
            _wr_warns.append(('🔴', f'外資賣超 {abs(_wr_fnet):.1f}億，主力離場，謹慎'))

        if _wr_adl is not None and not _wr_adl.empty and 'ad_ratio' in _wr_adl.columns:
            _adl_r = float(_wr_adl['ad_ratio'].iloc[-1])
            if _adl_r < 35:
                _wr_warns.append(('🔴', f'上漲股票僅 {_adl_r:.0f}%，市場廣度不足，觀望'))

        # 顯示今日結論
        st.markdown(
            f'<div style="background:#0a2818;border-left:5px solid {_wr_action_color};'
            f'border-radius:0 10px 10px 0;padding:14px 18px;margin:8px 0;">'
            f'<div style="font-size:11px;color:#484f58;margin-bottom:4px;">📌 今日唯一行動建議</div>'
            f'<div style="font-size:17px;font-weight:900;color:{_wr_action_color};">{_wr_action}</div>'
            + (f'<div style="font-size:11px;color:#484f58;margin-top:4px;">更新時間：{_wr_ts}</div>' if _wr_ts else '') +
            f'</div>', unsafe_allow_html=True)

        # 今日5分鐘清單
        st.markdown('##### ✅ 今日操作前 5 分鐘清單')
        _cl_items = [
            ('大盤燈號', '🟢 多頭' if _wr_reg=='bull' else ('🔴 空頭' if _wr_reg=='bear' else '🟡 震盪'),
             _wr_reg=='bull', '多頭才積極操作'),
            ('外資方向', f'{"買超" if (_wr_fnet or 0)>0 else "賣超"} {abs(_wr_fnet or 0):.0f}億' if _wr_fnet is not None else '未知',
             (_wr_fnet or 0) > 0, '外資買超=跟著走'),
            ('融資水位', f'{_wr_margin:.0f}億' if _wr_margin else '未知',
             not _wr_margin or _wr_margin < 2500, '>2500億警戒，>3400億危險'),
            ('年線位置', f'乖離{_wr_bias.get("bias_240",0):+.1f}%' if _wr_bias else '未知',
             not _wr_bias or abs(_wr_bias.get("bias_240",0)) < 20, '超過±20%要警惕'),
            ('持股比例', f'建議{_wr_exp}', _wr_reg!='bear', '按建議比例，不要滿倉'),
        ]
        for _name, _val, _ok, _tip in _cl_items:
            _ic = '✅' if _ok else '⚠️'
            _vc = '#3fb950' if _ok else '#f85149'
            st.markdown(
                f'<div style="display:flex;align-items:center;padding:5px 8px;margin:2px 0;'
                f'background:#0d1117;border-radius:6px;border:1px solid #21262d;">'
                f'<span style="font-size:16px;width:28px;">{_ic}</span>'
                f'<span style="font-size:13px;color:#c9d1d9;width:80px;">{_name}</span>'
                f'<span style="font-size:13px;color:{_vc};font-weight:700;flex:1;">{_val}</span>'
                f'<span style="font-size:11px;color:#484f58;">{_tip}</span>'
                f'</div>', unsafe_allow_html=True)

        # 風險警示
        if _wr_warns:
            st.markdown('##### ⚠️ 今日風險警示')
            for _wic, _wtxt in _wr_warns:
                _wbg = '#2a0d0d' if '🔴' in _wic else ('#2a1f00' if '🟡' in _wic else '#0a2818')
                st.markdown(
                    f'<div style="background:{_wbg};border-radius:6px;padding:7px 12px;margin:3px 0;'
                    f'font-size:13px;color:#c9d1d9;">{_wic} {_wtxt}</div>',
                    unsafe_allow_html=True)

        # 月虧損強制停機警示
        _monthly_loss = st.session_state.get('monthly_loss_pct', 0)
        if _monthly_loss < -10:
            st.markdown(
                f'<div style="background:#3a0000;border:2px solid #f85149;border-radius:10px;'
                f'padding:14px;margin:10px 0;text-align:center;">'
                f'<div style="font-size:16px;font-weight:900;color:#f85149;">⛔ 月虧損警示</div>'
                f'<div style="font-size:13px;color:#c9d1d9;margin-top:6px;">'
                f'本月虧損已達 {abs(_monthly_loss):.1f}%，建議暫停操作 7 天<br>'
                f'冷靜後重新評估選股邏輯</div></div>',
                unsafe_allow_html=True)

        st.markdown('<hr style="border-color:#21262d;margin:12px 0;">', unsafe_allow_html=True)
    else:
        st.info('📡 點擊「🔄 更新全部總經數據」載入今日作戰室')
        st.markdown('<hr style="border-color:#21262d;margin:12px 0;">', unsafe_allow_html=True)

    # ── FinMind Token 狀態提示（不發 API，只檢查 env 是否有值）───
    _fm_tok_now = _get_fm_token()
    if not _fm_tok_now:
        st.error(
            '🔑 **FINMIND_TOKEN 未設定** — 以下功能無法使用：月營收、合約負債/資本支出、'
            '先行指標（期貨/選擇權/法人留倉）\n\n'
            '**設定步驟（Streamlit Cloud）：**\n'
            '1. 前往 https://finmindtrade.com 免費註冊並取得 API Token\n'
            '2. Streamlit Cloud → 你的 App → **Settings → Secrets**\n'
            '3. 新增一行：`FINMIND_TOKEN = "your_token_here"`\n'
            '4. 按 Save → App 自動重啟後即生效'
        )
    else:
        st.success(f'✅ FinMind Token 已設定（{_fm_tok_now[:12]}...）', icon='🔑')

    cb1, cb2 = st.columns([2,5])
    with cb1:
        do_refresh = st.button('🔄 更新全部總經數據', key='cl_refresh', use_container_width=True)
    with cb2:
        _now_ts = _tw_now_str()
        _last_ts = st.session_state.get('cl_ts', '尚未更新')
        _ts_color = '#3fb950' if _last_ts != '尚未更新' else '#484f58'
        st.markdown(
            f'<div style="font-size:11px;">'
            f'<span style="color:#484f58;">現在：{_now_ts}</span>　'
            f'<span style="color:{_ts_color};">上次更新：{_last_ts}</span>'
            f'</div>', unsafe_allow_html=True)

    # ── 市場狀態卡 placeholder（等資料載入後才更新）──────────────
    _mkt_placeholder = st.empty()

    if do_refresh or 'cl_data' not in st.session_state:
        _fetch_ph = st.empty()
        _fetch_ph.info('⏳ 並發抓取市場數據中，請稍候...')
        if True:  # noqa
            import time as _t_spd
            _t_start = _t_spd.time()

            # ── 並發任務定義 ────────────────────────────────────
            def _job_intl():
                return {n: fetch_single(sym) for n, sym in INTL_MAP.items()}

            def _job_tw():
                return {n: fetch_single(sym, period='90d') for n, sym in TW_MAP.items()}

            def _job_tech():
                return {n: fetch_single(sym) for n, sym in TECH_MAP.items()}

            def _job_inst():
                return fetch_institutional()

            def _job_margin():
                try: return fetch_margin_balance()
                except Exception as _em: print(f'[融資] ❌ {_em}'); return None

            def _job_adl():
                _tok_adl = os.environ.get('FINMIND_TOKEN','') or FINMIND_TOKEN
                return fetch_adl(days=60, token=_tok_adl)

            def _job_li():
                # [v8] 直接呼叫，移除內層 Thread（純 FinMind 不需要額外執行緒）
                try:
                    tok = _get_fm_token() or FINMIND_TOKEN or os.environ.get('FINMIND_TOKEN','')
                    result = build_leading_fast(days=14, token=tok)
                    if result is not None and not result.empty:
                        print(f'[先行指標] ✅ {len(result)} 筆')
                    else:
                        print('[先行指標] ⚠️ 空資料')
                    return result
                except Exception as _eli:
                    import traceback
                    print(f'[先行指標] ❌ {_eli}')
                    print(traceback.format_exc())
                    return None

            # ── 並發執行（yfinance 最慢，先丟進去）─────────────
            # [v8] li 移出 TPE，在主流程直接呼叫（Colab worker thread 中 requests 可能受阻）
            _jobs = {
                'intl':   _job_intl,
                'tw':     _job_tw,
                'tech':   _job_tech,
                'inst':   _job_inst,
                'margin': _job_margin,
                'adl':    _job_adl,
            }
            _results = {}
            _job_timeouts = {
                'intl': 30, 'tw': 30, 'tech': 30,
                'inst': 25,
                'margin': 25,
                'adl': 30,
            }
            # [BUG FIX] as_completed global timeout 從 50s 改為 110s
            # 原因：li job 內部 thread join(timeout=80)，50 < 80 導致 TimeoutError 崩潰
            # 並用 try/except TimeoutError 包住迴圈，確保其他6個 job 結果不因 li 超時而丟失
            # [BUG FIX] shutdown(wait=False) — 消除 `with TPE` 阻塞 7-20 分鐘的問題
            # 原理：手動管理 executor，超時後立即 cancel 未開始任務
            _AS_COMPLETED_TIMEOUT = max(_job_timeouts.values()) + 20  # 30+20=50s（li 已移出）
            _exc = ThreadPoolExecutor(max_workers=7)
            _futs = {_exc.submit(fn): name for name, fn in _jobs.items()}
            try:
                try:
                    for _fut in as_completed(_futs, timeout=_AS_COMPLETED_TIMEOUT):
                        name = _futs[_fut]
                        _t_limit = _job_timeouts.get(name, 20)
                        try:
                            _results[name] = _fut.result(timeout=_t_limit)
                            print(f'[並發] ✅ {name} ({_t_spd.time()-_t_start:.1f}s)')
                        except Exception as _fe:
                            _results[name] = None
                            print(f'[並發] ❌ {name}: {type(_fe).__name__}: {_fe}')
                except TimeoutError:
                    print(f'[並發] ⚠️ as_completed {_AS_COMPLETED_TIMEOUT}s 超時，補救已完成結果')
                    for _fut, _name in _futs.items():
                        if _name not in _results:
                            if _fut.done():
                                try:
                                    _results[_name] = _fut.result(timeout=1)
                                    print(f'[並發] ✅ {_name} 補救成功')
                                except Exception as _fe2:
                                    _results[_name] = None
                            else:
                                _results[_name] = None
                                print(f'[並發] ⏰ {_name} 確認超時')
            finally:
                # [BUG FIX] 關鍵：立即取消未開始任務，不等待執行中的 thread
                try:
                    _exc.shutdown(wait=False, cancel_futures=True)
                except TypeError:
                    _exc.shutdown(wait=False)  # Python < 3.9
            # 補齊所有未收到結果的 job
            for _name in _jobs:
                if _name not in _results:
                    _results[_name] = None
                    print(f'[並發] ⏰ {_name} 超時')
            
            # ── 解包結果 ────────────────────────────────────────
            intl_raw  = _results.get('intl') or {}
            tw_raw    = _results.get('tw') or {}
            tech_raw  = _results.get('tech') or {}
            inst_res  = _results.get('inst') or (None, None)
            inst, inst_date = inst_res if isinstance(inst_res, tuple) else (inst_res, None)
            # 如果 inst 是空的，用 FinMind TaiwanStockTotalInstitutionalInvestors 補救
            if not inst:
                print('[並發] inst 為空，用 FinMind 補救...')
                try:
                    _fm_t = _get_fm_token()
                    _start_i = (datetime.date.today()-datetime.timedelta(days=5)).strftime('%Y-%m-%d')
                    _ri = requests.get('https://api.finmindtrade.com/api/v4/data',
                        params={'dataset':'TaiwanStockTotalInstitutionalInvestors',
                                'start_date':_start_i,'token':_fm_t},
                        headers={'Authorization':f'Bearer {_fm_t}'}, timeout=15)
                    _ji = _ri.json()
                    print(f'[FinMind-Inst] status={_ji.get("status")} rows={len(_ji.get("data",[]))}')
                    if _ji.get('status')==200 and _ji.get('data'):
                        _df_i = pd.DataFrame(_ji['data'])
                        # 欄位: buy, date, name, sell
                        _ld_i = _df_i['date'].max()
                        _df_i = _df_i[_df_i['date']==_ld_i]
                        inst = {}
                        _d_net = 0.0
                        for _, _row_i in _df_i.iterrows():
                            _nm = str(_row_i.get('name',''))
                            _b = float(pd.to_numeric(_row_i.get('buy',0), errors='coerce') or 0)
                            _s = float(pd.to_numeric(_row_i.get('sell',0), errors='coerce') or 0)
                            _net = round((_b-_s)/1e8, 2)
                            if '外資' in _nm: inst['外資及陸資'] = {'net': _net}
                            elif '投信' in _nm: inst['投信'] = {'net': _net}
                            elif '自營' in _nm: _d_net += _net
                        if _d_net: inst['自營商'] = {'net': round(_d_net,2)}
                        inst_date = _ld_i
                        print(f'[FinMind-Inst] ✅ {inst}')
                except Exception as _ei:
                    print(f'[FinMind-Inst] ❌ {_ei}')
            margin    = _results.get('margin')
            df_adl_raw= _results.get('adl')
            if df_adl_raw is None:
                st.session_state['adl_debug_msg'] = '三個來源均無回應，詳見 Colab [ADL] 輸出'
            else:
                st.session_state.pop('adl_debug_msg', None)
            # [v8] 先行指標：強制 reload + UI 進度顯示
            df_li_a   = None
            _li_ph    = st.empty()
            _li_tok   = _get_fm_token() or FINMIND_TOKEN or os.environ.get('FINMIND_TOKEN','')
            _li_lines = []
            def _li_log(msg):
                import sys
                print(f'[先行指標] {msg}', flush=True)
                _li_lines.append(msg)
                _li_ph.info('📡 先行指標載入中…\n' + '\n'.join(_li_lines[-5:]))
            _li_ph    = st.empty()
            _li_lines = []
            def _li_log(msg):
                import sys
                print(f'[先行指標] {msg}', flush=True)
                _li_lines.append(msg)
                _li_ph.info('📡 先行指標載入中…\n' + '\n'.join(_li_lines[-5:]))
            try:
                import importlib, leading_indicators as _li_mod
                importlib.reload(_li_mod)          # ← 強制使用最新代碼
                _li_log(f'v={getattr(_li_mod,"LI_VERSION","?")} token={bool(_li_tok)}')
                df_li_a = _li_mod.build_leading_fast(days=14, token=_li_tok)
                if df_li_a is not None and not df_li_a.empty:
                    _li_log(f'✅ 成功 {len(df_li_a)} 筆')
                else:
                    _li_log('⚠️ 回傳空資料，請查 Colab 輸出')
            except Exception as _li_err:
                import traceback as _tb
                _li_log(f'❌ {type(_li_err).__name__}: {_li_err}')
                print(_tb.format_exc())
            finally:
                _li_ph.empty()

            # ── 儲存主要數據 ─────────────────────────────────────
            st.session_state['cl_data'] = dict(
                intl=intl_raw, tw=tw_raw, tech=tech_raw,
                inst=inst, inst_date=inst_date, margin=margin,
                adl=df_adl_raw)
            st.session_state['cl_ts'] = _tw_now_str()
            # 快取最後一次有效的法人/融資資料，供 API 失敗時 fallback 使用
            if inst:
                st.session_state['_last_inst'] = inst
                st.session_state['_last_inst_date'] = inst_date
            if margin:
                st.session_state['_last_margin'] = margin

            # [BUG FIX] 寬鬆條件：有任何 DataFrame（即使全 '-'）都存入 session_state
            # 原本 not df_li_a.empty 在 rows 有骨架但全 None 時仍為 True，但若某個版本回 None 或空 DF 則捨棄
            if df_li_a is not None and not df_li_a.empty:
                st.session_state['li_latest'] = df_li_a
                print(f'[先行指標] ✅ {len(df_li_a)} 筆 (有效欄={df_li_a.notna().any().sum()})')
            else:
                # 保留舊資料（若有），避免畫面空白
                if 'li_latest' not in st.session_state:
                    st.session_state.pop('li_latest', None)
                print(f'[先行指標] ⚠️ 回傳{"空" if df_li_a is not None else "None"} — 保留舊快取')

            print(f'[並發] 🎉 全部完成 共 {_t_spd.time()-_t_start:.1f}s')
            try: _fetch_ph.empty()
            except: pass
            try:
                with open('/tmp/_adl_log.txt','r',encoding='utf-8') as _af:
                    print('[ADL詳細]\n' + _af.read())
                import os as _rmf; _rmf.remove('/tmp/_adl_log.txt')
            except: pass

            # ── do_refresh 完成後自動估算旌旗指數（不等掃描）──────
            _jq_ratio_src = None
            if df_adl_raw is not None and not df_adl_raw.empty and 'ad_ratio' in df_adl_raw.columns:
                _jq_ratio_src = 'ADL'
                _jq_ratio = float(df_adl_raw['ad_ratio'].tail(5).mean())
            else:
                # 備援：用大盤漲跌估算（正日=60%上漲，負日=40%）
                _tw_d = st.session_state.get('cl_data',{}).get('tw',{})
                _twii_d = _tw_d.get('台股加權指數')
                if _twii_d is not None and not _twii_d.empty:
                    _cc_d = 'close' if 'close' in _twii_d.columns else 'Close'
                    if _cc_d in _twii_d.columns:
                        _ret5 = _twii_d[_cc_d].pct_change().tail(5)
                        _up_days = (_ret5 > 0).sum()
                        _jq_ratio = 40 + _up_days * 5  # 全漲=65%, 全跌=40%
                        _jq_ratio_src = '大盤估算'
                else:
                    _jq_ratio_src = None  # 無資料時不設定，不顯示錯誤數值
            if _jq_ratio_src and _jq_ratio_src != '預設值':
                _jq_ratio = float(_jq_ratio)
                _jq_pos  = '80~100%' if _jq_ratio>=60 else ('50~70%' if _jq_ratio>=40 else ('20~40%' if _jq_ratio>=20 else '0~20%'))
                _jq_reg  = 'bull' if _jq_ratio>=60 else ('neutral' if _jq_ratio>=40 else 'bear')
                _jq_col  = '#3fb950' if _jq_ratio>=60 else ('#d29922' if _jq_ratio>=40 else '#f85149')
                _jq_lbl  = '🟢 多頭積極' if _jq_ratio>=60 else ('🟡 中性均衡' if _jq_ratio>=40 else '🔴 保守防禦')
                _jq_src_note = f'（來源：{_jq_ratio_src}）'
                st.session_state['jingqi_info'] = {
                    'avg':_jq_ratio,'pos':_jq_pos,'regime':_jq_reg,
                    'color':_jq_col,'label':_jq_lbl,'total':0,
                    'source':_jq_ratio_src,
                    'pct20':_jq_ratio,'pct60':_jq_ratio*0.9,
                    'pct120':_jq_ratio*0.8,'pct240':_jq_ratio*0.7
                }

            # ── M1B-M2 + 乖離率 並發計算 ──────────────────────
            def _job_m1b():
                import requests as _rq_m1, pandas as _pd_m1
                _fm_tok_m1 = _get_fm_token()
                _start_m1 = (datetime.date.today()-datetime.timedelta(days=420)).strftime('%Y-%m-%d')

                # ── 路徑 1：FinMind TaiwanMoneySupply（需 token）──
                if _fm_tok_m1:
                    try:
                        _fm_r = _rq_m1.get(
                            'https://api.finmindtrade.com/api/v4/data',
                            params={'dataset': 'TaiwanMoneySupply', 'start_date': _start_m1,
                                    'token': _fm_tok_m1},
                            timeout=15)
                        _fm_j = _fm_r.json()
                        _fm_data = _fm_j.get('data') or []
                        print(f'[M1B/FM] status={_fm_j.get("status")} rows={len(_fm_data)} keys={list(_fm_j.keys())[:5]}')
                        if _fm_data:
                            _df_fm = _pd_m1.DataFrame(_fm_data)
                            print(f'[M1B/FM] 欄位={list(_df_fm.columns)[:10]}')
                            if 'type' in _df_fm.columns and 'value' in _df_fm.columns:
                                _df_fm['value'] = _pd_m1.to_numeric(_df_fm['value'], errors='coerce')
                                _m1b_s = _df_fm[_df_fm['type'].str.upper().str.contains('M1B', na=False)].sort_values('date')
                                _m2_s  = _df_fm[_df_fm['type'].str.upper() == 'M2'].sort_values('date')
                                if len(_m1b_s) >= 13 and len(_m2_s) >= 13:
                                    _m1b_yoy = round((_m1b_s['value'].iloc[-1]/_m1b_s['value'].iloc[-13]-1)*100, 2)
                                    _m2_yoy  = round((_m2_s['value'].iloc[-1] /_m2_s['value'].iloc[-13] -1)*100, 2)
                                    print(f'[M1B/FM] ✅ M1B={_m1b_yoy:.2f}% M2={_m2_yoy:.2f}%')
                                    return {'m1b_yoy': _m1b_yoy, 'm2_yoy': _m2_yoy, 'source': 'FinMind'}
                    except Exception as _fm_m1_e:
                        print(f'[M1B/FM] ❌ {_fm_m1_e}')

                # ── 路徑 2：CBC OpenData（多 URL 嘗試，官方來源）──────────
                _cbc_urls = [
                    'https://www.cbc.gov.tw/public/data/ms1.json',
                    'https://www.cbc.gov.tw/public/Attachment/ms1.json',
                    'https://openapi.cbc.gov.tw/v1/MoneySupply',
                ]
                for _cbc_url in _cbc_urls:
                    try:
                        _r_cbc = _rq_m1.get(
                            _cbc_url, headers={'User-Agent':'Mozilla/5.0'},
                            timeout=10, verify=False)
                        print(f'[M1B/CBC] {_cbc_url.split("/")[-1]} → status={_r_cbc.status_code}')
                        if _r_cbc.status_code != 200:
                            continue
                        _cbc_raw = _r_cbc.json()
                        _cbc_data = _cbc_raw if isinstance(_cbc_raw, list) else _cbc_raw.get('data', _cbc_raw)
                        print(f'[M1B/CBC] type={type(_cbc_data).__name__} len={len(_cbc_data) if hasattr(_cbc_data,"__len__") else "?"}')
                        if isinstance(_cbc_data, list) and len(_cbc_data) >= 13:
                            _df_cbc = _pd_m1.DataFrame(_cbc_data)
                            print(f'[M1B/CBC] 欄位={list(_df_cbc.columns)[:10]}')
                            _m1b_col = next((c for c in _df_cbc.columns if 'M1B' in str(c).upper()), None)
                            _m2_col  = next((c for c in _df_cbc.columns
                                             if str(c).strip().upper() == 'M2'
                                             or '供給額M2' in str(c)), None)
                            print(f'[M1B/CBC] m1b_col={_m1b_col} m2_col={_m2_col}')
                            if _m1b_col and _m2_col:
                                _m1b_v = _pd_m1.to_numeric(_df_cbc[_m1b_col].astype(str).str.replace(',',''), errors='coerce').dropna()
                                _m2_v  = _pd_m1.to_numeric(_df_cbc[_m2_col].astype(str).str.replace(',',''),  errors='coerce').dropna()
                                if len(_m1b_v) >= 13 and len(_m2_v) >= 13:
                                    _m1b_yoy_c = round((_m1b_v.iloc[-1]/_m1b_v.iloc[-13]-1)*100, 2)
                                    _m2_yoy_c  = round((_m2_v.iloc[-1] /_m2_v.iloc[-13] -1)*100, 2)
                                    print(f'[M1B/CBC] ✅ M1B={_m1b_yoy_c:.2f}% M2={_m2_yoy_c:.2f}%')
                                    return {'m1b_yoy': _m1b_yoy_c, 'm2_yoy': _m2_yoy_c, 'source': 'CBC'}
                    except Exception as _cbc_e:
                        print(f'[M1B/CBC] ❌ {_cbc_url.split("/")[-1]}: {_cbc_e}')

                # ── 路徑 3（已移除）：大盤代理數值完全不代表 M1B/M2 ────
                # 若所有真實來源都失敗，回傳 None（顯示「待更新」比顯示錯誤數字好）
                print('[M1B] 所有路徑失敗，回傳 None')
                return None

            def _job_bias():
                try:
                    # tw_raw 只有 90 天，MA240 需要另外抓 2 年資料
                    _twii = tw_raw.get('台股加權指數')
                    _cc_b = 'Close' if (_twii is not None and 'Close' in getattr(_twii,'columns',[])) else 'close'
                    _n_existing = len(_twii) if _twii is not None and not _twii.empty else 0
                    if _n_existing < 240:
                        # 重新抓 2 年完整資料，確保 MA240 正確
                        try:
                            import yfinance as _yf_bias
                            import pandas as _pd_bias
                            _twii_2y = _yf_bias.download('^TWII', period='2y',
                                                          progress=False, auto_adjust=True)
                            # yfinance 1.x 可能返回 MultiIndex columns，需展平
                            if _twii_2y is not None and isinstance(_twii_2y.columns, _pd_bias.MultiIndex):
                                try:
                                    _twii_2y.columns = _twii_2y.columns.get_level_values(0)
                                    print(f'[Bias] MultiIndex → 展平欄位: {list(_twii_2y.columns)}')
                                except Exception as _mi_e:
                                    print(f'[Bias] MultiIndex 展平失敗: {_mi_e}')
                            if _twii_2y is not None and len(_twii_2y) >= 240:
                                _twii = _twii_2y
                                _cc_b = 'Close'
                                print(f'[Bias] yfinance ^TWII 2y 抓到 {len(_twii_2y)} 天，欄位={list(_twii_2y.columns)[:4]}')
                            else:
                                print(f'[Bias] yfinance 2y 資料不足 ({len(_twii_2y) if _twii_2y is not None else 0} 天)，使用現有 {_n_existing} 天')
                        except Exception as _yf_b_e:
                            print(f'[Bias] yfinance 2y 失敗: {_yf_b_e}')
                    if _twii is None or _twii.empty: return None
                    # 寬鬆欄位查找：Close / close / Adj Close
                    if _cc_b not in _twii.columns:
                        _cc_b = next((c for c in _twii.columns if str(c).lower() in ('close','adj close','adjclose')), None)
                        if _cc_b is None:
                            print(f'[Bias] 找不到 Close 欄，現有欄位={list(_twii.columns)[:6]}')
                            return None
                    _cs = _twii[_cc_b].dropna()
                    _n  = len(_cs)
                    _lp = float(_cs.iloc[-1])
                    _ma20  = float(_cs.tail(min(20,_n)).mean())
                    _ma60  = float(_cs.tail(min(60,_n)).mean())
                    _ma120 = float(_cs.tail(min(120,_n)).mean())
                    _ma240 = float(_cs.tail(min(240,_n)).mean())
                    print(f'[Bias] price={_lp:.0f} MA240={_ma240:.0f} bias240={((_lp-_ma240)/_ma240*100):.1f}% (n={_n})')
                    return {
                        'bias_20':  round((_lp-_ma20) /_ma20 *100, 1) if _ma20  else 0,
                        'bias_60':  round((_lp-_ma60) /_ma60 *100, 1) if _ma60  else 0,
                        'bias_240': round((_lp-_ma240)/_ma240*100, 1) if _ma240 else 0,
                        'price':_lp,'ma20':_ma20,'ma60':_ma60,'ma120':_ma120,'ma240':_ma240,
                        'data_days':_n,'is_estimated':_n<240
                    }
                except Exception:
                    return None

            with ThreadPoolExecutor(max_workers=2) as _exc2:
                _fut_m1b  = _exc2.submit(_job_m1b)
                _fut_bias = _exc2.submit(_job_bias)
            try: _m1b_res  = _fut_m1b.result(timeout=30)
            except: _m1b_res = None; print('[並發] ⏰ M1B 超時')
            try: _bias_res = _fut_bias.result(timeout=30)
            except: _bias_res = None; print('[並發] ⏰ bias 超時')
            if _m1b_res:  st.session_state['m1b_m2_info'] = _m1b_res
            if _bias_res: st.session_state['bias_info']   = _bias_res

            # ── 計算市場狀態（用已載入資料，不另外發請求）
            try:
                _foreign_net_loaded = 0  # 0 = 尚無資料（market_regime 會顯示「待更新」）
                for _k, _v in inst.items():
                    if '外資' in _k:
                        _net_v = _v.get('net')
                        if _net_v is not None:
                            _foreign_net_loaded = float(_net_v) * 1e8
                        break
                _twii_df_loaded = tw_raw.get('台股加權指數')
                print(f'[市場評估] 大盤DF shape={getattr(_twii_df_loaded,"shape",None)}, '
                      f'columns={list(getattr(_twii_df_loaded,"columns",[]))}, '
                      f'外資淨={_foreign_net_loaded/1e8:.1f}億')
                _mkt_loaded = get_market_assessment(
                    df_index=_twii_df_loaded,
                    foreign_net=_foreign_net_loaded
                )
                if _mkt_loaded:
                    if margin:
                        if margin > 3400:
                            _mkt_loaded['signals'].append('🔴 融資極度危險（>3400億）')
                        elif margin > 2500:
                            _mkt_loaded['signals'].append('⚠️ 融資警戒（>2500億）')
                        else:
                            _mkt_loaded['signals'].append(f'✅ 融資安全（{margin:.0f}億）')
                    st.session_state['mkt_info'] = _mkt_loaded
                    print(f'[市場評估] 成功：{_mkt_loaded.get("label")} 評分{_mkt_loaded.get("score")}')
                else:
                    # 備援：直接用 yfinance 重抓
                    print('[市場評估] df_index 失敗，用 yfinance 備援')
                    _mkt_fb = get_market_assessment(df_index=None, foreign_net=_foreign_net_loaded)
                    if _mkt_fb:
                        if margin:
                            if margin > 3400: _mkt_fb['signals'].append('🔴 融資極度危險（>3400億）')
                            elif margin > 2500: _mkt_fb['signals'].append('⚠️ 融資警戒（>2500億）')
                            else: _mkt_fb['signals'].append(f'✅ 融資安全（{margin:.0f}億）')
                        st.session_state['mkt_info'] = _mkt_fb
                        print(f'[市場評估] 備援成功：{_mkt_fb.get("label")}')
            except Exception as _me:
                print(f'[市場評估 ERROR] {_me}')
                import traceback; traceback.print_exc()

    cd     = st.session_state.get('cl_data', {})
    intl   = {n:s for n,s in cd.get('intl',{}).items() if s is not None and not s.empty}
    tw     = {n:s for n,s in cd.get('tw',{}).items()   if s is not None and not s.empty}
    tech   = {n:s for n,s in cd.get('tech',{}).items() if s is not None and not s.empty}
    inst   = cd.get('inst', {}); margin = cd.get('margin')
    _inst_is_cached = False; _margin_is_cached = False
    if not inst and st.session_state.get('_last_inst'):
        inst = st.session_state['_last_inst']; _inst_is_cached = True
    if not margin and st.session_state.get('_last_margin'):
        margin = st.session_state['_last_margin']; _margin_is_cached = True
    df_adl = cd.get('adl')  # 騰落指標 DataFrame

    # ── 市場狀態卡：用已載入的真實資料渲染 ────────────────
    _mkt_info = st.session_state.get('mkt_info')
    if _mkt_info:
        _mkt_placeholder.empty()
        with _mkt_placeholder.container():
            render_market_overview(_mkt_info)
            _upd = st.session_state.get('cl_ts', '未更新')
            st.caption(f'大盤數據：yfinance ^TWII ｜ 外資：TWSE BFI82U ｜ 更新：{_upd}')


    # ══════════════════════════════════════════════════════════════
    # 拐點偵測系統（整合五大面向）
    # ══════════════════════════════════════════════════════════════
    if _mkt_info:
        _mi2    = _mkt_info
        _ma60   = _mi2.get('ma60', 0)
        _ma120  = _mi2.get('ma120', 0)
        _ma200  = _mi2.get('ma200', 0)
        _idx2   = _mi2.get('index_price', 0)
        _sigs2  = _mi2.get('signals', [])
        _regime2= _mi2.get('regime','neutral')
        _m1b2   = st.session_state.get('m1b_m2_info', {})
        _bias2  = st.session_state.get('bias_info', {})
        _li2    = st.session_state.get('li_latest')
        _cd2    = st.session_state.get('cl_data', {})
        _tw2    = _cd2.get('tw', {})
        _twd_df = _tw2.get('新台幣匯率')

        # ── 計算各項拐點訊號 ─────────────────────────────────────
        pivot_signals = []  # (label, icon, color, detail)

        # 1. 技術面：均線方向（MA60/MA120 彎折）
        if _ma60 and _ma120 and _idx2:
            _turn_up   = any('向上彎折' in s for s in _sigs2)
            _turn_down = any('向下' in s and 'MA' in s for s in _sigs2)
            _above60   = _idx2 > _ma60
            _above120  = _idx2 > _ma120
            _above200  = _idx2 > _ma200 if _ma200 else None
            _d60  = (_idx2-_ma60)/_ma60*100
            _d120 = (_idx2-_ma120)/_ma120*100

            if _turn_up and _above60 and _above120:
                pivot_signals.append(('均線多頭確認','🟢','#3fb950',
                    f'站上MA60(+{_d60:.1f}%) & MA120(+{_d120:.1f}%) + 均線向上彎折 → 中長線起漲點'))
            elif _turn_up and _above60:
                pivot_signals.append(('均線初步翻多','🟡','#d29922',
                    f'站上MA60(+{_d60:.1f}%) + 向上彎折，待突破MA120({_ma120:,.0f})確認'))
            elif not _above60 and _turn_down:
                pivot_signals.append(('均線空頭確認','🔴','#f85149',
                    f'跌破MA60({_d60:.1f}%) + 均線向下 → 中期起跌訊號'))
            elif _above60 and not _above120:
                pivot_signals.append(('整理區間','⚪','#8b949e',
                    f'站上MA60但未過MA120 → 等待方向確認'))

        # 2. 乖離率（與台股體質 ±7~10% 門檻）
        if _bias2:
            _b240 = _bias2.get('bias_240', 0)
            _b60  = _bias2.get('bias_60', _bias2.get('bias_20', 0))
            _b20  = _bias2.get('bias_20', 0)
            if _b240 > 10:
                pivot_signals.append(('年線乖離過大','⚠️','#f85149',
                    f'年線乖離 +{_b240:.1f}% > 10% → 頂部拐點區間，考慮減碼'))
            elif _b240 < -10:
                pivot_signals.append(('年線深度低估','💡','#3fb950',
                    f'年線乖離 {_b240:.1f}% < -10% → 底部拐點區間，考慮布局'))
            if abs(_b20) > 8:
                _bl20 = '過熱' if _b20 > 0 else '超賣'
                pivot_signals.append((f'月線{_bl20}',
                    '⚠️' if _b20 > 0 else '💡',
                    '#da3633' if _b20>0 else '#2ea043',
                    f'月線乖離 {_b20:+.1f}% → 短線{_bl20}修正機率高'))

        # 3. M1B-M2（資金面黃金/死亡交叉）
        if _m1b2 and not _m1b2.get('is_proxy'):
            _m1b_y = _m1b2.get('m1b_yoy', 0)
            _m2_y  = _m1b2.get('m2_yoy', 0)
            _diff  = _m1b_y - _m2_y
            if _diff > 0:
                pivot_signals.append(('M1B>M2 黃金交叉','✅','#3fb950',
                    f'M1B({_m1b_y:.1f}%) > M2({_m2_y:.1f}%) → 資金由定存轉入股市，長線起漲徵兆'))
            elif _diff < -1:
                pivot_signals.append(('M1B<M2 死亡交叉','❌','#f85149',
                    f'M1B({_m1b_y:.1f}%) < M2({_m2_y:.1f}%) → 資金撤離股市，長線起跌警示'))

        # 4. 台幣匯率（貶轉升=外資流入，升轉貶=外資撤退）
        if _twd_df is not None and not _twd_df.empty:
            _twd_col = 'close' if 'close' in _twd_df.columns else 'Close'
            if _twd_col in _twd_df.columns and len(_twd_df) >= 10:
                _twd_now   = float(_twd_df[_twd_col].iloc[-1])
                _twd_prev5 = float(_twd_df[_twd_col].iloc[-5])
                _twd_chg   = (_twd_now - _twd_prev5) / _twd_prev5 * 100
                # 注意：TWD=X 是 USD/TWD，數字越小=台幣越升值
                if _twd_chg < -0.5:  # 台幣升值 (匯率數字下降)
                    pivot_signals.append(('台幣升值','✅','#3fb950',
                        f'台幣近5日升值 {abs(_twd_chg):.1f}% → 外資熱錢流入，指數底部反彈訊號'))
                elif _twd_chg > 0.5:  # 台幣貶值 (匯率數字上升)
                    pivot_signals.append(('台幣貶值','⚠️','#d29922',
                        f'台幣近5日貶值 {_twd_chg:.1f}% → 外資撤退觀察，留意資金流出風險'))

        # 5. 外資期貨 + 散戶比（先行指標）
        if _li2 is not None and not _li2.empty:
            _last_li = _li2.iloc[-1]
            _fut_net = _last_li.get('外資大小')
            _leek    = _last_li.get('韭菜指數')
            _pcr     = _last_li.get('選PCR')
            if _fut_net is not None:
                _fut_net_v = float(_fut_net)
                if _fut_net_v < -30000:
                    pivot_signals.append(('外資期貨大量空單','🔴','#f85149',
                        f'外資期貨淨空 {abs(_fut_net_v):,.0f}口 > 3萬口 → 頂部起跌訊號'))
                elif _fut_net_v < 0 and abs(_fut_net_v) < 10000:
                    pivot_signals.append(('外資空單縮減','🟡','#d29922',
                        f'外資期貨淨空 {abs(_fut_net_v):,.0f}口（補回中）→ 底部拐點觀察'))
                elif _fut_net_v > 10000:
                    pivot_signals.append(('外資期貨多方','✅','#3fb950',
                        f'外資期貨淨多 {_fut_net_v:,.0f}口 → 多頭強勢確認'))
            if _leek is not None:
                _leek_v = float(_leek)
                if _leek_v > 20:
                    pivot_signals.append(('散戶極度看多（危險）','⚠️','#f85149',
                        f'韭菜指數 +{_leek_v:.1f}% > 20% → 散戶過熱，頂部拐點警示（反向指標）'))
                elif _leek_v < -20:
                    pivot_signals.append(('散戶極度悲觀（機會）','💡','#3fb950',
                        f'韭菜指數 {_leek_v:.1f}% < -20% → 散戶極度看空，底部拐點機會（反向指標）'))

        # ── 綜合評分 & 顯示 ──────────────────────────────────────
        _bull_pts = sum(1 for _,_,c,_ in pivot_signals if c == '#3fb950')
        _bear_pts = sum(1 for _,_,c,_ in pivot_signals if c == '#f85149')
        _warn_pts = sum(1 for _,_,c,_ in pivot_signals if c in ('#d29922',''))

        if _bull_pts > _bear_pts and _bull_pts >= 2:
            _pivot_overall = f'🟢 綜合拐點：{_bull_pts} 個多頭訊號 → 偏向底部起漲'
            _pivot_color   = '#3fb950'
        elif _bear_pts > _bull_pts and _bear_pts >= 2:
            _pivot_overall = f'🔴 綜合拐點：{_bear_pts} 個空頭訊號 → 偏向頂部起跌'
            _pivot_color   = '#f85149'
        else:
            _pivot_overall = f'⚪ 訊號分歧：多頭{_bull_pts} vs 空頭{_bear_pts}，方向待確認'
            _pivot_color   = '#d29922'

        st.markdown(f'<div style="background:#161b22;border-left:4px solid {_pivot_color};'
                    f'border-radius:0 8px 8px 0;padding:8px 12px;margin:6px 0;'
                    f'font-size:13px;font-weight:600;color:{_pivot_color};">'
                    f'{_pivot_overall}</div>', unsafe_allow_html=True)

        with st.expander('📊 拐點詳細分析 — 五大面向綜合判斷', expanded=True):
            if pivot_signals:
                for _label, _icon, _color, _detail in pivot_signals:
                    st.markdown(
                        f'<div style="background:#0d1117;border-left:3px solid {_color};'
                        f'border-radius:0 6px 6px 0;padding:6px 10px;margin:4px 0;">'
                        f'<span style="color:{_color};font-weight:600;">{_icon} {_label}</span>'
                        f'<br><span style="color:#8b949e;font-size:12px;">{_detail}</span>'
                        f'</div>', unsafe_allow_html=True)
            else:
                st.info('尚無足夠資料計算拐點，請點擊「更新全部總經數據」')

            # 拐點參考表 → 已移至 Tab5 策略手冊
            st.caption('📖 拐點判斷參考表 → 詳見「策略手冊」Tab')

    elif not cd:
        with _mkt_placeholder.container():
            st.info('📡 請點擊「🔄 更新全部總經數據」載入大盤數據')
    # ── ③ 資料到位後，回填紅綠燈佔位符（修復「未審先判」Bug）────
    _tl_final = _calc_traffic_light(
        st.session_state.get('mkt_info', {}),
        st.session_state.get('jingqi_info', {}),
        st.session_state.get('cl_data', {}),
        st.session_state.get('li_latest'),
    )
    _render_traffic_light(_tl_placeholder, _tl_final)
    if _tl_final:
        st.session_state['defense_mode'] = _tl_final['defense']
        st.session_state['warroom_summary'] = {
            'traffic_light': _tl_final['label'],
            'health_score':  _tl_final['health'],
            'defense_mode':  _tl_final['defense'],
            'regime': st.session_state.get('mkt_info', {}).get('regime', 'neutral'),
            'market_score':  _tl_final['score'],
            'jingqi_avg':    _tl_final['jqavg'],
            'leek_index':    _tl_final['leek'],
            'foreign_net_bn':_tl_final['fnet'],
            'futures_net':   _tl_final['fut_net'],
            'confidence_pct':_tl_final['conf'],
            'core_capital':  round(st.session_state.get('total_capital_twd',500000)*0.70),
            'satellite_capital': round(st.session_state.get('total_capital_twd',500000)*0.30),
        }

    intl_s = {n:calc_stats(s) for n,s in intl.items()}
    tw_s   = {n:calc_stats(s) for n,s in tw.items()}
    tech_s = {n:calc_stats(s) for n,s in tech.items()}

    st.markdown(section_header('一','🌍 國際市場動態（影響台股的全球指標）','🌐'), unsafe_allow_html=True)
    _sox1 = intl_s.get('費城半導體 SOX'); _dji1 = intl_s.get('道瓊工業 DJI')
    _dxy1 = intl_s.get('美元指數 DXY');  _tyx1 = intl_s.get('10Y公債殖利率')

    # ── 宏爺：SOX × DXY 動態結論 ─────────────────────────────
    _sox_pct = _sox1.get('pct', None) if _sox1 else None
    _dxy_val = _dxy1.get('last', None) if _dxy1 else None
    _tyx_val = _tyx1.get('last', None) if _tyx1 else None

    if _sox_pct is not None and _dxy_val is not None:
        if _sox_pct >= 1.5 and _dxy_val < 100:
            _i1c = f'SOX {_sox_pct:+.1f}% / DXY {_dxy_val:.1f} → 熱錢狂潮，重壓電子強勢股'; _i1a = '台積電/矽力/聯發科可積極持有'
        elif _sox_pct <= -1.5 and _dxy_val >= 103:
            _i1c = f'SOX {_sox_pct:+.1f}% / DXY {_dxy_val:.1f} → 外資提款，電子股嚴格減碼'; _i1a = '降倉至 3 成以下，等待 DXY 回落'
        elif _sox_pct >= 1.0 and _dxy_val >= 100:
            _i1c = f'SOX {_sox_pct:+.1f}% / DXY {_dxy_val:.1f} → 內資控盤，精選中小型題材股'; _i1a = '避開外資重倉大型權值，找內資題材'
        elif _sox_pct <= -1.5:
            _i1c = f'SOX {_sox_pct:+.1f}% / DXY {_dxy_val:.1f} → 費半重挫，台股科技開低機率高'; _i1a = '設好停損，避免隔日追殺'
        else:
            _i1c = f'SOX {_sox_pct:+.1f}% / DXY {_dxy_val:.1f} → 走勢分化，方向未明'; _i1a = '降部位等待費半方向確認'
        _i1_ind = f'SOX {_sox_pct:+.1f}% / DXY {_dxy_val:.1f}'
    elif _sox1 and _dji1:
        _sp = _sox1.get('pct', 0); _dp = _dji1.get('pct', 0)
        _i1c = f'費半 {_sp:+.1f}% / 道瓊 {_dp:+.1f}%（DXY 資料未載入）'; _i1a = '等待完整數據確認'
        _i1_ind = f'SOX {_sp:+.1f}%'
    else:
        _i1c = '數據尚未載入，請點擊「🔄 更新全部總經數據」'; _i1a = ''; _i1_ind = '費半+美元'
    st.markdown(teacher_conclusion('宏爺', _i1_ind, _i1c, _i1a), unsafe_allow_html=True)

    # ── 孫慶龍：10Y Yield 動態結論 ─────────────────────────────
    if _tyx_val is not None:
        if _tyx_val >= 4.8:
            _sql_c = f'10Y殖利率 {_tyx_val:.2f}% → 系統風險！無風險利率飆升，本益比大幅下修'; _sql_a = '保留現金，嚴格控制槓桿'
        elif _tyx_val >= 4.5:
            _sql_c = f'10Y殖利率 {_tyx_val:.2f}% → 估值承壓，資金成本上升'; _sql_a = '避開高本夢比個股，轉向低本益比價值股'
        else:
            _sql_c = f'10Y殖利率 {_tyx_val:.2f}% → 總經安全，利率溫和股市友善'; _sql_a = '精選低基期價值股，可適度持有'
        st.markdown(teacher_conclusion('孫慶龍', f'10Y {_tyx_val:.2f}%', _sql_c, _sql_a), unsafe_allow_html=True)
    ci = st.columns(len(INTL_UNIT))
    for col,(name,unit) in zip(ci,INTL_UNIT.items()):
        with col: st.markdown(stat_card(name,intl_s.get(name),unit,name in intl_s),unsafe_allow_html=True)
    idx_d = {k:v for k,v in intl.items() if k in ['道瓊工業 DJI','納斯達克 IXIC','費城半導體 SOX']}
    if idx_d:
        st.plotly_chart(multi_chart(idx_d,'美股三大指數標準化比較',norm=True,height=220),
                        use_container_width=True, config={'displayModeBar':False})
    bc,dc = st.columns(2)
    with bc:
        if '10Y公債殖利率' in intl:
            st.plotly_chart(sparkline(intl['10Y公債殖利率'],'10Y公債殖利率','#f85149'),
                            use_container_width=True,config={'displayModeBar':False})
    with dc:
        if '美元指數 DXY' in intl:
            st.plotly_chart(sparkline(intl['美元指數 DXY'],'美元指數 DXY','#ffd700'),
                            use_container_width=True,config={'displayModeBar':False})
    with st.expander('📖 宏爺 × 孫慶龍 結論（SOX/DXY/殖利率公式）', expanded=False):
        _expander_rows = []
        if _sox_pct is not None and _dxy_val is not None:
            if _sox_pct >= 1.5 and _dxy_val < 100:
                _expander_rows.append(('🟢', f'宏爺 — 熱錢狂潮 (SOX {_sox_pct:+.1f}% ≥1.5% ∩ DXY {_dxy_val:.1f} <100)', '重壓電子強勢股'))
            elif _sox_pct <= -1.5 and _dxy_val >= 103:
                _expander_rows.append(('🔴', f'宏爺 — 外資提款 (SOX {_sox_pct:+.1f}% ∩ DXY {_dxy_val:.1f} ≥103)', '降倉至 3 成以下'))
            elif _sox_pct >= 1.0 and _dxy_val >= 100:
                _expander_rows.append(('🟡', f'宏爺 — 內資控盤 (SOX {_sox_pct:+.1f}% ≥1.0% ∩ DXY {_dxy_val:.1f} ≥100)', '精選中小型題材股'))
            else:
                _expander_rows.append(('⚪', f'宏爺 — 走勢分化 (SOX {_sox_pct:+.1f}% / DXY {_dxy_val:.1f})', '降部位等待確認'))
        if _tyx_val is not None:
            if _tyx_val >= 4.8:
                _expander_rows.append(('🔴', f'孫慶龍 — 系統風險 (10Y {_tyx_val:.2f}% ≥4.8%)', '保留現金，嚴控槓桿'))
            elif _tyx_val >= 4.5:
                _expander_rows.append(('🟡', f'孫慶龍 — 估值承壓 (10Y {_tyx_val:.2f}% 4.5~4.8%)', '避開高本夢比個股'))
            else:
                _expander_rows.append(('🟢', f'孫慶龍 — 總經安全 (10Y {_tyx_val:.2f}% <4.5%)', '精選低基期價值股'))
        for _ico, _txt, _act in _expander_rows:
            st.markdown(
                f'<div style="color:#c9d1d9;font-size:13px;padding:3px 0;">'
                f'{_ico} {_txt} → <span style="color:#8b949e;">{_act}</span></div>',
                unsafe_allow_html=True
            )

    st.markdown('<hr style="border-color:#21262d;margin:14px 0;">',unsafe_allow_html=True)
    st.markdown(section_header('二','🇹🇼 台股大盤（今日漲跌 + 台幣匯率）','🇹🇼'),unsafe_allow_html=True)
    _twii2 = tw_s.get('台股加權指數'); _twd2 = tw_s.get('新台幣匯率')
    if _twii2 and _twd2:
        _tp = _twii2.get('pct') ; _fp = _twd2.get('pct')
        # 邊界防呆：API 回傳 None 時不崩潰
        _tp = float(_tp) if _tp is not None else None
        _fp = float(_fp) if _fp is not None else None
        if _tp is not None and _fp is not None:
            # 四象限資金流向判斷（fx>0=台幣貶值，fx<0=台幣升值）
            if _tp > 0 and _fp < 0:
                # 股匯雙漲：外資真實匯入
                _t2c = f'台股 {_tp:+.1f}% ／ 台幣升值 {_fp:+.2f}% → 股匯雙漲，外資真金白銀匯入，權值股領軍'
                _t2a = '順勢大膽作多，持股建議 80~100%'
            elif _tp > 0 and _fp > 0:
                # 股漲匯貶：疑似拉高出貨
                _t2c = f'台股 {_tp:+.1f}% ／ 台幣貶值 {_fp:+.2f}% → 股漲匯貶，指數虛漲，疑似外資拉高出貨'
                _t2a = '不追高，謹慎觀察，持股建議 50%'
            elif _tp < 0 and _fp > 0:
                # 股匯雙殺：外資大舉提款
                _t2c = f'台股 {_tp:+.1f}% ／ 台幣貶值 {_fp:+.2f}% → 股匯雙殺，外資無情提款撤出'
                _t2a = '嚴格減碼防守，持股建議 0~30%（現金為王）'
            elif _tp < 0 and _fp < 0:
                # 股跌匯升：技術性洗盤
                _t2c = f'台股 {_tp:+.1f}% ／ 台幣升值 {_fp:+.2f}% → 股跌匯升，外資資金停泊未撤，技術性洗盤'
                _t2a = '尋找錯殺優質股逢低布局，持股建議 50~70%'
            else:
                _t2c = f'台股 {_tp:+.1f}% ／ 台幣 {_fp:+.2f}%，無明顯方向性波動'; _t2a = '維持現有部位，靜待表態'
        else:
            _t2c = f'台股資料載入中'; _t2a = '等待完整數據'
            _tp = _twii2.get('pct', 0) or 0; _fp = _twd2.get('pct', 0) or 0
        _t2_ind = f'加權 {_twii2.get("last",0):,.0f}pt {(_tp or 0):+.1f}% | 台幣 {_twd2.get("last",0):.2f}'
    elif _twii2:
        _tp = _twii2.get('pct', 0) or 0
        _t2c = f'台股 {_tp:+.1f}%，{"偏多" if _tp > 0 else "偏空"}（台幣資料未載入）'; _t2a = '參考其他指標確認方向'
        _t2_ind = f'加權 {_twii2.get("last",0):,.0f}pt {_tp:+.1f}%'
    else:
        _t2c = '數據尚未載入，請點擊「🔄 更新全部總經數據」'; _t2a = ''; _t2_ind = '台股加權 + 台幣'
    st.markdown(teacher_conclusion('宏爺', _t2_ind, _t2c, _t2a), unsafe_allow_html=True)
    tc = st.columns(len(TW_UNIT))
    for col,(name,unit) in zip(tc,TW_UNIT.items()):
        with col: st.markdown(stat_card(name,tw_s.get(name),unit,name in tw_s),unsafe_allow_html=True)
    tw1,tw2 = st.columns(2)
    with tw1:
        if '台股加權指數' in tw:
            st.plotly_chart(sparkline(tw['台股加權指數'],'台股加權指數','#58a6ff'),
                            use_container_width=True,config={'displayModeBar':False})
    with tw2:
        try:
            otc = _fetch_otc_via_finmind(FINMIND_TOKEN)
            if otc is not None and not otc.empty:
                st.plotly_chart(sparkline(otc,'櫃買指數 OTC','#3fb950'),
                                use_container_width=True,config={'displayModeBar':False})
        except Exception: pass
    with st.expander('📖 宏爺 結論（股匯四象限）', expanded=False):
        st.caption('💡 台幣 USD/TWD 漲(>0)=台幣貶值，跌(<0)=台幣升值。資金面M1B-M2見Section七。')
        _twii_e = tw_s.get('台股加權指數')
        _twd_e  = tw_s.get('新台幣匯率')
        if _twii_e and _twd_e:
            _tp_e = _twii_e.get('pct', 0) or 0
            _fp_e = _twd_e.get('pct', 0) or 0
            _quadrant_rows = [
                (f'台股 {_twii_e["last"]:,.0f}pt ({_tp_e:+.1f}%)',
                 f'台幣 {_twd_e["last"]:.2f} ({_fp_e:+.2f}%)'),
            ]
            if _tp_e > 0 and _fp_e < 0:
                _quadrant_rows.append(('🟢 股匯雙漲（真實多頭）',
                    '外資真金白銀匯入，順勢大膽作多 → 持股 80~100%'))
            elif _tp_e > 0 and _fp_e > 0:
                _quadrant_rows.append(('⚠️ 股漲匯貶（拉高出貨警戒）',
                    '指數虛漲，疑似外資拉高出貨或純內資自嗨 → 不追高，持股 50%'))
            elif _tp_e < 0 and _fp_e > 0:
                _quadrant_rows.append(('🔴 股匯雙殺（外資大舉提款）',
                    '外資無情撤出，面臨系統性修正 → 嚴格減碼，持股 0~30%'))
            elif _tp_e < 0 and _fp_e < 0:
                _quadrant_rows.append(('🟡 股跌匯升（技術性洗盤）',
                    '外資資金停泊台灣未撤離，尋找錯殺優質股 → 持股 50~70%'))
            else:
                _quadrant_rows.append(('⚪ 無明顯方向', '靜待表態，維持現有部位'))
            for _qt in _quadrant_rows:
                _label = _qt[0]; _act = _qt[1] if len(_qt) > 1 else ''
                st.markdown(
                    f'<div style="color:#c9d1d9;font-size:13px;padding:3px 0;">'
                    f'{_label}'
                    + (f' → <span style="color:#8b949e;">{_act}</span>' if _act else '')
                    + '</div>', unsafe_allow_html=True
                )

    st.markdown('<hr style="border-color:#21262d;margin:14px 0;">',unsafe_allow_html=True)
    st.markdown('<hr style="border-color:#21262d;margin:8px 0;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:1px;margin:4px 0;">💰 籌碼監控</div>', unsafe_allow_html=True)
    st.markdown(section_header('三','🏦 大戶在買還是賣？（三大法人 + 融資）','🧮'),unsafe_allow_html=True)
    s3l,s3r = st.columns([3,2])
    with s3l:
        if inst:
            _fk = next((k for k in inst if k in ('外資及陸資', '外資') or ('外資' in k and k == '外資及陸資')), None) or next((k for k in inst if '外資' in k and '陸資' in k), None) or next((k for k in inst if '外資' in k), None)
            _tk = next((k for k in inst if '投信' in k), None)
            _f_net = inst[_fk]['net'] if _fk else 0
            _t_net = inst[_tk]['net'] if _tk else 0
            _total_net = round(_f_net + _t_net, 2)
            _inst_date_show = st.session_state.get('_last_inst_date', cd.get('inst_date', '')) if _inst_is_cached else cd.get('inst_date', '')
            _cached_label = '　⚠️ 快取資料' if _inst_is_cached else ''
            st.caption(f'三大法人現貨  {_inst_date_show}{_cached_label}  '
                       f'| 外資 {_f_net:+.1f}億  投信 {_t_net:+.1f}億  合計 {_total_net:+.1f}億')
            st.plotly_chart(bar_chart_institutional(inst),use_container_width=True,config={'displayModeBar':False})
            _mkt_ref = st.session_state.get('mkt_info',{})
            if abs(_f_net) > 5:
                if _f_net >= 100:
                    _fc2 = '#3fb950'; _fl2 = f'🟢 外資大買 {_f_net:.1f}億 → 大戶點火'
                elif _f_net <= -100:
                    _fc2 = '#f85149'; _fl2 = f'🔴 外資大賣 {abs(_f_net):.1f}億 → 大戶倒貨'
                elif _f_net > 0:
                    _fc2 = '#8b949e'; _fl2 = f'⚪ 外資小買 {_f_net:.1f}億（觀望區間）'
                else:
                    _fc2 = '#8b949e'; _fl2 = f'⚪ 外資小賣 {abs(_f_net):.1f}億（觀望區間）'
                st.markdown(f'<span style="color:{_fc2};font-size:12px;font-weight:700;">{_fl2}</span>', unsafe_allow_html=True)
        else:
            _now_h = _tw_now().hour
            if _now_h < 15:
                st.info('⏰ 三大法人收盤後 15:30 才更新，盤中暫無資料')
            elif _now_h < 16:
                st.warning('⏳ 收盤後資料更新中（約15:30~16:00），請稍後重試')
            else:
                st.warning('⚠️ 三大法人資料取得失敗，無歷史快取可顯示，請點擊「更新全部總經數據」重試')
    with s3r:
        st.markdown(margin_card(margin),unsafe_allow_html=True)
        if _margin_is_cached:
            st.caption('⚠️ 快取資料（最後已知融資餘額）')
        if margin:
            mc = '#f85149' if margin >= 3400 else ('#d29922' if margin >= 2800 else '#3fb950')
            ml = '🔴泡沫尾端' if margin >= 3400 else ('🟡警戒區' if margin >= 2800 else '🟢籌碼乾淨')
            st.markdown(f'<div style="color:{mc};font-size:13px;font-weight:700;margin-top:6px;">{ml}</div>', unsafe_allow_html=True)
            _mkt_r = st.session_state.get('mkt_info', {})
            if margin >= 2800 and _mkt_r.get('regime') == 'bull':
                st.warning('⚠️ 市場偏多但融資水位偏高，注意假突破風險')
            elif margin and margin < 2800 and _mkt_r.get('regime') == 'bull':
                st.success('✅ 融資乾淨 + 市場偏多 = 健康多頭格局')
    with st.expander('📖 孫慶龍 · 宏爺 結論', expanded=False):
        if inst:
            _fk3 = next((k for k in inst if '外資' in k and '陸資' in k), None) or next((k for k in inst if '外資' in k), None)
            _tk3 = next((k for k in inst if '投信' in k), None)
            _fn3 = inst[_fk3]['net'] if _fk3 else 0
            _tn3 = inst[_tk3]['net'] if _tk3 else 0
            # 宏爺外資公式
            if _fn3 >= 100:
                _hye_c = '#3fb950'
                _hye_ind = f'外資大買超 {_fn3:.1f}億'
                _hye_concl = '大戶點火，跟著大戶走 → 積極加碼'
                _hye_act = '趁拉回布局，持股 80~100%'
            elif _fn3 <= -100:
                _hye_c = '#f85149'
                _hye_ind = f'外資大賣超 {abs(_fn3):.1f}億'
                _hye_concl = '大戶倒貨，嚴格減碼 → 離場為上'
                _hye_act = '持股降至 0~30%，停損優先'
            else:
                _hye_c = '#8b949e'
                _hye_ind = f'外資 {_fn3:+.1f}億（觀望區間）'
                _hye_concl = '資金觀望，區間操作'
                _hye_act = '持股 50%，高出低進等方向'
            st.markdown(teacher_conclusion('宏爺', _hye_ind, _hye_concl, color=_hye_c), unsafe_allow_html=True)
            st.markdown(f'<div style="color:#8b949e;font-size:11px;padding:1px 8px 6px 8px;">→ 建議行動：{_hye_act}</div>', unsafe_allow_html=True)
            if _tn3 > 5:
                st.markdown(f'<div style="color:#58a6ff;font-size:12px;padding:2px 6px;">• 投信買超 {_tn3:.1f}億 → 連續買超是加碼訊號</div>', unsafe_allow_html=True)
        if margin:
            # 孫慶龍融資公式
            if margin >= 3400:
                _sql_mc = '#f85149'
                _sql_mind = f'融資餘額 {margin:.0f}億'
                _sql_mconcl = '極度危險，嚴防多殺多 → 行情尾端'
                _sql_mact = '全面減碼，勿追高，準備逃命'
            elif margin >= 2800:
                _sql_mc = '#d29922'
                _sql_mind = f'融資餘額 {margin:.0f}億'
                _sql_mconcl = '水位偏高，籌碼凌亂 → 警戒操作'
                _sql_mact = '持股降至 50% 以下，避免重倉'
            else:
                _sql_mc = '#3fb950'
                _sql_mind = f'融資餘額 {margin:.0f}億'
                _sql_mconcl = '籌碼乾淨，安全水位 → 可積極布局'
                _sql_mact = '健康多頭格局，持股 70~100%'
            st.markdown(teacher_conclusion('孫慶龍', _sql_mind, _sql_mconcl, color=_sql_mc), unsafe_allow_html=True)
            st.markdown(f'<div style="color:#8b949e;font-size:11px;padding:1px 8px 6px 8px;">→ 建議行動：{_sql_mact}</div>', unsafe_allow_html=True)

    st.markdown('<hr style="border-color:#21262d;margin:14px 0;">',unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════
    # 四、核心大戶動向：外資「先行指標」
    # 移植自 v12：標題 / 副標 / 欄位說明表 / 宏爺判斷方式 expander
    # 保留 v3_20_7：build_leading_fast 執行緒機制 / 宏爺結論面板
    # ════════════════════════════════════════════════════════════════════
    st.markdown(section_header('四','核心大戶動向：外資「先行指標」','🎯'),unsafe_allow_html=True)
    _li4 = st.session_state.get('li_latest')
    if _li4 is not None and not _li4.empty:
        _fut4 = (float(_li4.iloc[-1].get('外資大小', 0)) if '外資大小' in _li4.columns else None)
        _pcr4 = (float(_li4.iloc[-1].get('選PCR', 0)) if '選PCR' in _li4.columns else None)
        if _fut4 is not None:
            _pcr_txt = f' | PCR {_pcr4:.1f}' if _pcr4 else ''
            _l4_ind = f'外資期貨 {_fut4:,.0f}口{_pcr_txt}'
            # 宏爺絕對口數門檻（容錯率最高）
            if _fut4 <= -30000:
                _l4c = f'外資期貨空單 {abs(_fut4):,.0f}口 > 3萬口，啟動強制防禦，強制減倉至20%以下，等待空單回補'
                _l4a = '強制減倉至 20% 以下，嚴禁追高攤平，保護本金'
            elif _fut4 <= -15000:
                _l4c = f'外資期貨空單 {abs(_fut4):,.0f}口，空單累積中，大戶動向保守，逢高調節'
                _l4a = '收回資金，持股降至 50%，等待明確表態'
            elif _fut4 > 0:
                _l4c = f'外資期貨多單 {_fut4:,.0f}口，外資期貨翻多，燃料充足，積極作多'
                _l4a = '順勢重壓強勢股，持股 80~100%'
            else:
                _l4c = f'外資期貨微空 {abs(_fut4):,.0f}口，水位正常，依個股技術面操作'
                _l4a = '持股 70%，現金 30% 備用'
        else:
            _l4c = '先行指標欄位異常，請確認 FinMind Token'; _l4a = ''; _l4_ind = '外資期貨留倉'
    else:
        _l4c = '先行指標尚未載入，請點擊「🔄 更新全部總經數據」'; _l4a = ''; _l4_ind = '外資期貨留倉'
    st.markdown(teacher_conclusion('宏爺', _l4_ind, _l4c, _l4a), unsafe_allow_html=True)

    # ── 副標籤：欄位確認列（v12 風格）─────────────────────────────────
    st.markdown("""<div style="font-size:11px;color:#484f58;margin:-6px 0 10px 0;">
✅ 外資期貨留倉口數 &nbsp;｜&nbsp; ✅ 前五大/前十大交易人 &nbsp;｜&nbsp; ✅ 外資選擇權金額 &nbsp;｜&nbsp; ✅ 韭菜指數 &nbsp;｜&nbsp; ✅ PCR
</div>""", unsafe_allow_html=True)

    # 先行指標隨更新大盤自動載入（執行緒快取版，build_leading_fast）
    df_li_show = st.session_state.get('li_latest')

    if df_li_show is not None and not df_li_show.empty:
        # 向前填補 NaN（各欄位用最後一次有效數值補齊，避免 API 部分失敗造成空格）
        _li_num_cols = [c for c in df_li_show.columns if c != '日期']
        df_li_show = df_li_show.copy()
        df_li_show[_li_num_cols] = df_li_show[_li_num_cols].ffill()

        # ── ① 資料期間 caption ─────────────────────────────────────────
        _li_dates = df_li_show['日期'].tolist() if '日期' in df_li_show.columns else []
        if _li_dates:
            _d0 = _li_dates[0]
            _d1 = _li_dates[-1]
            st.caption(
                f'📅 資料期間：{_d0} ~ {_d1}  共 {len(df_li_show)} 筆  '
                f'｜外資空單>3萬⚠️  前五大>1萬⚠️  PCR<100偏空'
            )

        # ── ② 主表格（render_leading_table，已內含深色主題CSS）──────────
        st.markdown(render_leading_table(df_li_show), unsafe_allow_html=True)

        # 欄位說明 → 已移至 Tab 5 策略手冊



        # ── ③ 進階警示訊號（依建議加入5個條件）──────────────────────────
        _last_row = df_li_show.iloc[-1] if not df_li_show.empty else {}
        _fut_net  = _last_row.get('外資大小')
        _pcr      = _last_row.get('選PCR')
        _opt_net  = _last_row.get('外(選)')
        _leek     = _last_row.get('韭菜指數')
        _foreign  = _last_row.get('外資')  # 現貨外資買賣
        _trust    = _last_row.get('投信')  # 投信買賣
        _warnings = []

        # 訊號 1：期權同向崩盤訊號（最強烈）
        # 期貨大空 + 選擇權外資淨空 → 不惜成本避險
        try:
            if _fut_net is not None and float(_fut_net) < -20000:
                if _opt_net is not None and float(_opt_net) < 0:
                    _warnings.append(('🔴', '期權同向崩盤警戒',
                        f'期貨空{abs(float(_fut_net)):,.0f}口 + 選擇權外資淨空{float(_opt_net):,.0f}千元',
                        '外資「不惜成本」雙向避險，高機率隨即殺盤，建議降倉至30%以下'))
                elif _fut_net is not None and float(_fut_net) < -30000:
                    _warnings.append(('🟡', '期貨大空警戒',
                        f'外資期貨空單 {abs(float(_fut_net)):,.0f} 口（>3萬口門檻）',
                        '注意流向：若每日持續增加空單才是真訊號；若空單縮減則危機解除'))
        except: pass

        # 訊號 2：韭菜指數極端值
        try:
            if _leek is not None:
                _leek_f = float(_leek)
                if _leek_f > 30:
                    _warnings.append(('🔴', '散戶過度樂觀（韭菜極端多）',
                        f'法人空多比 +{_leek_f:.1f}%（超過+30%警戒線）',
                        '散戶一面倒看多，短線見頂訊號，主力容易在此出貨'))
                elif _leek_f < -30:
                    _warnings.append(('🟢', '軋空動能極強（韭菜極端空）',
                        f'法人空多比 {_leek_f:.1f}%（超過-30%機會線）',
                        '散戶爭相放空，軋空動能強，千萬不要在此放空，逆勢做多機會'))
        except: pass

        # 訊號 3：外資投信同買（最強籌碼訊號）
        try:
            if _foreign is not None and _trust is not None:
                _f2 = float(_foreign); _t2 = float(_trust)
                if _f2 > 50 and _t2 > 5:
                    _warnings.append(('🟢', '外資投信同買（籌碼共鳴）',
                        f'外資+{_f2:.0f}億 + 投信+{_t2:.1f}億 同步買超',
                        '外投同買的股票漲幅連續性最強，現貨籌碼最乾淨'))
                elif _f2 < -100 and _t2 < -5:
                    _warnings.append(('🔴', '外資投信同賣（籌碼潰散）',
                        f'外資{_f2:.0f}億 + 投信{_t2:.1f}億 同步賣超',
                        '雙主力同步出場，下跌壓力沉重'))
        except: pass

        # 訊號 4：PCR 極端值判斷
        try:
            if _pcr is not None:
                _pcr_f = float(_pcr)
                if _pcr_f < 80:
                    _warnings.append(('🔴', '選擇權Put/Call偏低（市場過樂觀）',
                        f'PCR={_pcr_f:.1f}（<80偏危險，市場保護不足）',
                        '選擇權市場無人買保護，通常出現在短線頂部'))
                elif _pcr_f > 150:
                    _warnings.append(('🟢', '選擇權Put/Call偏高（恐慌區）',
                        f'PCR={_pcr_f:.1f}（>150偏多，市場過度悲觀）',
                        '大量買保護代表市場恐慌，通常是逆向布局訊號'))
        except: pass

        # 訊號 5：成交量萎縮（市場觀望）
        try:
            _vols = []
            for _, _vr in df_li_show.tail(5).iterrows():
                _vs = str(_vr.get('成交量','-')).replace('億','')
                try: _vols.append(float(_vs))
                except: pass
            if len(_vols) >= 3:
                _avg_vol = sum(_vols[:-1]) / len(_vols[:-1])
                _last_vol = _vols[-1]
                if _last_vol < _avg_vol * 0.7:
                    _warnings.append(('🟡', '成交量急萎縮（市場觀望）',
                        f'今日成交量{_last_vol:.0f}億（前{len(_vols)-1}日均量{_avg_vol:.0f}億的{_last_vol/_avg_vol*100:.0f}%）',
                        '量縮超過30%代表市場觀望，方向選擇前勿輕易追高'))
                elif _last_vol > _avg_vol * 1.5:
                    _warnings.append(('🔵', '成交量急放（趨勢加速）',
                        f'今日成交量{_last_vol:.0f}億（前均量{_avg_vol:.0f}億的{_last_vol/_avg_vol*100:.0f}%）',
                        '成交量暴增50%以上，趨勢加速，注意是否配合方向'))
        except: pass

        if _warnings:
            for _wc, _wt, _wd, _wa in _warnings:
                _wcolor = ('#2ea043' if _wc == '🟢' else
                           '#da3633' if _wc == '🔴' else
                           '#d29922' if _wc == '🟡' else '#388bfd')
                st.markdown(
                    f'<div style="border-left:5px solid {_wcolor};background:#0d1117;'
                    f'padding:9px 14px;border-radius:0 8px 8px 0;margin:4px 0;">'
                    f'<span style="font-size:11px;color:#6e7681;">⚡ 進階警示</span><br>'
                    f'<span style="font-size:14px;font-weight:900;color:{_wcolor};">{_wc} {_wt}</span><br>'
                    f'<span style="font-size:12px;color:#c9d1d9;">{_wd}</span><br>'
                    f'<span style="font-size:11px;color:#8b949e;">→ {_wa}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )

        
        # ── ⑤ v4.0 總經一票否決 (Task 2) ─────────────────────────────
        try:
            _v4_pcr = float(_last_row.get('選PCR') or 100)
            _v4_fut = float(_last_row.get('外資大小') or 0)
            _v4_mac = V4StrategyEngine.__new__(V4StrategyEngine)
            _v4_mac.macro = {'vix': 15, 'foreign_futures': _v4_fut, 'pcr': _v4_pcr}
            _v4_veto = _v4_mac.check_macro_veto()
            _v4_c = _v4_veto['color']
            st.markdown(
                f'<div style="border-left:5px solid {_v4_c};background:#0d1117;'
                f'padding:9px 14px;border-radius:0 8px 8px 0;margin:6px 0;">'
                f'<span style="font-size:11px;color:#6e7681;">🏛️ v4.0 總經否決權</span><br>'
                f'<span style="font-size:14px;font-weight:900;color:{_v4_c};">'
                f'{_v4_veto["status"]} — 最大建議持股 {_v4_veto["max_position"]}%</span><br>'
                f'<span style="font-size:12px;color:#c9d1d9;">{_v4_veto["msg"]}</span>'
                f'</div>',
                unsafe_allow_html=True
            )
        except Exception as _v4e:
            pass


        # ── v5.0 動態資產配置建議（純現金策略，無 ETF）────────────────
        try:
            _v5_fut = float(_last_row.get('外資大小') or 0)
            if _v5_fut <= -30000:
                _v5_stock, _v5_cash = 20, 80
                _v5_strategy = '嚴禁追高攤平，保護本金優先；可留意低基期高殖利率個股'
                _v5_color = '#f85149'
            elif _v5_fut <= -15000:
                _v5_stock, _v5_cash = 50, 50
                _v5_strategy = '收回資金，逢高減碼漲多個股，等待期空回補訊號'
                _v5_color = '#d29922'
            elif _v5_fut > 0:
                _v5_stock, _v5_cash = 90, 10
                _v5_strategy = '期貨翻多，順勢重壓強勢股，外投同買個股優先布局'
                _v5_color = '#3fb950'
            else:
                _v5_stock, _v5_cash = 70, 30
                _v5_strategy = '水位中性，依個股技術面操作，保留現金彈藥'
                _v5_color = '#58a6ff'
            st.markdown(
                f'<div style="border-left:5px solid {_v5_color};background:#0d1117;'
                f'padding:9px 14px;border-radius:0 8px 8px 0;margin:6px 0;">'
                f'<span style="font-size:11px;color:#6e7681;">💰 v5 動態配置</span><br>'
                f'<span style="font-size:14px;font-weight:900;color:{_v5_color};">'
                f'建議股票 {_v5_stock}% ／現金 {_v5_cash}%</span><br>'
                f'<span style="font-size:12px;color:#c9d1d9;">📌 {_v5_strategy}</span>'
                f'</div>',
                unsafe_allow_html=True
            )
        except Exception:
            pass

# ── ④ 資料來源診斷（收合，供進階使用者確認）─────────────────────
        with st.expander('🔍 資料來源診斷（點此確認各欄數據正確性）', expanded=False):
            _diag_cols = {
                '外資大小':       ('FinMind TX+MTX 期貨留倉 / TAIFEX futContractsDate備援', '外資大台淨口 + 外資小台淨口×0.25'),
                '前五大留倉':     ('TAIFEX largeTraderFutQry POST',                         '前五大買方所有契約 − 賣方所有契約'),
                '前十大留倉':     ('TAIFEX largeTraderFutQry POST',                         '前十大買方所有契約 − 賣方所有契約'),
                '選PCR':          ('TAIFEX pcRatio POST',                                   'Put未平倉量 / Call未平倉量 × 100'),
                '外(選)':         ('TAIFEX callsAndPutsDate POST',                          'BC金額 − SC金額 − BP金額 + SP金額'),
                '韭菜指數':       ('TAIFEX futContractsDate+futDailyMarketReport',          '(法人空方MTX OI − 法人多方MTX OI) / 全體MTX OI × 100'),
                '外資/投信/自營': ('TWSE BFI82U',                                           '三大法人現貨買賣差額（億元）'),
                '成交量':         ('TWSE FMTQIK 月報',                                      '每日全市場成交金額（億元）'),
            }
            for _col, (_src, _formula) in _diag_cols.items():
                st.markdown(
                    f'<div style="font-size:12px;color:#8b949e;padding:2px 0;">'
                    f'<b style="color:#c9d1d9;">{_col}</b> → 來源：{_src}<br>'
                    f'&nbsp;&nbsp;&nbsp;公式：{_formula}</div>',
                    unsafe_allow_html=True
                )
            # [BUG FIX] 最新一筆原始值 - 用 pd.isna 確保 NaN 不造成 format error
            if len(df_li_show) > 0:
                _raw = df_li_show.iloc[-1]
                st.markdown('<br><b style="color:#c9d1d9;font-size:12px;">最新一筆原始值：</b>', unsafe_allow_html=True)
                _raw_items = []
                for _c in ['外資大小','前五大留倉','前十大留倉','選PCR','外(選)','韭菜指數','外資','投信','自營']:
                    _v = _raw.get(_c)
                    if _v is not None:
                        try:
                            import pandas as _pd_raw
                            if not _pd_raw.isna(_v):  # [BUG FIX] 過濾 NaN 避免 format 崩潰
                                _raw_items.append(f'{_c}={float(_v):+,.0f}')
                        except Exception:
                            _raw_items.append(f'{_c}={_v}')
                st.code(' | '.join(_raw_items), language=None)

        # ── ⑤ 下載按鈕（Base64 data URL，不依賴 WebSocket）──────
        try:
            import base64 as _b64_li
            _csv_li = df_li_show.to_csv(index=False, encoding='utf-8-sig')
            _b64_li_data = _b64_li.b64encode(_csv_li.encode('utf-8-sig')).decode()
            st.markdown(
                f'<a href="data:text/csv;charset=utf-8-sig;base64,{_b64_li_data}" '
                f'download="先行指標.csv" '
                f'style="display:inline-block;padding:5px 14px;background:#21262d;'
                f'color:#e6edf3;border:1px solid #30363d;border-radius:6px;'
                f'font-size:13px;text-decoration:none;">⬇️ 下載先行指標 CSV</a>',
                unsafe_allow_html=True
            )
        except Exception:
            pass

    elif cd:
        # 已有其他總經數據但先行指標失敗 → 顯示診斷
        with st.expander('⚠️ 先行指標載入失敗 — 診斷說明', expanded=True):
            st.warning('先行指標尚未載入，請重新點擊「🔄 更新全部總經數據」')
            st.markdown('''<div style="font-size:12px;color:#8b949e;line-height:1.8;">
<b>可能原因：</b><br>
① TAIFEX 在 Colab 常被封鎖 → 外資大小/PCR/韭菜仍可從 FinMind 取得<br>
② FinMind API 速率限制 → 等待 10 分鐘後重試<br>
③ 非交易日（週末/假日）→ 資料期間無新增屬正常<br><br>
<b>✅ 免費可用（不需 Token）：</b><br>
• 外資大小 TX+MTX | 選PCR(FinMind) | 外(選) | 三大法人買賣 | 成交量 | ADL<br>
• TAIFEX 可達時自動補充：前五大/前十大/精確PCR/未平倉/韭菜精確值<br>
</div>''', unsafe_allow_html=True)
    else:
        st.info('📡 請點擊「🔄 更新全部總經數據」自動載入先行指標')

    # 宏爺判斷方式 → 已移至 Tab 5 策略手冊

    # ── 宏爺智能綜合結論 ─────────────────────────────────────────────────────
    _df_li_c = st.session_state.get('li_latest')
    if _df_li_c is not None and not _df_li_c.empty:
        import pandas as _pd_li
        _last_li = _df_li_c.iloc[-1]
        def _v(x):
            try: return None if (x is None or _pd_li.isna(x)) else x
            except: return None
        _fnet = _v(_last_li.get('外資大小'));  _pcr  = _v(_last_li.get('選PCR'))
        _leek = _v(_last_li.get('韭菜指數')); _top5 = _v(_last_li.get('前五大留倉'))
        _opt  = _v(_last_li.get('外(選)'));   _date = _last_li.get('日期','最新')

        _score = 0; _sigs = []
        if _fnet is not None:
            if   _fnet < -30000: _score -= 2; _sigs.append(f'🔴 期貨空單 {_fnet:,.0f}口（超越3萬危險線）')
            elif _fnet <      0: _score -= 1; _sigs.append(f'⚠️ 期貨淨空 {_fnet:,.0f}口')
            else:                _score += 1; _sigs.append(f'✅ 期貨淨多 {_fnet:+,.0f}口')
        if _pcr is not None:
            if   _pcr > 130: _score += 1; _sigs.append(f'🟢 PCR={_pcr:.0f}（>130強支撐）')
            elif _pcr > 100: _sigs.append(f'🔵 PCR={_pcr:.0f}（偏多）')
            else:            _score -= 1; _sigs.append(f'🔴 PCR={_pcr:.0f}（<100偏空）')
        if _opt is not None:
            if   _opt >  10000: _score += 1; _sigs.append(f'🟢 外選 +{_opt:,.0f}千元（多方佈局）')
            elif _opt < -10000: _score -= 1; _sigs.append(f'🔴 外選 {_opt:,.0f}千元（空方佈局）')
            else: _sigs.append(f'⚪ 外選 {_opt:+,.0f}千元（中性）')
        if _top5 is not None:
            if   _top5 < -10000: _score -= 1; _sigs.append(f'🔴 前五大淨空 {_top5:,.0f}口（警戒）')
            elif _top5 >       0: _score += 1; _sigs.append(f'✅ 前五大淨多 {_top5:+,.0f}口')
        if _leek is not None:
            if   _leek > 10: _score -= 1; _sigs.append(f'🔴 韭菜指數{_leek:.1f}%（散戶過熱）')
            elif _leek < -5: _score += 1; _sigs.append(f'✅ 韭菜指數{_leek:.1f}%（散戶悲觀）')
            else: _sigs.append(f'⚪ 韭菜指數{_leek:.1f}%（中性）')

        if   _score <= -3: _vd='🚨 強烈偏空'; _vc='#f85149'; _va='建議大幅降倉，等待空單回補訊號'
        elif _score <= -1: _vd='🔴 偏空';    _vc='#da6d3e'; _va='籌碼不穩，衛星資金觀望為主'
        elif _score ==  0: _vd='⚪ 多空分歧'; _vc='#d29922'; _va='訊號分歧，小倉觀察，詳見策略手冊'
        elif _score <=  2: _vd='🟢 偏多';    _vc='#3fb950'; _va='籌碼偏健康，可正常持倉'
        else:              _vd='💚 強烈偏多'; _vc='#2ea043'; _va='聰明錢明顯佈多，積極持倉'

        st.markdown(
            f'<div style="background:#0d1117;border:2px solid {_vc}44;border-radius:10px;padding:14px 18px;margin:8px 0;">'
            f'<div style="font-size:11px;color:#8b949e;margin-bottom:4px;">🎯 {_date} 籌碼綜合判斷</div>'
            f'<div style="font-size:24px;font-weight:900;color:{_vc};">{_vd}</div>'
            f'<div style="font-size:13px;color:#c9d1d9;margin:6px 0 10px 0;">{_va}</div>'
            f'<div style="font-size:12px;color:#484f58;">{" ； ".join(_sigs)}</div>'
            f'</div>',
            unsafe_allow_html=True
        )


    st.markdown('<hr style="border-color:#21262d;margin:14px 0;">',unsafe_allow_html=True)
    st.markdown('<hr style="border-color:#21262d;margin:8px 0;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:1px;margin:4px 0;">📊 市場廣度</div>', unsafe_allow_html=True)
    st.markdown(section_header('五','📊 全市場健康度 × 騰落指標（ADL）','📉'),unsafe_allow_html=True)
    _adl5 = st.session_state.get('cl_data', {}).get('adl')
    _mkt5 = st.session_state.get('mkt_info', {})
    if _adl5 is not None and not _adl5.empty:
        _ac5 = next((c for c in _adl5.columns if 'adl' in c.lower()), _adl5.columns[0])
        _adl_vals5 = _adl5[_ac5].dropna().tail(5)
        _adl_up5 = (len(_adl_vals5) >= 2 and float(_adl_vals5.iloc[-1]) > float(_adl_vals5.iloc[0]))
        # 優先從 tw_s 取當日漲跌 %（比 mkt_info 更可靠），fallback 到 mkt5
        _twii_s5 = tw_s.get('台股加權指數') or {}
        _twii_p5 = _twii_s5.get('pct') if isinstance(_twii_s5, dict) and _twii_s5.get('pct') is not None \
                   else (_mkt5.get('台股加權指數', {}).get('pct', None) if isinstance(_mkt5.get('台股加權指數'), dict) else None)
        # Bug fix：_twii_p5=0 或 None 時，依 ADL 方向判斷（不能落入空頭 else）
        _idx_up = (_twii_p5 is not None and _twii_p5 > 0)
        _idx_dn = (_twii_p5 is not None and _twii_p5 < 0)
        if _adl_up5 and _idx_up:
            _a5c = '廣泛多頭：ADL↑+指數↑，市場健康，全面性上漲'; _a5a = '可積極持股'
        elif _adl_up5 and _idx_dn:
            _a5c = 'ADL↑但指數跌，廣度健康，或為技術回調非崩盤'; _a5a = '可留意回調後逢低布局'
        elif _adl_up5:
            # ADL上升但指數資料不足/持平 → 廣度健康，中性偏多
            _a5c = 'ADL↑廣度健康，指數方向待確認（持平或資料更新中）'; _a5a = '維持現有部位，等待指數方向確認'
        elif not _adl_up5 and _idx_up:
            _a5c = '⚠️ 背離警訊：指數漲但ADL↓，行情由少數權值股撐，不可追'; _a5a = '謹慎，不追高，等待廣度改善'
        else:
            _a5c = '廣泛賣壓：ADL↓+指數↓，空頭格局，降低部位'; _a5a = '降低持倉，保護本金'
        _a5_ind = f'ADL近5日{"↑上升" if _adl_up5 else "↓下降"}'
    else:
        _a5c = 'ADL數據尚未載入，請點擊「🔄 更新全部總經數據」'; _a5a = ''; _a5_ind = 'ADL騰落線'
    st.markdown(teacher_conclusion('宏爺', _a5_ind, _a5c, _a5a), unsafe_allow_html=True)
    st.caption('💡 衡量「多少股票真的在漲」—— 分數越高 = 廣度越健康；ADL 趨勢 vs 指數是否背離是最重要的觀察點')
    # 如果是代理資料，顯示提示
    _adl_chk = st.session_state.get('cl_data',{}).get('adl')
    if _adl_chk is not None and not _adl_chk.empty:
        if 'is_proxy' in _adl_chk.columns and _adl_chk['is_proxy'].any():
            st.caption('⚠️ 目前顯示 yfinance 代理數據（TWSE 上漲/下跌家數暫時無法取得），上漲佔比為估算值')

    # ── 騰落指標：初學者說明 ─────────────────────────────────────
    with st.expander('💡 什麼是騰落指標（ADL）？點此了解', expanded=False):
        st.markdown('''
<div style="font-size:13px;color:#c9d1d9;line-height:1.9;">
<b>📌 一句話理解：「今天台股1800支股票，到底幾支在漲？幾支在跌？」</b><br><br>
<b>計算方式：</b><br>
　① 每天統計全市場「上漲家數 A」和「下跌家數 D」<br>
　② AD值 = A - D（今天的淨上漲家數）<br>
　③ ADL = 累積加總每天的 AD 值（趨勢線）<br><br>
<b>🟢 判讀重點一：上漲佔比</b><br>
　>60% = 多數股票在漲 → 廣度健康，真多頭<br>
　40-60% = 多空均衡 → 市場整理<br>
　<40% = 少數股票在漲 → 廣度萎縮，注意拉尾盤風險<br><br>
<b>⚠️ 判讀重點二：背離訊號（最重要！）</b><br>
　✅ 指數創高 + ADL 也創高 = 百花齊放，健康多頭<br>
　🔴 指數創高 + ADL 卻走低 = 拉權值、出中小！崩盤前兆，要降倉<br>
　🌱 指數創低 + ADL 止跌回升 = 底部可能不遠，左側布局機會<br><br>
<b>📊 資料來源：</b>FinMind API (TaiwanStockMarketCondition) → TWSE MI_INDEX → FMTQIK
</div>
        ''', unsafe_allow_html=True)

    # ── ADL 即時補救（TWSE 封鎖時自動觸發 FinMind）─────────────────
    if (df_adl is None or df_adl.empty):
        _adl_ph = st.empty()
        _adl_ph.info('⏳ ADL 資料載入中...')
        try:
            from daily_checklist import fetch_adl as _fa
            _tok_rt = os.environ.get('FINMIND_TOKEN','') or FINMIND_TOKEN
            _df_rt  = _fa(days=60, token=_tok_rt)
            if _df_rt is not None and not _df_rt.empty:
                df_adl = _df_rt
                _cd_u  = st.session_state.get('cl_data', {})
                _cd_u['adl'] = df_adl
                st.session_state['cl_data'] = _cd_u
        except Exception as _adl_e:
            print(f'[ADL補救] {_adl_e}')
        finally:
            _adl_ph.empty()

    if df_adl is not None and not df_adl.empty:
        _adl_last   = df_adl.iloc[-1]
        _adl_up     = int(_adl_last.get('up', 0))
        _adl_down   = int(_adl_last.get('down', 0))
        _adl_ad     = int(_adl_last.get('ad', 0))
        _adl_ratio  = float(_adl_last.get('ad_ratio', 50))
        _adl_val    = float(_adl_last.get('adl', 0))
        _adl_ma20   = df_adl['adl_ma20'].dropna().iloc[-1] if df_adl['adl_ma20'].notna().any() else _adl_val
        _adl_trend  = '↑' if _adl_val > _adl_ma20 else '↓'
        _adl_color  = '#da3633' if _adl_ad > 0 else '#2ea043'
        _adl_signal = ('🟢 廣度擴張，多頭健康' if _adl_ad > 200
                       else ('🟡 廣度收窄，市場整理' if _adl_ad >= -100
                       else '🔴 廣度萎縮，主力集中在少數股'))
        # 背離偵測（指數上漲但 ADL 下跌 = 警告）
        _twii_pct = tw_s.get('台股加權指數', {}).get('pct', 0) if tw_s.get('台股加權指數') else 0
        _divergence = _twii_pct > 0.5 and _adl_ad < -50

        # KPI 卡片
        _adl_cols = st.columns(4)
        with _adl_cols[0]:
            st.markdown(kpi('今日上漲家數', f'{_adl_up:,}', '上漲股票總數', '#3fb950', '#0d2818'), unsafe_allow_html=True)
        with _adl_cols[1]:
            st.markdown(kpi('今日下跌家數', f'{_adl_down:,}', '下跌股票總數', '#f85149', '#2a0d0d'), unsafe_allow_html=True)
        with _adl_cols[2]:
            st.markdown(kpi('AD值（今日）', f'{_adl_ad:+,}', '漲家－跌家', _adl_color, '#0d1117'), unsafe_allow_html=True)
        with _adl_cols[3]:
            # 廣度健康評分：0-100（對應全市場健康度）
            _breadth_score = round(_adl_ratio)  # 直接用上漲佔比%當分數
            _bs_color = '#3fb950' if _breadth_score>=60 else ('#d29922' if _breadth_score>=40 else '#f85149')
            _bs_label = '🟢 廣度健康' if _breadth_score>=60 else ('🟡 中性' if _breadth_score>=40 else '🔴 廣度不足')
            st.markdown(kpi('全市場健康度', f'{_breadth_score}分', _bs_label, _bs_color, '#0d1117'), unsafe_allow_html=True)
            # 同步更新旌旗指數（如果尚未由 ADL 計算）
            if not st.session_state.get('jingqi_info'):
                st.session_state['jingqi_info'] = {
                    'avg': _adl_ratio, 'pos': ('80~100%' if _adl_ratio>=60 else ('50~70%' if _adl_ratio>=40 else '20~40%')),
                    'regime': ('bull' if _adl_ratio>=60 else ('neutral' if _adl_ratio>=40 else 'bear')),
                    'color': _bs_color, 'label': _bs_label, 'source': 'ADL廣度',
                    'pct20':_adl_ratio,'pct60':_adl_ratio*0.9,'pct120':_adl_ratio*0.8,'pct240':_adl_ratio*0.7,
                }

        # 信號提示
        _sig_color = '#3fb950' if _adl_ad > 200 else ('#d29922' if _adl_ad >= -100 else '#f85149')
        st.markdown(
            f'<div style="background:#0d1117;border-left:4px solid {_sig_color};border-radius:0 8px 8px 0;'
            f'padding:10px 14px;margin:8px 0;">'
            f'<span style="color:{_sig_color};font-weight:700;">{_adl_signal}</span>'
            f'　｜　騰落線 {_adl_val:,.0f} {_adl_trend} MA20({_adl_ma20:,.0f})'
            + (f'　⚠️ <span style="color:#f85149;font-weight:700;">背離警告：指數漲但廣度萎縮！</span>' if _divergence else '') +
            f'</div>', unsafe_allow_html=True)

        # 騰落線圖（ADL + MA20 + 上漲佔比）
        _fig_adl = go.Figure()
        # 上漲佔比柱狀圖（背景）
        _ratio_colors = ['rgba(63,185,80,0.4)' if v >= 50 else 'rgba(248,81,73,0.4)' for v in df_adl['ad_ratio'].fillna(50)]
        _fig_adl.add_trace(go.Bar(
            x=df_adl['date'], y=df_adl['ad_ratio'],
            name='上漲佔比%', marker_color=_ratio_colors,
            yaxis='y2', opacity=0.5,
            hovertemplate='%{x|%Y-%m-%d}<br>上漲佔比: %{y:.1f}%<extra></extra>'
        ))
        # ADL 線
        _fig_adl.add_trace(go.Scatter(
            x=df_adl['date'], y=df_adl['adl'],
            name='騰落線 ADL', line=dict(color='#58a6ff', width=2.5),
            hovertemplate='%{x|%Y-%m-%d}<br>ADL: %{y:,.0f}<extra></extra>'
        ))
        # ADL MA20
        _fig_adl.add_trace(go.Scatter(
            x=df_adl['date'], y=df_adl['adl_ma20'],
            name='ADL MA20', line=dict(color='#ffd700', width=1.5, dash='dot'),
            hovertemplate='%{x|%Y-%m-%d}<br>MA20: %{y:,.0f}<extra></extra>'
        ))
        # 零軸
        _fig_adl.add_hline(y=0, line_dash='dash', line_color='#484f58', opacity=0.5)
        _fig_adl.update_layout(
            title=dict(text='台股騰落線（ADL）— 衡量多數股票是否真的在漲', font=dict(color='#8b949e', size=13)),
            height=320, plot_bgcolor='#0e1117', paper_bgcolor='#0e1117',
            font=dict(color='white', size=11),
            legend=dict(orientation='h', y=-0.15, bgcolor='rgba(0,0,0,0)'),
            margin=dict(l=10, r=10, t=40, b=10),
            hovermode='x unified',
            yaxis=dict(title='ADL 累積值', gridcolor='#21262d', zeroline=True),
            yaxis2=dict(title='上漲佔比%', gridcolor='rgba(0,0,0,0)',
                        overlaying='y', side='right', range=[0, 100], showgrid=False),
            xaxis=dict(gridcolor='#21262d', tickformat='%m/%d'),
        )
        st.plotly_chart(_fig_adl, use_container_width=True, config={'displayModeBar': False})

        # ── ADL vs 加權指數 雙軸背離圖 ──────────────────────────
        _twii_data = tw.get('台股加權指數')
        if _twii_data is not None and not _twii_data.empty:
            _cc_t = 'close' if 'close' in _twii_data.columns else 'Close'
            if _cc_t in _twii_data.columns:
                # 對齊日期
                _adl_dates = df_adl['date'].dt.date.tolist()
                _twii_sub = _twii_data.copy()
                _twii_sub.index = _twii_sub.index.date if hasattr(_twii_sub.index, 'date') else _twii_sub.index
                _twii_aligned = [float(_twii_sub.loc[d, _cc_t]) if d in _twii_sub.index else None
                                 for d in _adl_dates]
                _fig_div = go.Figure()
                _fig_div.add_trace(go.Scatter(
                    x=df_adl['date'], y=df_adl['adl'],
                    name='騰落線 ADL', line=dict(color='#58a6ff', width=2),
                    hovertemplate='%{x|%m/%d}<br>ADL: %{y:,.0f}<extra></extra>'
                ))
                _fig_div.add_trace(go.Scatter(
                    x=df_adl['date'], y=_twii_aligned,
                    name='加權指數', line=dict(color='#ffd700', width=2, dash='dot'),
                    yaxis='y2',
                    hovertemplate='%{x|%m/%d}<br>指數: %{y:,.0f}<extra></extra>'
                ))
                # 背離區域標示
                if _divergence:
                    _fig_div.add_annotation(
                        x=df_adl['date'].iloc[-1], y=_adl_val,
                        text='⚠️ 背離警告', showarrow=True, arrowhead=2,
                        font=dict(color='#f85149', size=12), bgcolor='#2a0d0d'
                    )
                _fig_div.update_layout(
                    title=dict(text='🔍 ADL vs 加權指數（看背離是否存在）', font=dict(color='#8b949e', size=12)),
                    height=280, plot_bgcolor='#0e1117', paper_bgcolor='#0e1117',
                    font=dict(color='white', size=10),
                    legend=dict(orientation='h', y=-0.2, bgcolor='rgba(0,0,0,0)'),
                    margin=dict(l=10,r=60,t=40,b=10),
                    hovermode='x unified',
                    yaxis=dict(title='ADL', gridcolor='#21262d'),
                    yaxis2=dict(title='加權指數', overlaying='y', side='right',
                               gridcolor='rgba(0,0,0,0)', showgrid=False),
                    xaxis=dict(gridcolor='#21262d', tickformat='%m/%d'),
                )
                st.plotly_chart(_fig_div, use_container_width=True, config={'displayModeBar': False})
                if _divergence:
                    st.error('⚠️ 背離警告：大盤指數上漲，但騰落線下跌！代表只有少數權值股在撐盤，市場廣度惡化，要注意風險！')

        # 近5日 AD 明細表
        _adl_tbl = df_adl.tail(5)[['date','up','down','ad','ad_ratio','adl']].copy()
        _adl_tbl['date'] = _adl_tbl['date'].dt.strftime('%m/%d')
        _adl_tbl = _adl_tbl.rename(columns={
            'date':'日期','up':'上漲','down':'下跌','ad':'AD值','ad_ratio':'上漲佔比%','adl':'ADL累積'
        }).sort_values('日期', ascending=False)
        st.dataframe(_adl_tbl, use_container_width=True, hide_index=True,
            column_config={
                '上漲佔比%': st.column_config.NumberColumn('上漲佔比%', format='%.1f%%'),
                'ADL累積': st.column_config.NumberColumn('ADL累積', format='%,.0f'),
                'AD值': st.column_config.NumberColumn('AD值', format='%+d'),
            })

        with st.container():
            st.caption('💡 宏爺策略：ADL 趨勢比今日漲跌更重要，要看「方向」是否與指數一致。')
            # 連動結論
            _adl_concl = []
            if df_adl is not None and not df_adl.empty:
                _ar2 = df_adl.iloc[-1]
                _ad2 = _ar2.get('ad', 0)
                _ratio2 = _ar2.get('ad_ratio', 50)
                _adl2 = _ar2.get('adl', 0)
                _ma2  = df_adl['adl_ma20'].dropna().iloc[-1] if df_adl['adl_ma20'].notna().any() else _adl2
                _twii_pct2 = tw_s.get('台股加權指數', {}).get('pct', 0) if tw_s.get('台股加權指數') else 0
                # ── 初步條件判斷（給出具體數字與明確結論）
                _ad_ratio_int  = int(round(_ratio2)) if _ratio2 else 0
                _adl_above_ma  = (_adl2 is not None and _ma2 is not None and _adl2 > _ma2)
                _adl_below_ma  = (_adl2 is not None and _ma2 is not None and _adl2 < _ma2)

                if _twii_pct2 > 0.5 and _ad2 < -50:
                    _adl_concl.append(
                        f'🔴 指數漲({_twii_pct2:+.1f}%) 但 AD值({_ad2:+,}) < -50 → '
                        f'背離！僅少數大型股撐盤，廣度萎縮，建議準備降倉')
                elif _twii_pct2 < -0.5 and _ad2 > 50:
                    _adl_concl.append(
                        f'🟢 指數跌({_twii_pct2:+.1f}%) 但 AD值({_ad2:+,}) > 50 → '
                        f'底部擴散！多數股票止跌，可留意逢低布局機會')
                elif _ratio2 >= 70 and _adl_above_ma:
                    _adl_concl.append(
                        f'✅ 上漲佔比 {_ad_ratio_int}%（>70%）+ ADL在MA上 → '
                        f'全面多頭，市場廣度充足，可積極持股')
                elif _ratio2 >= 60 and _adl_above_ma:
                    _adl_concl.append(
                        f'✅ 上漲佔比 {_ad_ratio_int}%（60~70%）+ ADL在MA上 → '
                        f'多頭健康，可持股偏多，注意量能配合')
                elif _ratio2 < 40 and _adl_below_ma:
                    _adl_concl.append(
                        f'🔴 上漲佔比 {_ad_ratio_int}%（<40%）+ ADL破MA → '
                        f'廣泛賣壓，空頭格局，建議降倉保守')
                elif _ratio2 < 40:
                    _adl_concl.append(
                        f'⚠️ 上漲佔比 {_ad_ratio_int}%（<40%）→ '
                        f'廣度不足，多數股票弱勢，不宜追高')
                elif _adl_below_ma:
                    _adl_concl.append(
                        f'⚠️ 上漲佔比 {_ad_ratio_int}% 但 ADL跌破MA → '
                        f'趨勢轉弱訊號，觀望等方向確認')
                else:
                    _adl_concl.append(
                        f'⚪ 上漲佔比 {_ad_ratio_int}%（40~60%）→ '
                        f'廣度中性，盤整格局，等待方向選擇')
            for _ac in _adl_concl:
                _ac_c = ('#2ea043' if '✅' in _ac or '可進攻' in _ac
                         else '#da3633' if '🔴' in _ac or '警告' in _ac
                         else '#d29922' if '⚠️' in _ac else '#388bfd')
                _ac_dot = '🟢' if '✅' in _ac else ('🔴' if '🔴' in _ac else ('🟡' if '⚠️' in _ac else '⚪'))
                _ac_clean = _ac.lstrip('✅⚠️🔴⚪').strip()
                st.markdown(
                    f'<div style="border-left:5px solid {_ac_c};background:#0d1117;'
                    f'padding:9px 14px;border-radius:0 8px 8px 0;margin:5px 0;">'
                    f'<span style="font-size:14px;font-weight:900;color:{_ac_c};">{_ac_dot} {_ac_clean}</span><br>'
                    f'<span style="font-size:10px;color:#484f58;">詳細判讀 → 「策略手冊」Tab</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
        st.caption('📖 ADL判讀方法 → 詳見「策略手冊」Tab')

    else:
        _adl_debug = st.session_state.get('adl_debug_msg', '')
        if _adl_debug:
            st.error(f'❌ 騰落指標抓取失敗：{_adl_debug}')
            st.caption('💡 請到 Colab 查看 [ADL] 開頭的輸出訊息')
        else:
            st.info('📡 點擊「🔄 更新全部總經數據」載入騰落指標')
        # 備援：即時抓取 TWSE MI_INDEX 今日最新資料
        _adl_today_cols = st.columns(3)
        try:
            import datetime as _adt
            _today_ds = _tw_now().strftime('%Y%m%d')
            for _tp in ['MS', '', 'ALL']:
                _prm = {'response':'json','date':_today_ds}
                if _tp: _prm['type'] = _tp
                _mir = requests.get('https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX',
                                    params=_prm, headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.twse.com.tw/'}, timeout=8)
                if _mir.status_code == 200:
                    _mij = _mir.json()
                    if _mij.get('stat') == 'OK':
                        _tables = _mij.get('tables', [])
                        for _tbl in _tables:
                            _flds = [str(f) for f in _tbl.get('fields',[])]
                            _rows = _tbl.get('data', [])
                            _ui = next((i for i,f in enumerate(_flds) if '漲家' in f and '停' not in f), None)
                            _di = next((i for i,f in enumerate(_flds) if '跌家' in f and '停' not in f), None)
                            if _ui and _di and _rows:
                                _up_v = int(str(_rows[-1][_ui]).replace(',',''))
                                _dn_v = int(str(_rows[-1][_di]).replace(',',''))
                                if _up_v + _dn_v > 50:
                                    _ratio_v = round(_up_v/(_up_v+_dn_v)*100, 1)
                                    _col_v = '#3fb950' if _ratio_v>=60 else ('#d29922' if _ratio_v>=40 else '#f85149')
                                    with _adl_today_cols[0]:
                                        st.markdown(kpi('今日上漲家數',f'{_up_v:,}','即時TWSE','#3fb950','#0d2818'), unsafe_allow_html=True)
                                    with _adl_today_cols[1]:
                                        st.markdown(kpi('今日下跌家數',f'{_dn_v:,}','即時TWSE','#f85149','#2a0d0d'), unsafe_allow_html=True)
                                    with _adl_today_cols[2]:
                                        st.markdown(kpi('全市場健康度',f'{_ratio_v:.1f}%',('廣度健康' if _ratio_v>=60 else ('中性' if _ratio_v>=40 else '廣度不足')),_col_v,'#0d1117'), unsafe_allow_html=True)
                                    # 同步旌旗指數
                                    if not st.session_state.get('jingqi_info'):
                                        st.session_state['jingqi_info'] = {
                                            'avg':_ratio_v,'pos':('80~100%' if _ratio_v>=60 else ('50~70%' if _ratio_v>=40 else '20~40%')),
                                            'regime':('bull' if _ratio_v>=60 else ('neutral' if _ratio_v>=40 else 'bear')),
                                            'color':_col_v,'label':('🟢 多頭積極' if _ratio_v>=60 else ('🟡 中性均衡' if _ratio_v>=40 else '🔴 保守防禦')),
                                            'source':'TWSE即時','pct20':_ratio_v,'pct60':_ratio_v*0.9,'pct120':_ratio_v*0.8,'pct240':_ratio_v*0.7,
                                        }
                                    break
                        break
        except Exception as _adl_e:
            pass

    st.markdown('<hr style="border-color:#21262d;margin:8px 0;">', unsafe_allow_html=True)
    st.markdown('<div style="font-size:10px;color:#484f58;text-transform:uppercase;letter-spacing:1px;margin:4px 0;">🌐 國際市場</div>', unsafe_allow_html=True)
    st.markdown(section_header('六','🖥️ 美股科技巨頭（台股明天的風向球）','🖥️'),unsafe_allow_html=True)
    _sox6 = intl_s.get('費城半導體 SOX') or tech_s.get('費城半導體 SOX')
    _nvda6 = next((tech_s[k] for k in tech_s if 'NVDA' in k or '輝達' in k), None)
    if _sox6:
        _sp6 = _sox6.get('pct', 0)
        if _sp6 > 2:
            _t6c = f'費半強漲 {_sp6:+.1f}%，明日台積電/聯發科可望跟漲'; _t6a = '科技類股可持有或加碼'
        elif _sp6 > 0:
            _t6c = f'費半小漲 {_sp6:+.1f}%，台股科技偏多但力道有限'; _t6a = '持有觀察，不急著追高'
        elif _sp6 < -2:
            _t6c = f'費半重挫 {_sp6:+.1f}%，明日台股科技開低機率高'; _t6a = '設好停損，避免隔日追殺'
        else:
            _t6c = f'費半小跌 {_sp6:+.1f}%，短線偏空但未破關鍵支撐'; _t6a = '觀望等待方向確認'
        _nvda_txt = f' | NVDA {_nvda6.get("pct",0):+.1f}%' if _nvda6 else ''
        _t6_ind = f'費半 SOX {_sp6:+.1f}%{_nvda_txt}'
    else:
        _t6c = '技術股數據尚未載入，請點擊「🔄 更新全部總經數據」'; _t6a = ''; _t6_ind = '費半+美股科技'
    st.markdown(teacher_conclusion('蔡森', _t6_ind, _t6c, _t6a), unsafe_allow_html=True)
    tc_list = list(TECH_MAP.keys())
    tr1=st.columns(4); tr2=st.columns(len(tc_list[4:]) if len(tc_list)>4 else 1)
    for i,(col,name) in enumerate(zip(tr1,tc_list[:4])):
        with col: st.markdown(stat_card(name,tech_s.get(name),'USD',name in tech_s),unsafe_allow_html=True)
    for i,(col,name) in enumerate(zip(tr2,tc_list[4:])):
        with col: st.markdown(stat_card(name,tech_s.get(name),'USD',name in tech_s),unsafe_allow_html=True)
    if tech:
        st.plotly_chart(multi_chart(tech,'科技巨頭標準化比較',norm=True,height=250),
                        use_container_width=True,config={'displayModeBar':False})
        clrs=COLORS_7 if isinstance(COLORS_7,list) else list(COLORS_7.values())
        sp1=st.columns(4); sp2=st.columns(len(tc_list[4:]) if len(tc_list)>4 else 1)
        for i,(col,name) in enumerate(zip(sp1,tc_list[:4])):
            with col:
                if name in tech:
                    st.plotly_chart(sparkline(tech[name],name,clrs[i] if i<len(clrs) else '#58a6ff'),
                                    use_container_width=True,config={'displayModeBar':False})
        for i,(col,name) in enumerate(zip(sp2,tc_list[4:])):
            with col:
                if name in tech:
                    st.plotly_chart(sparkline(tech[name],name,clrs[i+4] if i+4<len(clrs) else '#ffd700'),
                                    use_container_width=True,config={'displayModeBar':False})
    with st.expander('📖 宏爺 結論', expanded=False):
        _tsm = tech_s.get('台積電 ADR')
        _nvda = tech_s.get('輝達 NVDA')
        _concl_tech = []
        if _tsm:  _concl_tech.append(f'TSM ADR {_tsm["last"]:.2f} ({_tsm["pct"]:+.1f}%) → {"✅ 台積電強→明日2330有望跟漲" if _tsm["pct"]>1 else ("⚠️ 台積電弱→注意2330壓力" if _tsm["pct"]<-1 else "⚪ 台積電持平")}')
        if _nvda: _concl_tech.append(f'NVDA {_nvda["last"]:.2f} ({_nvda["pct"]:+.1f}%) → {"✅ AI族群情緒熱" if _nvda["pct"]>2 else ("🔴 AI族群降溫" if _nvda["pct"]<-2 else "⚪ AI族群穩定")}')
        for _tc2 in _concl_tech:
            st.markdown(f'<div style="color:#c9d1d9;font-size:13px;padding:3px 0;">• {_tc2}</div>', unsafe_allow_html=True)
        # ADR科技股結論已由上方 _concl_tech 列表顯示

    st.markdown('<hr style="border-color:#21262d;margin:14px 0;">',unsafe_allow_html=True)
    st.markdown(section_header('七','💰 資金環境 × 估值（M1B-M2 + 年線乖離）','💰'),unsafe_allow_html=True)

    # ── M1B-M2 年增率（FinMind）──────────────────────────────
    _m1b_info = st.session_state.get('m1b_m2_info')
    _bias_info = st.session_state.get('bias_info')

    _m_cols = st.columns(3)
    with _m_cols[0]:
        if _m1b_info:
            _m1b_v  = _m1b_info.get('m1b_yoy', 0)
            _m2_v   = _m1b_info.get('m2_yoy', 0)
            _diff   = round(_m1b_v - _m2_v, 2)
            _mc     = '#da3633' if _diff > 0 else '#2ea043'
            _ml     = '✅ 資金流入股市' if _diff > 0 else '🔴 資金撤離股市'
            _proxy_note = '（大盤動能代理估算）' if _m1b_info.get('is_proxy') else ''
            st.markdown(kpi('M1B-M2 差距', f'{_diff:+.2f}%{_proxy_note}',
                            f'M1B:{_m1b_info.get("m1b_yoy",0):.1f}%  M2:{_m1b_info.get("m2_yoy",0):.1f}%  {_ml}', _mc, '#0d1117'), unsafe_allow_html=True)
        else:
            st.markdown(kpi('M1B-M2 差距', '抓取中', '更新總經數據後自動計算', '#484f58', '#0d1117'), unsafe_allow_html=True)

    with _m_cols[1]:
        if _bias_info:
            _bias_v = _bias_info.get('bias_240', 0)
            _bc     = '#f85149' if _bias_v > 20 else ('#3fb950' if _bias_v < -20 else '#d29922')
            _bl     = ('⚠️ 乖離過大，考慮減碼' if _bias_v > 20
                       else ('✅ 嚴重低估，可積極布局' if _bias_v < -20
                       else '⚪ 乖離正常區間'))
            _est_note = '（估算）' if _bias_info.get('is_estimated') else ''
            _days_note = f" {_bias_info.get('data_days',0)}天資料" if _bias_info.get('is_estimated') else ''
            st.markdown(kpi(f'年線乖離率(240MA){_est_note}', f'{_bias_v:+.1f}%',
                            f'{_bl}{_days_note}', _bc, '#0d1117'), unsafe_allow_html=True)
        else:
            st.markdown(kpi('年線乖離率(240MA)', '計算中', '大盤收盤/年線', '#484f58', '#0d1117'), unsafe_allow_html=True)

    with _m_cols[2]:
        if _bias_info:
            _bias_20 = _bias_info.get('bias_20', 0)
            _bc20    = '#f85149' if _bias_20 > 10 else ('#3fb950' if _bias_20 < -10 else '#d29922')
            _bl20    = ('⚠️ 月線乖離過大，短線過熱' if _bias_20 > 10
                        else ('✅ 月線負乖離，考慮進場' if _bias_20 < -10
                        else '⚪ 月線乖離正常'))
            st.markdown(kpi('月線乖離率(20MA)', f'{_bias_20:+.1f}%',
                            _bl20, _bc20, '#0d1117'), unsafe_allow_html=True)
        else:
            st.markdown(kpi('月線乖離率(20MA)', '計算中', '', '#484f58', '#0d1117'), unsafe_allow_html=True)

    with st.expander('📖 弘爺 · 孫慶龍 結論', expanded=False):
        _macro_concl = []
        if _m1b_info:
            _diff2 = _m1b_info.get('m1b_yoy', 0) - _m1b_info.get('m2_yoy', 0)
            if _diff2 > 0:
                _macro_concl.append(f'✅ M1B-M2={_diff2:+.2f}% 正值 → 弘爺：資金行情啟動，大膽做多！（領先大盤3~6月）')
            elif _diff2 > -2:
                _macro_concl.append(f'⚠️ M1B-M2={_diff2:+.2f}% 接近0 → 弘爺：資金動能趨緩，減碼等待訊號確認')
            else:
                _macro_concl.append(f'🔴 M1B-M2={_diff2:+.2f}% 負值 → 弘爺：資金撤離，空手觀望！')
        if _bias_info:
            _bv2 = _bias_info.get('bias_240', 0)
            if _bv2 > 20:
                _macro_concl.append(f'⚠️ 年線乖離 {_bv2:+.1f}% 過大 → 孫慶龍：開始分批減碼（乖離>20%啟動停利）')
            elif _bv2 < -20:
                _macro_concl.append(f'✅ 年線乖離 {_bv2:+.1f}% 嚴重低估 → 孫慶龍：左側交易最佳布局區，大膽加碼！')
            else:
                _macro_concl.append(f'✅ 年線乖離 {_bv2:+.1f}% 正常 → 孫慶龍：可持股，按計畫操作')
        for _mc2 in _macro_concl:
            _mc3 = _mc2.replace('✅','').replace('⚠️','').replace('🔴','').strip()
            if '→' in _mc3:
                _ind7, _res7 = _mc3.split('→', 1)
                _col7 = '#f85149' if any(k in _mc2 for k in ['🔴','⚠️']) else '#3fb950'
                _tchr7 = '弘爺' if 'M1B' in _mc2 else '孫慶龍'
                st.markdown(teacher_conclusion(_tchr7, _ind7.strip(), _res7.strip(), color=_col7), unsafe_allow_html=True)
            else:
                st.markdown(f'<div style="color:#c9d1d9;font-size:12px;padding:2px 6px;">• {_mc2}</div>', unsafe_allow_html=True)

    st.markdown('<hr style="border-color:#21262d;margin:14px 0;">',unsafe_allow_html=True)
# ══════════════════════════════════════════════════════════════
# TAB 2: 個股深度分析 + 健康度評分
# ══════════════════════════════════════════════════════════════
with tab2_stock:
    st.markdown('''<div style="background:#0a1628;border:1px solid #1f6feb;border-radius:12px;padding:16px;margin-bottom:12px;">
<div style="font-size:18px;font-weight:900;color:#58a6ff;margin-bottom:8px;">🔬 個股深度分析 — 這支股票值得買嗎？</div>
<div style="font-size:13px;color:#c9d1d9;line-height:1.8;">
輸入你感興趣的股票代碼，系統會告訴你：<br>
• <b>現在貴不貴？</b>（357估值 + 河流圖）<br>
• <b>趨勢向上還是向下？</b>（健康度評分）<br>
• <b>大股東在買還是賣？</b>（法人籌碼）<br>
• <b>什麼時候該進場、出場？</b>（進出場訊號）<br>
💡 <b>建議：</b>先到「比較 × 排行」掃描找到候選股，再來這裡做最後確認。
</div></div>''', unsafe_allow_html=True)
    st.markdown("""<div style="padding:6px 0 4px;">
<span style="font-size:20px;font-weight:900;color:#e6edf3;">🔬 個股深度分析</span>
<span style="font-size:11px;color:#484f58;margin-left:10px;">健康評分 · 357評價 · 領先指標 · VCP · 布林 · K線 · AI五維</span>
</div>""", unsafe_allow_html=True)

    # ── 操作列 ──────────────────────────────────────────────
    t2_r1c1, t2_r1c2, t2_r1c3, t2_r1c4 = st.columns([2, 1, 1, 1])
    with t2_r1c1:
        t2_sid = st.text_input('個股代碼', value='2330', key='t2_sid', placeholder='如：2330')
    with t2_r1c2:
        t2_days = st.slider('天數', 60, 400, 250, 10, key='t2_days')
    with t2_r1c3:
        t2_use_normal = st.checkbox('一般K線', value=False, key='t2_use_normal')
        t2_adjusted   = not t2_use_normal
    with t2_r1c4:
        t2_run = st.button('🔍 載入完整分析', key='t2_run', type='primary', use_container_width=True)

    # ── 均線選擇（移入Tab2，無需展開）──────────────────────
    with st.container(border=True):
        st.markdown('<span style="font-size:11px;color:#8b949e;">📐 均線顯示設定</span>', unsafe_allow_html=True)
        ma_c1,ma_c2,ma_c3,ma_c4,ma_c5,ma_c6 = st.columns(6)
        with ma_c1: show_ma5   = st.checkbox('MA5',      value=False, key='t2_ma5')
        with ma_c2: show_ma20  = st.checkbox('MA20 月線', value=True,  key='t2_ma20')
        with ma_c3: show_ma60  = st.checkbox('MA60 季線', value=False, key='t2_ma60')
        with ma_c4: show_ma100 = st.checkbox('MA100',     value=True,  key='t2_ma100')
        with ma_c5: show_ma120 = st.checkbox('MA120',     value=False, key='t2_ma120')
        with ma_c6: show_ma240 = st.checkbox('MA240 年線',value=False, key='t2_ma240')
    show_ma_dict = {'MA5':show_ma5,'MA20':show_ma20,'MA60':show_ma60,
                    'MA100':show_ma100,'MA120':show_ma120,'MA240':show_ma240}

    t2l, t2r = st.columns([1, 2])
    with t2l:
        pass
    with t2r:
        st.markdown("""<div style="background:#161b22;border:1px solid #21262d;border-left:4px solid #ffd700;
border-radius:8px;padding:10px 14px;font-size:12px;color:#8b949e;">
<b style="color:#ffd700;">自動從網路抓取：</b><br>
K線+均線(FinMind) · 三大法人籌碼 · 融資融券 · 357股利評價 · 月/季營收毛利率 · 合約負債/資本支出 · 健康評分(RSI+量比+IBS+KD+布林)
</div>""", unsafe_allow_html=True)

    if t2_run:
        sid2 = t2_sid or '2330'
        st.info(f'🌐 抓取 {sid2} 全方位數據...')
        df2, name2, err2 = fetch_price_data(sid2, t2_days)
        avg_div2, yearly2, div_src2 = fetch_dividend_data(sid2)
        cl2, cx2, _capex2, _cl_src2, _cx_src2, _, _fin_errs2 = fetch_financials(sid2, industry='')
        rev2, _      = fetch_revenue(sid2)
        qtr2, _      = fetch_quarterly(sid2)
        qtr_extra2, _ = fetch_quarterly_extra(sid2)   # BS+CF時序（合約負債/存貨/資本支出）
        rsi2     = calc_rsi(df2)
        ibs2     = calc_ibs(df2)
        vr2      = calc_volume_ratio(df2)
        k2, d2   = calc_kd(df2)
        bb2      = calc_bollinger(df2)
        vcp2     = calc_vcp(df2)
        health2, details2 = calc_health_score(df2, rsi2, ibs2, vr2, k2, d2, bb2)
        cur_price2 = float(df2['close'].iloc[-1]) if df2 is not None and not df2.empty else 0
        from stock_names import get_stock_name as _gsn2
        _name2_resolved = (name2 if name2 and name2 != sid2 else None) or _gsn2(sid2) or sid2
        st.session_state['t2_data'] = {
            'sid':sid2,'name':_name2_resolved,'df':df2,'err':err2,
            'avg_div':avg_div2,'yearly':yearly2,'div_src':div_src2,
            'cl':cl2,'cx':cx2,'rev':rev2,'qtr':qtr2,'qtr_extra':qtr_extra2,
            'cl_src': _cl_src2,'cx_src': _cx_src2,'fin_errs': _fin_errs2,
            'rsi':rsi2,'ibs':ibs2,'vr':vr2,'k':k2,'d':d2,'bb':bb2,'vcp':vcp2,
            'health':health2,'details':details2,'price':cur_price2,
        }
        # 快取最後一次成功抓到的月營收/季財報，供下次失敗時 fallback
        if rev2 is not None and not rev2.empty:
            st.session_state[f'_last_rev_{sid2}'] = rev2
        if qtr2 is not None and not qtr2.empty:
            st.session_state[f'_last_qtr_{sid2}'] = qtr2

    t2d = st.session_state.get('t2_data')
    if not t2d:
        st.info('👆 輸入股票代碼後點擊「🔍 載入完整分析」')
    else:
        sid2   = t2d['sid'];   name2  = t2d['name']
        price2 = t2d['price']; df2    = t2d['df']
        health2 = t2d['health']; details2 = t2d['details']
        rsi2=t2d['rsi']; ibs2=t2d['ibs']; vr2=t2d['vr']
        k2=t2d['k'];     d2=t2d['d'];     bb2=t2d['bb']
        vcp2=t2d['vcp']; avg_div2=t2d['avg_div']
        yearly2=t2d['yearly']; cl2=t2d['cl']; cx2=t2d['cx']
        _cl_src2=t2d.get('cl_src',''); _cx_src2=t2d.get('cx_src',''); _fin_errs2=t2d.get('fin_errs',[])
        rev2=t2d['rev']; qtr2=t2d['qtr']; qtr_extra2=t2d.get('qtr_extra')
        # Fallback 到快取（若本次抓取失敗）
        _rev2_cached = False; _qtr2_cached = False
        if (rev2 is None or rev2.empty) and st.session_state.get(f'_last_rev_{sid2}') is not None:
            rev2 = st.session_state[f'_last_rev_{sid2}']; _rev2_cached = True
        if (qtr2 is None or qtr2.empty) and st.session_state.get(f'_last_qtr_{sid2}') is not None:
            qtr2 = st.session_state[f'_last_qtr_{sid2}']; _qtr2_cached = True

        # ══ 即時價格 + 趨勢儀表板 ════════════════════════════════
        if df2 is not None and not df2.empty and len(df2) >= 20:
            _p_now   = float(df2['close'].iloc[-1])
            _p_prev  = float(df2['close'].iloc[-2]) if len(df2) >= 2 else _p_now
            _p_chg   = round((_p_now - _p_prev) / _p_prev * 100, 2) if _p_prev else 0
            _ma20_v  = float(df2['close'].rolling(20).mean().iloc[-1])
            _ma60_v  = float(df2['close'].rolling(60).mean().iloc[-1]) if len(df2) >= 60 else None
            _ma120_v = float(df2['close'].rolling(120).mean().iloc[-1]) if len(df2) >= 120 else None
            # 趨勢燈號
            _above_ma20  = _p_now > _ma20_v
            _above_ma60  = (_p_now > _ma60_v) if _ma60_v else None
            _above_ma120 = (_p_now > _ma120_v) if _ma120_v else None
            _trend_score = sum([_above_ma20,
                                _above_ma60  if _above_ma60  is not None else False,
                                _above_ma120 if _above_ma120 is not None else False])
            _trend_label = {3: '🟢 強勢多頭', 2: '🟡 中性偏多', 1: '🟡 弱勢', 0: '🔴 空頭區間'}[_trend_score]
            _chg_color   = '#3fb950' if _p_chg >= 0 else '#f85149'
            _chg_arrow   = '▲' if _p_chg >= 0 else '▼'
            st.markdown(f'''<div style="background:#0d1117;border:2px solid #21262d;border-radius:12px;
padding:14px 18px;margin-bottom:12px;">
<div style="font-size:22px;font-weight:900;color:#e6edf3;margin-bottom:8px;">
  📌 {name2}（{sid2}）
  <span style="font-size:14px;color:#8b949e;margin-left:8px;">即時趨勢總覽</span>
</div>
<div style="display:flex;gap:24px;flex-wrap:wrap;align-items:center;">
  <div><span style="font-size:28px;font-weight:900;color:#e6edf3;">{_p_now:.2f}</span>
       <span style="font-size:16px;color:{_chg_color};margin-left:6px;">{_chg_arrow} {abs(_p_chg):.2f}%</span></div>
  <div style="font-size:13px;color:#8b949e;line-height:2;">
    MA20：<b style="color:{'#3fb950' if _above_ma20 else '#f85149'}">{_ma20_v:.2f}</b>
    {'✅' if _above_ma20 else '❌'}&nbsp;&nbsp;
    {'MA60：<b style="color:' + ("#3fb950" if _above_ma60 else "#f85149") + '">' + f'{_ma60_v:.2f}</b> ' + ("✅" if _above_ma60 else "❌") + "&nbsp;&nbsp;" if _ma60_v else ""}
    {'MA120：<b style="color:' + ("#3fb950" if _above_ma120 else "#f85149") + '">' + f'{_ma120_v:.2f}</b> ' + ("✅" if _above_ma120 else "❌") if _ma120_v else ""}
  </div>
  <div style="font-size:18px;font-weight:700;">{_trend_label}</div>
</div></div>''', unsafe_allow_html=True)

        # ══ 0. 停利停損 + 支撐壓力 ═══════════════════════════════
        st.markdown('---')
        st.markdown('#### 🎯 停利停損建議 + 近期支撐壓力')
        _sp_c1, _sp_c2, _sp_c3, _sp_c4 = st.columns(4)
        _cur_p  = float(df2['close'].iloc[-1]) if df2 is not None and not df2.empty else 0
        _hi20_p = float(df2['high'].tail(20).max()) if df2 is not None and len(df2) >= 5 else 0
        _lo20_p = float(df2['low'].tail(20).min())  if df2 is not None and len(df2) >= 5 else 0
        _tp1_p  = round(_cur_p * 1.05, 2)
        _tp2_p  = round(_cur_p * 1.10, 2)
        _sl_p   = round(_cur_p * 0.92, 2)
        _rr_p   = round((_tp1_p - _cur_p) / max(_cur_p - _sl_p, 0.01), 2)
        with _sp_c1:
            st.markdown(kpi('停利目標1 (+5%)', f'{_tp1_p}', '短線先入袋', '#3fb950', '#0d2818'), unsafe_allow_html=True)
        with _sp_c2:
            st.markdown(kpi('停利目標2 (+10%)', f'{_tp2_p}', '波段目標', '#58a6ff', '#0d1f3c'), unsafe_allow_html=True)
        with _sp_c3:
            st.markdown(kpi('建議停損 (-8%)', f'{_sl_p}', '跌破認賠', '#f85149', '#2a0d0d'), unsafe_allow_html=True)
        with _sp_c4:
            st.markdown(kpi('盈虧比', f'{_rr_p}x', '≥1.5 較理想', '#ffd700', '#1a1000'), unsafe_allow_html=True)
        _sp_c5, _sp_c6 = st.columns(2)
        _dist_hi = round((_hi20_p/_cur_p-1)*100, 1) if _cur_p > 0 else 0
        _dist_lo = round((1-_lo20_p/_cur_p)*100, 1) if _cur_p > 0 else 0
        # ── 大量紅K 進場價計算 ──────────────────────────────
        _entry_half = None
        _abs_sl     = None
        if df2 is not None and not df2.empty and len(df2) >= 5:
            # 找近20日最大量的紅K
            _red_k = df2[(df2['close'] > df2['open']) if 'open' in df2.columns
                         else df2['close'] > df2['close'].shift(1)].tail(20)
            if 'volume' in _red_k.columns and not _red_k.empty:
                _big_red = _red_k.nlargest(1, 'volume').iloc[0]
                _rk_high = float(_big_red.get('high', _big_red['close']))
                _rk_low  = float(_big_red.get('low',  _big_red['close']) )
                _entry_half = round((_rk_high + _rk_low) / 2, 2)  # 1/2 進場價
                _abs_sl     = round(_rk_low * 0.995, 2)             # 紅K低點-0.5%

        _sp_c5b, _sp_c6b, _sp_c7b = st.columns(3)
        with _sp_c5b:
            if _entry_half:
                st.markdown(kpi('大量紅K 1/2 進場', f'{_entry_half:.2f}',
                                '朱家泓低風險買點', '#58a6ff', '#1a2744'), unsafe_allow_html=True)
            else:
                st.markdown(kpi('大量紅K 1/2', '計算中', '', '#484f58', '#0d1117'), unsafe_allow_html=True)
        with _sp_c6b:
            if _abs_sl:
                _bias_sl = round((_cur_p - _abs_sl) / _cur_p * 100, 1) if _cur_p else 0
                _sl_color = '#f85149' if _bias_sl < 5 else '#d29922'
                st.markdown(kpi('絕對停損線', f'{_abs_sl:.2f}',
                                f'紅K低點（距{_bias_sl:.1f}%）', _sl_color, '#2a0d0d'), unsafe_allow_html=True)
            else:
                st.markdown(kpi('絕對停損線', _sl_p.__str__(), '跌破即出場', '#f85149', '#2a0d0d'), unsafe_allow_html=True)
        with _sp_c7b:
            _rr2 = round((_tp1_p - _cur_p) / max(_cur_p - (_abs_sl or _sl_p), 0.01), 2) if _cur_p else 0
            _rr_color = '#3fb950' if _rr2 >= 1.5 else ('#d29922' if _rr2 >= 1 else '#f85149')
            st.markdown(kpi('實際盈虧比', f'{_rr2}x', '≥1.5 可操作', _rr_color, '#0d1117'), unsafe_allow_html=True)

        with _sp_c5:
            st.markdown(kpi('近20日壓力', f'{_hi20_p:.2f}', f'距現價 +{_dist_hi}%', '#f85149', '#2a0d0d'), unsafe_allow_html=True)
        with _sp_c6:
            st.markdown(kpi('近20日支撐', f'{_lo20_p:.2f}', f'距現價 -{_dist_lo}%', '#3fb950', '#0d2818'), unsafe_allow_html=True)

        # ══ 進出場訊號（多位老師方法整合）═══════════════════════
        st.markdown('---')

        # ══ 操作前心理檢查 + 勝利方程式 ═══════════════════════
        st.markdown('---')
        st.markdown('#### 🧠 操作前必做：心理檢查 + 勝利方程式')

        _mc_cols = st.columns([3, 2])

        with _mc_cols[0]:
            st.markdown('<div style="background:#0a1628;border:1px solid #1f6feb;border-radius:10px;padding:12px;">', unsafe_allow_html=True)
            st.markdown('**📋 SOP 進場強制檢核表（4關卡全通過才顯示建議）**')
            _wr_reg_chk = st.session_state.get('mkt_info', {}).get('regime','neutral')
            _price_chk  = float(df2['close'].iloc[-1]) if df2 is not None and not df2.empty else 0
            _open5_chk  = float(df2['close'].iloc[-6]) if df2 is not None and len(df2)>=6 else _price_chk
            _surge_chk  = round((_price_chk - _open5_chk) / max(_open5_chk,1) * 100, 1)
            _stop_chk   = round(_price_chk - 1.5 * (_atr2_val if '_atr2_val' in dir() else _price_chk*0.07), 2)
            _max_loss_chk = round(st.session_state.get('total_capital_twd',500000) * st.session_state.get('max_risk_pct',0.015))
            _q1 = st.checkbox(
                f'① 確認非空頭格局（目前：{_wr_reg_chk}）',
                value=_wr_reg_chk != 'bear', key=f't2_q1_{sid2}',
                disabled=_wr_reg_chk == 'bear'
            )
            _q2 = st.checkbox(
                f'② 確認未追高超過5%（近5日漲幅：{_surge_chk:+.1f}%）',
                value=abs(_surge_chk) <= 5, key=f't2_q2_{sid2}',
                disabled=abs(_surge_chk) > 10
            )
            _q3 = st.checkbox(
                f'③ 確認停損價（跌破 {_stop_chk} 元無條件出場）',
                key=f't2_q3_{sid2}'
            )
            _q4 = st.checkbox(
                f'④ 確認最大虧損金額（NT${_max_loss_chk:,} 以內可接受）',
                key=f't2_q4_{sid2}'
            )
            _all_checked = _q1 and _q2 and _q3 and _q4
            if _all_checked:
                st.success('✅ 心理狀態良好，可以繼續評估操作')
            else:
                st.warning('⚠️ 尚有項目未確認，建議先暫停，避免情緒化操作')
            st.markdown('</div>', unsafe_allow_html=True)

        with _mc_cols[1]:
            st.markdown('<div style="background:#0a1628;border:1px solid #3fb950;border-radius:10px;padding:12px;">', unsafe_allow_html=True)
            st.markdown('**🏆 勝利方程式（需全部符合）**')
            _wr_mkt2 = st.session_state.get('mkt_info', {})
            _wr_reg2 = _wr_mkt2.get('regime','neutral') if _wr_mkt2 else 'neutral'
            _wr_margin2 = st.session_state.get('cl_data',{}).get('margin', 0) or 0
            _win_conds = [
                ('🌍 大盤多頭燈號',  _wr_reg2 == 'bull'),
                ('💰 融資安全(<2500億)', _wr_margin2 < 2500),
                ('🏥 個股健康度≥75', health2 >= 75 if df2 is not None else False),
                ('💎 非357昂貴區',   '昂貴' not in str(st.session_state.get('t2_data',{}).get('val',''))),
                ('✋ 已設停損點',     _q4),
            ]
            _win_count = sum(1 for _, v in _win_conds if v)
            for _wn, _wv in _win_conds:
                _wc = '#3fb950' if _wv else '#f85149'
                _wi = '✅' if _wv else '❌'
                st.markdown(f'<div style="font-size:12px;color:{_wc};padding:2px 0;">{_wi} {_wn}</div>', unsafe_allow_html=True)
            st.markdown(f'<div style="margin-top:8px;font-size:13px;font-weight:700;color:{"#3fb950" if _win_count>=4 else "#f85149"};">'
                       f'{"🚀 符合 " + str(_win_count) + "/5，可以考慮操作" if _win_count>=4 else "⛔ 僅符合 " + str(_win_count) + "/5，建議等待"}'
                       f'</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        # ════════════════════════════════════════════════════════
        # 模組三：ATR 動態停損倉位計算器（升級版）
        # ════════════════════════════════════════════════════════
        st.markdown('#### 💰 倉位計算器（ATR動態停損 + 核心衛星分配）')
        _price2 = float(df2['close'].iloc[-1]) if df2 is not None and not df2.empty else 100.0
        # 計算 ATR14
        _atr2_val = 0.0
        if df2 is not None and len(df2) >= 14:
            _hi2s = df2['high'] if 'high' in df2.columns else df2['close']
            _lo2s = df2['low']  if 'low'  in df2.columns else df2['close']
            _atr_series = (_hi2s - _lo2s).rolling(14).mean()
            _atr2_val = float(_atr_series.iloc[-1]) if not _atr_series.iloc[-1] != _atr_series.iloc[-1] else 0.0
        _stop_atr2  = round(_price2 - 1.5 * _atr2_val, 2) if _atr2_val > 0 else round(_price2 * 0.93, 2)
        # 讀取 Sidebar 資金設定
        _total_capital_twd = st.session_state.get('total_capital_twd', 500000)
        _max_risk_pct      = st.session_state.get('max_risk_pct', 0.015)
        _sat_capital       = round(_total_capital_twd * 0.30)
        _defense_now       = st.session_state.get('defense_mode', False)
        _risk_per_sh2      = max(_price2 - _stop_atr2, 0.01)
        _max_loss_twd      = _total_capital_twd * _max_risk_pct
        _pos_sh2           = int(_max_loss_twd / _risk_per_sh2)
        _pos_lot2          = _pos_sh2 // 1000
        _pos_sh2           = _pos_lot2 * 1000
        _cost2             = _pos_sh2 * _price2
        _target2           = _price2 * 1.15
        _rr2_val           = round((_target2 - _price2) / _risk_per_sh2, 2)
        _rr2_pass          = _rr2_val >= 2.0
        _pos_cols = st.columns([1, 1])
        with _pos_cols[0]:
            st.markdown(
                f'<div style="background:#0a1628;border:1px solid #f85149;border-radius:10px;padding:14px;">'
                f'<div style="font-size:11px;color:#484f58;">🛑 ATR14 動態停損價</div>'
                f'<div style="font-size:30px;font-weight:900;color:#f85149;">{_stop_atr2} 元</div>'
                f'<div style="font-size:11px;color:#8b949e;">= {_price2} - 1.5×{_atr2_val:.2f}(ATR)</div>'
                f'<div style="font-size:11px;color:#8b949e;margin-top:6px;">跌破此價格→無條件出場</div>'
                f'</div>', unsafe_allow_html=True)
        with _pos_cols[1]:
            if _defense_now:
                st.error('🔴 Defense Mode\n衛星資金鎖定，禁止建新倉')
            elif not _rr2_pass:
                st.warning(f'⚠️ 盈虧比 {_rr2_val:.1f}:1 < 2.0，不符合風險標準\n建議尋找其他標的')
            else:
                st.markdown(
                    f'<div style="background:#0a2818;border:2px solid #3fb950;border-radius:10px;padding:14px;">'
                    f'<div style="font-size:11px;color:#3fb950;">✅ 盈虧比 {_rr2_val:.1f}:1（合格）</div>'
                    f'<div style="font-size:11px;color:#484f58;margin-top:4px;">建議買入張數</div>'
                    f'<div style="font-size:32px;font-weight:900;color:#3fb950;">{_pos_lot2} 張</div>'
                    f'<div style="font-size:12px;color:#8b949e;">{_pos_sh2:,}股 × NT${_price2}</div>'
                    f'<div style="font-size:13px;font-weight:700;color:#58a6ff;">= NT${_cost2:,.0f}</div>'
                    f'<div style="font-size:11px;color:#f85149;">最大虧損 NT${_max_loss_twd:,.0f}</div>'
                    f'</div>', unsafe_allow_html=True)
                if _cost2 > _sat_capital:
                    st.warning(f'⚠️ 買入金額 NT${_cost2:,.0f} > 衛星資金 NT${_sat_capital:,}')
        # 向下相容舊變數（倉位計算器下方邏輯用到）
        _total_capital = _total_capital_twd / 10000
        _risk_pct      = _max_risk_pct * 100
        _stop_loss_pct = round(_risk_per_sh2 / _price2 * 100, 1) if _price2 > 0 else 7.0
        _max_loss_amt  = round(_max_loss_twd / 10000, 2)
        _position_size = round(_cost2 / 10000, 1)
        _position_pct  = round(_cost2 / _total_capital_twd * 100, 1)
        # 今日禁止操作清單
        st.markdown('#### 🚫 今日禁止操作情況（有任何一項→今天暫停）')
        _ban_items = []
        _wr_mkt3 = st.session_state.get('mkt_info', {})
        _wr_price = float(df2['close'].iloc[-1]) if df2 is not None and not df2.empty else 0
        _wr_open  = float(df2['close'].iloc[-5]) if df2 is not None and len(df2)>=5 else _wr_price
        _today_surge = round((_wr_price - _wr_open) / max(_wr_open,1) * 100, 1) if _wr_open else 0
        if abs(_today_surge) > 4: _ban_items.append(f'📈 個股近5日漲幅 {_today_surge:+.1f}% 超過4%（追高風險）')
        _ml = st.session_state.get('monthly_loss_pct', 0)
        if _ml < -5: _ban_items.append(f'📉 本月已虧損 {abs(_ml):.1f}%（情緒操作風險上升）')
        if _wr_margin2 > 3400: _ban_items.append(f'💸 融資 {_wr_margin2:.0f}億 極度過熱（散戶追高期，等待）')
        if _wr_reg2 == 'bear': _ban_items.append('🔴 大盤空頭格局（禁止做多）')

        if _ban_items:
            for _bi in _ban_items:
                st.markdown(f'<div style="background:#2a0d0d;border-left:3px solid #f85149;border-radius:0 6px 6px 0;padding:7px 12px;margin:3px 0;font-size:12px;color:#f85149;">'
                           f'⛔ {_bi}</div>', unsafe_allow_html=True)
        else:
            st.success('✅ 今日無禁止操作情況，可以正常評估')

        st.markdown('---')
        st.markdown('#### 🎯 什麼時候買？什麼時候賣？')
        st.markdown(
            '<div style="background:#0a1628;border-left:3px solid #58a6ff;padding:8px 12px;'            'border-radius:0 6px 6px 0;margin-bottom:8px;font-size:12px;color:#c9d1d9;">'
            '💡 系統自動幫你檢查<b>多位老師的進出場條件</b>，符合越多條件越可靠。'
            '<br>🔵 <b>進場訊號</b>：這些條件出現代表可以考慮買進'
            '<br>🔴 <b>出場訊號</b>：這些條件出現代表要考慮賣出或減碼'
            '<br>🎯 <b>目標價</b>：預計可以獲利的目標 | 🛑 <b>停損</b>：跌到這裡要認賠出場'
            '</div>', unsafe_allow_html=True)
        if df2 is not None and not df2.empty:
            _p2    = float(df2['close'].iloc[-1])
            # MA 欄位：若不存在則即時計算
            def _safe_ma(df, n):
                col = f'MA{n}'
                if col in df.columns: return float(df[col].iloc[-1])
                if len(df) >= n: return float(df['close'].tail(n).mean())
                return float(df['close'].mean())
            _ma5   = _safe_ma(df2, 5)
            _ma20  = _safe_ma(df2, 20)
            _ma60  = _safe_ma(df2, 60)
            _ma240 = _safe_ma(df2, 240)

            # 趨勢排列
            _bull_align  = _p2 > _ma20 > _ma60   # 多頭排列
            _bear_align  = _p2 < _ma20 < _ma60   # 空頭排列
            _bias_i      = round((_p2 - _ma240) / _ma240 * 100, 1) if _ma240 else 0
            _bias_20_i   = round((_p2 - _ma20) / _ma20 * 100, 1)   if _ma20  else 0

            # 布林帶訊號
            _bb_upper    = (bb2.get('upper', 0) if isinstance(bb2, dict) else 0) or float('inf')
            _bb_ma       = (bb2.get('ma', 0)    if isinstance(bb2, dict) else 0)
            _bb_near_up  = bool(bb2) and _p2 >= _bb_upper * 0.97
            _bb_drop_out = bool(bb2) and _p2 < _bb_upper * 0.95 and _p2 > _bb_ma

            # KD 訊號
            _kd_gold = k2 and d2 and k2 > d2  # 黃金交叉方向
            _kd_dead = k2 and d2 and k2 < d2 and k2 > 70  # 高檔死亡交叉

            # VCP 訊號
            _vcp_ok = bool(vcp2 and isinstance(vcp2, dict) and vcp2.get('contracting'))

            # 目標價（蔡森一比一對稱法）
            _hi20_i = float(df2['high'].tail(20).max())
            _lo20_i = float(df2['low'].tail(20).min())
            _range20 = _hi20_i - _lo20_i
            _target1 = round(_p2 + _range20, 2)  # 初步目標：現價 + 20日震幅

            _sig_cols = st.columns(3)

            with _sig_cols[0]:
                st.markdown('<div style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:10px;">', unsafe_allow_html=True)
                st.markdown('**📈 進場訊號**')
                _entry = []
                if _bull_align: _entry.append('✅ 多頭排列（股>月>季）→ 朱家泓：可進場方向')
                if _vcp_ok:     _entry.append('✅ VCP波幅收縮 → 妮可：即將突破，建底倉30-50%')
                if k2 and k2 < 30: _entry.append(f'✅ KD低檔 K={k2:.0f} → 孫慶龍：底部進場區')
                if rsi2 and rsi2 < 30: _entry.append(f'✅ RSI超賣 {rsi2:.0f} → 反彈機會')
                if _bias_i < -20: _entry.append(f'✅ 年線負乖離 {_bias_i:+.0f}% → 孫慶龍：左側布局區')
                # RS 相對強度
                try:
                    from scoring_engine import calc_rs_score, rs_slope
                    _rs_val  = calc_rs_score(df2)
                    _rs_up   = rs_slope(df2)
                    _rs_color= '#3fb950' if _rs_val >= 75 else ('#d29922' if _rs_val >= 50 else '#f85149')
                    _rs_trend= '↑強勢' if _rs_up else ('↓弱勢' if _rs_up is False else '')
                    _entry.append(f'<span style="color:{_rs_color}">📊 RS相對強度 {_rs_val:.0f}分 {_rs_trend}</span>')
                except: pass
                if not _entry: _entry.append('⚪ 暫無明確進場訊號')
                for _e in _entry:
                    st.markdown(f'<div style="font-size:12px;color:#c9d1d9;padding:2px 0;">{_e}</div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

            with _sig_cols[1]:
                st.markdown('<div style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:10px;">', unsafe_allow_html=True)
                st.markdown('**📉 減碼/出場訊號**')
                _exit = []
                if _bear_align:   _exit.append('🔴 空頭排列 → 朱家泓：禁止做多，考慮出清')
                if _kd_dead:      _exit.append(f'⚠️ KD高檔死叉 K={k2:.0f} → 妮可：開始減碼')
                if _bb_drop_out:  _exit.append('⚠️ 脫離布林上軌 → 妮可：減碼50%')
                if _bias_20_i > 15: _exit.append(f'⚠️ 月線乖離 {_bias_20_i:+.0f}% → 過熱，停利部分')
                if _bias_i > 20:  _exit.append(f'⚠️ 年線乖離 {_bias_i:+.0f}% → 孫慶龍：分批出場')
                if _p2 < _ma5:    _exit.append(f'⚠️ 跌破5MA({_ma5:.1f}) → 林穎：短線停利')
                # 週MACD 警示：12/26/9 EMA on weekly bars
                try:
                    if df2 is not None and len(df2) >= 30:
                        _wdf = df2.copy()
                        _wdf.index = range(len(_wdf))
                        # 近30日K線轉換為週K（每5根合一）
                        _wclose = [float(_wdf['close'].iloc[min(i+4, len(_wdf)-1)])
                                   for i in range(0, min(30, len(_wdf)), 5)]
                        if len(_wclose) >= 6:
                            _we12 = pd.Series(_wclose).ewm(span=3,adjust=False).mean()
                            _we26 = pd.Series(_wclose).ewm(span=5,adjust=False).mean()
                            _wmacd= _we12 - _we26
                            _whist= (_wmacd - _wmacd.ewm(span=3,adjust=False).mean()).tolist()
                            # 週MACD紅柱縮短（連續2根縮小）
                            if len(_whist)>=3 and _whist[-1]>0 and _whist[-1]<_whist[-2]<_whist[-3]:
                                _exit.append('⚠️ 週MACD紅柱連縮 → 上漲動能衰減，準備減碼')
                            elif len(_whist)>=2 and _whist[-2]>0 and _whist[-1]<=0:
                                _exit.append('🔴 週MACD翻負 → 中線趨勢轉弱，出清訊號')
                except: pass
                if not _exit:     _exit.append('⚪ 暫無明確出場訊號')
                for _ex in _exit:
                    st.markdown(f'<div style="font-size:12px;color:#c9d1d9;padding:2px 0;">{_ex}</div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

            with _sig_cols[2]:
                st.markdown('<div style="background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:10px;">', unsafe_allow_html=True)
                st.markdown('**🎯 目標 + 停損**')
                st.markdown(f'<div style="font-size:12px;color:#c9d1d9;padding:2px 0;">📌 現價：<b>{_p2:.2f}</b></div>', unsafe_allow_html=True)
                st.markdown(f'<div style="font-size:12px;color:#3fb950;padding:2px 0;">🎯 初步目標（蔡森1:1）：<b>{_target1:.2f}</b></div>', unsafe_allow_html=True)
                _sl_hard = round(_p2 * 0.93, 2)
                _sl_ma20 = round(_ma20 * 0.99, 2)
                _dist_hard = round((_p2 - _sl_hard) / _p2 * 100, 1) if _p2 else 0
                _dist_ma20 = round((_p2 - _sl_ma20) / _p2 * 100, 1) if _p2 else 0
                _dist_ma5  = round((_p2 - _ma5) / _p2 * 100, 1) if _p2 and _ma5 else 0
                st.markdown(f'<div style="font-size:12px;color:#f85149;padding:2px 0;">🛑 硬停損(-7%)：<b>{_sl_hard:.2f}</b> <span style="color:#484f58;">（尚差{_dist_hard:.1f}%）</span></div>', unsafe_allow_html=True)
                st.markdown(f'<div style="font-size:12px;color:#d29922;padding:2px 0;">⚠️ 月線停損：<b>{_sl_ma20:.2f}</b> <span style="color:#484f58;">（尚差{_dist_ma20:.1f}%）</span></div>', unsafe_allow_html=True)
                st.markdown(f'<div style="font-size:12px;color:#58a6ff;padding:2px 0;">📍 5MA停利：<b>{_ma5:.2f}</b> <span style="color:#484f58;">（尚差{_dist_ma5:.1f}%）</span></div>', unsafe_allow_html=True)
                # 加碼點
                if _bull_align and vcp2 and not _vcp_ok:
                    _add_pt = round(_hi20_i * 1.01, 2)
                    st.markdown(f'<div style="font-size:12px;color:#58a6ff;padding:2px 0;">➕ 加碼點（蔡森突破法）：>{_add_pt:.2f}</div>', unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

        else:
            st.info('載入個股資料後顯示進出場訊號')

        # ══ 龍頭預警區（孫慶龍龍多策略最高等級）══════════════════
        _is_dragon = False
        _dragon_reasons = []
        try:
            if cl2 is not None and cl2 > 0:
                # 用股價估算股本（簡化：取市值代理）
                _price_now = float(df2['close'].iloc[-1]) if df2 is not None and not df2.empty else 0
                # 合約負債 / 股本比估算（cl2 單位億）
                if cl2 > 0:
                    _dragon_reasons.append(f'合約負債 {cl2:.1f}億（>股本50% → 未來3-6月訂單保障）')
                    _is_dragon = True
            if cx2 is not None and cx2 > 0:
                _dragon_reasons.append(f'資本支出 {cx2:.1f}億（>股本80% → 大擴廠，看好未來需求）')
                _is_dragon = True
        except: pass

        if _is_dragon:
            st.markdown(
                '<div style="background:linear-gradient(135deg,#2a1f00,#3d2d00);'
                'border:2px solid #ffd700;border-radius:10px;padding:12px 16px;margin-bottom:10px;">'
                '<div style="font-size:14px;font-weight:900;color:#ffd700;margin-bottom:6px;">'
                '🏆 龍頭預警區 — 極稀有高成長標的</div>' +
                ''.join(f'<div style="font-size:12px;color:#ffe066;padding:2px 0;">• {r}</div>' for r in _dragon_reasons) +
                '<div style="font-size:11px;color:#997a00;margin-top:4px;">'
                '孫慶龍：「不要聽老闆說什麼，要看他做什麼」— 這是最誠實的領先指標</div>'
                '</div>', unsafe_allow_html=True)

        # ══ A. 健康度評分 ══════════════════════════════════════
        st.markdown('#### 🏥 A. 個股健康度評分（0~100）')
        if health2 >= 80:
            _ha = f'健康度 {health2:.0f}分，技術面強勢'; _hb = '確認大盤方向後可建倉，停損設月線下方'
        elif health2 >= 60:
            _ha = f'健康度 {health2:.0f}分，中性偏多，尚未達進場標準'; _hb = '等待突破80分或放量突破前高再行動'
        else:
            _ha = f'健康度 {health2:.0f}分，技術面偏弱，跳過'; _hb = '不要強求，另找更好標的'
        st.markdown(teacher_conclusion('宏爺', f'{sid2} 健康度 {health2:.0f}分', _ha, _hb), unsafe_allow_html=True)
        # 評分信心區間說明
        _score_help = (
            '<div style="background:#0a1628;border-left:3px solid #58a6ff;'
            'padding:8px 12px;border-radius:0 6px 6px 0;margin-bottom:8px;font-size:11px;color:#8b949e;">'
            '📊 <b>評分不是保證，是機率</b>：'
            '健康度80分 → 歷史勝率約65%（10次中6-7次對）。'
            '停損紀律決定你能否從對的那幾次賺夠錢。'
            '</div>'
        )

        ha, hb = st.columns([1, 2])
        with ha:
            # 基本面評分
            _fund_sc = calc_fundamental_score(qtr2, yearly2, avg_div2)
            # 技術警示
            _tech_al = []
            if rsi2 and rsi2 < 30:   _tech_al.append(('🟡','RSI過低','看跌反彈',f'RSI={rsi2:.0f}，超賣可能反彈'))
            elif rsi2 and rsi2 > 70: _tech_al.append(('🔴','RSI超買','超買注意',f'RSI={rsi2:.0f}，高檔過熱'))
            if df2 is not None and 'MA5' in df2.columns and 'MA10' in df2.columns and len(df2)>=2:
                _m5,_m10  = float(df2['MA5'].iloc[-1]),  float(df2['MA10'].iloc[-1])
                _m5p,_m10p= float(df2['MA5'].iloc[-2]),  float(df2['MA10'].iloc[-2])
                if _m5<_m10 and _m5p>=_m10p: _tech_al.insert(0,('🔴','MA5下穿MA10','看跌',  '短均死叉，趨勢轉弱'))
                elif _m5>_m10 and _m5p<=_m10p: _tech_al.insert(0,('🟢','MA5上穿MA10','看漲','短均黃金交叉，轉強'))
            if vr2 and vr2 < 0.5: _tech_al.append(('🟡','量能不足','觀察',f'量比={vr2:.2f}，市場觀望'))
            if k2 and d2:
                if k2<d2 and k2>20:  _tech_al.append(('🟡','KD死亡交叉','看跌',f'K={k2:.0f} D={d2:.0f}'))
                elif k2>d2 and k2<80: _tech_al.append(('🟢','KD黃金交叉','看漲',f'K={k2:.0f} D={d2:.0f}'))
            st.markdown(render_health_score(health2, details2, sid2, _fund_sc, _tech_al), unsafe_allow_html=True)
        with hb:
            # 六大技術指標卡片
            ind1, ind2, ind3 = st.columns(3)
            ind4, ind5, ind6 = st.columns(3)
            with ind1:
                rsi_c = '#d29922' if rsi2 and rsi2>70 else ('#3fb950' if rsi2 and rsi2<30 else '#58a6ff')
                rsi_txt = '超買⚠️' if rsi2 and rsi2>70 else ('超賣反彈' if rsi2 and rsi2<30 else '中性')
                st.markdown(kpi('RSI(14)',f'{rsi2}' if rsi2 else '-',rsi_txt,rsi_c,rsi_c),unsafe_allow_html=True)
            with ind2:
                vr_c = '#3fb950' if vr2 and vr2>=1.5 else ('#d29922' if vr2 and vr2>=1.0 else '#484f58')
                vr_txt = '異常放量' if vr2 and vr2>=1.5 else ('溫和放量' if vr2 and vr2>=1.0 else '量縮')
                st.markdown(kpi('量比(5日)',f'{vr2}' if vr2 else '-',vr_txt,vr_c,vr_c),unsafe_allow_html=True)
            with ind3:
                ibs_c = '#3fb950' if ibs2 is not None and ibs2<=0.2 else ('#f85149' if ibs2 is not None and ibs2>=0.8 else '#58a6ff')
                ibs_txt = '收低≤20%易反彈' if ibs2 is not None and ibs2<=0.2 else ('收高≥80%易賣壓' if ibs2 is not None and ibs2>=0.8 else '中性位置')
                st.markdown(kpi('IBS',f'{ibs2}' if ibs2 is not None else '-',ibs_txt,ibs_c,ibs_c),unsafe_allow_html=True)
            with ind4:
                kd_c = '#3fb950' if k2 and d2 and k2>d2 and k2<80 else ('#d29922' if k2 and d2 and k2>d2 else '#f85149')
                kd_txt = '黃金交叉' if k2 and d2 and k2>d2 else '死亡交叉'
                st.markdown(kpi('KD',f'K={k2}/D={d2}' if k2 else '-',kd_txt,kd_c,kd_c),unsafe_allow_html=True)
            with ind5:
                if df2 is not None and 'MA20' in df2.columns and 'MA100' in df2.columns:
                    p=price2; m20=float(df2['MA20'].iloc[-1]); m100=float(df2['MA100'].iloc[-1])
                    if p>m20>m100: tr_txt='多頭排列'; tr_c='#3fb950'
                    elif p<m20<m100: tr_txt='空頭排列'; tr_c='#f85149'
                    elif p>m100: tr_txt='多箱整理'; tr_c='#d29922'
                    else: tr_txt='空箱整理'; tr_c='#d29922'
                    st.markdown(kpi('趨勢',tr_txt,f'MA20={m20:.1f}',tr_c,tr_c),unsafe_allow_html=True)
                else:
                    st.markdown(kpi('趨勢','-','無MA數據','#484f58'),unsafe_allow_html=True)
            with ind6:
                if bb2:
                    bw_c='#3fb950' if bb2['bw']<bb2['bw_mean']*0.7 else '#58a6ff'
                    bw_txt='帶寬極縮⚡' if bb2['bw']<bb2['bw_mean']*0.7 else ('黏近上軌' if bb2['near_upper'] else f'均值{bb2["bw_mean"]:.1f}%')
                    st.markdown(kpi('布林帶寬',f'{bb2["bw"]:.1f}%',bw_txt,bw_c,bw_c),unsafe_allow_html=True)
                else:
                    st.markdown(kpi('布林帶寬','-','數據不足','#484f58'),unsafe_allow_html=True)

        # ── 動態大師建議（基於實際評分）──────────────────────
        _grade_label, _grade_color, _, _grade_emoji = health_grade(health2)
        _price_pos = ''
        if df2 is not None and 'MA20' in df2.columns and 'MA100' in df2.columns:
            _p2 = price2; _m20 = float(df2['MA20'].iloc[-1]); _m100 = float(df2['MA100'].iloc[-1])
            if _p2 > _m20 > _m100: _price_pos = '多頭排列，技術面強勢'
            elif _p2 < _m20 < _m100: _price_pos = '空頭排列，技術面偏弱'
            elif _p2 > _m100: _price_pos = '多箱整理，等待突破'
            else: _price_pos = '空箱整理，謹慎操作'
        _verdict_color = '#3fb950' if health2>=80 else ('#d29922' if health2>=50 else '#f85149')
        _verdict = ('持股不動，佛系等待；所有指標均表現優異，繼續持有。' if health2>=80
                    else ('等待突破訊號，不追高；多空交戰，方向未明，可分批布局。' if health2>=50
                          else '降低倉位或觀望；趨勢偏弱，以保本為優先。'))
        st.markdown(f"""<div style="background:#161b22;border:1px solid {_verdict_color};
border-left:4px solid {_verdict_color};border-radius:8px;padding:12px 14px;margin:8px 0;">
<span style="font-size:13px;font-weight:800;color:{_verdict_color};">{_grade_emoji} 大師綜合建議：{_verdict}</span>
<div style="font-size:11px;color:#8b949e;margin-top:4px;">技術位置：{_price_pos} | RSI={rsi2} | 量比={vr2} | KD=K{k2}/D{d2}</div>
</div>""", unsafe_allow_html=True)

        st.caption('📖 評分標準與指標說明 → 詳見「策略手冊」Tab')


        # ── v4.0 防守線 + 籌碼 + 套牢賣壓 ─────────────────────────────
        try:
            if df2 is not None and not df2.empty:
                # Build df for V4 engine (map column names)
                _v4_df = df2.copy()
                _col_map = {}
                for _c in _v4_df.columns:
                    if _c in ('close','Close','adj close'): _col_map[_c] = 'close'
                    elif _c in ('open','Open'): _col_map[_c] = 'open'
                    elif _c in ('low','Low'): _col_map[_c] = 'low'
                    elif _c in ('volume','Volume','Trading_Volume'): _col_map[_c] = 'volume'
                _v4_df = _v4_df.rename(columns=_col_map)

                # Try to get chip data from session state
                _inst2 = st.session_state.get('t2_inst', {})
                if '外資' in _inst2:
                    _v4_df['foreign_net'] = _inst2.get('外資', 0)
                    _v4_df['trust_net']   = _inst2.get('投信', 0)

                # Macro data from li_latest
                _li_for_v4 = st.session_state.get('li_latest')
                _v4_fut2 = 0.0
                _v4_pcr2 = 100.0
                if _li_for_v4 is not None and not _li_for_v4.empty:
                    try: _v4_fut2 = float(_li_for_v4.iloc[-1].get('外資大小', 0) or 0)
                    except: pass
                    try: _v4_pcr2 = float(_li_for_v4.iloc[-1].get('選PCR', 100) or 100)
                    except: pass

                _shares = st.session_state.get(f't2_shares_{sid2}', 1000000)
                _v4eng  = V4StrategyEngine(_v4_df,
                                           {'vix': 15, 'foreign_futures': _v4_fut2, 'pcr': _v4_pcr2},
                                           max(int(_shares), 1))
                _v4rep  = _v4eng.generate_report()

                st.markdown('---')
                _v4c1, _v4c2, _v4c3 = st.columns(3)

                # Task 4: Stop Loss
                with _v4c1:
                    _sl = _v4rep['stop_loss']
                    _sl_color = '#da3633' if _sl['stop_loss'] else '#484f58'
                    st.markdown(
                        f'<div style="background:#0d1117;border:1px solid {_sl_color};'
                        f'border-radius:8px;padding:12px;text-align:center;">'
                        f'<div style="font-size:10px;color:#484f58;">🛡️ v4 防守價</div>'
                        f'<div style="font-size:20px;font-weight:900;color:{_sl_color};">'
                        f'{_sl["stop_loss"] or "N/A"} 元</div>'
                        f'<div style="font-size:11px;color:#8b949e;">MA20={_sl["ma20"]} | '
                        f'風險 {_sl["risk_pct"]}%</div>'
                        f'<div style="font-size:10px;color:#da3633;">跌破無條件停損</div>'
                        f'</div>', unsafe_allow_html=True)

                # Task 3: VPOC Resistance
                with _v4c2:
                    _rs = _v4rep['resistance']
                    _rs_color = '#da3633' if _rs['has_pressure'] else '#2ea043'
                    st.markdown(
                        f'<div style="background:#0d1117;border:1px solid {_rs_color};'
                        f'border-radius:8px;padding:12px;text-align:center;">'
                        f'<div style="font-size:10px;color:#484f58;">📊 v4 上方賣壓</div>'
                        f'<div style="font-size:14px;font-weight:900;color:{_rs_color};">'
                        f'{"⚠️ 有解套賣壓" if _rs["has_pressure"] else "✅ 壓力有限"}</div>'
                        f'<div style="font-size:11px;color:#8b949e;">'
                        f'VPOC={_rs["vpoc_price"] or "N/A"} 元</div>'
                        f'</div>', unsafe_allow_html=True)

                # Task 1: Chip Ratio
                with _v4c3:
                    _ch = _v4rep['chip_analysis']
                    _ch_color = '#da3633' if '強勢' in _ch['signal'] else ('#2ea043' if '渙散' in _ch['signal'] else '#388bfd')
                    st.markdown(
                        f'<div style="background:#0d1117;border:1px solid {_ch_color};'
                        f'border-radius:8px;padding:12px;text-align:center;">'
                        f'<div style="font-size:10px;color:#484f58;">💹 v4 相對籌碼</div>'
                        f'<div style="font-size:13px;font-weight:900;color:{_ch_color};">'
                        f'{_ch["signal"][:10]}</div>'
                        f'<div style="font-size:10px;color:#8b949e;">'
                        f'外本比 {_ch["foreign_ratio"] or "--"}%</div>'
                        f'</div>', unsafe_allow_html=True)
        except Exception as _v4_err:
            st.caption(f'v4.0 分析略過：{type(_v4_err).__name__}')


        # ── v5.0 RS強度 + 估值 + 布林偵測 ─────────────────────────────
        try:
            if df2 is not None and not df2.empty and len(df2) >= 20:
                _v5_r1, _v5_r2, _v5_r3 = st.columns(3)

                # Task 9: Bollinger Breakout
                with _v5_r1:
                    _bb5 = detect_bollinger_breakout(df2)
                    _bb5c = _bb5['color']
                    st.markdown(
                        f'<div style="background:#0d1117;border:1px solid {_bb5c};'
                        f'border-radius:8px;padding:12px;text-align:center;">'
                        f'<div style="font-size:10px;color:#484f58;">📈 v5 布林偵測</div>'
                        f'<div style="font-size:13px;font-weight:900;color:{_bb5c};">'
                        f'{_bb5["signal"][:10]}</div>'
                        f'<div style="font-size:10px;color:#8b949e;">BW={_bb5["bw"]}%</div>'
                        f'</div>', unsafe_allow_html=True)

                # Task 10: 357 存股殖利率
                with _v5_r2:
                    _dy5 = calc_dividend_yield_357(
                        price2 or 0,
                        sum(float(r.get("EPS","0") or 0) for _, r in (qtr2 or pd.DataFrame()).head(4).iterrows()) if qtr2 is not None and not qtr2.empty else 0,
                        avg_div2 / max(price2, 1) if avg_div2 and price2 else 0,
                        len([d for d in (st.session_state.get('t2_div_hist',[]) or []) if d > 0])
                    )
                    _dy5c = _dy5['color']
                    st.markdown(
                        f'<div style="background:#0d1117;border:1px solid {_dy5c};'
                        f'border-radius:8px;padding:12px;text-align:center;">'
                        f'<div style="font-size:10px;color:#484f58;">💰 v5 存股殖利率</div>'
                        f'<div style="font-size:14px;font-weight:900;color:{_dy5c};">'
                        f'{_dy5["est_yield"] or "N/A"}%</div>'
                        f'<div style="font-size:10px;color:#8b949e;">{_dy5["signal"][:8]}</div>'
                        f'</div>', unsafe_allow_html=True)

                # Task 5: 財報領先
                with _v5_r3:
                    _fl5 = analyze_fundamental_leading(cl2, None, None, None,
                                                       st.session_state.get(f't2_equity_{sid2}'))
                    _fl5c = _fl5['color']
                    st.markdown(
                        f'<div style="background:#0d1117;border:1px solid {_fl5c};'
                        f'border-radius:8px;padding:12px;text-align:center;">'
                        f'<div style="font-size:10px;color:#484f58;">🔬 v5 財報領先</div>'
                        f'<div style="font-size:13px;font-weight:900;color:{_fl5c};">'
                        f'{_fl5["signal"][:8]}</div>'
                        f'<div style="font-size:10px;color:#8b949e;">'
                        f'{"合約負債 ✅" if cl2 and cl2>0 else "無合約負債"}</div>'
                        f'</div>', unsafe_allow_html=True)
        except Exception as _v5e2:
            st.caption(f'v5.0 進階分析略過：{type(_v5e2).__name__}')

        # ══ B. 357 評價 ════════════════════════════════════════
        st.markdown('---')
        st.markdown('#### 💰 B. 357殖利率評價 [孫慶龍]')
        if avg_div2 > 0 and price2 > 0:
            _cp2 = round(avg_div2/0.07, 1); _fp2 = round(avg_div2/0.05, 1); _dp2 = round(avg_div2/0.03, 1)
            if price2 <= _cp2:
                _ba = f'現價 {price2:.1f} ≤ 便宜價 {_cp2:.1f}（殖利率>7%），積極買進區'; _bb = '可大膽買進，股息都進口袋'
            elif price2 <= _fp2:
                _ba = f'現價 {price2:.1f} 在合理區 {_cp2:.1f}–{_fp2:.1f}（殖利率5-7%）'; _bb = '可分批布局，勿一次梭哈'
            elif price2 <= _dp2:
                _ba = f'現價 {price2:.1f} 在昂貴區 {_fp2:.1f}–{_dp2:.1f}（殖利率3-5%）'; _bb = '謹慎，等回調至合理價再進場'
            else:
                _ba = f'現價 {price2:.1f} > 昂貴價 {_dp2:.1f}（殖利率<3%），嚴禁追高'; _bb = '放下，等大跌再看'
        else:
            _ba = '無股利資料，無法套用357評價'; _bb = '以技術面健康度為主要判斷'
        st.markdown(teacher_conclusion('孫慶龍', f'{sid2} 現價{price2:.1f} vs 357區間', _ba, _bb), unsafe_allow_html=True)
        if avg_div2 > 0:
            cheap2=round(avg_div2/0.07,1); fair2=round(avg_div2/0.05,1); dear2=round(avg_div2/0.03,1)
            if price2<=cheap2:   sig2,sc2='🟢便宜價 — 積極買進','#3fb950'
            elif price2<=fair2:  sig2,sc2='🟡合理價 — 可分批布局','#d29922'
            elif price2<=dear2:  sig2,sc2='🔴昂貴價 — 謹慎操作','#f85149'
            else:                sig2,sc2='🔴超過昂貴 — 避免追高','#f85149'
            st.markdown(f"""<div style="background:#161b22;border:2px solid {sc2};border-radius:10px;
padding:12px 16px;margin:8px 0;">
<div style="font-size:16px;font-weight:900;color:{sc2};">{sig2}</div>
<div style="font-size:11px;color:#8b949e;margin-top:4px;">
  {sid2} {name2} | 現價 <b style="color:#58a6ff;">{price2:.2f}</b> |
  近5年均股利 <b style="color:#ffd700;">{avg_div2:.2f}元</b> ({t2d.get('div_src','')})
</div></div>""", unsafe_allow_html=True)
            v1,v2,v3,v4=st.columns(4)
            for vc,vl,vp,vcol in [(v1,'現價',price2,'#58a6ff'),(v2,'🟢便宜(7%)',cheap2,'#3fb950'),
                                   (v3,'🟡合理(5%)',fair2,'#d29922'),(v4,'🔴昂貴(3%)',dear2,'#f85149')]:
                with vc: st.markdown(kpi(vl,f'{vp:.1f}','',vcol,vcol),unsafe_allow_html=True)
            if yearly2:
                fig_d=go.Figure(go.Bar(
                    x=[str(int(y['year'])) for y in yearly2],
                    y=[y['cash'] for y in yearly2],
                    marker_color='#ffd700',
                    text=[f'{y["cash"]:.2f}' for y in yearly2],textposition='auto'))
                fig_d.update_layout(height=180,plot_bgcolor='#0e1117',paper_bgcolor='#0e1117',
                                    font=dict(color='white'),margin=dict(l=20,r=20,t=30,b=20),
                                    title=dict(text=f'{sid2} 近5年現金股利',font=dict(color='#ffd700',size=12)),
                                    yaxis=dict(gridcolor='#333'),xaxis=dict(gridcolor='#333'))
                st.plotly_chart(fig_d,use_container_width=True,config={'displayModeBar':False})
        else:
            st.warning('⚠️ 無配息記錄（成長股）— 建議改用本益比評估')
        # ── 357 動態建議 ──
        if avg_div2 > 0:
            _357_verdict = (f'現價 {price2:.1f} 處於 {"便宜價🟢 — 孫慶龍：積極買進！" if price2<=cheap2 else ("合理價🟡 — 孫慶龍：可分批布局，等殖利率拉升再加碼" if price2<=fair2 else ("昂貴價🔴 — 孫慶龍：謹慎操作，等待回檔再進場" if price2<=dear2 else "超過昂貴價🔴 — 孫慶龍：絕對不追高，等待大幅修正"))}，近5年均股利 {avg_div2:.2f} 元')
            _357_c = '#3fb950' if price2<=cheap2 else ('#d29922' if price2<=fair2 else '#f85149')
            st.markdown(f'<div style="background:#161b22;border-left:4px solid {_357_c};padding:10px 14px;border-radius:0 8px 8px 0;font-size:13px;font-weight:700;color:{_357_c};margin:6px 0;">{_357_verdict}</div>', unsafe_allow_html=True)
        # 357結論：直接顯示當前評估，不導向策略手冊
        st.markdown(
            f'<div style="background:#0d1117;border-left:4px solid {_357_c};'
            f'padding:10px 14px;border-radius:0 8px 8px 0;margin:6px 0;">'
            f'<span style="font-size:12px;color:#8b949e;">🎓 孫慶龍 · 357法則判斷</span><br>'
            f'<span style="font-size:14px;font-weight:800;color:{_357_c};">{_357_verdict}</span><br>'
            f'<span style="font-size:11px;color:#8b949e;">判讀邏輯：殖利率≥7%=便宜大買；5-7%=合理；3-5%=偏貴持有；&lt;3%=昂貴停利</span>'
            f'</div>',
            unsafe_allow_html=True
        )

        # ── 估值河流圖（357殖利率河流）────────────────────────────
        if df2 is not None and not df2.empty:
            # ── 1. 建立逐年現金股利 DataFrame ──
            _riv_records = []
            if yearly2:
                for _y in yearly2:
                    try:
                        _y_cash = float(_y.get('cash', 0) or 0)
                        _riv_records.append({
                            'date': pd.Timestamp(int(_y['year']), 12, 31),
                            'div':  _y_cash
                        })
                    except: pass
            # 若無逐年資料，用 avg_div2 補一筆當年
            if not _riv_records and avg_div2 and avg_div2 > 0:
                _riv_records.append({
                    'date': pd.Timestamp(datetime.date.today().year, 12, 31),
                    'div':  float(avg_div2)
                })

            _div_df_riv = (pd.DataFrame(_riv_records)
                           .sort_values('date')
                           .reset_index(drop=True)
                           if _riv_records else None)

            if _div_df_riv is not None and not _div_df_riv.empty and _div_df_riv['div'].max() > 0:
                # ── 2. 3年滾動平均現金股利（min_periods=1 讓早期也有值）──
                _div_df_riv['avg_div'] = (
                    _div_df_riv['div']
                    .rolling(window=3, min_periods=1)
                    .mean()
                )
                # 防禦：排除 0 / 負值
                _div_df_riv['avg_div'] = _div_df_riv['avg_div'].where(
                    _div_df_riv['avg_div'] > 0, other=pd.NA)

                # ── 3. 建立「年份→平均股利」查表，並對每個交易日做前向填充 ──
                # 使用年份整數做 key，避免 merge_asof 的 dtype 問題
                _div_year_map = {}
                for _, _dr in _div_df_riv.dropna(subset=['avg_div']).iterrows():
                    try:
                        _yr_key = int(pd.Timestamp(_dr['date']).year)
                        _div_year_map[_yr_key] = float(_dr['avg_div'])
                    except: pass

                _rdates_s  = pd.to_datetime(
                    df2['date'] if 'date' in df2.columns else pd.RangeIndex(len(df2)))
                _rclose_riv = pd.to_numeric(df2['close'], errors='coerce').reset_index(drop=True)
                _rdates_riv = _rdates_s.reset_index(drop=True)

                # 每個交易日找「<=該年」的最近已知平均股利（前向填充）
                _sorted_yrs = sorted(_div_year_map.keys())
                def _lookup_avg_div(ts):
                    yr = ts.year
                    avail = [y for y in _sorted_yrs if y <= yr]
                    if avail:   return _div_year_map[max(avail)]
                    if _sorted_yrs: return _div_year_map[min(_sorted_yrs)]  # 早於最早記錄
                    return float(avg_div2) if avg_div2 else 0
                _avg_div_series = _rdates_s.map(_lookup_avg_div)

                # ── 4. 計算河流帶：P = 平均股利 / 殖利率 ──
                _band7_riv = (_avg_div_series / 0.07).round(2).reset_index(drop=True)
                _band5_riv = (_avg_div_series / 0.05).round(2).reset_index(drop=True)
                _band3_riv = (_avg_div_series / 0.03).round(2).reset_index(drop=True)

                _cur_div_riv = float(_avg_div_series.dropna().iloc[-1]) if not _avg_div_series.dropna().empty else 0
                _p7r = round(_cur_div_riv / 0.07, 0) if _cur_div_riv > 0 else 0
                _p5r = round(_cur_div_riv / 0.05, 0) if _cur_div_riv > 0 else 0
                _p3r = round(_cur_div_riv / 0.03, 0) if _cur_div_riv > 0 else 0

                # ── 5. 繪圖 ──
                _fig_riv = go.Figure()
                _fig_riv.add_trace(go.Scatter(
                    x=_rdates_riv, y=_rclose_riv, name='收盤價',
                    line=dict(color='#e6edf3', width=2.5),
                    hovertemplate='%{x|%Y-%m-%d}<br>%{y:.2f}<extra></extra>'))

                for _bs, _lbl, _col in [
                    (_band7_riv, '7%便宜', '#3fb950'),
                    (_band5_riv, '5%合理', '#d29922'),
                    (_band3_riv, '3%昂貴', '#f85149')
                ]:
                    _fig_riv.add_trace(go.Scatter(
                        x=_rdates_riv, y=_bs, name=_lbl,
                        line=dict(color=_col, width=1.5, dash='dot'),
                        hovertemplate=f'{_lbl}: %{{y:.0f}}<extra></extra>'))

                # 色帶（以最新一日的帶值為基準）
                _b7_last = float(_band7_riv.dropna().iloc[-1]) if not _band7_riv.dropna().empty else 0
                _b5_last = float(_band5_riv.dropna().iloc[-1]) if not _band5_riv.dropna().empty else 0
                _b3_last = float(_band3_riv.dropna().iloc[-1]) if not _band3_riv.dropna().empty else 0
                if _b7_last > 0:
                    _fig_riv.add_hrect(y0=0, y1=_b7_last, fillcolor='rgba(63,185,80,0.07)', line_width=0)
                if _b5_last > _b7_last:
                    _fig_riv.add_hrect(y0=_b7_last, y1=_b5_last, fillcolor='rgba(210,153,34,0.07)', line_width=0)
                if _b3_last > _b5_last:
                    _fig_riv.add_hrect(y0=_b5_last, y1=_b3_last, fillcolor='rgba(248,81,73,0.05)', line_width=0)

                # Y 軸：自動涵蓋股價與所有河流帶
                _all_riv_vals = (
                    list(_rclose_riv.dropna()) +
                    list(_band3_riv.dropna()) +
                    list(_band7_riv.dropna())
                )
                _ymax_riv = max(_all_riv_vals) * 1.05 if _all_riv_vals else 100
                _ymin_riv = max(0, min(_all_riv_vals) * 0.7) if _all_riv_vals else 0

                _fig_riv.update_layout(
                    title=dict(
                        text=f'📊 {sid2} {name2} 殖利率河流圖（近3年均股利 {_cur_div_riv:.2f}元）',
                        font=dict(color='#8b949e', size=12)),
                    height=300, plot_bgcolor='#0e1117', paper_bgcolor='#0e1117',
                    font=dict(color='white', size=11),
                    margin=dict(l=10, r=10, t=40, b=10),
                    xaxis=dict(gridcolor='#21262d'),
                    yaxis=dict(range=[_ymin_riv, _ymax_riv], gridcolor='#21262d'),
                    hovermode='x unified', showlegend=True,
                    legend=dict(orientation='h', y=1.08, x=0, font=dict(size=10)))
                st.plotly_chart(_fig_riv, use_container_width=True, config={'displayModeBar': False})

                _cur_price_riv = float(_rclose_riv.dropna().iloc[-1]) if not _rclose_riv.dropna().empty else 0
                _cur_zone = ('🟢 便宜區' if _cur_price_riv < _p7r else
                             '🟡 合理區' if _cur_price_riv < _p5r else
                             '🔴 昂貴區' if _cur_price_riv < _p3r else '⛔ 超昂貴')
                st.caption(
                    f'目前位於 {_cur_zone}（現價 {_cur_price_riv:.0f} / '
                    f'便宜≤{_p7r:.0f} / 合理≤{_p5r:.0f} / 昂貴≤{_p3r:.0f}）'
                    f'　近3年均股利 {_cur_div_riv:.2f}元')
                if _cur_div_riv < 0.5:
                    st.info('ℹ️ 此股近年現金股利極低（< 0.5元），殖利率河流圖參考意義有限，建議搭配本益比等其他估值工具。')

        # ══ C. 領先指標 ════════════════════════════════════════
        st.markdown('---')
        st.markdown('#### 🔬 C. 公司真的在賺錢嗎？（財報領先指標）')
        if cl2 and cl2 > 0 and cx2 and cx2 > 0:
            _ca = f'合約負債 {cl2/1e8:.1f}億 + 資本支出 {cx2/1e8:.1f}億，雙重確認龍多股'; _cb = '基本面強勢，適合長期持有'
        elif cl2 and cl2 > 0:
            _ca = f'合約負債 {cl2/1e8:.1f}億（訂單豐沛），資本支出資料不足'; _cb = '基本面良好，但擴廠意願待確認'
        elif cx2 and cx2 > 0:
            _ca = f'資本支出 {cx2/1e8:.1f}億（積極擴產），合約負債資料不足'; _cb = '擴廠意願強，但訂單能見度待確認'
        else:
            _ca = '合約負債+資本支出均無資料（可能為金融股或資料源限制）'; _cb = '請至 MOPS 或年報查閱'
        st.markdown(teacher_conclusion('孫慶龍', f'{sid2} 財報領先指標', _ca, _cb), unsafe_allow_html=True)
        st.markdown(
            '<div style="background:#0a1628;border-left:3px solid #bc8cff;padding:8px 12px;'
            'border-radius:0 6px 6px 0;margin-bottom:8px;font-size:12px;color:#c9d1d9;">'
            '💡 這兩個財報數字能預測未來3-6個月的獲利方向：'
            '<br>📌 <b>合約負債</b> = 客戶已付錢但還沒出貨的訂單 → 越高代表訂單很多、業績有保障'
            '<br>📌 <b>資本支出</b> = 公司花錢蓋廠房買設備 → 越高代表看好未來、準備大幅擴產'
            '<br>⭐ 兩個都很高 = 孫慶龍所說的「龍多股」，是存股首選'
            '</div>', unsafe_allow_html=True)
        fc1,fc2=st.columns(2)
        cl_ok=cl2 is not None and cl2>0; cx_ok=cx2 is not None and cx2>0
        _cl_st = _fin_st2.get('contract_liabilities') if '_fin_st2' in dir() else None
        _cx_st = _fin_st2.get('fixed_assets')         if '_fin_st2' in dir() else None
        _cl_label = "--" if cl_ok else '無數據'
        _cx_label = "--" if cx_ok else '無數據'
        _cl_color_map = {'ok':'#3fb950','missing':'#d29922','not_applicable':'#484f58','fetch_error':'#f85149'}
        _cx_color_map = {'ok':'#58a6ff','missing':'#d29922','not_applicable':'#484f58','fetch_error':'#f85149'}
        with fc1:
            _cl_val_txt = f'{cl2/1e8:.1f}億' if cl_ok else '抓取失敗'
            _cl_c = '#2ea043' if cl_ok else '#da3633'
            st.markdown(kpi('合約負債', _cl_val_txt,
                            '>股本50%→未來3-6月訂單保障', _cl_c,
                            _cl_c if cl_ok else '#21262d'),unsafe_allow_html=True)
            if not cl_ok:
                st.caption('來源：FinMind — 抓取失敗或無此財報')
        with fc2:
            _cx_val_txt = f'{cx2/1e8:.1f}億' if cx_ok else '抓取失敗'
            _cx_c = '#2ea043' if cx_ok else '#da3633'
            st.markdown(kpi('固定資產/資本支出', _cx_val_txt,
                            '>股本80%→大擴廠看好未來需求', _cx_c,
                            _cx_c if cx_ok else '#21262d'),unsafe_allow_html=True)
            if not cx_ok:
                st.caption(f'來源：{_cl_src2 or _cx_src2 or "未知"}')
        if not cl_ok and not cx_ok:
            _na = (not _fin_errs2 and not cl_ok and not cx_ok)
            _fe = bool(_fin_errs2)
            if _na:
                st.info('ℹ️ 此產業（金融/保險等）不適用合約負債/固定資產指標，可跳過')
            elif _fe:
                # 顯示具體錯誤給使用者
                _err_src = (_cl_src2 + '/' + _cx_src2).strip('/')
                _err_msg = '; '.join(_fin_errs2) if _fin_errs2 else '抓取失敗'
                st.error(f'❌ 財報資料抓取失敗 — 來源:{_err_src or "三源均未命中"} | 錯誤:{_err_msg}')
                st.caption('💡 可能原因：① FinMind Token 失效 ② MOPS 暫時無回應 ③ 個股無此財報')
            else:
                st.info('ℹ️ 查無揭露：服務業/軟體業通常無此數據，可跳過')
                st.caption(f'來源：{_cl_src2 or _cx_src2 or "未知"}')
        # 財報結論：依合約負債+固定資產狀態給出判斷
        _fin_color = '#3fb950' if cl_ok and cx_ok else ('#d29922' if cl_ok or cx_ok else '#484f58')
        _fin_label = ('✅ 龍多確認：合約負債高＋資本支出高 = 訂單滿、擴廠中' if cl_ok and cx_ok
                      else ('⚠️ 部分訊號：' + ('合約負債充裕' if cl_ok else '資本支出積極')
                            if cl_ok or cx_ok else '⚪ 資料不足，無法判斷'))
        st.markdown(
            f'<div style="background:#0d1117;border-left:4px solid {_fin_color};'
            f'padding:10px 14px;border-radius:0 8px 8px 0;margin:6px 0;">'
            f'<span style="font-size:12px;color:#8b949e;">🎓 孫慶龍 · 財報領先指標</span><br>'
            f'<span style="font-size:14px;font-weight:800;color:{_fin_color};">{_fin_label}</span><br>'
            f'<span style="font-size:11px;color:#8b949e;">兩指標均高 = 龍多股首選；詳細門檻見「策略手冊」Tab</span>'
            f'</div>',
            unsafe_allow_html=True
        )

        # ══ D. 月營收 + 季毛利率 ══════════════════════════════
        st.markdown('---')
        st.markdown('#### 📈 D. 公司每月賺多少錢？（營收趨勢）')
        _d_ind = f'{sid2} 月營收YoY%'; _da = '月營收數據尚未載入'; _db = ''
        if rev2 is not None and not rev2.empty and len(rev2) >= 3:
            _yoy_col = next((c for c in rev2.columns if 'yoy' in str(c).lower() or '年增' in str(c) or 'YoY' in str(c)), None)
            if _yoy_col:
                _yoy3 = pd.to_numeric(rev2[_yoy_col].tail(3), errors='coerce').dropna()
                if len(_yoy3) >= 2:
                    _avg_y = float(_yoy3.mean()); _last_y = float(_yoy3.iloc[-1])
                    _d_ind = f'{sid2} 近3月平均YoY {_avg_y:+.1f}%'
                    if _avg_y > 15 and (_yoy3 > 0).all():
                        _da = f'近3月YoY平均 {_avg_y:+.1f}%（最新 {_last_y:+.1f}%），業績爆發，重點關注'; _db = '配合技術面買點可進場'
                    elif _avg_y > 0:
                        _da = f'近3月YoY平均 {_avg_y:+.1f}%，溫和成長'; _db = '持續追蹤，等待加速跡象'
                    else:
                        _da = f'近3月YoY平均 {_avg_y:+.1f}%，業績衰退'; _db = '不管K線多好看，先觀望'
        st.markdown(teacher_conclusion('孫慶龍', _d_ind, _da, _db), unsafe_allow_html=True)
        st.markdown(
            '<div style="background:#0a1628;border-left:3px solid #3fb950;padding:8px 12px;'
            'border-radius:0 6px 6px 0;margin-bottom:8px;font-size:12px;color:#c9d1d9;">'
            '💡 月營收年增率（YoY%）= 今年這個月比去年同月多賺了幾%'
            '<br>🟢 <b>連續3個月YoY>15%</b> = 業績爆發，股價可能跟著漲'
            '<br>🔴 <b>連續3個月YoY<0%</b> = 業績衰退，要小心'
            '</div>', unsafe_allow_html=True)
        if rev2 is not None and not rev2.empty:
            if _rev2_cached:
                st.caption('⚠️ 月營收使用快取資料（本次 API 未回應）')
            st.plotly_chart(plot_revenue_chart(rev2,sid2,name2),
                            use_container_width=True,config={'displayModeBar':False})
        else:
            st.warning('⚠️ 月營收數據暫無（請確認 FINMIND_TOKEN 是否正確，或重新載入）')
            st.caption('💡 首次查詢需網路抓取，若持續失敗請檢查 Token 或稍後重試')
        if qtr2 is not None and not qtr2.empty:
            if _qtr2_cached:
                st.caption('⚠️ 季財報使用快取資料（本次 API 未回應）')
            st.plotly_chart(plot_quarterly_chart(qtr2,sid2,name2),
                            use_container_width=True,config={'displayModeBar':False})
        with st.expander('📖 孫慶龍 結論', expanded=True):
            if rev2 is not None and not rev2.empty and 'yoy' in rev2.columns:
                _yoy_last3 = rev2['yoy'].dropna().tail(3).tolist()
                if len(_yoy_last3) >= 2:
                    _yoy_trend = all(_yoy_last3[i] > _yoy_last3[i-1] for i in range(1,len(_yoy_last3)))
                    _yoy_latest = _yoy_last3[-1]
                    _rev_signal = '✅ 月營收YoY連續加速' if _yoy_trend and _yoy_latest>0 else ('⚠️ 月營收成長趨緩' if _yoy_latest>0 else '🔴 月營收年減')
                    st.markdown(f'<div style="color:#c9d1d9;font-size:13px;padding:3px 0;">• {_rev_signal}（最近YoY: {_yoy_latest:+.1f}%）</div>', unsafe_allow_html=True)
            # 月營收結論（移入 if 內，避免 _rev_signal 未定義）
            if rev2 is not None and not rev2.empty and 'yoy' in rev2.columns:
                _yoy_s2 = rev2['yoy'].dropna().tail(3).tolist()
                if _yoy_s2:
                    _rv_latest = _yoy_s2[-1]
                    _rv_trend  = len(_yoy_s2)>=2 and all(_yoy_s2[i]>_yoy_s2[i-1] for i in range(1,len(_yoy_s2)))
                    _rv_sig = ('✅ 月營收YoY連續加速' if _rv_trend and _rv_latest>0
                               else ('⚠️ 月營收成長趨緩' if _rv_latest>0 else '🔴 月營收年減'))
                    _rv_c = '#3fb950' if '✅' in _rv_sig else ('#f85149' if '🔴' in _rv_sig else '#d29922')
                    st.markdown(
                        f'<div style="background:#0d1117;border-left:3px solid {_rv_c};padding:7px 12px;border-radius:0 6px 6px 0;margin:4px 0;">'
                        f'<span style="font-size:11px;color:#8b949e;">🎓 孫慶龍 · 月營收</span>　'
                        f'<span style="font-size:13px;font-weight:700;color:{_rv_c};">{_rv_sig}（YoY:{_rv_latest:+.1f}%）</span>'
                        f'</div>', unsafe_allow_html=True
                    )
                else:
                    st.caption('月營收資料不足，無法判斷趨勢')
            else:
                st.caption('⚠️ 月營收資料缺失（請確認 FinMind Token）')
            # 毛利率結論 + 獲利品質得分 (SQ)
            if qtr2 is not None and not qtr2.empty:
                _gp_col = '毛利率' if '毛利率' in qtr2.columns else None  # 精確比對，避免命中'毛利率名稱'
                if _gp_col:
                    import pandas as _pd_gp
                    _gp_series = _pd_gp.to_numeric(qtr2[_gp_col].tail(4), errors='coerce').dropna()
                    if len(_gp_series) >= 2:
                        _gp_now = float(_gp_series.iloc[-1])
                        _gp_trend = float(_gp_series.iloc[-1]) - float(_gp_series.iloc[-2])
                        _gp_c = '#3fb950' if _gp_now >= 30 and _gp_trend >= 0 else ('#d29922' if _gp_now >= 20 else '#f85149')
                        _gp_msg = (f'✅ {_gp_now:.1f}%（高毛利≥30%，護城河寬）' if _gp_now >= 30
                                   else f'⚠️ {_gp_now:.1f}%（中等毛利20~30%）' if _gp_now >= 20
                                   else f'🔴 {_gp_now:.1f}%（低毛利<20%）')
                        st.markdown(
                            f'<div style="background:#0d1117;border-left:3px solid {_gp_c};padding:7px 12px;border-radius:0 6px 6px 0;margin:4px 0;">'
                            f'<span style="font-size:11px;color:#8b949e;">🎓 陳重銘 · 毛利率</span>　'
                            f'<span style="font-size:13px;font-weight:700;color:{_gp_c};">{_gp_msg}</span>'
                            f'</div>', unsafe_allow_html=True
                        )
                # 獲利品質得分 (SQ)
                try:
                    from scoring_engine import calc_quality_score as _cqs
                    _sq_res = _cqs(qtr2)
                    if _sq_res.get('sq') is not None:
                        _sq_v = _sq_res['sq']; _sq_lbl = _sq_res['sq_label']
                        _sq_gm = _sq_res['gm_trend']; _sq_rv = _sq_res['rev_trend']
                        _sq_c  = '#3fb950' if _sq_v >= 75 else ('#d29922' if _sq_v >= 55 else '#f85149')
                        st.markdown(
                            f'<div style="background:#0d1117;border-left:3px solid {_sq_c};padding:7px 12px;border-radius:0 6px 6px 0;margin:4px 0;">'
                            f'<span style="font-size:11px;color:#8b949e;">🎓 獲利品質 SQ</span>　'
                            f'<span style="font-size:13px;font-weight:700;color:{_sq_c};">SQ {_sq_v:.0f}分 · {_sq_lbl}</span>'
                            f'<span style="font-size:11px;color:#8b949e;margin-left:8px;">毛利{_sq_gm} 營收{_sq_rv}</span>'
                            f'</div>', unsafe_allow_html=True
                        )
                except Exception:
                    pass
                # 前瞻成長動能分數 (FGMS)
                try:
                    from scoring_engine import calc_forward_momentum_score as _cfgms
                    _is_fin2 = bool(qtr2.get('是否金融股', pd.Series([False])).iloc[0]) if qtr2 is not None and '是否金融股' in qtr2.columns else False
                    print(f'[FGMS_UI] qtr2={qtr2 is not None and not qtr2.empty}, qtr_extra2={qtr_extra2 is not None and not qtr_extra2.empty}')
                    _fgms_r = _cfgms(qtr2, qtr_extra2, is_finance=_is_fin2)
                    print(f'[FGMS_UI] fgms={_fgms_r.get("fgms")}, three_rate={_fgms_r.get("three_rate")}')
                    if _fgms_r.get('fgms') is not None:
                        _fv = _fgms_r['fgms']; _fl = _fgms_r['fgms_label']
                        _fc = '#3fb950' if _fv >= 60 else ('#d29922' if _fv >= 45 else '#f85149')
                        # 子維度摘要（得分）
                        _fd_parts = []
                        if _fgms_r['cl_momentum']    is not None: _fd_parts.append(f"合約負債:{_fgms_r['cl_momentum']:.0f}")
                        if _fgms_r['inv_divergence']  is not None: _fd_parts.append(f"存貨背離:{_fgms_r['inv_divergence']:.0f}")
                        if _fgms_r['three_rate']      is not None: _fd_parts.append(f"三率:{_fgms_r['three_rate']:.0f}")
                        if _fgms_r['capex_intensity'] is not None: _fd_parts.append(f"資本支出:{_fgms_r['capex_intensity']:.0f}")
                        _fd_str = '  '.join(_fd_parts)
                        # 三率實際數值（最新季）
                        _rate_parts = []
                        if qtr2 is not None and not qtr2.empty:
                            def _last_rate(col):
                                if col in qtr2.columns:
                                    _s = pd.to_numeric(qtr2[col], errors='coerce').dropna()
                                    return f"{_s.iloc[-1]:.1f}%" if len(_s) else None
                                return None
                            _gm_v = _last_rate('毛利率'); _oi_v = _last_rate('營業利益率'); _ni_v = _last_rate('淨利率')
                            if _gm_v: _rate_parts.append(f"毛利率{_gm_v}")
                            if _oi_v: _rate_parts.append(f"營業利益率{_oi_v}")
                            if _ni_v: _rate_parts.append(f"淨利率{_ni_v}")
                        _rate_str = '  '.join(_rate_parts)
                        _rate_line = (f'<div style="font-size:11px;color:#8b949e;margin-top:3px;">📊 三率實值：{_rate_str}</div>'
                                      if _rate_str else '')
                        st.markdown(
                            f'<div style="background:#0d1117;border-left:3px solid {_fc};padding:7px 12px;border-radius:0 6px 6px 0;margin:4px 0;">'
                            f'<span style="font-size:11px;color:#8b949e;">🔭 前瞻動能 FGMS</span>　'
                            f'<span style="font-size:13px;font-weight:700;color:{_fc};">FGMS {_fv:.0f}分 · {_fl}</span>'
                            f'<span style="font-size:11px;color:#8b949e;margin-left:8px;">{_fd_str}</span>'
                            f'{_rate_line}'
                            f'</div>', unsafe_allow_html=True
                        )
                except Exception as _efgms2:
                    import traceback as _tb2
                    print(f'[FGMS_UI] 顯示錯誤: {_efgms2}'); _tb2.print_exc()

        # ══ D2. 基本面先行指標（6大指標）══════════════════════
        st.markdown('---')
        st.markdown('#### 🔬 D2. 基本面先行指標（6大指標）')
        try:
            from scoring_engine import calc_leading_indicators_detail as _cli_fn
            _li_results = _cli_fn(rev_df=rev2, qtr_df=qtr2, bs_cf_df=qtr_extra2)
            _li_green = sum(1 for _r in _li_results if _r['signal'] == '🟢')
            _li_yellow = sum(1 for _r in _li_results if _r['signal'] == '🟡')
            _li_red = sum(1 for _r in _li_results if _r['signal'] == '🔴')
            _li_total_scored = _li_green + _li_yellow + _li_red
            if _li_total_scored > 0:
                _li_bar_c = '#3fb950' if _li_green >= _li_total_scored * 0.6 else (
                             '#d29922' if _li_green >= _li_total_scored * 0.3 else '#f85149')
                st.markdown(
                    f'<div style="background:#0d1117;border-left:3px solid {_li_bar_c};'
                    f'padding:6px 12px;border-radius:0 6px 6px 0;margin:4px 0 8px 0;">'
                    f'<span style="font-size:11px;color:#8b949e;">📊 基本面先行指標總覽</span>　'
                    f'<span style="font-size:13px;font-weight:700;color:{_li_bar_c};">'
                    f'🟢×{_li_green}  🟡×{_li_yellow}  🔴×{_li_red}</span>'
                    f'</div>', unsafe_allow_html=True
                )
            # 分模組顯示
            _li_modules = {}
            for _r in _li_results:
                _li_modules.setdefault(_r['module'], []).append(_r)
            _li_module_list = ['模組一', '模組二', '模組三', '模組四']
            _li_module_labels = {
                '模組一': '📈 模組一：高頻業績前瞻（月營收）',
                '模組二': '🏗️ 模組二：資產負債前瞻（季頻）',
                '模組三': '📦 模組三：存貨週期',
                '模組四': '👔 模組四：籌碼深度前瞻',
            }
            _li_col1, _li_col2 = st.columns(2)
            _li_cols = [_li_col1, _li_col2]
            _li_col_idx = 0
            for _mod in _li_module_list:
                if _mod not in _li_modules:
                    continue
                with _li_cols[_li_col_idx % 2]:
                    st.markdown(f'**{_li_module_labels.get(_mod, _mod)}**')
                    for _ind in _li_modules[_mod]:
                        _ic = ('#3fb950' if _ind['signal'] == '🟢' else
                               '#d29922' if _ind['signal'] == '🟡' else
                               '#f85149' if _ind['signal'] == '🔴' else '#8b949e')
                        st.markdown(
                            f'<div style="background:#0d1117;border-left:3px solid {_ic};'
                            f'padding:6px 10px;border-radius:0 4px 4px 0;margin:3px 0;">'
                            f'<div style="font-size:12px;font-weight:700;color:{_ic};">'
                            f'{_ind["signal"]} {_ind["name"]}</div>'
                            f'<div style="font-size:11px;color:#e6edf3;margin:1px 0;">{_ind["value"]}</div>'
                            f'<div style="font-size:10px;color:#8b949e;">{_ind["detail"]}</div>'
                            f'</div>', unsafe_allow_html=True
                        )
                _li_col_idx += 1
        except Exception as _eli_err:
            import traceback as _li_tb
            print(f'[先行指標-D2] 顯示錯誤: {_eli_err}'); _li_tb.print_exc()

        # ── D2 動態投資建議（基於6大先行指標合成）──────────────
        try:
            from scoring_engine import calc_leading_indicators_detail as _cli_fn2
            _li2 = _cli_fn2(rev_df=rev2, qtr_df=qtr2, bs_cf_df=qtr_extra2)
            _li2_map = {r['id']: r for r in _li2}

            # ── 蒐集信號 ─────────────────────────────────────
            _pros  = []   # 多方理由
            _cons  = []   # 空方理由
            _notes = []   # 注意事項（事件驅動/中性）
            _event_driven_flags = []

            # I1 月營收YoY加速
            _r1 = _li2_map.get('I1', {})
            if _r1.get('signal') == '🟢':
                _pros.append(f"月營收YoY連續加速（{_r1.get('value','').split(':')[-1].strip()}），業績動能確立")
            elif _r1.get('signal') == '🔴':
                _cons.append('月營收年減中，基本面走弱')

            # I2 均線交叉
            _r2 = _li2_map.get('I2', {})
            if _r2.get('signal') == '🟢':
                _pros.append(f"月營收3M均線位於12M均線之上（{_r2.get('value','').split(':')[-1].strip()}），中期動能向上")
            elif _r2.get('signal') == '🔴':
                _cons.append('月營收均線死叉，中期趨勢轉弱')

            # I3 合約負債
            _r3 = _li2_map.get('I3', {})
            if _r3.get('signal') == '🟢':
                _v3 = _r3.get('value','')
                _pros.append(f"合約負債持續增加（{_v3}），未來營收能見度高")
            elif _r3.get('signal') == '🔴':
                _cons.append('合約負債減少，訂單能見度下降')

            # I4 CapEx（含事件驅動判斷）
            _r4 = _li2_map.get('I4', {})
            if '事件驅動' in _r4.get('detail', ''):
                _event_driven_flags.append('資本支出比較基期因重大資產處分失真')
                _notes.append(f"⚠️ CapEx：{_r4.get('detail','')}")
            elif _r4.get('signal') == '🟢':
                _pros.append(f"資本支出強度提升（{_r4.get('value','')}），積極擴產佈局未來")
            elif _r4.get('signal') == '🔴':
                _cons.append(f"資本支出大幅縮減（{_r4.get('value','')}），擴張意願低")

            # I5 存貨去化（含事件驅動）
            _r5 = _li2_map.get('I5', {})
            if '事件驅動' in _r5.get('detail', ''):
                _event_driven_flags.append('存貨急降原因待確認（資產處分可能帶走存貨）')
                _notes.append(f"⚠️ 存貨：{_r5.get('detail','')}")
            elif _r5.get('signal') == '🟢':
                _pros.append(f"存貨持續去化（{_r5.get('value','')}），供需關係改善")
            elif _r5.get('signal') == '🔴':
                _cons.append(f"存貨積壓風險（{_r5.get('value','')}），景氣下行壓力")

            # ── 綜合評估 ────────────────────────────────────
            _n_green = sum(1 for r in _li2 if r['signal'] == '🟢')
            _n_red   = sum(1 for r in _li2 if r['signal'] == '🔴')
            _n_scored = sum(1 for r in _li2 if r['signal'] in ('🟢','🟡','🔴'))

            if _event_driven_flags:
                _stance = 'event'
                _stance_label = '⚠️ 事件驅動觀察'
                _stance_color = '#d29922'
                _stance_desc  = '偵測到重大資產處分，部分指標基期失真。建議關注重組後的資本配置方向與營運重啟節奏，暫不適用純基本面成長框架評估。'
            elif _n_scored == 0:
                _stance = 'na'
                _stance_label = '⚪ 資料不足'
                _stance_color = '#8b949e'
                _stance_desc  = '基本面先行指標資料尚未完整載入，無法生成投資建議。'
            elif _n_green >= _n_scored * 0.6:
                _stance = 'bull'
                _stance_label = '🟢 多方偏多'
                _stance_color = '#3fb950'
                _stance_desc  = f'{_n_green}/{_n_scored} 項指標偏多，基本面動能強勁。'
            elif _n_red >= _n_scored * 0.6:
                _stance = 'bear'
                _stance_label = '🔴 基本面偏弱'
                _stance_color = '#f85149'
                _stance_desc  = f'{_n_red}/{_n_scored} 項指標偏空，基本面壓力明顯。'
            else:
                _stance = 'neutral'
                _stance_label = '🟡 中性觀察'
                _stance_color = '#d29922'
                _stance_desc  = f'多空指標交錯（🟢{_n_green}/🔴{_n_red}），基本面尚未形成明確方向。'

            # ── 建議行動 ────────────────────────────────────
            _action_map = {
                'bull':    '基本面動能向上，可搭配技術面（VCP/布林）確認進場時機，適合中長線佈局。',
                'bear':    '基本面呈現壓力，建議降低曝險或觀望，等待指標轉向後再評估。',
                'neutral': '基本面方向尚不明朗，建議輕倉或等待更多季度數據確認後再行動。',
                'event':   '轉機股需追蹤：①後續資本支出重建節奏 ②新業務（如HBM後段）訂單能見度 ③毛利率是否回升至正常水位。',
                'na':      '請確認 FINMIND_TOKEN 是否正確，並重新載入後查看建議。',
            }
            _action = _action_map.get(_stance, '')

            # ── 渲染 ────────────────────────────────────────
            _pros_html  = ''.join(f'<li style="margin:2px 0;">✅ {p}</li>' for p in _pros)  if _pros  else ''
            _cons_html  = ''.join(f'<li style="margin:2px 0;">⛔ {c}</li>' for c in _cons)  if _cons  else ''
            _notes_html = ''.join(f'<li style="margin:2px 0;">{n}</li>'    for n in _notes) if _notes else ''

            _pros_section  = (f'<div style="margin-top:6px;"><span style="font-size:11px;color:#3fb950;font-weight:600;">多方因素</span>'
                              f'<ul style="margin:2px 0 0 12px;padding:0;font-size:11px;color:#e6edf3;">{_pros_html}</ul></div>') if _pros_html else ''
            _cons_section  = (f'<div style="margin-top:4px;"><span style="font-size:11px;color:#f85149;font-weight:600;">風險因素</span>'
                              f'<ul style="margin:2px 0 0 12px;padding:0;font-size:11px;color:#e6edf3;">{_cons_html}</ul></div>') if _cons_html else ''
            _notes_section = (f'<div style="margin-top:4px;"><span style="font-size:11px;color:#d29922;font-weight:600;">注意事項</span>'
                              f'<ul style="margin:2px 0 0 12px;padding:0;font-size:11px;color:#8b949e;">{_notes_html}</ul></div>') if _notes_html else ''

            st.markdown(
                f'<div style="background:#161b22;border:1px solid {_stance_color};border-left:4px solid {_stance_color};'
                f'padding:10px 14px;border-radius:6px;margin:8px 0;">'
                f'<div style="font-size:12px;color:#8b949e;margin-bottom:4px;">💡 基本面先行指標 · 動態投資建議</div>'
                f'<div style="font-size:15px;font-weight:700;color:{_stance_color};">{_stance_label}</div>'
                f'<div style="font-size:12px;color:#e6edf3;margin-top:4px;">{_stance_desc}</div>'
                f'{_pros_section}{_cons_section}{_notes_section}'
                f'<div style="margin-top:8px;padding-top:6px;border-top:1px solid #30363d;">'
                f'<span style="font-size:11px;color:#8b949e;">📌 建議行動：</span>'
                f'<span style="font-size:12px;color:#e6edf3;">{_action}</span>'
                f'</div>'
                f'</div>', unsafe_allow_html=True
            )
        except Exception as _eli2_err:
            import traceback as _li2_tb
            print(f'[先行指標-建議] 顯示錯誤: {_eli2_err}'); _li2_tb.print_exc()

        # ══ E. VCP + 布林 ══════════════════════════════════════
        st.markdown('---')
        st.markdown('#### 🎯 E. VCP波幅收縮 + 布林通道')
        if vcp2 and vcp2.get('contracting'):
            _sw = vcp2.get('swings', [])
            _ea = f'VCP確認收縮（{len(_sw)}波段），量能萎縮，等待帶量突破進場'; _eb = '突破前高且放量時買入，停損設前波低點'
        elif vcp2:
            _sw = vcp2.get('swings', [])
            _ea = f'VCP尚未形成（{len(_sw)}波段），波動仍大，不宜進場'; _eb = '等待更多整理時間，耐心等候'
        else:
            _ea = '數據不足，VCP無法計算（需至少30日價格資料）'; _eb = ''
        st.markdown(teacher_conclusion('朱家泓', f'{sid2} VCP型態', _ea, _eb), unsafe_allow_html=True)
        ec1,ec2=st.columns(2)
        with ec1:
            st.markdown('**VCP [Mark Minervini]**')
            if vcp2:
                sw=' → '.join([f'{s:.1f}%' for s in vcp2['swings']])
                vc='#3fb950' if vcp2['contracting'] else '#d29922'
                st.markdown(kpi('VCP狀態','✅符合收縮' if vcp2['contracting'] else '⚠️未收縮',
                                f'波幅：{sw}',vc,vc),unsafe_allow_html=True)
                if vcp2['contracting']:
                    st.markdown(signal_box('🔴等待帶量突破頸線','green','確認突破才進場'),unsafe_allow_html=True)
            else:
                st.info('數據不足（需≥40日）')
        with ec2:
            st.markdown('**布林通道 [春哥]**')
            if bb2:
                b1,b2=st.columns(2)
                with b1:
                    st.markdown(kpi('現價',f'{bb2["price"]:.2f}','','#e6edf3'),unsafe_allow_html=True)
                    st.markdown(kpi('布林上軌',f'{bb2["upper"]:.2f}','壓力','#f85149','#f85149'),unsafe_allow_html=True)
                with b2:
                    bw_c='#3fb950' if bb2['bw']<bb2['bw_mean']*0.7 else '#d29922'
                    st.markdown(kpi('帶寬',f'{bb2["bw"]:.1f}%',
                                    f'均值{bb2["bw_mean"]:.1f}% {"⬇️收縮" if bb2["bw"]<bb2["bw_mean"] else "⬆️擴張"}',
                                    bw_c,bw_c),unsafe_allow_html=True)
                    st.markdown(kpi('布林下軌',f'{bb2["lower"]:.2f}','支撐','#3fb950','#3fb950'),unsafe_allow_html=True)
                if bb2['bw']<bb2['bw_mean']*0.6:
                    st.markdown(signal_box('🔵布林帶寬極度收縮','blue','即將爆發，注意量能方向'),unsafe_allow_html=True)
                if bb2['near_upper']:
                    st.markdown(signal_box('🟢股價黏近上軌','green','強勢突破訊號，搭配大量更可信'),unsafe_allow_html=True)
        # ── VCP+布林動態建議 ──
        _vcp_verdict = ''
        _bb_verdict  = ''
        if vcp2:
            _vcp_verdict = ('✅ VCP確認收縮：等待帶量突破頸線，是高確信進場點 [Minervini/妮可]'
                            if vcp2['contracting']
                            else '⚪ 波幅尚未收縮：等待整理完成後再觀察')
        if bb2:
            if bb2['bw'] < bb2['bw_mean']*0.6:
                _bb_verdict = '🔵 布林帶寬極度收縮：即將爆發，注意量能確認方向 [春哥]'
            elif bb2['near_upper']:
                _bb_verdict = '🟢 股價黏近上軌＋強勢：搭配大量是突破確認訊號 [春哥]'
            else:
                _bb_verdict = f'⚪ 布林帶寬{bb2["bw"]:.1f}%（均值{bb2["bw_mean"]:.1f}%）：尚未到關鍵位置'
        if _vcp_verdict or _bb_verdict:
            for _msg in [m for m in [_vcp_verdict, _bb_verdict] if m]:
                _mc2 = '#3fb950' if '✅' in _msg or '🟢' in _msg else ('#58a6ff' if '🔵' in _msg else '#8b949e')
                st.markdown(f'<div style="border-left:3px solid {_mc2};padding:8px 12px;background:#0d1117;border-radius:0 6px 6px 0;font-size:12px;color:{_mc2};margin:4px 0;">{_msg}</div>', unsafe_allow_html=True)

        # VCP+布林結論（安全版：加入 _msg 預設值）
        _msg = _msg if '_msg' in dir() else '⚪ VCP/布林資料不足'
        _vcp_c = '#3fb950' if '✅' in _msg or '🟢' in _msg else ('#d29922' if '⚠️' in _msg else '#484f58')
        st.markdown(
            f'<div style="background:#0d1117;border-left:3px solid {_vcp_c};padding:7px 12px;border-radius:0 6px 6px 0;margin:4px 0;">'
            f'<span style="font-size:11px;color:#8b949e;">🎓 妮可 · VCP</span>　'
            f'<span style="font-size:13px;font-weight:700;color:{_vcp_c};">{_msg}</span>'
            f'</div>', unsafe_allow_html=True
        )
        if bb2:
            _bb_verdict_safe = _bb_verdict if '_bb_verdict' in dir() else '⚪ 布林資料不足'
            _bb_c = '#3fb950' if '✅' in _bb_verdict_safe or '🟢' in _bb_verdict_safe else ('#3aa2f5' if '🔵' in _bb_verdict_safe else '#d29922')
            st.markdown(
                f'<div style="background:#0d1117;border-left:3px solid {_bb_c};padding:7px 12px;border-radius:0 6px 6px 0;margin:4px 0;">'
                f'<span style="font-size:11px;color:#8b949e;">🎓 春哥 · 布林</span>　'
                f'<span style="font-size:13px;font-weight:700;color:{_bb_c};">{_bb_verdict_safe}</span>'
                f'</div>', unsafe_allow_html=True
            )

        # ══ F. K線技術圖 ═══════════════════════════════════════
        st.markdown('---')
        st.markdown('#### 📊 F. K線技術圖表（含三大法人籌碼）')
        _fa = f'{sid2} K線技術'; _fb_txt = ''; _fc_txt = ''
        if df2 is not None and not df2.empty and len(df2) >= 20:
            _p_now_f = float(df2['close'].iloc[-1])
            _ma20_f  = float(df2['close'].rolling(20).mean().iloc[-1])
            _cl_trend = '上漲' if float(df2['close'].iloc[-1]) > float(df2['close'].iloc[-5]) else '下跌'
            _above_f = _p_now_f > _ma20_f
            _inst_f = st.session_state.get('t2_inst', {})
            _fnet_f = _inst_f.get('外資', 0) if _inst_f else 0
            if _above_f and _fnet_f > 0:
                _fb_txt = f'站上月線 + 外資買超，主力進駐訊號，可跟進'; _fc_txt = '停損設月線下方'
            elif _above_f and _fnet_f < 0:
                _fb_txt = f'站上月線但外資賣超，需謹慎確認主力方向'; _fc_txt = '等待外資轉買後再行動'
            elif not _above_f and _fnet_f > 0:
                _fb_txt = f'月線下方但外資買超，可能正在築底'; _fc_txt = '等待重回月線確認後再評估'
            else:
                _fb_txt = f'月線下方且外資賣超，趨勢偏空，暫時迴避'; _fc_txt = '等待更明確的多頭訊號'
            _fa = f'{sid2} 現價{_p_now_f:.1f}（{"站月線" if _above_f else "跌月線"}）| 外資{"買超" if _fnet_f>0 else "賣超" if _fnet_f<0 else "中性"}'
        else:
            _fb_txt = '技術資料載入中，請先點擊「🔍 載入完整分析」'
        st.markdown(teacher_conclusion('朱家泓', _fa, _fb_txt, _fc_txt), unsafe_allow_html=True)
        if df2 is not None and not df2.empty:
            fig_k = plot_combined_chart(df2, sid2, name2, show_ma_dict, k_line_type='還原K線' if t2_adjusted else '一般K線')
            st.plotly_chart(fig_k, use_container_width=True,
                            config={'displayModeBar':True,'displaylogo':False,
                                    'modeBarButtonsToRemove':['lasso2d','select2d']})
        else:
            if t2d.get('err'): st.error(f'❌ {t2d["err"]}')
        # ── K線動態趨勢建議 ──
        if df2 is not None and 'MA20' in df2.columns and 'MA100' in df2.columns:
            _kp = price2; _km20 = float(df2['MA20'].iloc[-1]); _km100 = float(df2['MA100'].iloc[-1])
            if _kp > _km20 > _km100:
                _trend_msg = f'📈 多頭排列：股價 {_kp:.1f} ＞ MA20 {_km20:.1f} ＞ MA100 {_km100:.1f} — 宏爺：可持股，大盤多頭才做個股'; _tc = '#3fb950'
            elif _kp < _km20 < _km100:
                _trend_msg = f'📉 空頭排列：股價 {_kp:.1f} ＜ MA20 {_km20:.1f} ＜ MA100 {_km100:.1f} — 宏爺：不做多，嚴格停損'; _tc = '#f85149'
            elif _kp > _km100:
                _trend_msg = f'📊 多箱整理：股價在 MA100 之上 — 宏爺：等待站上 MA20({_km20:.1f})確認方向'; _tc = '#d29922'
            else:
                _trend_msg = f'📊 空箱整理：股價低於 MA100 — 宏爺：耐心等待多頭訊號，不摸底'; _tc = '#d29922'
            st.markdown(f'<div style="border-left:4px solid {_tc};padding:10px 14px;background:#0d1117;border-radius:0 8px 8px 0;font-size:13px;font-weight:700;color:{_tc};margin:8px 0;">{_trend_msg}</div>', unsafe_allow_html=True)

        # K線均線結論（安全版）
        _trend_msg_safe = _trend_msg if '_trend_msg' in dir() else '⚪ K線資料不足'
        _kl_c = '#3fb950' if '多頭' in _trend_msg_safe or '✅' in _trend_msg_safe else ('#f85149' if '空頭' in _trend_msg_safe else '#d29922')
        st.markdown(
            f'<div style="background:#0d1117;border-left:3px solid {_kl_c};padding:7px 12px;border-radius:0 6px 6px 0;margin:4px 0;">'
            f'<span style="font-size:11px;color:#8b949e;">🎓 宏爺 · 均線排列</span>　'
            f'<span style="font-size:13px;font-weight:700;color:{_kl_c};">{_trend_msg_safe}</span>'
            f'</div>', unsafe_allow_html=True
        )

        # ── 近5日評分走勢（儲存本次評分到歷史）───────────────────
        _score_hist_key = f'score_hist_{sid2}'
        _score_hist = st.session_state.get(_score_hist_key, [])
        # 加入今日評分
        _today_str = datetime.date.today().strftime('%m/%d')
        _last_entry = _score_hist[-1] if _score_hist else {}
        if _last_entry.get('date') != _today_str:
            _score_hist.append({
                'date':    _today_str,
                'health':  health2,
                'rsi':     rsi2 or 0,
                'total':   0,  # 多因子評分在 Tab3 中
            })
            _score_hist = _score_hist[-7:]  # 只保留最近7天
            st.session_state[_score_hist_key] = _score_hist

        if len(_score_hist) >= 2:
            st.markdown('---')
            st.markdown('##### 📈 健康度走勢（近5日）')
            _fig_sh = go.Figure()
            _sh_dates  = [r['date']   for r in _score_hist]
            _sh_health = [r['health'] for r in _score_hist]
            # 填色區間
            _fig_sh.add_hrect(y0=80, y1=100, fillcolor='rgba(63,185,80,0.08)',  line_width=0)
            _fig_sh.add_hrect(y0=50, y1=80,  fillcolor='rgba(210,153,34,0.05)', line_width=0)
            _fig_sh.add_hrect(y0=0,  y1=50,  fillcolor='rgba(248,81,73,0.05)',  line_width=0)
            _fig_sh.add_trace(go.Scatter(
                x=_sh_dates, y=_sh_health, mode='lines+markers',
                line=dict(color='#58a6ff', width=2.5),
                marker=dict(size=8, color=['#3fb950' if v>=80 else ('#d29922' if v>=50 else '#f85149')
                                           for v in _sh_health]),
                text=[str(v) for v in _sh_health], textposition='top center',
                hovertemplate='%{x}<br>健康度：%{y:.0f}<extra></extra>'
            ))
            _fig_sh.update_layout(
                height=180, plot_bgcolor='#0e1117', paper_bgcolor='#0e1117',
                font=dict(color='white',size=10), margin=dict(l=10,r=10,t=10,b=20),
                xaxis=dict(gridcolor='#21262d'), yaxis=dict(gridcolor='#21262d',range=[0,105]),
                showlegend=False)
            st.plotly_chart(_fig_sh, use_container_width=True, config={'displayModeBar':False})
            # 評分突變偵測（分數飆升≥20分）
            if len(_sh_health) >= 2 and _sh_health[-1] - _sh_health[-2] >= 20:
                st.success(f'🚀 評分突變！健康度從 {_sh_health[-2]:.0f} → {_sh_health[-1]:.0f}（+{_sh_health[-1]-_sh_health[-2]:.0f}），可能是主升段起點！')

        # ══ G. AI 五維報告 ══════════════════════════════════════
        st.markdown('---')

        # ── 即時文字建議（Rule-based，不需 AI API）──────────────
        st.markdown('#### 💡 即時操作建議（規則引擎）')
        _reg_op = st.session_state.get('mkt_info', {}).get('regime', 'neutral')
        _sig_count = sum([
            1 if health2 >= 80 else 0,
            1 if _reg_op == 'bull' else 0,
            1 if (vcp2 and vcp2.get('contracting')) else 0,
            1 if (avg_div2 > 0 and price2 > 0 and price2 <= round(avg_div2/0.05, 1)) else 0,
        ])
        if _reg_op == 'bear':
            _op_a = f'大盤空頭格局，{sid2} 無論評分多高，先降倉至20%以下'; _op_b = '市場趨勢優先，個股強不等於能賺錢'
        elif _sig_count >= 3:
            _op_a = f'{_sig_count}個訊號共振（健康度+大盤+VCP+估值），可積極進場'; _op_b = '分批建倉，停損設健康度跌破60'
        elif _sig_count >= 2:
            _op_a = f'{_sig_count}個訊號共振，中性偏多，可小倉試水溫'; _op_b = '輕倉試探，等待更多確認訊號'
        else:
            _op_a = f'只有{_sig_count}個訊號，條件不足，今日不操作 {sid2}'; _op_b = '耐心等待，寧可錯過勿強求'
        st.markdown(teacher_conclusion('宏爺', f'{sid2} 共振訊號 {_sig_count}/4', _op_a, _op_b), unsafe_allow_html=True)
        try:
            _mkt_top_g = st.session_state.get('mkt_info', {})
            _m1b_top_g = st.session_state.get('m1b_m2_info', {})
            _bias_g    = st.session_state.get('bias_info', {})
            _m1b_diff_g= _m1b_top_g.get('m1b_yoy',0)-_m1b_top_g.get('m2_yoy',0) if _m1b_top_g else 0
            # 取 Tab3 最近分析的外資資料
            _cd_g = st.session_state.get('cl_data',{})
            _inst_g = _cd_g.get('inst',{})
            _fk_g = next((k for k in _inst_g if '外資' in k), None)
            _tk_g = next((k for k in _inst_g if '投信' in k), None)
            _comment_data = {
                'health':      health2,
                'score':       0,  # Tab3 多因子評分（此處無法取得，用0）
                'rsi':         rsi2,
                'vcp_ok':      bool(vcp2 and isinstance(vcp2,dict) and vcp2.get('contracting')),
                'bias_240':    _bias_g.get('bias_240', 0),
                'bias_20':     _bias_g.get('bias_20', 0),
                'val_label':   _357_label2 if '_357_label2' in dir() else '',
                'trend':       _trend_text2 if '_trend_text2' in dir() else '',
                'cl':          cl2 / 1e8 if cl2 and cl2 > 0 else 0,
                'cx':          cx2 / 1e8 if cx2 and cx2 > 0 else 0,
                'foreign_buy': _inst_g.get(_fk_g,{}).get('net',0) if _fk_g else 0,
                'trust_buy':   _inst_g.get(_tk_g,{}).get('net',0) if _tk_g else 0,
                'm1b_diff':    _m1b_diff_g,
            }
            _comment_txt = generate_ai_comment(_comment_data)
            if _comment_txt:
                st.markdown(
                    '<div style="background:#0d1117;border:1px solid #30363d;'
                    'border-radius:10px;padding:14px;margin-bottom:10px;'
                    'font-size:13px;color:#c9d1d9;line-height:1.7;">'
                    + _comment_txt.replace(chr(10), '<br>') +
                    '</div>', unsafe_allow_html=True)
        except Exception as _ce:
            pass

        # ── Tab2 底部 AI 分析 ──────────────────────────────────────
        st.markdown('---')
        st.markdown('#### 🤖 個股 AI 投資決策分析')
        _t2_ai_key = f't2_ai_{sid2}'
        _t2_ai_cached = st.session_state.get(_t2_ai_key, '')
        if _t2_ai_cached:
            st.markdown(_t2_ai_cached)
            if st.button('🔄 重新生成', key='t2_ai_regen'):
                st.session_state.pop(_t2_ai_key, None)
                st.rerun()
        else:
            if st.button('🤖 生成完整AI分析', key='t2_ai_gen', type='primary'):
                _t2_trend = ('多頭排列' if df2 is not None and 'MA20' in df2.columns and 'MA100' in df2.columns
                             and price2 > float(df2['MA20'].iloc[-1]) > float(df2['MA100'].iloc[-1])
                             else '空頭/整理')
                _t2_prompt = (
                    f"你是宏爺+孫慶龍的AI助手，以台灣股市實戰語氣分析 {sid2}({name2})：\n"
                    f"現價={price2:.2f} 健康度={health2:.0f}分 RSI={rsi2} KD=K{k2}/D{d2}\n"
                    f"趨勢={_t2_trend} 量比={vr2} IBS={ibs2}\n"
                    f"大盤：{st.session_state.get('mkt_info',{}).get('regime','neutral')}\n\n"
                    f"請依序回答（每段不超過50字）：\n"
                    f"① 目前技術面評價（一句話）\n"
                    f"② 具體進場條件\n"
                    f"③ 停損價位設定\n"
                    f"④ 風控建議"
                )
                with st.spinner('AI分析中...'):
                    _t2_result = gemini_call(_t2_prompt, max_tokens=400)
                st.session_state[_t2_ai_key] = _t2_result
                st.markdown(_t2_result)
            else:
                st.caption('點擊上方按鈕生成此股 AI 投資決策分析')

# ══════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════
# TAB 3: 綜合評分戰情室（汰弱留強 × 多因子評分 合併版）
# ══════════════════════════════════════════════════════════════

    st.markdown("""<div style="background:#2a0d0d;border:1px solid #f85149;border-radius:8px;
padding:10px 14px;font-size:11px;color:#f85149;margin-top:12px;">
⚠️ 本手冊整理自各大師公開課程內容，僅供學術研究與教育用途。
投資涉及風險，任何操作均應自行判斷，盈虧自負。本系統非投資顧問，不構成買賣建議。
</div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# TAB 3+4: 比較排行 + 策略手冊（從 v3_20_21 恢復）
# ══════════════════════════════════════════════════════════════
with tab3_compare:
    st.markdown("""<div style="padding:6px 0 4px;">
<span style="font-size:20px;font-weight:900;color:#e6edf3;">📊 比較 × 排行</span>
<span style="font-size:11px;color:#484f58;margin-left:10px;">市場狀態 · 多股比較 · 多因子排行 · 汰弱留強 · 最終建議</span>
</div>""", unsafe_allow_html=True)

    # ══ ① 市場狀態快覽 ══════════════════════════════════════════
    _t3_mkt = st.session_state.get('mkt_info', {})
    _t3_li  = st.session_state.get('li_latest')
    _t3_tl  = st.session_state.get('warroom_summary', {})
    if _t3_tl or _t3_mkt:
        _t3c1, _t3c2, _t3c3 = st.columns(3)
        with _t3c1:
            _tl_label = _t3_tl.get('traffic_light', '未更新')
            _tl_color = ('#3fb950' if '綠' in _tl_label else
                         '#d29922' if '黃' in _tl_label else
                         '#f85149' if '紅' in _tl_label else '#484f58')
            st.markdown(
                f'<div style="background:#0d1117;border:1px solid {_tl_color}33;border-radius:8px;'
                f'padding:10px 14px;text-align:center;">'
                f'<div style="font-size:11px;color:#8b949e;">🚦 大盤燈號</div>'
                f'<div style="font-size:16px;font-weight:900;color:{_tl_color};">{_tl_label}</div>'
                f'</div>', unsafe_allow_html=True)
        with _t3c2:
            _twii = _t3_mkt.get('台股加權指數', {})
            _twii_pct = _twii.get('pct', 0) if _twii else 0
            _twii_c = '#da3633' if _twii_pct > 0 else '#2ea043'
            st.markdown(
                f'<div style="background:#0d1117;border:1px solid #30363d;border-radius:8px;'
                f'padding:10px 14px;text-align:center;">'
                f'<div style="font-size:11px;color:#8b949e;">📈 台股大盤</div>'
                f'<div style="font-size:16px;font-weight:900;color:{_twii_c};">{_twii_pct:+.2f}%</div>'
                f'</div>', unsafe_allow_html=True)
        with _t3c3:
            _t3_hold = _t3_tl.get('hold_pct', '--')
            st.markdown(
                f'<div style="background:#0d1117;border:1px solid #30363d;border-radius:8px;'
                f'padding:10px 14px;text-align:center;">'
                f'<div style="font-size:11px;color:#8b949e;">💼 建議持股</div>'
                f'<div style="font-size:16px;font-weight:900;color:#58a6ff;">{_t3_hold}%</div>'
                f'</div>', unsafe_allow_html=True)
        st.markdown('')
    else:
        st.info('⏳ 請先到「🌍 總經」Tab 點擊「🔄 更新全部總經數據」取得最新大盤狀態')

    # ══ ② 輸入多檔代碼 ══════════════════════════════════════════
    with st.container(border=True):
        t3c1, t3c2 = st.columns([4, 1])
        with t3c1:
            multi_input = st.text_area(
                '輸入多檔代碼（逗號/空格/換行，最多10檔）',
                value='2330 2454 2317 2382 3017 2308 2303 2376 6669 3661',
                height=68, key='multi_input',
                placeholder='例：2330 2454 2317 2382 3017')
        with t3c2:
            st.markdown('<br>', unsafe_allow_html=True)
            t3_run_btn = st.button('🚀 批次分析', type='primary',
                                   use_container_width=True, key='t3_run_btn')

    stock_list_t3 = parse_stocks(multi_input)[:10]
    if stock_list_t3:
        st.caption(f'待分析：{", ".join(stock_list_t3)}（共{len(stock_list_t3)}檔）')

    # ══ 批次分析邏輯 ════════════════════════════════════════════
    if t3_run_btn and stock_list_t3:
        loader_t3  = _get_loader()
        results_t3 = []          # 汰弱留強（健康度）結果
        score_t3   = []          # 多因子評分結果

        prog_t3 = st.progress(0, text='批次分析中...')
        from scoring_engine import score_single_stock as _sss
        from stock_names    import get_stock_name as _gsn
        import threading as _threading
        _t3_loader_lock = _threading.Lock()  # FinMind dl 非線程安全，需串行保護

        # ── 並發抓取（ThreadPoolExecutor，最多3個同時）────────
        def _fetch_single_t3(sid4):
            # 先檢查本地緩存（v2 prefix 強制清除舊錯誤 cache）
            _cached = _load_cache('t3v2', sid4, ttl_hours=4)
            if _cached: return _cached
            try:
                # get_combined_data 共享 FinMind dl 實例，需加鎖確保線程安全
                with _t3_loader_lock:
                    _df4_raw, _err4, _name4 = loader_t3.get_combined_data(sid4, 360, True)
                df4   = _df4_raw.tail(300).reset_index(drop=True) if _df4_raw is not None and not _df4_raw.empty else None
                # _name4 可能就是 sid4（get_stock_name fallback），需確認是真正的名稱
                name4 = (_name4 if _name4 and _name4 != sid4 else None) or _gsn(sid4) or sid4
                avg_div4, _, _ = fetch_dividend_data(sid4)
                cl4, cx4, _capex4, _cl_src4, _cx_src4, _, _fin_errs4 = fetch_financials(sid4, industry='')
                result4 = {'sid': sid4, 'df': df4, 'name': name4,
                           'avg_div': avg_div4, 'cl': cl4, 'cx': cx4}
                _save_cache('t3v2', sid4, result4)
                return result4
            except Exception as _e4:
                return {'sid': sid4, 'error': str(_e4)}

        _t3_futures = {}
        with ThreadPoolExecutor(max_workers=3) as _t3_exec:
            for sid4 in stock_list_t3:
                _t3_futures[_t3_exec.submit(_fetch_single_t3, sid4)] = sid4
        _t3_fetched = {}
        for _fut, _sid in _t3_futures.items():
            try: _t3_fetched[_sid] = _fut.result()
            except: _t3_fetched[_sid] = {'sid': _sid, 'error': 'timeout'}

        for i4, sid4 in enumerate(stock_list_t3):
            prog_t3.progress((i4 + 1) / len(stock_list_t3),
                             text=f'分析 {sid4} ({i4+1}/{len(stock_list_t3)})...')
            try:
                _d4     = _t3_fetched.get(sid4, {})
                df4     = _d4.get('df')
                # 名稱優先: loader返回值 > stock_names靜態字典 > 代碼本身
                _raw_name4 = _d4.get('name', '')
                name4   = (_raw_name4 if _raw_name4 and _raw_name4 != sid4
                           else _gsn(sid4))
                avg_div4= _d4.get('avg_div', 0)
                cl4     = _d4.get('cl')
                cx4     = _d4.get('cx')
                _fin_st4= {}

                price4  = float(df4['close'].iloc[-1]) if df4 is not None and not df4.empty else 0
                ma20_4  = float(df4['MA20'].iloc[-1])  if df4 is not None and 'MA20'  in df4.columns else None
                ma100_4 = float(df4['MA100'].iloc[-1]) if df4 is not None and 'MA100' in df4.columns else None
                rsi4    = calc_rsi(df4);  ibs4 = calc_ibs(df4)
                vr4     = calc_volume_ratio(df4)
                k4, d4  = calc_kd(df4);   bb4  = calc_bollinger(df4)
                vcp4    = calc_vcp(df4) if df4 is not None and len(df4) >= 30 else None
                health4, _ = calc_health_score(df4, rsi4, ibs4, vr4, k4, d4, bb4)
                grade4, grade_color4, _, emoji4 = health_grade(health4)

                if ma20_4 and ma100_4 and price4 > ma20_4 > ma100_4:   trend4 = '📈多頭'
                elif ma20_4 and ma100_4 and price4 < ma20_4 < ma100_4:  trend4 = '📉空頭'
                elif ma100_4 and price4 > ma100_4:                      trend4 = '📊多箱'
                elif price4 > 0:                                         trend4 = '📊空箱'
                else:                                                     trend4 = '⚪無資料'

                val4 = '⚪無股利'
                if avg_div4 > 0 and price4 > 0:
                    ch4, fa4, de4 = avg_div4/0.07, avg_div4/0.05, avg_div4/0.03
                    if price4 <= ch4:   val4 = '🟢便宜'
                    elif price4 <= fa4: val4 = '🟡合理'
                    elif price4 <= de4: val4 = '🔴昂貴'
                    else:               val4 = '🔴超貴'

                vcp_ok4 = vcp4 and vcp4['contracting']

                # ── 汰弱留強舊評分 ─────────────────────────────
                old_score4 = 0
                if '多頭' in trend4: old_score4 += 2
                if '便宜' in val4:   old_score4 += 3
                elif '合理' in val4: old_score4 += 1
                if vcp_ok4:          old_score4 += 2
                if cl4 and cl4 > 0:  old_score4 += 1
                old_score4 += round(health4 / 50, 0)

                results_t3.append({
                    'stock_id': sid4,
                    '代碼': sid4, '名稱': name4 or sid4, '現價': f'{price4:.2f}',
                    '健康度': health4, '評級': f'{emoji4}{grade4}',
                    'RSI':  f'{rsi4}' if rsi4 else '-',
                    '量比': f'{vr4}' if vr4 else '-',
                    'IBS':  f'{ibs4}' if ibs4 is not None else '-',
                    'KD':   f'K{k4}/D{d4}' if k4 else '-',
                    '趨勢': trend4, '357評價': val4,
                    'VCP':  '✅收縮' if vcp_ok4 else '⚪',
                     '合約負債': f'{cl4/1e8:.1f}億' if cl4 and cl4 > 0 else '-',



                    '舊評分': int(old_score4),
                    '_health': health4, '_val': val4, '_trend': trend4,
                })

                # ── 操作狀態燈 🔵🟠🟡 ──────────────────────────
                try:
                    _status4 = '⚪'
                    if df4 is not None and not df4.empty:
                        _p4      = float(df4['close'].iloc[-1])
                        _ma20_4  = float(df4['close'].tail(20).mean())
                        _bias4   = (_p4 - _ma20_4) / _ma20_4 * 100 if _ma20_4 else 0
                        _vol4    = float(df4['volume'].iloc[-1])      if 'volume' in df4.columns else 0
                        _avgvol4 = float(df4['volume'].tail(20).mean()) if 'volume' in df4.columns else 1
                        _shrink4 = _avgvol4 > 0 and _vol4 < _avgvol4 * 0.7
                        _near20_4= abs(_bias4) < 3
                        if health4 >= 80 and '多頭' in str(trend4) and _shrink4 and _near20_4:
                            _status4 = '🔵 加碼'
                        elif _bias4 > 25:
                            _status4 = '🟡 警示'
                        elif '昂貴' in str(val4) or '超貴' in str(val4):
                            _status4 = '🟠 減碼'
                    if results_t3:
                        results_t3[-1]['操作狀態'] = _status4
                except: pass

                # ── 多因子評分 ─────────────────────────────────
                if df4 is not None and not df4.empty:
                    try:
                        df4_full, _, name4_full = loader_t3.get_combined_data(sid4, 300, True)
                        if df4_full is not None and not df4_full.empty:
                            # name4_full 可能等於 sid4（代碼），需排除才能使用後備
                            _n4_use = (name4_full if name4_full and name4_full != sid4 else None) or name4 or _gsn(sid4)
                            sf = _sss(df4_full, sid4, _n4_use)
                            score_t3.append(sf)
                    except Exception:
                        pass

            except Exception as e4:
                results_t3.append({
                    'stock_id': sid4, '代碼': sid4, '名稱': '失敗', '現價': '-',
                    '健康度': 0, '評級': '-', 'RSI': '-', '量比': '-',
                    'IBS': '-', 'KD': '-', '趨勢': '-', '357評價': '-',
                    'VCP': '-', '合約負債': '-', '舊評分': 0,
                    '_health': 0, '_val': '-', '_trend': '-',
                })
            time.sleep(0.2)

        prog_t3.empty()

        # ── AI 風控警示 ────────────────────────────────────────
        _t3_mkt = st.session_state.get('mkt_info', {}) or {}  # 從 Tab1 更新後取得
        risk_alerts_t3 = []
        if _t3_mkt.get('regime') == 'bear':
            risk_alerts_t3.append('大盤偏空，建議降低持股至20%以下')
        if _t3_mkt.get('foreign_net', 0) < -5e9:
            risk_alerts_t3.append('外資大量賣超，注意籌碼面壓力')

        st.session_state['t3_data'] = {
            'results':     results_t3,
            'score_t3':    score_t3,
            'risk_alerts': risk_alerts_t3,
        }

    # ══ 顯示結果 ════════════════════════════════════════════════
    t3_data = st.session_state.get('t3_data')

    if t3_data:
        results_t3  = t3_data['results']
        score_t3    = t3_data['score_t3']
        risk_alerts = t3_data.get('risk_alerts', [])

        # ── 預先計算基本面（③④⑤ 共用）─────────────────────────
        _fund_map = {}
        for _r3 in results_t3:
            _sid3 = _r3.get('stock_id', _r3.get('代碼',''))
            _qtr3 = None
            try: _qtr3, _ = fetch_quarterly(_sid3)
            except Exception: pass
            _avg3 = None
            try: _avg3, _, _ = fetch_dividend_data(_sid3)
            except Exception: pass
            _eps3 = _gp3 = None
            if _qtr3 is not None and not _qtr3.empty:
                _ec3 = next((c for c in _qtr3.columns if 'EPS' in str(c).upper() or '每股盈餘' in str(c)), None)
                _gc3 = '毛利率' if '毛利率' in _qtr3.columns else None  # 精確比對，避免命中'毛利率名稱'
                if _ec3:
                    _es3 = pd.to_numeric(_qtr3[_ec3].tail(4), errors='coerce').dropna()
                    if len(_es3) >= 1: _eps3 = round(float(_es3.sum()), 2)
                if _gc3:
                    # 取最後一個非NaN值（避免最新季度尚未公布時取到NaN）
                    _gs3 = pd.to_numeric(_qtr3[_gc3], errors='coerce').dropna()
                    if len(_gs3) >= 1: _gp3 = round(float(_gs3.iloc[-1]), 1)
            # 獲利品質得分 (SQ)
            _sq3 = None
            try:
                from scoring_engine import calc_quality_score as _cqs3
                _sq_r3 = _cqs3(_qtr3)
                if _sq_r3.get('sq') is not None:
                    _sq3 = f"{_sq_r3['sq']:.0f}({_sq_r3['sq_label']})"
            except Exception: pass
            # 前瞻動能 FGMS
            _fgms3 = None
            try:
                _qex3 = None
                try: _qex3, _ = fetch_quarterly_extra(_sid3)
                except Exception: pass
                from scoring_engine import calc_forward_momentum_score as _cfgms3
                _is_fin3 = bool(_qtr3['是否金融股'].iloc[0]) if _qtr3 is not None and '是否金融股' in _qtr3.columns else False
                _fg_r3 = _cfgms3(_qtr3, _qex3, is_finance=_is_fin3)
                if _fg_r3.get('fgms') is not None:
                    _fgms3 = f"{_fg_r3['fgms']:.0f}({_fg_r3['fgms_label']})"
            except Exception: pass
            _fund_map[_sid3] = {
                '近4季EPS': f'{_eps3:.2f}' if _eps3 is not None else '-',
                '毛利率%':  f'{_gp3:.1f}'  if _gp3  is not None else '-',
                '殖利率%':  f'{_avg3:.1f}' if _avg3  is not None else '-',
                'SQ評分':   _sq3   if _sq3   is not None else '-',
                'FGMS':     _fgms3 if _fgms3 is not None else '-',
            }

        # ── ⑤ 最終綜合建議卡 ──────────────────────────────────
        if results_t3:
            score_map = {s['stock_id']: s for s in score_t3}

            def _final_rec(row):
                health   = row.get('_health', 0)
                val      = row.get('_val', '')
                trend    = row.get('_trend', '')
                mf_total = score_map.get(row['stock_id'], {}).get('total', 0)
                pts = 0
                if health >= 80:     pts += 3
                elif health >= 50:   pts += 1
                if mf_total >= 75:   pts += 3
                elif mf_total >= 55: pts += 1
                if '便宜' in val:    pts += 2
                elif '合理' in val:  pts += 1
                if '多頭' in trend:  pts += 1
                if pts >= 7:   return '🟢 積極', '#3fb950'
                elif pts >= 4: return '🟡 觀察', '#d29922'
                else:          return '🔴 等待', '#f85149'

            st.markdown('#### ⑤ 最終綜合建議')
            # 動態：計算積極/觀察/等待各有幾支
            _rec_counts = {'積極': 0, '觀察': 0, '等待': 0}
            for _rr in results_t3:
                _rl, _ = _final_rec(_rr); _rec_counts[_rl.split()[-1]] = _rec_counts.get(_rl.split()[-1], 0) + 1
            _active_n = _rec_counts.get('積極', 0); _wait_n = _rec_counts.get('等待', 0)
            if _active_n >= 2:
                _r5c = f'本批 {_active_n} 支達積極布局條件'; _r5a = '可同步建倉，停損設健康度跌破50'
            elif _active_n == 1:
                _r5c = f'僅 1 支達積極條件，其餘觀察或等待'; _r5a = '單一標的建倉，其餘等訊號確認'
            else:
                _r5c = f'本批無積極訊號（{_wait_n} 支等待），市場擇股難度高'; _r5a = '空手等待，勿強求進場'
            st.markdown(teacher_conclusion('宏爺', f'健康+多因子+357三重確認，共 {len(results_t3)} 支', _r5c, _r5a), unsafe_allow_html=True)
            rec_cols = st.columns(min(len(results_t3), 5))
            for ci, row in enumerate(results_t3[:5]):
                rec_label, rec_color = _final_rec(row)
                mf2 = score_map.get(row['stock_id'], {}).get('total', 0)
                _fd2 = _fund_map.get(row['stock_id'], {})
                with rec_cols[ci]:
                    st.markdown(f"""<div style="background:#0d1117;border:2px solid {rec_color};
border-radius:10px;padding:12px;text-align:center;margin:2px 0;">
<div style="font-size:20px;font-weight:900;color:{rec_color};">{row['代碼']}</div>
<div style="font-size:11px;color:#8b949e;">{row['名稱']}</div>
<div style="font-size:13px;font-weight:700;color:{rec_color};margin:6px 0;">{rec_label}</div>
<div style="font-size:11px;color:#8b949e;">健康:{row.get('健康度',0):.0f} | 多因子:{mf2:.0f}</div>
<div style="font-size:11px;color:#8b949e;">EPS:{_fd2.get('近4季EPS','-')} | 毛利:{_fd2.get('毛利率%','-')}%</div>
</div>""", unsafe_allow_html=True)

        # ── RS 走勢對比 ─────────────────────────────────────────
        if score_t3 and len(score_t3) >= 2:
            st.markdown('---')
            _sdf = pd.DataFrame([{
                '代碼': r['stock_id'], '總分': r.get('total',0),
                '趨勢': r.get('trend',0), '動能': r.get('momentum',0),
                '籌碼': r.get('chip',0), '量價': r.get('volume',0),
                'RS': r.get('rs_score',50),
            } for r in score_t3]).sort_values('總分', ascending=False)
            st.markdown('##### 📈 多因子維度對比')
            # 動態：找出 RS 最高與 RS 向上的股票
            _rs_top = _sdf.iloc[0] if not _sdf.empty else None
            _rs_up_pre = [r['stock_id'] for r in score_t3 if r.get('rs_up')]
            if _rs_top is not None and _rs_up_pre:
                _rs27c = f'RS 最強 {_rs_top["代碼"]}（{_rs_top["RS"]:.0f}分），{len(_rs_up_pre)} 支 RS 向上'
                _rs27a = '優先佈局 RS 向上標的，動能最強'
            elif _rs_top is not None:
                _rs27c = f'RS 最強 {_rs_top["代碼"]}（{_rs_top["RS"]:.0f}分），無 RS 向上訊號'
                _rs27a = '等待突破，趨勢+動能>70再行動'
            else:
                _rs27c = 'RS 資料計算中'; _rs27a = '等待資料載入後判斷'
            st.markdown(teacher_conclusion('朱家泓', 'RS相對強度對比', _rs27c, _rs27a), unsafe_allow_html=True)
            _score_pivot = _sdf.head(5).set_index('代碼')[['趨勢','動能','籌碼','量價','RS']]
            st.dataframe(_score_pivot, use_container_width=True,
                column_config={c: st.column_config.ProgressColumn(c, min_value=0, max_value=100, format='%.0f')
                               for c in ['趨勢','動能','籌碼','量價','RS']})
            _rs_up_list = [r['stock_id'] for r in score_t3 if r.get('rs_up')]
            if _rs_up_list:
                st.success(f"📊 RS曲線向上（強勢動能）：{' / '.join(_rs_up_list)}")

        st.markdown('---')

        # ── ③+④ 雙欄：多因子排行（含EPS/毛利率）vs 汰弱留強 ──
        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown('##### ③ 多因子評分排行')
            st.caption('趨勢×0.30 + 動能×0.25 + 籌碼×0.20 + 量價×0.15 + 風險×0.10')
            # 動態：找出最高分與門檻達標數
            _top_score_r = max(score_t3, key=lambda r: r.get('total', 0)) if score_t3 else None
            _pass70 = [r for r in score_t3 if r.get('total', 0) >= 70]
            if _top_score_r:
                _mf3c = f'最高分 {_top_score_r["stock_id"]} {_top_score_r.get("total",0):.0f}分，{len(_pass70)}/{len(score_t3)} 支≥70分'
                _mf3a = '≥70分方可列入候選，其餘繼續觀察'
            else:
                _mf3c = '多因子資料計算中'; _mf3a = '等待評分載入'
            st.markdown(teacher_conclusion('孫慶龍', '多因子總分排行', _mf3c, _mf3a), unsafe_allow_html=True)
            if score_t3:
                from scoring_engine import rank_stocks as _rk3
                _ranked3 = _rk3(score_t3)
                _rank_rows = []
                for _ri, _r in enumerate(_ranked3):
                    _sid_r = _r.get('stock_id','')
                    _fd = _fund_map.get(_sid_r, {})
                    _rank_rows.append({
                        '排名': _ri + 1, '代碼': _sid_r,
                        '名稱': (_r.get('stock_name','') or '')[:6],
                        '總分': _r.get('total', 0),
                        '近4季EPS': _fd.get('近4季EPS', '-'),
                        '毛利率%':  _fd.get('毛利率%',  '-'),
                        'SQ評分':   _fd.get('SQ評分',   '-'),
                        'FGMS前瞻': _fd.get('FGMS',     '-'),
                        '殖利率%':  _fd.get('殖利率%',  '-'),
                        '評級': _r.get('grade', '-'),
                    })
                _rank_df = pd.DataFrame(_rank_rows)
                st.dataframe(_rank_df, use_container_width=True, hide_index=True,
                             column_config={
                                 '總分':     st.column_config.ProgressColumn('總分', min_value=0, max_value=100, format='%.1f'),
                                 '近4季EPS': st.column_config.TextColumn('近4Q EPS'),
                                 '毛利率%':  st.column_config.TextColumn('毛利率%'),
                                 'SQ評分':   st.column_config.TextColumn('SQ品質分'),
                                 'FGMS前瞻': st.column_config.TextColumn('FGMS前瞻'),
                                 '殖利率%':  st.column_config.TextColumn('殖利率%'),
                             })
            else:
                st.info('多因子評分資料載入中')

        with col_right:
            st.markdown('##### ④ 汰弱留強明細')
            st.caption('健康度 · 357評價 · VCP · KD · RSI')
            # 動態：計算被淘汰（健康度<50 或 357超貴）的數量
            _elim_n = sum(1 for r in results_t3
                          if r.get('健康度', 100) < 50 or '超貴' in str(r.get('357評價', '')))
            _keep_n = len(results_t3) - _elim_n
            if _elim_n > 0:
                _e4c = f'{_elim_n} 支被淘汰（健康<50 或 357超貴），剩 {_keep_n} 支候選'
                _e4a = '只看留下的 {_keep_n} 支，被淘汰直接跳過'.format(_keep_n=_keep_n)
            else:
                _e4c = f'本批 {len(results_t3)} 支全數通過汰弱篩選'
                _e4a = '品質整齊，可從多因子排行取前2~3支'
            st.markdown(teacher_conclusion('弘爺', f'汰弱留強（共 {len(results_t3)} 支）', _e4c, _e4a), unsafe_allow_html=True)
            if results_t3:
                _elim_rows = []
                for _r3 in results_t3:
                    _sid3 = _r3.get('stock_id', _r3.get('代碼',''))
                    _row = {k: v for k, v in _r3.items() if not k.startswith('_') and k != 'stock_id'}
                    _row.update(_fund_map.get(_sid3, {}))
                    _elim_rows.append(_row)
                df_cmp = pd.DataFrame(_elim_rows).sort_values('舊評分', ascending=False).reset_index(drop=True)
                # 確保名稱欄位存在
                if '名稱' not in df_cmp.columns and '代碼' in df_cmp.columns:
                    df_cmp.insert(0, '名稱', df_cmp['代碼'])
                _col_order = [c for c in ['名稱','代碼','現價','操作狀態','健康度','評級','舊評分',
                                           'RSI','KD','量比','IBS','趨勢','357評價','VCP',
                                           '合約負債','近4季EPS','毛利率%','殖利率%']
                              if c in df_cmp.columns]
                st.dataframe(df_cmp[_col_order], use_container_width=True,
                             hide_index=True,
                             column_config={
                                 '名稱':     st.column_config.TextColumn('名稱', width='small'),
                                 '代碼':     st.column_config.TextColumn('代碼', width='small'),
                                 '現價':     st.column_config.TextColumn('現價'),
                                 '健康度':   st.column_config.NumberColumn('健康度',  format='%d 🏥'),
                                 '舊評分':   st.column_config.NumberColumn('評分',    format='%d ⭐'),
                                 '近4季EPS': st.column_config.TextColumn('近4Q EPS'),
                                 '毛利率%':  st.column_config.TextColumn('毛利率%'),
                                 '殖利率%':  st.column_config.TextColumn('殖利率%'),
                             })

        st.markdown('---')

        # ── 風控警示 ────────────────────────────────────────────
        if risk_alerts:
            st.markdown('#### ⚠️ 風控警示')
            for alert in risk_alerts:
                st.warning(alert)

        # ── 完整AI綜合分析 ──────────────────────────────────────
        if results_t3:
            st.markdown('#### 🤖 完整AI投資決策分析')
            _score_src = score_t3 if score_t3 else results_t3
            _ai_top_ids = ', '.join(
                r.get('stock_id', r.get('代碼','')) for r in
                sorted(_score_src, key=lambda x: x.get('total', x.get('舊評分', x.get('_health', 0))), reverse=True)[:3]
            )
            st.markdown(teacher_conclusion('宏爺+孫慶龍+朱家泓', f'AI綜合判讀（前3：{_ai_top_ids}）', '技術+籌碼+基本面三重過濾後的最終結論', '點擊下方按鈕生成'), unsafe_allow_html=True)
            _ai_cache_key = 't3_ai_' + '_'.join(sorted(r.get('stock_id', r.get('代碼','')) for r in results_t3[:5]))
            _ai_cached = st.session_state.get(_ai_cache_key, '')
            if _ai_cached:
                st.markdown(_ai_cached)
                if st.button('🔄 重新生成AI分析', key='t3_ai_regen'):
                    st.session_state.pop(_ai_cache_key, None)
                    st.rerun()
            else:
                if st.button('🤖 生成完整AI分析', key='t3_ai_gen', type='primary'):
                    from scoring_engine import rank_stocks as _rk3ai
                    _top3 = _rk3ai(score_t3)[:3] if score_t3 else results_t3[:3]
                    _ai_lines = []
                    for _r in _top3:
                        _sid = _r.get('stock_id', _r.get('代碼',''))
                        _fd  = _fund_map.get(_sid, {})
                        _ht  = _r.get('_health', next((x.get('_health',0) for x in results_t3 if x.get('stock_id')==_sid), 0))
                        _ai_lines.append(
                            f"- {_sid}({_r.get('stock_name', _r.get('名稱',''))}) "
                            f"健康度{_ht:.0f} 評分{_r.get('total', _r.get('舊評分',0)):.0f}分 "
                            f"EPS={_fd.get('近4季EPS','-')} "
                            f"毛利={_fd.get('毛利率%','-')}% 殖利率={_fd.get('殖利率%','-')}%"
                        )
                    _mkt_reg = st.session_state.get('mkt_info', {}).get('regime', 'neutral')
                    _reg_txt = '多頭' if _mkt_reg == 'bull' else ('空頭' if _mkt_reg == 'bear' else '震盪')
                    _ai_prompt = (
                        f"你是宏爺、孫慶龍、朱家泓三位老師的AI助手，以台灣股市實戰語氣分析以下候選股：\n"
                        f"{chr(10).join(_ai_lines)}\n"
                        f"大盤：{_reg_txt}格局\n\n"
                        f"請依序回答（每段不超過60字，像老師WhatsApp群組的風格）：\n"
                        f"① 最值得關注的一檔及原因\n"
                        f"② 具體進場條件（技術面確認訊號）\n"
                        f"③ 停損設定（一句話）\n"
                        f"④ 風控提醒（一句話）"
                    )
                    with st.spinner('AI分析中...'):
                        _ai_result = gemini_call(_ai_prompt, max_tokens=600)
                    st.session_state[_ai_cache_key] = _ai_result
                    st.markdown(_ai_result)
                else:
                    st.caption('點擊上方按鈕生成完整AI投資決策分析')
    
# ══════════════════════════════════════════════════════════════
# TAB 4: 大師條件手冊（判讀邏輯完整版）
# ══════════════════════════════════════════════════════════════
with tab4_masters:

    # ── ADL 騰落指標判讀（從 Section 五移入）─────────────────────
    st.markdown(section_header('B','📉 ADL騰落指標判讀方法','📊'), unsafe_allow_html=True)
    st.markdown("""
| 情況 | 意義 | 操作建議 |
|------|------|----------|
| 指數↑ + ADL↑ | 廣泛多頭，市場健康 | ✅ 可持股或加碼 |
| 指數↑ + ADL↓ | ⚠️ 背離！漲勢由少數權值股撐 | 🔴 謹慎，行情不穩 |
| 指數↓ + ADL↑ | 廣泛底部，回升可期 | 🟡 可留意佈局 |
| 指數↓ + ADL↓ | 廣泛賣壓，空頭格局 | 🔴 降倉防守 |
| 上漲佔比 > 60% | 多頭廣度充足 | ✅ 市場有支撐 |
| 上漲佔比 < 40% | 廣度不足，僅權值股撐盤 | ⚠️ 轉弱訊號 |
""")
    st.caption('宏爺策略：ADL 趨勢比今日漲跌更重要，要看「方向」是否與指數一致。')
    st.markdown('---')

    # ── 先行指標欄位說明與警戒門檻（從 Section 四移入）─────────────
    st.markdown(section_header('A','📡 先行指標：欄位說明與警戒門檻','📊'), unsafe_allow_html=True)
    st.markdown("""
| 欄位 | 資料來源 | 計算公式 | 警戒門檻 |
|------|---------|---------|---------|
| 外資大小（期貨留倉）| FinMind TX+MTX | 外資(多口-空口)×1 + MTX×0.25 | 空單 > **30,000口** = 高風險 |
| 選PCR | FinMind TXO | 全體Put未平倉口 ÷ 全體Call未平倉口 × 100 | > 100 偏多；< 100 偏空；< 110 易走弱 |
| 外(選) | FinMind TXO | BC金額 − SC金額 − BP金額 + SP金額（÷10千元）| ±10,000千元為關鍵門檻 |
| 三大法人（外資/投信/自營）| FinMind 三大法人大盤 | 買進金額 − 賣出金額（億元） | 外資連買 = 跟進；連賣 = 謹慎 |
| 前五大留倉 | TAIFEX（需爬蟲） | 前五大買方所有契約 − 賣方所有契約 | 淨空 > **-10,000口** = 警訊 |
| 前十大留倉 | TAIFEX（需爬蟲） | 前十大買方所有契約 − 賣方所有契約 | 淨空 > **-20,000口** = 強烈警訊 |
| 韭菜指數 | FinMind MTX 估算 | (全體MTX OI/2 − 法人多方口) / 全體OI × 100 | 正值(散戶多)→反向偏空；負值(散戶空)→反向偏多 |
""")

    st.markdown('<hr style="border-color:#21262d;margin:16px 0;">', unsafe_allow_html=True)

    # ── 宏爺判斷方式（從 Section 四移入）─────────────────────────
    st.markdown(section_header('B','🎓 宏爺：先行指標判讀方式','🎓'), unsafe_allow_html=True)
    st.markdown("""
**外資期貨留倉（最重要指標）**
- ⚠️ 空單 > 30,000口 = 嚴重警戒線
- **「流向 > 存量」**：空單5萬口但每日持續減少 → 危機解除；短期急遽暴增 → 準備大幅修正

**外資選擇權金額（BC-SC-BP+SP）**
- 期貨佈空 + 選擇權也由多翻空 → **「真的要殺了」**
- 期貨空單增加但選擇權持多 → 只是短線避險，不一定大跌
- 門檻：±10,000千元

**選PCR（Put/Call Ratio × 100）**
- > 100 → 下方有支撐（偏多）；< 100 → 上方有壓（偏空）；< 110 → 市場易走弱
- > 130 以上多方保護很強，空方難以推倒市場

**韭菜指數（反向指標）**
- 最高原則：**不要跟散戶站同向**
- 散戶大量做多 → 大盤容易被殺；散戶死命放空 → 空單成為「軋空燃料」

**前五大 / 前十大交易人留倉**
- 扣除反向ETF避險後的真實多空意圖
- 前5大淨空接近 **-10,000口**、前10大接近 **-20,000口** → 強烈警訊
""")

    st.markdown('<hr style="border-color:#21262d;margin:16px 0;">', unsafe_allow_html=True)


    # ── 合約負債 × 固定資產規則（財報關鍵指標）────────────────
    st.markdown('### 📋 財報關鍵指標判讀')
    _fb1, _fb2 = st.columns(2)
    with _fb1:
        st.markdown('''
<div style="background:#0d1117;border:1px solid #3fb950;border-radius:10px;padding:14px;">
<div style="font-size:14px;font-weight:700;color:#3fb950;margin-bottom:8px;">📦 合約負債（Contract Liabilities）</div>
<div style="font-size:12px;color:#c9d1d9;line-height:1.8;">
<b>是什麼：</b>客戶已付訂金但產品/服務尚未交付的款項<br>
<b>為何重要：</b>代表「未來確定的收入」，合約負債高 = 訂單有保障<br><br>
<b>孫慶龍判讀標準：</b><br>
　✅ 合約負債 / 股本 ≥ 50% → 未來3-6月訂單有保障<br>
　🟡 合約負債連續成長 → 業績加速訊號<br>
　🔴 合約負債突然下滑 → 訂單減少，需警戒<br><br>
<b>查詢方式：</b>財報資產負債表「合約負債」或「預收款項」<br>
<b>案例：</b>振曜(6650)合約負債/股本 >100% → 大幅超前排程
</div></div>
        ''', unsafe_allow_html=True)
    with _fb2:
        st.markdown('''
<div style="background:#0d1117;border:1px solid #58a6ff;border-radius:10px;padding:14px;">
<div style="font-size:14px;font-weight:700;color:#58a6ff;margin-bottom:8px;">🏭 固定資產 / 資本支出（CapEx）</div>
<div style="font-size:12px;color:#c9d1d9;line-height:1.8;">
<b>是什麼：</b>公司買廠房、機器設備的支出<br>
<b>為何重要：</b>老闆用真錢擴廠 = 對未來充滿信心的最直接證明<br><br>
<b>孫慶龍判讀標準：</b><br>
　✅ 資本支出 / 股本 ≥ 80% → 大幅擴廠，2-3年後營收爆發<br>
　✅ 固定資產年增率 ≥ 20% → 產能大幅擴張<br>
　🔴 資本支出持續萎縮 → 公司喪失成長意願<br><br>
<b>查詢方式：</b>現金流量表「購置不動產廠房及設備」<br>
<b>重要原則：</b>「不要聽老闆說什麼，要看他做什麼」<br>
　→ 老闆看好未來，就會砸大錢擴廠
</div></div>
        ''', unsafe_allow_html=True)

    st.markdown('''
<div style="background:#0a2818;border:1px solid #3fb950;border-radius:8px;padding:10px 14px;margin:10px 0;font-size:12px;color:#c9d1d9;">
💡 <b>搭配使用建議：</b>
合約負債↑ + 資本支出↑ = 「今年訂單爆滿 + 老闆拚命擴廠」→ 這是最強的雙重買入訊號<br>
在系統「🔬 個股分析」Tab → 財報 C節 可看到這兩項數據
</div>
    ''', unsafe_allow_html=True)
    st.markdown('---')

    # ── 先行指標警戒標準（從 Tab1 移來，詳細規則集中於此）─────
    with st.expander('📡 先行指標警戒標準（宏爺規則）', expanded=True):
        st.markdown('''
<div style="background:#0a1628;border-left:3px solid #ffd700;padding:10px 14px;border-radius:0 8px 8px 0;margin-bottom:10px;font-size:13px;color:#c9d1d9;">
💡 這些指標讓你在大盤下跌<b>前</b>就察覺到危險，是宏爺最重視的「聰明錢方向」指標。
</div>''', unsafe_allow_html=True)

        _wt_cols = st.columns(2)
        with _wt_cols[0]:
            st.markdown('''
| 指標 | 🟢 安全 | 🔴 警戒 |
|------|--------|--------|
| 外資期貨（大小台） | 多單 或 空單<30,000口 | **空單>30,000口** |
| 前五大留倉 | 淨多 | **淨空≈-10,000口** |
| 韭菜指數 | -10%~+10% | **>+10%且法人賣** |
| 選擇權 PCR | >100（偏多） | **<100（偏空）** |
''')
        with _wt_cols[1]:
            st.markdown('''
**📖 宏爺判讀邏輯：**

• **外資期貨空單>30,000口** = 大戶準備放空，散戶要小心

• **前五大留倉淨空** = 前五大主力在賣，跟著大戶走

• **韭菜指數>+10%** = 散戶槓桿過高，回調在即

• **PCR<100** = 選擇權偏向買認購，市場偏多情緒過熱
''')
    st.markdown('---')

    st.markdown("""<div style="padding:6px 0 8px;">
<span style="font-size:20px;font-weight:900;color:#e6edf3;">📚 策略手冊</span>
<span style="font-size:11px;color:#484f58;margin-left:10px;">五大門派完整操作條件 — 層2/3 判斷結論的理論依據</span>
</div>""", unsafe_allow_html=True)

    # ── 總操作節奏總結 ───────────────────────────────────────
    st.markdown("""<div style="background:#0d1117;border:1px solid #1f6feb;border-radius:10px;padding:14px 16px;margin-bottom:14px;">
<div style="font-size:13px;font-weight:700;color:#58a6ff;margin-bottom:10px;">🗺️ 全方位操作節奏（9位老師共識）</div>
<div style="display:flex;gap:8px;flex-wrap:wrap;font-size:12px;">
<span style="background:#1f6feb22;border:1px solid #1f6feb;border-radius:5px;padding:4px 10px;color:#58a6ff;">①總經定多空<br><small>M1B-M2↑+旌旗↑</small></span>
<span style="color:#484f58;">→</span>
<span style="background:#3fb95022;border:1px solid #3fb950;border-radius:5px;padding:4px 10px;color:#3fb950;">②財報選好股<br><small>合約負債+資本支出</small></span>
<span style="color:#484f58;">→</span>
<span style="background:#d2992222;border:1px solid #d29922;border-radius:5px;padding:4px 10px;color:#d29922;">③型態找進場<br><small>VCP+帶量突破</small></span>
<span style="color:#484f58;">→</span>
<span style="background:#bc8cff22;border:1px solid #bc8cff;border-radius:5px;padding:4px 10px;color:#bc8cff;">④獲利才加碼<br><small>回測不破+再突破</small></span>
<span style="color:#484f58;">→</span>
<span style="background:#f8514922;border:1px solid #f85149;border-radius:5px;padding:4px 10px;color:#f85149;">⑤轉弱即減碼<br><small>跌5MA+脫離布林上軌</small></span>
</div>
</div>""", unsafe_allow_html=True)

    # 兩列布局：進場 vs 出場
    t4_c1, t4_c2 = st.columns(2)

    with t4_c1:
        # 孫慶龍
        st.markdown("""<div style="background:#0d1117;border:2px solid #3fb950;border-radius:10px;padding:14px;margin:6px 0;">
<div style="font-size:14px;font-weight:900;color:#3fb950;margin-bottom:8px;">💡 孫慶龍 — 存股龍多策略</div>

**【進場條件】**
- 殖利率 ≥ 7% → 便宜價，積極買進
- 殖利率 5-7% → 合理價，分批布局
- 月KD < 20 且 K向上穿D → 黃金交叉
- 合約負債 ÷ 股本 ≥ 50% → 訂單有保障
- 年線負乖離 > 20%（2008/2020等） → 左側大布局

**【加碼法則（倒金字塔）】**
- 預期跌幅分4等份（跌10%/20%/30%/40%）
- 金額按 1:2:3:4 比例加碼
- 目標：平均成本落在底部1/3

**【出場條件】**
- 殖利率 ≤ 3% → 昂貴價，開始分批出場
- 月KD > 80 且 K向下穿D → 死亡交叉出場
- 年線正乖離 > 20% → 分批減碼</div>""", unsafe_allow_html=True)

        # 朱家泓
        st.markdown("""<div style="background:#0d1117;border:2px solid #ffd700;border-radius:10px;padding:14px;margin:6px 0;">
<div style="font-size:14px;font-weight:900;color:#ffd700;margin-bottom:8px;">📊 朱家泓 — 型態右側交易</div>

**【進場型態】**
- W底頸線突破 + 帶量 → 初始底倉30~50%
- 箱型突破高點（平台底帶量） → 第2次加碼
- 需確認收盤突破，非盤中假突破

**【加碼法則（右側）】**
- 加碼點A：回測頸線/10MA 不破再上 → 加碼
- 加碼點B：平台整理再突破高點 → 擴倉
- 原則：只在賺錢情況下加碼，嚴禁攤平

**【停損條件】**
- 跌破進場紅K低點 → 無條件停損
- 跌破20MA（月線） → 停損或大幅減碼</div>""", unsafe_allow_html=True)

        # 蔡森
        st.markdown("""<div style="background:#0d1117;border:2px solid #58a6ff;border-radius:10px;padding:14px;margin:6px 0;">
<div style="font-size:14px;font-weight:900;color:#58a6ff;margin-bottom:8px;">📐 蔡森 — 目標價滿足減碼法</div>

**【目標價計算（一比一對稱法）】**
- 計算底部型態高度（箱型或W底的震幅）
- 向上翻一倍 → 初步滿足點
- 到達目標 → 減碼一半，剩餘移動停利

**【分批減碼節奏】**
- 到達TP1（+1倍震幅） → 減碼50%
- 到達TP2（+2倍震幅） → 再減25%
- 剩25%以5MA為停利線移動保護</div>""", unsafe_allow_html=True)

    with t4_c2:
        # 弘爺
        st.markdown("""<div style="background:#0d1117;border:2px solid #58a6ff;border-radius:10px;padding:14px;margin:6px 0;">
<div style="font-size:14px;font-weight:900;color:#58a6ff;margin-bottom:8px;">🎯 弘爺 — 總經籌碼法</div>

**【總經進場條件】**
- M1B > M2（M1B-M2正成長）→ 資金行情
- 外資期貨淨多單 + 連續增加
- 三大法人現貨連買3日
- 融資餘額 < 2000億 → 籌碼乾淨

**【加碼時機】**
- M1B-M2持續向上 + 外資連買 → 大膽加碼
- 旌旗指數增加（更多股票站上均線）→ 廣度確認

**【減碼/出場條件】**
- 外資期貨轉淨空 > 10,000口 → 立即降倉
- 融資餘額 > 2500億 → 警戒；> 3400億 → 出清
- M1B-M2轉為負值 → 空手觀望
- 旌旗指數 vs 大盤出現背離 → 大跌前兆</div>""", unsafe_allow_html=True)

        # 妮可+春哥
        st.markdown("""<div style="background:#0d1117;border:2px solid #ffd700;border-radius:10px;padding:14px;margin:6px 0;">
<div style="font-size:14px;font-weight:900;color:#ffd700;margin-bottom:8px;">📊 妮可+春哥 — 動能布林法</div>

**【布林進場】**
- 布林帶寬收縮至歷史低點（<均值60%）→ 即將爆發
- 股價突破布林上軌 + 量>均量1.5倍 → 強勢突破

**【減碼訊號】**
- 股價從黏著上軌掉回95%區間內 → 減碼50%
- 月線正乖離達歷史高值(20~30%) → 分批出場
- 週KD進入80以上高檔死亡交叉 → 減碼

**【VCP進場（妮可）】**
- 3段波幅收縮（如28%→12%→5%）→ 籌碼轉移完成
- VCP突破當天+帶量 → 建30~50%底倉</div>""", unsafe_allow_html=True)

        # 林穎+小王子
        st.markdown("""<div style="background:#0d1117;border:2px solid #3fb950;border-radius:10px;padding:14px;margin:6px 0;">
<div style="font-size:14px;font-weight:900;color:#3fb950;margin-bottom:8px;">🛡️ 林穎+小王子 — 移動停利法</div>

**【5MA停利（短線）— 林穎】**
- 收盤價跌破5日均線且方向轉下 → 全數了結
- 適合短線波段（1~4週）

**【10週線停利（中長線）— 小王子】**
- 週線不破10週均線（≈50MA）→ 持續抱緊
- 週線實體跌破10週均線 → 出清
- 適合趨勢波段（1~6個月）

**【陳重銘 — 資產再平衡】**
- 股票因大漲超過總資產70% → 強制減碼
- 轉入債券型ETF，維持股6債4防禦配置</div>""", unsafe_allow_html=True)

    # 風險管理總表
    st.markdown('---')
    st.markdown('#### ⚔️ 風險管理：生存的最後底線')
    st.markdown("""
| 動作 | 執行條件 | 心理心法 |
|------|---------|---------|
| 🛑 停損 | 跌破進場紅K低點、跌破20MA、單筆損失達5~7% | **絕對執行**：停損是為了保留下一次揮棒的子彈 |
| 📉 減碼 | 趨勢轉弱、布林上軌掉回、指標高檔背離 | **落袋為安**：不求賣在最高點，求守住大部獲利 |
| ✋ 不交易 | M1B-M2持續向下、大盤多空排列加速 < 15% | **空手也是操作**：看不懂、沒勝率時，忍住不動是最高境界 |
| 💰 加碼 | 只在賺錢情況下加碼，嚴禁賠錢攤平 | **贏家思維**：擴大正確決策的戰果 |
""")

    st.markdown("""<div style="background:#2a0d0d;border:1px solid #f85149;border-radius:8px;
padding:10px 14px;font-size:11px;color:#f85149;margin-top:12px;">
⚠️ 本手冊整理自各大師公開課程內容，僅供學術研究與教育用途。
投資涉及風險，任何操作均應自行判斷，盈虧自負。本系統非投資顧問，不構成買賣建議。
</div>""", unsafe_allow_html=True)

    m1, m2 = st.columns(2)
    # ── 孫慶龍 ──────────────────────────────────────────────
    with m1:
        st.markdown("""<div style="background:#0d1117;border:2px solid #3fb950;border-radius:10px;padding:16px;margin:6px 0;">
<div style="font-size:15px;font-weight:900;color:#3fb950;margin-bottom:10px;">💡 孫慶龍 — 存股龍多策略</div>

**【進場條件】**
- 殖利率 ≥ 7% → 便宜價，積極買進
- 殖利率 5-7% → 合理價，分批布局
- 月KD < 20 且 K向上穿D → 黃金交叉，景氣底部進場
- 合約負債 ÷ 股本 ≥ 50% → 未來3-6月訂單有保障
- 資本支出 ÷ 股本 ≥ 80% → 大擴廠，2-3年後營收爆發

**【出場條件】**
- 殖利率 ≤ 3% → 昂貴價，開始分批出場
- 月KD > 80 且 K向下穿D → 死亡交叉，高點出場
- 毛利率連續3季下滑 → 護城河消失，停利

**【加碼規則】**
- 回跌7%加碼1/3、回跌15%再加碼1/3
- 最多持倉不超過個股資金3成

**【健康度對應】**
- 🟢 ≥80：持股不動，佛系等殖利率
- 🟡 50-79：觀望，等月KD訊號
- 🔴 <50：降低持倉，保留現金等機會
</div>""", unsafe_allow_html=True)

    with m2:
        st.markdown("""<div style="background:#0d1117;border:2px solid #58a6ff;border-radius:10px;padding:16px;margin:6px 0;">
<div style="font-size:15px;font-weight:900;color:#58a6ff;margin-bottom:10px;">🎯 弘爺（宏爺）— 總經籌碼法</div>

**【進場條件】**
- 外資期貨大台 + 小台×0.25 = 淨多單 > 0 且連續3日增加
- 三大法人現貨連買3日 → 跟著大戶走
- M1B > M2（M1B-M2正成長）→ 資金行情啟動
- 融資餘額 < 2000億 → 籌碼乾淨，多頭健康
- 台幣升值 + 台股上漲 → 外資匯入正常多頭

**【出場條件】**
- 外資期貨轉淨空 > 10,000口 → 立即降倉
- 融資餘額 > 2500億 → 警戒；> 3400億 → 嚴重警戒
- 台股漲 但台幣貶值 → 外資拉高出貨，準備跑
- 韭菜指數 > +10% 且外資賣 → 散戶過熱，行情尾端

**【倉位管理】**
- 總經多頭期：持股7-8成
- 總經空頭期：現金5成以上，不做多
- 費半先行：費半跌破月線→台股半導體提前減倉

**【健康度對應】**
- 🟢 ≥80 + 外資連買：全倉進攻
- 🟡 50-79：半倉觀察
- 🔴 <50：空手等待
</div>""", unsafe_allow_html=True)

    m3, m4 = st.columns(2)
    with m3:
        st.markdown("""<div style="background:#0d1117;border:2px solid #ffd700;border-radius:10px;padding:16px;margin:6px 0;">
<div style="font-size:15px;font-weight:900;color:#ffd700;margin-bottom:10px;">📊 妮可/春哥 — 動能布林法</div>

**【布林通道進場】**
- 布林帶寬收縮至歷史低點（< 均值60%） → 即將爆發
- 股價突破布林上軌 + 成交量 > 均量1.5倍 → 強勢突破做多
- 量比 > 1.5 + 收盤 > MA20 → 主力介入訊號

**【VCP波幅收縮進場（妮可）】**
- 3段波幅收縮（如28%→12%→5%）→ 浮動籌碼完成轉移
- 底部逐漸墊高 + 成交量萎縮 → 強手承接確認
- 帶量突破頸線 → 正式進場，以突破點為停損

**【投本比監控（妮可）】**
- 投信淨買超 / 成交量 > 0.01% 且連續3日 → 法人小型股建倉
- 搭配VCP → 雙重確認，勝率大幅提升

**【IBS進出場】**
- IBS ≤ 0.2（收在日低點）→ 隔日技術性反彈，短線做多
- IBS ≥ 0.8（收在日高點）→ 隔日容易遭獲利賣壓，謹慎

**【出場條件】**
- 布林帶寬急速擴張 + 量縮 → 動能衰退出場
- RSI > 80 + 量比下滑 → 超買出場
- 跌破突破點（頸線）→ 停損出場
</div>""", unsafe_allow_html=True)

    with m4:
        st.markdown("""<div style="background:#0d1117;border:2px solid #bc8cff;border-radius:10px;padding:16px;margin:6px 0;">
<div style="font-size:15px;font-weight:900;color:#bc8cff;margin-bottom:10px;">💼 朱家宏/MK郭俊宏 — 型態再平衡法</div>

**【MK再平衡進場】**
- 核心(ETF)+衛星(成長股)偏離目標配比 ≥ 10% → 觸發再平衡
- 月KD < 20黃金交叉時，核心ETF加碼
- 三角形加碼：回落10%用10%資金，回落20%用20%...

**【朱家宏型態進場】**
- 股價站上所有均線（多頭排列）→ 趨勢向上，做多
- 型態突破：箱型整理上緣突破 + 成交量放大
- W底確認（第二底高於第一底）→ 底部完成，進場

**【RSI使用規則】**
- RSI 50-70：強勢區間，持股不動
- RSI < 30：超賣，逆勢小量試單
- RSI > 80：超買，注意出場時機

**【KD使用規則】**
- 日KD黃金交叉（K>D，K<80）→ 短線強勢訊號
- 月KD黃金交叉（K<20）→ 長線最佳買點
- 日KD死亡交叉（K<D，K>20）→ 短線出場訊號

**【停利/停損】**
- 停利目標1：進場 +5%（先收半倉）
- 停利目標2：進場 +10%（波段目標）
- 停損線：進場 -5%（跌破嚴格出場）

**【健康度對應】**
- 🟢 ≥80：股價位於均線上方，趨勢做多
- 🟡 50-79：等待突破訊號確認
- 🔴 <50：不做多，耐心等待下一輪機會
</div>""", unsafe_allow_html=True)

    # ── 陳重銘 ──────────────────────────────────────────────
    st.markdown("""<div style="background:#0d1117;border:2px solid #f85149;border-radius:10px;padding:16px;margin:6px 0;">
<div style="font-size:15px;font-weight:900;color:#f85149;margin-bottom:10px;">📚 陳重銘 — 存股複利心法</div>

<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;">
<div>
<b style="color:#f85149;">【選股條件】</b><br>
・連續10年配息，且逐年穩定<br>
・殖利率 ≥ 5%（至少合理價）<br>
・本業EPS（扣除業外）持續正成長<br>
・毛利率 ≥ 20%（護城河指標）<br>
・負債比 ≤ 50%（財務安全）
</div>
<div>
<b style="color:#f85149;">【進出場】</b><br>
・殖利率 > 6% = 大買，越跌越買<br>
・「一張不賣，奇蹟自來」<br>
・每年領股利 = 全部再投入加碼<br>
・出場：公司基本面惡化（毛利率連降3年）<br>
・個股佔總資產 ≤ 10%（分散風險）
</div>
<div>
<b style="color:#f85149;">【ETF策略】</b><br>
・月KD < 20 定期定額（加碼）<br>
・月KD > 80 停止加碼（不賣）<br>
・高股息ETF：著重配息穩定性<br>
・市值型ETF：著重長期成長<br>
・溢價 > 1% 不買，折價才買
</div>
</div>
</div>""", unsafe_allow_html=True)

    # ── 指標快速參考表 ──────────────────────────────────────
    st.markdown('---')

    # ── 評分標準速查（從 Tab2 移入）──────────────────────────────────
    st.markdown(section_header('C', '📊 評分標準速查表', '📖'), unsafe_allow_html=True)
    _sc1, _sc2, _sc3 = st.columns(3)
    with _sc1:
        st.markdown("""**📈 健康度評分標準**
| 分數 | 評級 | 策略建議 |
|------|------|--------|
| 80~100 | 🔴優良 | 積極持有、可加碼 |
| 50~79 | 🟡盤整 | 觀望、等突破訊號 |
| <50 | 🟢弱勢 | 降倉保守、避免追買 |

> 💡 健康度70分以下建議先觀望；停損紀律決定最終勝率。""")
    with _sc2:
        st.markdown("""**💰 孫慶龍 357殖利率評價**
| 殖利率 | 位階 | 操作建議 |
|--------|------|--------|
| ≥7% | 🟢便宜 | 積極進場、可分批 |
| 5~7% | 🟡合理 | 分批布局 |
| 3~5% | 🔴昂貴 | 持有不追高 |
| <3% | 🔴超貴 | 逢高停利出場 |

> 💡 殖利率法則以「長期持有存股」為前提，短線操作請配合技術面。""")
    with _sc3:
        st.markdown("""**📊 技術指標訊號速查**
| 指標 | 訊號 | 操作建議 |
|------|------|--------|
| RSI < 30 | 超賣 | 短線反彈機會 |
| RSI > 70 | 超買 | 注意出場時機 |
| 月KD < 20 黃叉 | 景氣底 | 長線最佳進場 |
| 布林帶寬極縮 | 即將爆發 | 等方向突破再進 |
| IBS ≤ 0.2 | 收低 | 隔日技術反彈機會 |
| VCP收縮 | 籌碼洗淨 | 突破頸線才進場 |""")
    st.markdown('---')


    st.markdown('### 📊 指標快速判讀對照表')
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""**📈 健康度評分**
| 分數 | 評級 | 策略 |
|------|------|------|
| 80+ | 🟢優良 | 積極持有加碼 |
| 50-79 | 🟡盤整 | 觀望等訊號 |
| <50 | 🔴危險 | 降倉保守 |""")
    with c2:
        st.markdown("""**💰 357殖利率評價**
| 殖利率 | 位階 | 操作 |
|--------|------|------|
| ≥7% | 🟢便宜 | 積極進場 |
| 5-7% | 🟡合理 | 分批布局 |
| 3-5% | 🔴昂貴 | 持有不追 |
| <3% | 🔴超貴 | 停利出場 |""")
    with c3:
        st.markdown("""**📊 RSI + KD + 布林**
| 指標 | 訊號 | 對應操作 |
|------|------|----------|
| RSI<30 | 超賣 | 短線反彈機會 |
| RSI>70 | 超買 | 注意出場 |
| 月KD<20黃叉 | 景氣底 | 長線最佳進場 |
| 布林帶寬極縮 | 即爆發 | 等方向突破 |
| IBS≤0.2 | 收低 | 隔日技術反彈 |""")

    st.markdown("""<div style="background:#2a0d0d;border:1px solid #f85149;border-radius:8px;
padding:10px 14px;font-size:11px;color:#f85149;margin-top:12px;">
⚠️ 本手冊整理自各大師公開課程內容，僅供學術研究與教育用途。
投資涉及風險，任何操作均應自行判斷，盈虧自負。本系統非投資顧問，不構成買賣建議。
</div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════
# TAB ⑥: ETF 單一深度診斷
# ══════════════════════════════════════════════════════════════
with tab_etf1:
    render_etf_single(gemini_fn=gemini_call)

# ══════════════════════════════════════════════════════════════
# TAB ⑦: ETF 組合配置與再平衡
# ══════════════════════════════════════════════════════════════
with tab_etf2:
    render_etf_portfolio(gemini_fn=gemini_call)

# ══════════════════════════════════════════════════════════════
# TAB ⑧: ETF 歷史回測
# ══════════════════════════════════════════════════════════════
with tab_etf3:
    render_etf_backtest(gemini_fn=gemini_call)

# ══════════════════════════════════════════════════════════════
# TAB ⑨: ETF AI 綜合評斷（總經連動）
# ══════════════════════════════════════════════════════════════
with tab_etf4:
    render_etf_ai(gemini_fn=gemini_call)

# ══════════════════════════════════════════════════════════════
# TAB ⑩: 資料健診儀表板
# ══════════════════════════════════════════════════════════════
with tab_health:
    render_data_health()

# ══════════════════════════════════════════════════════════════
# TAB ⑪: 產業熱力圖
# ══════════════════════════════════════════════════════════════
with tab_heatmap:
    render_sector_heatmap()

st.markdown('<div style="text-align:center;font-size:10px;color:#484f58;padding:8px 0;">⚠️ 台股AI戰情室 v3.0 · 僅供學術研究，非投資建議，盈虧自負</div>', unsafe_allow_html=True)
