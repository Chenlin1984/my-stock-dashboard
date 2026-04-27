"""
ETF AI 儀表板核心引擎 v1.0
Tab ⑥ 單一 ETF 深度診斷 | Tab ⑦ 組合配置 | Tab ⑧ 回測 | Tab ⑨ AI 綜合評斷
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import yfinance as yf
from datetime import timedelta
from unified_decision import render_unified_decision
from daily_checklist import calc_stats

def _fetch_news_for(ticker: str, name: str = "", n: int = 4) -> str:
    """抓取個股/ETF 相關新聞，回傳格式化字串。失敗時回傳空字串。"""
    try:
        import feedparser as _fp, html as _h, re as _re2
    except ImportError:
        return ""
    _q = f"{ticker} {name}".strip()
    _feeds = [
        f'https://news.google.com/rss/search?q={_q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant',
        f'https://news.google.com/rss/search?q=Taiwan+ETF+{ticker}&hl=en-US&gl=US&ceid=US:en',
    ]
    _out = []
    for _url in _feeds:
        try:
            for _e in _fp.parse(_url).entries:
                _t = _h.unescape(_e.get('title', '')).strip()
                _p = str(_e.get('published', ''))[:10]
                if _t:
                    _out.append(f'- {_t}（{_p}）')
                if len(_out) >= n:
                    break
        except Exception:
            pass
        if len(_out) >= n:
            break
    return '\n'.join(_out[:n]) if _out else '（暫無相關新聞）'


# ── 總經連動配置建議表 ────────────────────────────────────────
MACRO_ALLOC = {
    'bull':    {'股票型ETF': 70, '債券型ETF': 15, '貨幣/現金': 15},
    'neutral': {'股票型ETF': 50, '債券型ETF': 30, '貨幣/現金': 20},
    'bear':    {'股票型ETF': 20, '債券型ETF': 50, '貨幣/現金': 30},
}
MACRO_DESC = {
    'bull':    '🟢 多頭市場：加大股票型ETF比重，可佈局成長型/科技型ETF',
    'neutral': '🟡 中性市場：股債平衡，降低單一類型集中度',
    'bear':    '🔴 空頭市場：大幅降低股票曝險，增加投資級債券ETF + 現金',
}

# ═══════════════════════════════════════════════════════════════
# 快取資料層
# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600)
def fetch_etf_price(ticker: str, period: str = '5y') -> pd.DataFrame:
    """取得 ETF 歷史價格（auto_adjust=True 還原權息）"""
    try:
        df = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df.ffill()
    except Exception as e:
        st.error(f'❌ 無法取得 {ticker} 價格：{e}')
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_etf_dividends(ticker: str) -> pd.Series:
    """取得 ETF 歷史配息"""
    try:
        divs = yf.Ticker(ticker).dividends
        if divs.empty:
            return pd.Series(dtype=float)
        divs.index = pd.to_datetime(divs.index).tz_localize(None)
        return divs
    except Exception:
        return pd.Series(dtype=float)

@st.cache_data(ttl=3600)
def fetch_etf_info(ticker: str) -> dict:
    """取得 ETF 基本資訊（費用率/Beta/AUM）"""
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}

# ═══════════════════════════════════════════════════════════════
# 計算函式
# ═══════════════════════════════════════════════════════════════

def calc_current_yield(df: pd.DataFrame, divs: pd.Series) -> float:
    """近12個月現金殖利率(%)"""
    if df.empty or divs.empty:
        return 0.0
    try:
        cutoff = df.index[-1] - timedelta(days=365)
        annual_div = float(divs[divs.index >= cutoff].sum())
        price = float(df['Close'].iloc[-1])
        return round(annual_div / price * 100, 2) if price > 0 else 0.0
    except Exception:
        return 0.0

def calc_total_return_1y(df: pd.DataFrame, divs: pd.Series) -> float:
    """近1年含息總報酬率(%)"""
    if df.empty:
        return 0.0
    try:
        cutoff = df.index[-1] - timedelta(days=365)
        df_1y = df[df.index >= cutoff]
        if len(df_1y) < 2:
            return 0.0
        p_start = float(df_1y['Close'].iloc[0])
        p_end   = float(df_1y['Close'].iloc[-1])
        div_sum = float(divs[divs.index >= cutoff].sum()) if not divs.empty else 0.0
        return round((p_end - p_start + div_sum) / p_start * 100, 2)
    except Exception:
        return 0.0

def calc_avg_yield(df: pd.DataFrame, divs: pd.Series, years: int = 5) -> float:
    """近N年平均殖利率（孫慶龍7%公式）"""
    if df.empty or divs.empty:
        return 0.0
    try:
        now = df.index[-1]
        result = []
        for y in range(years):
            y_start = now - timedelta(days=365 * (y + 1))
            y_end   = now - timedelta(days=365 * y)
            y_div   = float(divs[(divs.index >= y_start) & (divs.index < y_end)].sum())
            df_y    = df[(df.index >= y_start) & (df.index < y_end)]
            if df_y.empty or y_div <= 0:
                continue
            avg_p = float(df_y['Close'].mean())
            if avg_p > 0:
                result.append(y_div / avg_p * 100)
        return round(sum(result) / len(result), 2) if result else 0.0
    except Exception:
        return 0.0

def check_vcp_signal(df: pd.DataFrame) -> dict:
    """春哥 VCP 波幅收縮偵測"""
    r = {'signal': False, 'above_ma50': False, 'above_ma200': False,
         'vol_confirm': False, 'weekly_ranges': [], 'stop_loss': None}
    if df is None or len(df) < 210:
        return r
    try:
        close  = df['Close']
        last_c = float(close.iloc[-1])
        ma50   = float(close.rolling(50).mean().iloc[-1])
        ma200  = float(close.rolling(200).mean().iloc[-1])
        r['above_ma50']  = last_c > ma50
        r['above_ma200'] = last_c > ma200
        r['stop_loss']   = round(last_c * 0.92, 2)

        # 週K波幅（近5週）
        df_w = df.resample('W').agg({'High':'max','Low':'min',
                                       'Close':'last','Volume':'sum'}).dropna()
        if len(df_w) >= 6:
            ranges = []
            for i in range(-5, 0):
                row = df_w.iloc[i]
                mid = (float(row['High']) + float(row['Low'])) / 2
                if mid > 0:
                    ranges.append(round((float(row['High']) - float(row['Low'])) / mid * 100, 1))
            r['weekly_ranges'] = ranges
            if len(ranges) >= 5:
                early_avg = sum(ranges[:2]) / 2
                late_avg  = sum(ranges[-2:]) / 2
                shrinking = late_avg < early_avg * 0.6
                vol_ma50  = float(df['Volume'].rolling(50).mean().iloc[-1])
                vol_now   = float(df['Volume'].iloc[-1])
                r['vol_confirm'] = vol_now > vol_ma50
                r['signal'] = (r['above_ma50'] and r['above_ma200']
                                and shrinking and r['vol_confirm'])
    except Exception:
        pass
    return r

@st.cache_data(ttl=7200, show_spinner=False)
def fetch_etf_nav_history(ticker: str, days: int = 35, ver: int = 3) -> "pd.DataFrame":
    """ETF 歷史淨值及折溢價（最近 N 個交易日）
    資料來源優先順序：
      1. FinMind TaiwanETFNetAssetValue（批次，有/無 token 皆可）
      2. TWSE OpenAPI v1/ETF/TaiwanStockPremiumDiscountRatio（僅最新一日）
    回傳欄位：date / price / nav / premium / premium_pct
    """
    import os, datetime as _dt, requests as _rq_etfnav
    import pandas as _pd_etfnav
    code = ticker.replace('.TW', '').replace('.TWO', '')
    token = os.environ.get('FINMIND_TOKEN', '')
    start = (_dt.date.today() - _dt.timedelta(days=days + 10)).strftime('%Y-%m-%d')
    _df_stale = None   # path 4: stale FinMind fallback
    _days_stale = 999

    # ── 1. FinMind ETF NAV（試兩個 dataset 名稱 + 多種欄位名稱）───────────
    for _ds1 in ['TaiwanETFNetAssetValue', 'TaiwanStockETFNAV']:
        try:
            _p = {'dataset': _ds1, 'data_id': code, 'start_date': start}
            if token: _p['token'] = token
            _r = _rq_etfnav.get('https://api.finmindtrade.com/api/v4/data', params=_p,
                                  headers={'Authorization': f'Bearer {token}'} if token else {},
                                  timeout=15)
            _j = _r.json()
            _jstatus = _j.get('status')
            _jdata   = _j.get('data')
            if _jstatus == 200 and _jdata:
                _df = _pd_etfnav.DataFrame(_jdata)
                # 自動偵測 NAV 欄位名稱（FinMind 兩個版本欄位名不同）
                _nav_field = next((f for f in ['nav', 'base_unit_net_value', 'NavPrice', 'netAssetValue']
                                   if f in _df.columns), None)
                if _nav_field is None:
                    print(f'[ETF NAV] {code} {_ds1}: 找不到 NAV 欄位，現有={list(_df.columns)}')
                    continue
                _df['date'] = _pd_etfnav.to_datetime(_df['date']).dt.date
                _df['nav']  = _pd_etfnav.to_numeric(_df[_nav_field], errors='coerce')
                _df = _df[_df['nav'].notna() & (_df['nav'] > 0)].sort_values('date')
                if _df.empty:
                    print(f'[ETF NAV] {code} {_ds1}: 所有 nav 欄位為空/NaN，跳過')
                    continue
                _latest_d   = _df['date'].iloc[-1]
                _days_stale = (_dt.date.today() - _latest_d).days
                _df_stale   = _df[['date', 'nav']]   # 保留，供 path 4 備援
                print(f'[ETF NAV] {code} {_ds1}(field={_nav_field}): {len(_df)} 筆, 最新={_latest_d}, 距今={_days_stale}d')
                if _days_stale <= 7:           # 7天內視為新鮮，直接回傳
                    return _df_stale
                print(f'[ETF NAV] {_ds1} {code} 資料過舊({_days_stale}d)，改用 TWSE OpenAPI')
                break   # 找到資料就不再嘗試第二個 dataset
            else:
                _msg = str(_j.get('msg', ''))[:80]
                print(f'[ETF NAV] FinMind {_ds1} {code}: status={_jstatus} data_len={len(_jdata) if _jdata else 0} msg={_msg}')
        except Exception as _e1:
            print(f'[ETF NAV] FinMind {_ds1} {code}: {_e1}')

    # ── 2. TWSE OpenAPI — 直讀同日 NAV + 市價 + 折溢價率(%) ──────────────
    # 端點A：TaiwanStockPremiumDiscountRatio（含折溢價%）
    # 端點B：TaiwanStockNetValue（NAV-only，無收盤價，由 calc_premium_discount Path B 配 yfinance 收盤）
    for _ep2 in [
        'https://openapi.twse.com.tw/v1/ETF/TaiwanStockPremiumDiscountRatio',
        'https://openapi.twse.com.tw/v1/ETF/TaiwanStockNetValue',
    ]:
        try:
            _r2 = _rq_etfnav.get(
                _ep2,
                headers={'Accept': 'application/json', 'User-Agent': 'Mozilla/5.0'},
                timeout=10, verify=False)
            for _row in _r2.json():
                if str(_row.get('證券代號', '')).strip() == code:
                    # 淨值欄位（多種可能的 key）
                    for _nk in ['單位淨值', '淨值', 'NetAssetValue', 'nav']:
                        _nv = str(_row.get(_nk, '')).replace(',', '').strip()
                        if _nv:
                            try: _nav2 = float(_nv); break
                            except: pass
                    else:
                        _nav2 = 0.0
                    _price2 = 0.0
                    for _pk in ['收盤價', 'ClosingPrice', 'close']:
                        _pv2 = str(_row.get(_pk, '')).replace(',', '').strip()
                        if _pv2:
                            try: _price2 = float(_pv2); break
                            except: pass
                    # 折溢價率（直接欄位優先）
                    _prem_key = next((k for k in _row if '折溢價' in str(k)), None)
                    _prem2 = None
                    if _prem_key:
                        try: _prem2 = float(str(_row[_prem_key]).replace('%', '').replace(',', '') or 0)
                        except: pass
                    if _prem2 is None and _nav2 > 0 and _price2 > 0:
                        _prem2 = round((_price2 - _nav2) / _nav2 * 100, 2)

                    if _nav2 > 0:
                        _row_out = {'date': _dt.date.today(), 'nav': _nav2}
                        if _price2 > 0:
                            _row_out['price'] = _price2
                        if _prem2 is not None:
                            _row_out['premium_pct'] = _prem2
                        print(f'[ETF NAV] {code} TWSE({_ep2.split("/")[-1]}): '
                              f'nav={_nav2} price={_price2} prem={_prem2}%')
                        return _pd_etfnav.DataFrame([_row_out])
        except Exception as _e2:
            print(f'[ETF NAV] TWSE {_ep2.split("/")[-1]} {code}: {_e2}')

    # ── 3. MoneyDJ 爬蟲（BeautifulSoup，不需 token）──────────────────────
    try:
        from bs4 import BeautifulSoup as _BS4
        _hdrs_mdj = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8',
            'Referer': 'https://www.moneydj.com/',
        }
        _url_mdj = f'https://www.moneydj.com/ETF/X/Basic/Basic0004.xdjhtm?etfid={code}'
        # 優先用 curl_cffi 模擬 Chrome TLS 指紋，繞過反爬蟲；失敗再降級 requests
        try:
            from curl_cffi import requests as _cffi_req
            _r_mdj = _cffi_req.get(_url_mdj, impersonate='chrome124', timeout=12)
        except Exception:
            _r_mdj = _rq_etfnav.get(_url_mdj, headers=_hdrs_mdj, timeout=12, verify=False)
        if _r_mdj.status_code == 200:
            _soup = _BS4(_r_mdj.text, 'lxml')
            _nav_mdj = None
            # 策略1：找含「淨值」的 th/td，取下一格數字
            for _th in _soup.find_all(['th', 'td', 'span', 'div', 'dt']):
                _t = _th.get_text(strip=True)
                if ('淨值' in _t or 'NAV' in _t) and len(_t) < 20:
                    _td = _th.find_next_sibling()
                    if _td:
                        try:
                            _nav_mdj = float(_td.get_text(strip=True).replace(',', ''))
                            if _nav_mdj > 0:
                                break
                        except Exception:
                            pass
            # 策略2：regex 直接掃 HTML
            if not _nav_mdj:
                import re as _re_mdj
                _m = _re_mdj.search(r'(?:淨值|NAV)[^\d]{0,20}?(\d{1,5}\.\d{2,6})', _r_mdj.text)
                if _m:
                    try: _nav_mdj = float(_m.group(1))
                    except Exception: pass
            if _nav_mdj and _nav_mdj > 0:
                print(f'[ETF NAV] MoneyDJ {code}: nav={_nav_mdj}')
                return _pd_etfnav.DataFrame([{'date': _dt.date.today(), 'nav': _nav_mdj}])
            else:
                print(f'[ETF NAV] MoneyDJ {code}: HTTP {_r_mdj.status_code} 找不到淨值')
        else:
            print(f'[ETF NAV] MoneyDJ {code}: HTTP {_r_mdj.status_code}')
    except Exception as _e_mdj:
        print(f'[ETF NAV] MoneyDJ {code}: {_e_mdj}')

    # ── 4. yfinance ETF info.navPrice（加限速 retry）──────────────────────
    import time as _t3
    for _sfx3 in ('.TW', '.TWO'):
        for _retry3 in range(3):
            try:
                import yfinance as _yf3
                _tk3 = _yf3.Ticker(f'{code}{_sfx3}')
                _info3 = _tk3.info
                _nav3 = _info3.get('navPrice') or _info3.get('regularMarketNAV')
                if _nav3 and float(_nav3) > 0:
                    print(f'[ETF NAV] yfinance {code}{_sfx3}: navPrice={_nav3}')
                    return _pd_etfnav.DataFrame([{'date': _dt.date.today(), 'nav': float(_nav3)}])
                break  # 沒資料，不 retry
            except Exception as _e3:
                _e3s = str(_e3)
                if ('Too Many Requests' in _e3s or 'Rate' in _e3s) and _retry3 < 2:
                    _t3.sleep(2 + _retry3 * 2)  # 2s, 4s
                    print(f'[ETF NAV] yfinance {code}{_sfx3}: 限速 retry {_retry3+1}/3')
                    continue
                print(f'[ETF NAV] yfinance {code}{_sfx3}: {_e3}')
                break

    # ── 4. 過舊 FinMind 資料備援（比顯示 N/A 好）──────────────────────────
    if _df_stale is not None and not _df_stale.empty:
        print(f'[ETF NAV] {code} path4: 使用過舊FinMind資料({_days_stale}d)備援')
        return _df_stale

    return _pd_etfnav.DataFrame()

def calc_premium_discount(info: dict, df: "pd.DataFrame", ticker: str = '') -> dict:
    """折溢價率 = (市價 - 淨值) / 淨值 × 100
    核心原則：NAV 與市價必須來自同一日，避免跨來源日期錯位。
    資料來源：1. TWSE OpenAPI 直讀（同日 NAV+市價+折溢價率）
              2. FinMind NAV history + df 同日 inner join（精確日期配對）
              3. yfinance info navPrice
    """
    import pandas as _pd_prem
    try:
        if ticker:
            _nav_hist = fetch_etf_nav_history(ticker, days=10)
            if not _nav_hist.empty and 'nav' in _nav_hist.columns:
                _last = _nav_hist.iloc[-1]

                # ── 路徑A：TWSE 已含同日折溢價率，直接使用 ──
                if 'premium_pct' in _nav_hist.columns:
                    _prem_val = _last.get('premium_pct')
                    _price_val = _last.get('price', None)
                    if _prem_val is not None and not _pd_prem.isna(_prem_val):
                        _pv = float(_prem_val)
                        _latest_nav = float(_last['nav'])
                        _pr = float(_price_val) if _price_val else (_latest_nav * (1 + _pv / 100))
                        print(f'[折溢價-A] {ticker}: nav={_latest_nav} prem={_pv}% (TWSE直讀)')
                        return {'nav': _latest_nav, 'price': round(_pr, 4),
                                'premium_pct': _pv, 'warning': _pv > 1.0}

                # ── 路徑B：FinMind NAV history + df Same-Date Inner Join ──
                # 與「近30日淨值」表格相同的精確日期配對邏輯，杜絕日期錯位
                if not df.empty and 'Close' in df.columns:
                    _nav_df = _nav_hist[['date', 'nav']].copy()
                    _nav_df['date'] = _pd_prem.to_datetime(_nav_df['date']).dt.normalize()
                    _nav_df = _nav_df.set_index('date')
                    _price_s = df[['Close']].copy()
                    _price_s.index = _pd_prem.to_datetime(_price_s.index).normalize()
                    _merged = _nav_df.join(_price_s, how='inner').dropna()
                    if not _merged.empty:
                        _row = _merged.iloc[-1]  # 最近一筆同日配對
                        _nav_v = float(_row['nav'])
                        _pr_v  = float(_row['Close'])
                        _prem  = round((_pr_v - _nav_v) / _nav_v * 100, 2)
                        print(f'[折溢價-B] {ticker}: date={_merged.index[-1].date()} nav={_nav_v} price={_pr_v} prem={_prem}%')
                        return {'nav': _nav_v, 'price': _pr_v,
                                'premium_pct': _prem, 'warning': _prem > 1.0}

        print(f'[折溢價] {ticker}: 所有路徑失敗，回傳 N/A')
    except Exception as _ep:
        import traceback as _tb_p; print(f'[折溢價] 錯誤: {_ep}'); _tb_p.print_exc()
    return {'nav': None, 'price': None, 'premium_pct': None, 'warning': False}

def calc_tracking_error(df: pd.DataFrame, bench_df: pd.DataFrame) -> float:
    """追蹤誤差 = std(ETF日報酬 - 基準日報酬) × √252 × 100"""
    try:
        if df.empty or bench_df.empty:
            return None
        etf_r   = df['Close'].pct_change().dropna()
        bench_r = bench_df['Close'].pct_change().dropna()
        common  = etf_r.index.intersection(bench_r.index)
        if len(common) < 20:
            return None
        diff = etf_r.loc[common] - bench_r.loc[common]
        return round(float(diff.std() * (252 ** 0.5) * 100), 2)
    except Exception:
        return None

def calc_mdd(df: pd.DataFrame) -> float:
    """最大回撤 MDD(%)"""
    try:
        close    = df['Close']
        roll_max = close.cummax()
        return round(float(((close - roll_max) / roll_max * 100).min()), 2)
    except Exception:
        return None

def calc_cagr(df: pd.DataFrame) -> float:
    """年化報酬率 CAGR(%)"""
    try:
        if len(df) < 2:
            return 0.0
        days  = (df.index[-1] - df.index[0]).days
        if days < 30:
            return 0.0
        y     = days / 365.25
        start = float(df['Close'].iloc[0])
        end   = float(df['Close'].iloc[-1])
        return round(((end / start) ** (1 / y) - 1) * 100, 2)
    except Exception:
        return 0.0

def calc_sharpe(df: pd.DataFrame, rf: float = 5.33) -> float:
    """夏普值（年化，rf預設5.33% FEDFUNDS）"""
    try:
        ret     = df['Close'].pct_change().dropna()
        if len(ret) < 20:
            return 0.0
        ann_ret = float(ret.mean() * 252 * 100)
        ann_vol = float(ret.std() * (252 ** 0.5) * 100)
        return round((ann_ret - rf) / ann_vol, 2) if ann_vol > 0 else 0.0
    except Exception:
        return 0.0

def auto_detect_benchmark(ticker: str) -> str:
    t = ticker.upper()
    if t.endswith('.TW') or t.endswith('.TWO'):
        return '0050.TW'
    return '^GSPC'

# ═══════════════════════════════════════════════════════════════
# UI 輔助元件
# ═══════════════════════════════════════════════════════════════

def macro_allocation_banner(regime: str) -> None:
    """總經連動配置建議橫幅"""
    alloc = MACRO_ALLOC.get(regime, MACRO_ALLOC['neutral'])
    desc  = MACRO_DESC.get(regime, MACRO_DESC['neutral'])
    bg_map  = {'bull': '#0d2618', 'neutral': '#1e1a00', 'bear': '#2a0d0d'}
    brd_map = {'bull': '#2ea043',  'neutral': '#d29922',  'bear': '#f85149'}
    bg  = bg_map.get(regime, '#1a1f2e')
    brd = brd_map.get(regime, '#1f6feb')
    alloc_html = ' &nbsp;|&nbsp; '.join(
        f'<b>{k}</b>&nbsp;<span style="color:#58a6ff;">{v}%</span>'
        for k, v in alloc.items()
    )
    st.markdown(
        f'''<div style="background:{bg};border:1px solid {brd};border-radius:10px;
padding:10px 16px;margin-bottom:14px;">
<div style="font-size:12px;font-weight:700;color:#8b949e;margin-bottom:2px;">
📡 總經連動配置建議（來源：Tab① 市場評估）</div>
<div style="font-size:13px;color:#c9d1d9;">{desc}</div>
<div style="font-size:13px;margin-top:6px;">{alloc_html}</div>
</div>''', unsafe_allow_html=True)

def _colored_box(text: str, color: str = 'green') -> None:
    """統一彩色提示框"""
    cfg = {
        'green':  ('#0d2618', '#2ea043'),
        'yellow': ('#1e1a00', '#d29922'),
        'red':    ('#2a0d0d', '#f85149'),
        'blue':   ('#0a1628', '#1f6feb'),
    }
    bg, brd = cfg.get(color, cfg['blue'])
    st.markdown(
        f'<div style="background:{bg};border:1px solid {brd};border-radius:8px;'
        f'padding:10px 14px;margin:6px 0;">{text}</div>',
        unsafe_allow_html=True)

def _teacher_conclusion(teacher: str, indicator_val: str, conclusion: str,
                        action: str = '', color: str | None = None) -> None:
    """ETF dashboard 老師結論卡（與 app.py teacher_conclusion 同格式，直接 render）"""
    if color is None:
        _neg_kw = ['警戒', '危險', '賣超', '空單', '減碼', '停損', '撤離', '跌破', '過熱', '回調', '降倉', '空頭', '侵蝕', '高估']
        _pos_kw = ['強勢', '買超', '多頭', '安全', '健康', '買進', '加碼', '流入', '突破', '進攻', '上漲', '低估', '特價']
        if any(k in conclusion + action for k in _neg_kw):
            color = '#2ea043'
        elif any(k in conclusion + action for k in _pos_kw):
            color = '#da3633'
        else:
            color = '#d29922'
    _icon = {'宏爺': '🎯', '孫慶龍': '💡', '弘爺': '🎯', '朱家泓': '📊',
             '妮可': '📈', '春哥': '🌱', '蔡森': '📐', '郭俊宏': '💰'}.get(teacher, '👤')
    _action_str = f'，{action}' if action else ''
    st.markdown(
        f'<div style="border-left:3px solid {color};padding:6px 10px;margin:4px 0;'
        f'background:rgba(0,0,0,0.2);border-radius:0 6px 6px 0;">'
        f'<span style="color:#ffd700;font-weight:700;font-size:12px;">{_icon} {teacher}</span>'
        f'<span style="color:#8b949e;font-size:12px;">：</span>'
        f'<span style="color:#c9d1d9;font-size:12px;">{indicator_val} → </span>'
        f'<span style="color:{color};font-size:12px;font-weight:600;">{conclusion}</span>'
        f'<span style="color:#8b949e;font-size:11px;">{_action_str}</span>'
        f'</div>',
        unsafe_allow_html=True)

def _plot_etf_chart(df: pd.DataFrame, ticker: str,
                    benchmark: str, bench_df: pd.DataFrame) -> None:
    """ETF 走勢圖 + MA50/MA200 + 標準化基準（Y軸：漲幅%，以起始日為0%）"""
    fig   = go.Figure()
    close = df['Close']
    base  = float(close.iloc[0])   # 起始價，用來換算漲幅%

    def _pct(s): return ((s / base) - 1) * 100   # → 相對起始點的漲幅%

    _hover = '%{x|%Y-%m-%d}  %{y:.2f}%<extra></extra>'
    fig.add_trace(go.Scatter(x=df.index, y=_pct(close).round(2),
                              name=ticker, line=dict(color='#58a6ff', width=2),
                              hovertemplate=_hover))
    fig.add_trace(go.Scatter(x=df.index, y=_pct(close.rolling(50).mean()).round(2),
                              name='MA50', line=dict(color='#ffa657', width=1, dash='dot'),
                              hovertemplate=_hover))
    fig.add_trace(go.Scatter(x=df.index, y=_pct(close.rolling(200).mean()).round(2),
                              name='MA200', line=dict(color='#f85149', width=1, dash='dash'),
                              hovertemplate=_hover))
    if not bench_df.empty:
        _bc   = bench_df['Close'].reindex(df.index).ffill().dropna()
        _bc_b = float(_bc.iloc[0])
        _bc_pct = ((_bc / _bc_b) - 1) * 100   # 基準也從0%起算
        fig.add_trace(go.Scatter(x=_bc.index, y=_bc_pct.round(2),
                                  name=f'{benchmark}（基準）',
                                  line=dict(color='#3fb950', width=1.2, dash='dash'),
                                  hovertemplate=_hover))
    fig.update_layout(
        template='plotly_dark', height=380,
        margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor='#0d1117', plot_bgcolor='#0d1117',
        legend=dict(orientation='h', yanchor='bottom', y=1.01),
        yaxis=dict(title='漲幅 (%)', ticksuffix='%', zeroline=True,
                   zerolinecolor='#444', zerolinewidth=1),
    )
    st.plotly_chart(fig, width='stretch')

def _plot_correlation(corr: pd.DataFrame) -> None:
    """相關係數熱力圖"""
    labels = list(corr.columns)
    z      = corr.values.tolist()
    text   = [[f'{v:.2f}' for v in row] for row in z]
    fig = go.Figure(go.Heatmap(
        z=z, x=labels, y=labels,
        text=text, texttemplate='%{text}',
        colorscale='RdBu_r', zmid=0, zmin=-1, zmax=1,
        colorbar=dict(thickness=10),
    ))
    fig.update_layout(
        template='plotly_dark', height=320,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor='#0d1117', plot_bgcolor='#0d1117',
    )
    st.plotly_chart(fig, width='stretch')

def _render_bias(df: pd.DataFrame, ticker: str) -> None:
    """BIAS 乖離率：(Close - MAn) / MAn × 100%，顯示 MA20/MA60/MA120"""
    if df is None or len(df) < 20:
        st.info('資料不足，無法計算 BIAS')
        return
    close = df['Close'] if 'Close' in df.columns else df['close']
    bias_rows = []
    for n, label in [(20, 'MA20'), (60, 'MA60'), (120, 'MA120')]:
        if len(close) >= n:
            ma  = float(close.rolling(n).mean().iloc[-1])
            cur = float(close.iloc[-1])
            bias = (cur - ma) / ma * 100
            if bias > 10:
                hint = '🔴 嚴重高估，注意拉回'
            elif bias > 5:
                hint = '🟡 偏高，謹慎追高'
            elif bias < -10:
                hint = '🟢 嚴重低估，逢低佈局機會'
            elif bias < -5:
                hint = '🟡 偏低，可分批承接'
            else:
                hint = '⚪ 中性偏離，正常波動'
            bias_rows.append({'均線': label, 'MA值': f'{ma:.2f}',
                               'BIAS(%)': f'{bias:+.2f}%', '訊號': hint})
    if bias_rows:
        st.dataframe(pd.DataFrame(bias_rows), use_container_width=True, hide_index=True)
        # 視覺化近60日 BIAS(MA20)
        if len(close) >= 60:
            ma20 = close.rolling(20).mean()
            b20  = (close - ma20) / ma20 * 100
            b20  = b20.dropna().tail(60)
            fig  = go.Figure(go.Bar(
                x=b20.index, y=b20.values,
                marker_color=['#f85149' if v > 0 else '#3fb950' for v in b20.values],
                name='BIAS(MA20)',
            ))
            fig.add_hline(y=10,  line_dash='dot', line_color='#f85149',
                          annotation_text='+10%')
            fig.add_hline(y=-10, line_dash='dot', line_color='#3fb950',
                          annotation_text='-10%')
            fig.update_layout(
                template='plotly_dark', height=220,
                yaxis_title='BIAS %', margin=dict(l=0, r=0, t=20, b=0),
                paper_bgcolor='#0d1117', plot_bgcolor='#0d1117',
            )
            st.plotly_chart(fig, width='stretch')

# ═══════════════════════════════════════════════════════════════
# Tab ⑥：單一 ETF 深度診斷
# ═══════════════════════════════════════════════════════════════

def render_etf_single(gemini_fn=None):
    mkt_info = st.session_state.get('mkt_info', {})
    regime   = mkt_info.get('regime', 'neutral')
    macro_allocation_banner(regime)

    st.markdown('#### 🔍 輸入 ETF 代號')
    col_l, col_r = st.columns([2, 1])
    ticker    = col_l.text_input('ETF 代號（台灣加 .TW，如 0050.TW | 美國：SPY、QQQ）',
                                  value='0050.TW', key='etf_s_ticker').strip().upper()
    benchmark = col_r.text_input('對照基準（留空自動偵測）',
                                  value='', key='etf_s_bench').strip().upper()
    if not benchmark:
        benchmark = auto_detect_benchmark(ticker)

    if st.button('🔍 開始診斷', key='etf_s_btn', use_container_width=True):
        st.session_state['etf_s_active'] = ticker

    if st.session_state.get('etf_s_active') != ticker:
        st.info('💡 輸入 ETF 代號後點擊「開始診斷」')
        return

    with st.spinner(f'載入 {ticker} 資料中...'):
        df       = fetch_etf_price(ticker)
        divs     = fetch_etf_dividends(ticker)
        info     = fetch_etf_info(ticker)
        bench_df = fetch_etf_price(benchmark)

    if df.empty:
        st.error(f'❌ 找不到 {ticker}，請確認代號（台灣ETF需加 .TW）')
        st.session_state.pop('etf_s_active', None)
        return

    etf_name = info.get('longName') or info.get('shortName') or ticker
    expense  = info.get('annualReportExpenseRatio') or info.get('totalExpenseRatio')
    beta     = info.get('beta') or info.get('beta3Year')
    aum      = info.get('totalAssets')

    st.markdown(f'### 🏦 {etf_name} ({ticker})')

    c1, c2, c3, c4 = st.columns(4)
    c1.metric('最新收盤', f'{df["Close"].iloc[-1]:.2f}')
    c2.metric('內扣費用率', f'{expense*100:.2f}%' if expense else 'N/A')
    c3.metric('Beta', f'{float(beta):.2f}' if beta else 'N/A')
    c4.metric('AUM', f'{aum/1e9:.1f}B USD' if aum and aum > 1e6 else 'N/A')
    st.markdown('---')

    # ── 策略一：MK 郭俊宏 ─────────────────────────────────────
    st.markdown('#### 🧠 策略一：MK 郭俊宏 — 以息養股避雷策略')
    total_ret = calc_total_return_1y(df, divs)
    cur_yield = calc_current_yield(df, divs)
    ca, cb    = st.columns(2)
    ca.metric('近1年含息總報酬', f'{total_ret:.2f}%')
    cb.metric('現金殖利率（近12M）', f'{cur_yield:.2f}%')
    if cur_yield > 0 and total_ret < cur_yield:
        _colored_box('⚠️ <b>紅燈警示</b>：賺了股息賠了價差，侵蝕本金中，<b>不宜作為核心資產</b>', 'red')
        _teacher_conclusion('郭俊宏',
                            f'含息總報酬 {total_ret:.1f}% < 殖利率 {cur_yield:.1f}%',
                            '本金侵蝕中，高息陷阱',
                            '換標的，找總報酬為正的 ETF')
    elif cur_yield > 0:
        _colored_box(f'✅ 含息總報酬({total_ret:.1f}%) > 殖利率({cur_yield:.1f}%)，核心資產條件通過', 'green')
        _teacher_conclusion('郭俊宏',
                            f'含息總報酬 {total_ret:.1f}%，殖利率 {cur_yield:.1f}%',
                            '價差 + 配息雙贏，核心資產條件通過',
                            '可列入長期核心持倉')
    else:
        st.info('ℹ️ 無配息紀錄（成長型ETF），以價差報酬評估')
        _teacher_conclusion('郭俊宏',
                            f'近1年總報酬 {total_ret:.1f}%，無配息',
                            '成長型ETF，以價差報酬衡量',
                            '衡量 CAGR 是否超過大盤')

    # ── 策略二：孫慶龍 7% ─────────────────────────────────────
    st.markdown('#### 🧠 策略二：孫慶龍 — 7% 存股聖經估值買賣點')
    avg_yield = calc_avg_yield(df, divs, years=5)
    cc, cd    = st.columns(2)
    cc.metric('近5年平均殖利率', f'{avg_yield:.2f}%' if avg_yield else 'N/A')
    cd.metric('現今殖利率', f'{cur_yield:.2f}%')
    if avg_yield > 0:
        if cur_yield >= 7:
            _colored_box('🟢 <b>強烈買進（特價）</b>：殖利率 ≥ 7%，現值低估，值得分批佈局', 'green')
            _teacher_conclusion('孫慶龍',
                                f'現金殖利率 {cur_yield:.1f}%（5年均 {avg_yield:.1f}%）',
                                '殖利率 ≥ 7%，低估特價區，強烈買進',
                                '分批佈局，停損設 -15%')
        elif cur_yield <= 3:
            _colored_box('🔴 <b>獲利了結（昂貴）</b>：殖利率 ≤ 3%，現值高估，考慮減碼', 'red')
            _teacher_conclusion('孫慶龍',
                                f'現金殖利率 {cur_yield:.1f}%（5年均 {avg_yield:.1f}%）',
                                '殖利率 ≤ 3%，高估昂貴區，獲利了結',
                                '分批出清，等待殖利率回升到 5% 以上')
        elif cur_yield <= 5:
            _colored_box('🟡 <b>適度減碼（合理）</b>：殖利率 ≤ 5%，估值合理偏高', 'yellow')
            _teacher_conclusion('孫慶龍',
                                f'現金殖利率 {cur_yield:.1f}%（5年均 {avg_yield:.1f}%）',
                                '殖利率 3%~5%，估值合理偏高，適度減碼',
                                '不宜重倉，等待 5% 以上再加碼')
        else:
            st.info(f'殖利率 {cur_yield:.1f}% 位於 5%~7% 合理區間，中性持有')
            _teacher_conclusion('孫慶龍',
                                f'現金殖利率 {cur_yield:.1f}%（5年均 {avg_yield:.1f}%）',
                                '殖利率 5%~7% 合理區間，中性持有',
                                '可持有，待殖利率 ≥ 7% 再加碼')
    else:
        st.info('ℹ️ 無充足配息歷史，套用回測頁評估價差績效')
        _teacher_conclusion('孫慶龍',
                            '配息歷史不足',
                            '無法套用 7% 存股聖經，改看回測 CAGR',
                            '前往「ETF回測」確認年化報酬是否 ≥ 8%')

    # ── 策略三：春哥 VCP ──────────────────────────────────────
    st.markdown('#### 🧠 策略三：春哥（Stan Weinstein）— VCP 波幅收縮突破')
    vcp = check_vcp_signal(df)
    ce, cf, cg = st.columns(3)
    ce.metric('站上 50MA',  '✅' if vcp['above_ma50']  else '❌')
    cf.metric('站上 200MA', '✅' if vcp['above_ma200'] else '❌')
    cg.metric('量能確認',   '✅' if vcp['vol_confirm'] else '❌')
    if vcp['weekly_ranges']:
        st.caption('近5週波幅：' + ' → '.join(f'{r}%' for r in vcp['weekly_ranges']))
    if vcp['signal']:
        _colored_box(f'🚀 <b>VCP 突破買訊！</b> 嚴守 8% 停損線：{vcp["stop_loss"]}', 'green')
        _teacher_conclusion('春哥',
                            f'50MA ✅ | 200MA ✅ | 量能 ✅',
                            'VCP 三條件全過，突破買進',
                            f'停損設 {vcp["stop_loss"]}（-8%），突破後嚴守紀律')
    else:
        missing = []
        if not vcp['above_ma50']:  missing.append('未站上50MA')
        if not vcp['above_ma200']: missing.append('未站上200MA')
        if not vcp['vol_confirm']: missing.append('量能不足')
        if len(df) < 210:         missing.append('資料不足210天')
        _miss_str = ' | '.join(missing) if missing else '波幅尚未收縮'
        st.info('⏳ VCP 條件未滿足：' + _miss_str)
        _teacher_conclusion('春哥',
                            f'VCP 缺：{_miss_str}',
                            '條件未齊，耐心等候突破訊號',
                            '加入觀察清單，條件滿足再進場')

    # ── ETF 防呆：折溢價 + 追蹤誤差 + 建議買賣時機 ──────────
    st.markdown('#### 🛡️ ETF 折溢價 — 建議買賣時機')
    prem = calc_premium_discount(info, df, ticker)   # 傳入 ticker 以使用 FinMind/TWSE NAV
    te   = calc_tracking_error(df, bench_df)

    # 折溢價建議邏輯
    _pct = prem['premium_pct']
    if _pct is not None:
        if _pct <= -2:
            _prem_color  = '#3fb950'
            _prem_action = '🟢 強烈買進時機'
            _prem_reason = f'折價 {abs(_pct):.2f}%，低於 NAV 買入，立即為你創造安全邊際'
        elif _pct <= -0.5:
            _prem_color  = '#58a6ff'
            _prem_action = '🔵 合理買進'
            _prem_reason = f'折價 {abs(_pct):.2f}%，略低於 NAV，可正常分批買入'
        elif _pct <= 1.0:
            _prem_color  = '#d29922'
            _prem_action = '🟡 中性觀望'
            _prem_reason = f'溢價 {_pct:.2f}%（±1% 正常範圍），無需急追'
        elif _pct <= 3.0:
            _prem_color  = '#f85149'
            _prem_action = '🔴 暫緩買進'
            _prem_reason = f'溢價 {_pct:.2f}%，高於 NAV，追高風險較大，等待回落'
        else:
            _prem_color  = '#f85149'
            _prem_action = '🔴 嚴禁追高'
            _prem_reason = f'溢價 {_pct:.2f}%，嚴重高溢價，等待折價或換標的'
    else:
        _prem_color  = '#8b949e'
        _prem_action = 'ℹ️ 無 NAV 資料'
        _prem_reason = 'yfinance 未提供 NAV，建議至官網確認折溢價'

    st.markdown(
        f'<div style="background:#0d1117;border:2px solid {_prem_color};border-radius:10px;'
        f'padding:14px 18px;margin-bottom:10px;">'
        f'<div style="font-size:20px;font-weight:900;color:{_prem_color};">{_prem_action}</div>'
        f'<div style="font-size:13px;color:#c9d1d9;margin-top:4px;">{_prem_reason}</div>'
        + (f'<div style="font-size:12px;color:#8b949e;margin-top:6px;">折溢價率：'
           f'<b style="color:{_prem_color};">{_pct:+.2f}%</b></div>' if _pct is not None else '')
        + '</div>',
        unsafe_allow_html=True)

    if _pct is not None:
        _prem_concl = ('折價買進，獲得安全邊際' if _pct <= -0.5
                       else '中性，無需急追' if _pct <= 1.0
                       else '高溢價，追高風險大，等待回落')
        _prem_act2  = ('分批買進' if _pct <= -0.5
                       else '持有觀望' if _pct <= 1.0
                       else '暫緩或換標的')
        _teacher_conclusion('宏爺', f'{ticker} 折溢價 {_pct:+.2f}%', _prem_concl, _prem_act2)

    ch, ci = st.columns(2)
    ch.metric('折溢價率', f'{_pct:+.2f}%' if _pct is not None else 'N/A')
    if te is not None:
        ci.metric(f'追蹤誤差 vs {benchmark}', f'{te:.2f}%')
        if te > 1.5:
            ci.markdown('<small style="color:#d29922;">⚠️ 追蹤誤差 >1.5%，注意隱藏成本</small>',
                        unsafe_allow_html=True)
    else:
        ci.metric('追蹤誤差', 'N/A')

    # ── 歷史淨值及折溢價表 ────────────────────────────────────
    import pandas as _pd_navtbl
    _nav_hist = fetch_etf_nav_history(ticker, days=35)
    if not _nav_hist.empty and 'nav' in _nav_hist.columns and not df.empty:
        try:
            _price_s = df[['Close']].copy()
            _price_s.index = _pd_navtbl.to_datetime(_price_s.index).normalize()
            _nav_hist2 = _nav_hist.copy()
            _nav_hist2['date'] = _pd_navtbl.to_datetime(_nav_hist2['date'])
            _nav_hist2 = _nav_hist2.set_index('date')
            _merged = _nav_hist2.join(_price_s, how='inner').dropna()
            if not _merged.empty:
                _merged['折溢價']  = (_merged['Close'] - _merged['nav']).round(2)
                _merged['折溢價%'] = ((_merged['Close'] - _merged['nav']) / _merged['nav'] * 100).round(2)
                _display = _merged.reset_index()[['date','Close','nav','折溢價','折溢價%']].tail(20)
                _display.columns = ['日期','市價','淨值','折溢價','折溢價%']
                _display['日期'] = _display['日期'].dt.strftime('%Y/%m/%d')
                st.markdown(f'**{ticker} 近期淨值及折溢價**（折溢價% = (市價-淨值)/淨值×100）')
                st.dataframe(_display.sort_values('日期', ascending=False),
                             use_container_width=True, hide_index=True)
        except Exception as _ne:
            print(f'[ETF NAV Table] {_ne}')

    # ── BIAS 乖離率 ───────────────────────────────────────────
    st.markdown('#### 📐 BIAS 乖離率（均線偏離程度）')
    _render_bias(df, ticker)

    # ── 年線乖離率(MA240) + KD — 供存股 AI 使用 ──────────────
    _close_ai = df['Close'] if 'Close' in df.columns else df.get('close', pd.Series(dtype=float))
    _bias240_ai = None
    _kv_ai = _dv_ai = None
    if len(_close_ai) >= 240:
        _ma240_ai   = float(_close_ai.rolling(240).mean().iloc[-1])
        _bias240_ai = round((float(_close_ai.iloc[-1]) - _ma240_ai) / _ma240_ai * 100, 2)
    if 'High' in df.columns and 'Low' in df.columns and len(df) >= 9:
        _h9  = df['High'].rolling(9).max()
        _l9  = df['Low'].rolling(9).min()
        _rsv = ((df['Close'] - _l9) / (_h9 - _l9).replace(0, float('nan')) * 100).fillna(50)
        _k_s = _rsv.ewm(com=2, adjust=False).mean()
        _d_s = _k_s.ewm(com=2, adjust=False).mean()
        _kv_ai = round(float(_k_s.iloc[-1]), 1)
        _dv_ai = round(float(_d_s.iloc[-1]), 1)

    # ── 走勢圖 ────────────────────────────────────────────────
    st.markdown(f'#### 📈 {ticker} 近5年走勢')
    _plot_etf_chart(df, ticker, benchmark, bench_df)

    # ── 存入 session_state 供 Tab⑨ 使用 ─────────────────────
    st.session_state['etf_single_data'] = {
        'ticker': ticker, 'name': etf_name,
        'cur_yield': cur_yield, 'avg_yield': avg_yield,
        'total_ret': total_ret, 'vcp': vcp,
        'premium': prem, 'te': te, 'regime': regime,
        'price_df': df,
        'expense': expense, 'beta': beta, 'aum': aum,
        'k_val': _kv_ai, 'd_val': _dv_ai,
        'bias240': _bias240_ai,
    }

    # ── AI ETF 存股決策總結 ───────────────────────────────────
    if gemini_fn:
        _etf_ai_hokei(gemini_fn, ticker, etf_name, cur_yield, _bias240_ai, _kv_ai, _dv_ai)

    # ── 統一投資決策分析模組 ──────────────────────────────────
    render_unified_decision(gemini_fn, {
        'type': 'etf',
        'id':   ticker,
        'data': {
            'ETF':              f'{etf_name} ({ticker})',
            '現金殖利率':        f'{cur_yield:.2f}%',
            '近5年平均殖利率':   f'{avg_yield:.2f}%',
            '近1年含息總報酬':   f'{total_ret:.2f}%',
            '年線乖離率BIAS240': f'{_bias240_ai:+.2f}%' if _bias240_ai is not None else 'N/A（< 240日）',
            'KD': (f'K:{_kv_ai:.1f} D:{_dv_ai:.1f}' if _kv_ai is not None else 'N/A'),
            'VCP突破':           vcp.get('signal', False) if isinstance(vcp, dict) else False,
            '折溢價率':          f'{prem["premium_pct"]}%' if prem.get("premium_pct") is not None else 'N/A',
            '追蹤誤差':          f'{te:.2f}%' if te is not None else 'N/A',
            '大盤狀態':          regime,
        },
    })

def _etf_ai_hokei(gemini_fn, ticker, name, cur_yield, bias240, k_val, d_val):
    """ETF AI 存股決策總結 — 買跌不買漲（左側交易）鐵血紀律"""
    import re as _re, json as _json

    st.markdown('---')
    st.markdown('### 🤖 AI ETF 存股決策總結')
    st.caption('嚴守「買跌不買漲（左側交易）」紀律，以年線乖離率＋殖利率＋KD 三維度研判定期定額節奏。')

    # ── 規則引擎先行判定 ──────────────────────────────────────
    kd_high = (k_val is not None and k_val > 80) or (d_val is not None and d_val > 80)
    if bias240 is None:
        _sig, _col, _bg = '資料不足（< 240 日）', '#8b949e', '#161b22'
    elif bias240 <= 0 and cur_yield >= 6:
        _sig, _col, _bg = '極佳買點 (加速扣款)', '#3fb950', '#0d2818'
    elif bias240 <= 0:
        _sig, _col, _bg = '極佳買點 (加速扣款)', '#3fb950', '#0d2818'
    elif bias240 < 10:
        _sig, _col, _bg = '正常存股 (紀律扣款)', '#d29922', '#1c1500'
    elif kd_high:
        _sig, _col, _bg = '停止買進 (暫停扣款)', '#f85149', '#2a0d0d'
    else:
        _sig, _col, _bg = '謹慎觀望 (減少扣款)', '#d29922', '#1c1500'

    _b240_str = f'{bias240:+.2f}%' if bias240 is not None else 'N/A（資料不足 240 日）'
    _k_str    = f'{k_val:.1f}' if k_val is not None else 'N/A'
    _d_str    = f'{d_val:.1f}' if d_val is not None else 'N/A'
    _kd_label = f'K:{_k_str} / D:{_d_str}' + (' 🔴 高檔' if kd_high else '')

    # ── 資料概覽卡 ────────────────────────────────────────────
    st.markdown(
        f'<div style="background:{_bg};border:2px solid {_col};border-radius:12px;'
        f'padding:20px 24px;margin:8px 0;">'
        f'<div style="font-size:22px;font-weight:900;color:{_col};">{_sig}</div>'
        f'<div style="display:flex;gap:32px;margin-top:14px;flex-wrap:wrap;">'
        f'<div><div style="font-size:11px;color:#8b949e;">年線乖離率 (BIAS240)</div>'
        f'<div style="font-size:18px;font-weight:700;color:#c9d1d9;">{_b240_str}</div></div>'
        f'<div><div style="font-size:11px;color:#8b949e;">KD 指標</div>'
        f'<div style="font-size:18px;font-weight:700;color:#c9d1d9;">{_kd_label}</div></div>'
        f'<div><div style="font-size:11px;color:#8b949e;">現金殖利率</div>'
        f'<div style="font-size:18px;font-weight:700;color:#c9d1d9;">{cur_yield:.2f}%</div></div>'
        f'</div></div>',
        unsafe_allow_html=True)

    # ── LLM 精煉研判按鈕 ──────────────────────────────────────
    _sess_key = f'etf_hokei_{ticker}'
    if st.button('🤖 AI 精煉研判（存股節奏）', key='etf_hokei_btn'):
        _news_str = _fetch_news_for(ticker, name, 4)
        _prompt = (
            "你是嚴格執行「買跌不買漲（左側交易）」紀律的ETF存股顧問。\n"
            "根據以下數據，套用判定邏輯，只輸出 JSON，不含其他文字：\n\n"
            f"ETF: {name} ({ticker})\n"
            f"年線乖離率(BIAS240): {_b240_str}\n"
            f"K值: {_k_str}  D值: {_d_str}  KD高檔(>80): {'是' if kd_high else '否'}\n"
            f"現金殖利率: {cur_yield:.2f}%\n\n"
            f"【近期ETF相關新聞】\n{_news_str}\n\n"
            "判定邏輯：\n"
            "【極佳買點(加速扣款)】年線乖離率<=0% 且 殖利率>=6%\n"
            "【正常存股(紀律扣款)】0%<年線乖離率<10%\n"
            "【停止買進(暫停扣款)】年線乖離率>=10% 且 KD高檔(>80)\n\n"
            '輸出格式（嚴格JSON）：\n'
            '{"signal":"極佳買點|正常存股|停止買進","reading":"50字以內精煉解讀","action":"行動指令10字內"}'
        )
        with st.spinner('AI 存股研判中...'):
            raw = gemini_fn(_prompt, max_tokens=300)
        if raw and not raw.startswith('⚠️'):
            _m = _re.search(r'\{[^{}]+\}', raw, _re.DOTALL)
            try:
                _j = _json.loads(_m.group()) if _m else {}
                if not _j.get('signal'):
                    _j = {'signal': _sig, 'reading': raw[:200], 'action': ''}
            except Exception:
                _j = {'signal': _sig, 'reading': raw[:200], 'action': ''}
            st.session_state[_sess_key] = _j
            st.rerun()
        else:
            st.warning(raw or 'AI 回傳為空，請確認 GEMINI_API_KEY')

    # ── 顯示已快取結果 ────────────────────────────────────────
    _saved = st.session_state.get(_sess_key)
    if _saved:
        _s  = _saved.get('signal', _sig)
        _r  = _saved.get('reading', '')
        _a  = _saved.get('action', '')
        _sc = '#3fb950' if '極佳' in _s else ('#f85149' if '停止' in _s else '#d29922')
        _sb = '#0d2818' if '極佳' in _s else ('#2a0d0d' if '停止' in _s else '#1c1500')
        st.markdown(
            f'<div style="background:{_sb};border-left:4px solid {_sc};border-radius:8px;'
            f'padding:16px 20px;margin:8px 0;">'
            f'<div style="font-size:15px;font-weight:700;color:{_sc};">{_s}</div>'
            f'<div style="font-size:13px;color:#c9d1d9;margin-top:8px;line-height:1.7;">{_r}</div>'
            + (f'<div style="font-size:12px;color:#8b949e;margin-top:10px;'
               f'border-top:1px solid #30363d;padding-top:8px;">'
               f'📌 行動指令：<b style="color:{_sc};">{_a}</b></div>' if _a else '')
            + '</div>',
            unsafe_allow_html=True)
        if st.button('🔄 清除結果', key='etf_hokei_clear'):
            st.session_state.pop(_sess_key, None)
            st.rerun()

# ETF → GICS 類股對照（僅涵蓋常見 ETF，未知 ETF 歸入「其他」）
_ETF_SECTOR_MAP = {
    'XLK': '資訊科技', 'QQQ': '資訊科技', '00631L.TW': '資訊科技',
    'XLF': '金融', 'KBE': '金融',
    'XLE': '能源',
    'XLV': '醫療保健',
    'XLI': '工業',
    'XLP': '必需消費', 'XLY': '非必需消費',
    'XLU': '公用事業',
    'XLB': '原材料',
    'XLRE': '房地產', '00712.TW': '房地產',
    'XLC': '通訊服務',
    'SPY': '廣泛市場', 'IVV': '廣泛市場', 'VOO': '廣泛市場',
    '0050.TW': '廣泛市場', '00646.TW': '廣泛市場',
    'BND': '債券', 'AGG': '債券', 'TLT': '債券',
    '00678.TW': '債券', '00720B.TW': '債券',
    '00878.TW': '高股息', '00713.TW': '高股息', '0056.TW': '高股息',
    'GLD': '黃金/原物料', 'IAU': '黃金/原物料',
}

def _check_sector_exposure(rows: list, total_value: float) -> None:
    """計算各 GICS 類股曝險，標記超過 30% 的集中風險"""
    sector_vals: dict = {}
    for r in rows:
        sector = _ETF_SECTOR_MAP.get(r['ticker'], '其他')
        sector_vals[sector] = sector_vals.get(sector, 0) + r['current_value']

    sector_rows = []
    warnings = []
    for sec, val in sorted(sector_vals.items(), key=lambda x: -x[1]):
        pct = val / total_value * 100
        flag = '⚠️ 超限' if pct > 30 else '✅'
        sector_rows.append({'類股': sec, '合計現值(元)': f'{val:,.0f}',
                             '佔比': f'{pct:.1f}%', '狀態': flag})
        if pct > 30:
            warnings.append((sec, pct))

    st.dataframe(pd.DataFrame(sector_rows), use_container_width=True, hide_index=True)
    if warnings:
        for sec, pct in warnings:
            _colored_box(
                f'⚠️ <b>{sec}</b> 類股佔比 <b>{pct:.1f}%</b> 超過 30% 上限，'
                f'建議分散至其他類股或降低持倉', 'red')
    else:
        _colored_box('✅ 所有類股曝險均在 30% 以內，產業分散度良好', 'green')

# ═══════════════════════════════════════════════════════════════
# Tab ⑦：ETF 組合配置與動態再平衡引擎
# ═══════════════════════════════════════════════════════════════

def render_etf_portfolio(gemini_fn=None):
    mkt_info = st.session_state.get('mkt_info', {})
    regime   = mkt_info.get('regime', 'neutral')
    macro_allocation_banner(regime)

    st.markdown('#### 📋 輸入組合（格式：代號,目標權重%,現值 元）')
    default_input = "0050.TW,40,200000\n00713.TW,30,150000\nBND,20,100000\n00878.TW,10,50000"
    raw       = st.text_area('組合輸入', value=default_input, height=130,
                              key='etf_p_input', label_visibility='collapsed')
    tolerance = st.slider('再平衡容忍偏離度（%）', 1, 15, 5, key='etf_p_tol')

    if st.button('📊 計算組合', key='etf_p_btn', use_container_width=True):
        st.session_state['etf_p_active'] = True

    if not st.session_state.get('etf_p_active'):
        st.info('💡 填入組合後點擊「計算組合」')
        return

    # 解析輸入
    rows = []
    for line in raw.strip().splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) >= 3:
            try:
                rows.append({'ticker': parts[0].upper(),
                              'target_pct': float(parts[1]),
                              'current_value': float(parts[2])})
            except ValueError:
                st.warning(f'⚠️ 無法解析：{line}')
    if not rows:
        st.error('❌ 請輸入有效的組合資料'); return

    total_value = sum(r['current_value'] for r in rows)
    for r in rows:
        r['actual_pct']  = round(r['current_value'] / total_value * 100, 2)
        r['deviation']   = round(r['actual_pct'] - r['target_pct'], 2)

    st.markdown(f'**總資產現值：{total_value:,.0f} 元**')
    # 查詢 ETF 名稱（去掉 .TW/.TWO 後綴後查 stock_names）
    try:
        from stock_names import get_stock_name as _gsn_etf
        def _etf_name(tk):
            code = tk.replace('.TWO','').replace('.TW','')
            n = _gsn_etf(code)
            return n if n and n != code else (fetch_etf_info(tk).get('shortName') or fetch_etf_info(tk).get('longName') or tk)
    except Exception:
        def _etf_name(tk): return tk
    overview_df = pd.DataFrame([{
        'ETF': r['ticker'],
        '名稱': _etf_name(r['ticker']),
        '目標權重%': r['target_pct'],
        '實際權重%': r['actual_pct'], '偏離度%': r['deviation'],
        '現值(元)': f'{r["current_value"]:,.0f}',
    } for r in rows])
    st.dataframe(overview_df, use_container_width=True, hide_index=True)

    # ── 再平衡交易指令（含具體股數）────────────────────────────
    st.markdown('#### ⚖️ 再平衡交易指令')
    # 抓取現價以計算股數
    _cur_prices = {}
    with st.spinner('取得現價...'):
        for r in rows:
            try:
                _df_tmp = fetch_etf_price(r['ticker'], period='5d')
                _cur_prices[r['ticker']] = float(_df_tmp['Close'].iloc[-1]) if not _df_tmp.empty else 0
            except Exception:
                _cur_prices[r['ticker']] = 0

    rebal_actions = []
    for r in rows:
        if abs(r['deviation']) > tolerance:
            target_val = total_value * r['target_pct'] / 100
            adj        = target_val - r['current_value']
            action     = '買進' if adj > 0 else '賣出'
            cur_price  = _cur_prices.get(r['ticker'], 0)
            shares     = int(abs(adj) / cur_price) if cur_price > 0 else 0
            rebal_actions.append({
                'ETF': r['ticker'], '動作': action,
                '金額(元)': abs(adj), '偏離度%': r['deviation'],
                '現價': cur_price, '建議股數': shares,
            })

    if rebal_actions:
        ra_df = pd.DataFrame([{
            'ETF':    a['ETF'],
            '動作':   a['動作'],
            '現價':   f'{a["現價"]:.2f}' if a['現價'] > 0 else '-',
            '建議股數': f'{a["建議股數"]:,}' if a['建議股數'] > 0 else '-',
            '金額(元)': f'{a["金額(元)"]:,.0f}',
            '偏離度%': a['偏離度%'],
        } for a in rebal_actions])
        st.dataframe(ra_df, use_container_width=True, hide_index=True)
        for act in rebal_actions:
            color = 'green' if act['動作'] == '買進' else 'red'
            icon  = '📈' if act['動作'] == '買進' else '📉'
            _share_txt = (f'約 <b>{act["建議股數"]:,} 股</b>（現價 {act["現價"]:.2f} 元）'
                          if act['建議股數'] > 0 else '（無法取得現價）')
            _colored_box(
                f'{icon} <b>{act["動作"]} {act["ETF"]}</b> {_share_txt}，'
                f'預估金額 <b>{act["金額(元)"]:,.0f} 元</b>（偏離 {act["偏離度%"]:+.1f}%）',
                color)
    else:
        _colored_box(f'✅ 所有標的偏離度均在 ±{tolerance}% 內，無需再平衡', 'green')

    # ── 產業曝險上限檢查（單一類股 ≤ 30%）─────────────────────
    st.markdown('#### 🏗️ 產業曝險上限檢查（單一 GICS 類股 ≤ 30%）')
    _check_sector_exposure(rows, total_value)

    # ── 相關係數矩陣 ──────────────────────────────────────────
    st.markdown('#### 🔗 相關係數矩陣（近1年）')
    tickers = [r['ticker'] for r in rows]
    ret_dict = {}
    with st.spinner('計算相關係數...'):
        for t in tickers:
            df_t = fetch_etf_price(t, period='1y')
            if not df_t.empty:
                ret_dict[t] = df_t['Close'].pct_change()
    if len(ret_dict) >= 2:
        ret_df = pd.DataFrame(ret_dict).ffill().dropna()
        corr   = ret_df.corr()
        _plot_correlation(corr)
        for i in range(len(corr)):
            for j in range(i + 1, len(corr)):
                val = corr.iloc[i, j]
                if val > 0.85:
                    _colored_box(
                        f'⚠️ <b>{corr.index[i]} × {corr.columns[j]}</b> '
                        f'相關係數 {val:.2f} > 0.85，資產同質性過高', 'red')
    else:
        st.warning('資料不足，無法計算相關係數')

    # ── 壓力測試（S&P500 下跌20%）────────────────────────────
    st.markdown('#### 🧨 壓力測試（模擬 S&P 500 下跌 20%）')
    stress_results = []
    total_stress   = 0.0
    for r in rows:
        info_i  = fetch_etf_info(r['ticker'])
        beta_i  = info_i.get('beta') or info_i.get('beta3Year') or 1.0
        try:
            beta_i = float(beta_i)
        except Exception:
            beta_i = 1.0
        est_loss       = r['actual_pct'] / 100 * beta_i * (-0.20) * total_value
        total_stress  += est_loss
        stress_results.append({
            'ETF': r['ticker'], 'Beta': round(beta_i, 2),
            '實際權重%': r['actual_pct'],
            '預估虧損(元)': f'{est_loss:,.0f}',
        })
    st.dataframe(pd.DataFrame(stress_results), use_container_width=True, hide_index=True)
    loss_pct = abs(total_stress) / total_value * 100
    color    = 'red' if loss_pct > 20 else 'green'
    _colored_box(
        f'組合預估總虧損：<b>{total_stress:,.0f} 元</b>（{loss_pct:.1f}%）'
        + ('&nbsp; ⚠️ 超過20%，建議增加避險部位' if loss_pct > 20 else '&nbsp; ✅ 風險可控'),
        color)
    if loss_pct > 20:
        _teacher_conclusion('孫慶龍',
                            f'S&P500↓20% 壓力測試損失 {loss_pct:.1f}%',
                            '尾部風險超標，組合過於進攻型',
                            '增加債券 ETF 或現金部位，降低整體 Beta')
    else:
        _teacher_conclusion('孫慶龍',
                            f'S&P500↓20% 壓力測試損失 {loss_pct:.1f}%',
                            '壓力測試風險可控，組合防禦性足夠',
                            '維持現有配置，定期再平衡')

    # ── VaR 風險值（歷史模擬法 + 參數法）────────────────────────
    st.markdown('#### 📉 VaR 風險值（Value at Risk）')
    st.caption('衡量正常市況下單日最大可能虧損：歷史模擬法取近1年最差分位數，參數法假設常態分布')
    _var_rets = {}
    with st.spinner('計算 VaR...'):
        for r in rows:
            _df_v = fetch_etf_price(r['ticker'], period='1y')
            if not _df_v.empty:
                _var_rets[r['ticker']] = _df_v['Close'].pct_change().dropna()
    if len(_var_rets) >= 1:
        # 組合日報酬（加權合并）
        _all_idx = sorted(set().union(*[s.index for s in _var_rets.values()]))
        _port_ret = pd.Series(0.0, index=_all_idx)
        for r in rows:
            if r['ticker'] in _var_rets:
                _w = r['actual_pct'] / 100
                _port_ret = _port_ret.add(
                    _var_rets[r['ticker']].reindex(_all_idx).ffill().fillna(0) * _w)
        _port_ret = _port_ret.dropna()
        if len(_port_ret) >= 20:
            # 歷史模擬法
            _h95 = float(_port_ret.quantile(0.05)) * total_value
            _h99 = float(_port_ret.quantile(0.01)) * total_value
            # 參數法
            _mu  = float(_port_ret.mean())
            _sig = float(_port_ret.std())
            _p95 = (_mu - 1.645 * _sig) * total_value
            _p99 = (_mu - 2.326 * _sig) * total_value
            # 月度 VaR（√21 近似）
            _m99 = _h99 * (21 ** 0.5)

            _vc1, _vc2 = st.columns(2)
            with _vc1:
                st.markdown('**📊 歷史模擬法**')
                st.metric('95% 日 VaR', f'{abs(_h95):,.0f} 元',
                          f'{abs(_h95)/total_value*100:.2f}% 組合市值')
                st.metric('99% 日 VaR', f'{abs(_h99):,.0f} 元',
                          f'{abs(_h99)/total_value*100:.2f}% 組合市值')
                st.caption('95% VaR：正常市況下100天中，95天的虧損不超過此值')
            with _vc2:
                st.markdown('**📐 參數法（常態分布）**')
                st.metric('95% 日 VaR', f'{abs(_p95):,.0f} 元',
                          f'{abs(_p95)/total_value*100:.2f}% 組合市值')
                st.metric('99% 日 VaR', f'{abs(_p99):,.0f} 元',
                          f'{abs(_p99)/total_value*100:.2f}% 組合市值')
                st.caption('金融市場有肥尾效應，歷史模擬法通常比參數法更保守')
            _var_warn = abs(_m99) / total_value > 0.10
            _colored_box(
                f'📅 月度 99% VaR（√21 近似）：<b>{abs(_m99):,.0f} 元</b>'
                f'（{abs(_m99)/total_value*100:.2f}%）'
                + ('&nbsp; ⚠️ 超過10%，尾部風險偏高，建議增加防禦部位'
                   if _var_warn else '&nbsp; ✅ 月度尾部風險在可接受範圍內'),
                'red' if _var_warn else 'green')
            if _var_warn:
                _teacher_conclusion('弘爺',
                                    f'月度 99% VaR {abs(_m99)/total_value*100:.2f}%',
                                    '月度尾部風險 > 10%，組合波動過大',
                                    '增加低相關資產（如 BND/AGGG），降低整體波動')
            else:
                _teacher_conclusion('弘爺',
                                    f'月度 99% VaR {abs(_m99)/total_value*100:.2f}%',
                                    '月度尾部風險在可接受範圍，組合穩健',
                                    '維持現有風險配置，按計畫再平衡')
        else:
            st.warning('歷史資料不足（<20筆），無法計算 VaR')
    else:
        st.warning('無法取得價格資料，跳過 VaR 計算')

    # ── 配息日曆 × 年度現金流預估 ──────────────────────────────
    st.markdown('#### 💰 配息日曆 × 年度現金流預估')
    st.caption('依過去12個月配息紀錄 × 持有股數（市值/現價）推估未來現金流入')
    _div_data = []
    _monthly_cf = {m: 0.0 for m in range(1, 13)}
    with st.spinner('抓取配息資料...'):
        for r in rows:
            _div_s  = fetch_etf_dividends(r['ticker'])
            _price  = _cur_prices.get(r['ticker'], 0)
            _shares = int(r['current_value'] / _price) if _price > 0 else 0
            if _div_s.empty or _shares == 0:
                continue
            _cutoff  = pd.Timestamp.now() - pd.DateOffset(years=1)
            _recent  = _div_s[_div_s.index >= _cutoff]
            if _recent.empty:
                continue
            _sum = _recent.sum()
            _annual_per_share = float(np.ravel(_sum)[0]) if hasattr(_sum, '__len__') else float(_sum)
            _n_pay = len(_recent)
            _est_income = _annual_per_share * _shares
            _div_data.append({
                'ETF': r['ticker'],
                '持有股數': _shares,
                '近1年每股配息': round(_annual_per_share, 4),
                '預估年收入(元)': round(_est_income),
                '配息次數/年': _n_pay,
            })
            # 月度分配（依歷史配息月份）
            _pay_months = sorted(set(_recent.index.month.tolist()))
            for _m in _pay_months:
                _ms = _recent[_recent.index.month == _m].sum()
                _month_div = (float(np.ravel(_ms)[0]) if hasattr(_ms, '__len__') else float(_ms)) * _shares
                _monthly_cf[_m] = _monthly_cf.get(_m, 0) + _month_div

    if _div_data:
        _div_df = pd.DataFrame(_div_data)
        _div_df['預估年收入(元)'] = _div_df['預估年收入(元)'].apply(lambda x: f'{x:,}')
        st.dataframe(_div_df, use_container_width=True, hide_index=True)
        _total_annual = sum(d['預估年收入(元)'].replace(',', '')
                            if isinstance(d['預估年收入(元)'], str)
                            else d['預估年收入(元)']
                            for d in _div_data
                            if isinstance(d.get('預估年收入(元)'), (int, float)))
        # recalc from raw
        _total_annual_raw = sum(
            d['近1年每股配息'] * d['持有股數'] for d in _div_data)
        _yoc = _total_annual_raw / total_value * 100 if total_value > 0 else 0
        _colored_box(
            f'💰 組合預估年度現金流入：<b>{_total_annual_raw:,.0f} 元</b>'
            f'（組合殖利率 {_yoc:.2f}%）'
            + ('&nbsp; ✅ 每年現金流穩定，適合存股策略'
               if _yoc >= 3 else '&nbsp; 🟡 殖利率偏低，可考慮增加高息ETF比例'),
            'green' if _yoc >= 3 else 'yellow')
        if _yoc >= 5:
            _teacher_conclusion('郭俊宏',
                                f'組合殖利率 {_yoc:.2f}%，年現金流 {_total_annual_raw:,.0f} 元',
                                '殖利率優異，現金流充沛，以息養股目標達成',
                                '持續持有，配息再投入複利滾動')
        elif _yoc >= 3:
            _teacher_conclusion('郭俊宏',
                                f'組合殖利率 {_yoc:.2f}%，年現金流 {_total_annual_raw:,.0f} 元',
                                '殖利率合格，現金流穩定',
                                '可維持，視需要提高高息 ETF 比例')
        else:
            _teacher_conclusion('郭俊宏',
                                f'組合殖利率 {_yoc:.2f}%，年現金流 {_total_annual_raw:,.0f} 元',
                                '殖利率偏低，現金流不足以息養股',
                                '增加 00878/00713 等高息 ETF 比例')

        # 月度現金流長條圖
        import plotly.graph_objects as _go_div
        _fig_div = _go_div.Figure(_go_div.Bar(
            x=[f'{m}月' for m in range(1, 13)],
            y=[_monthly_cf[m] for m in range(1, 13)],
            marker_color='#3fb950',
            text=[f'{_monthly_cf[m]:,.0f}' if _monthly_cf[m] > 0 else ''
                  for m in range(1, 13)],
            textposition='auto',
        ))
        _fig_div.update_layout(
            title='未來12個月預估配息現金流（元，依歷史月份分配）',
            template='plotly_dark', height=260,
            paper_bgcolor='#0d1117', plot_bgcolor='#0d1117',
            margin=dict(l=0, r=0, t=32, b=0),
            yaxis_title='配息金額（元）',
        )
        st.plotly_chart(_fig_div, width='stretch')
    else:
        st.info('⏳ 配息資料無法取得（可能為非配息型ETF或yfinance資料限制）')

    # 存入 session_state
    st.session_state['etf_portfolio_data'] = {
        'rows': rows, 'rebal_actions': rebal_actions,
        'total_value': total_value, 'regime': regime,
        'loss_pct': loss_pct,
    }

    if gemini_fn:
        _etf_ai_portfolio(gemini_fn, rows, rebal_actions, regime, loss_pct)

    # ── 統一投資決策分析模組 ──────────────────────────────────
    render_unified_decision(gemini_fn, {
        'type': 'portfolio',
        'id':   'etf_portfolio',
        'data': {
            '組合明細': [
                {'ETF': r['ticker'],
                 '目標%': r['target_pct'],
                 '實際%': r['actual_pct'],
                 '偏離%': round(r['deviation'], 1)}
                for r in rows
            ],
            '壓力測試損失(S&P500跌20%)': f'{loss_pct:.1f}%',
            '再平衡筆數':                len(rebal_actions),
            '大盤狀態':                  regime,
        },
    })

def _etf_ai_portfolio(gemini_fn, rows, rebal_actions, regime, loss_pct):
    with st.expander('🤖 AI 組合評斷（展開）', expanded=False):
        row_txt = '\n'.join(
            f'  {r["ticker"]}：目標{r["target_pct"]}% 實際{r["actual_pct"]}% 偏離{r["deviation"]:+.1f}%'
            for r in rows)
        act_txt = '\n'.join(
            f'  {a["動作"]} {a["ETF"]} {a["金額(元)"]:,.0f}元'
            for a in rebal_actions) if rebal_actions else '  無需再平衡'
        if st.button('🤖 生成組合AI評斷', key='etf_ai_p_btn'):
            # 為組合中每檔 ETF 抓取新聞（最多各 2 則）
            _p_news_lines = []
            for _r in rows[:4]:
                _tk = _r.get('ticker', '')
                _nn = _fetch_news_for(_tk, _tk, 2)
                if _nn and _nn != '（暫無相關新聞）':
                    _p_news_lines.append(f'[{_tk}]\n{_nn}')
            _p_news_str = '\n'.join(_p_news_lines) if _p_news_lines else '（暫無相關新聞）'
            prompt = (
                f"你是ETF組合管理專家，依據以下資料給出精準建議，每項不超過200字，嚴禁捏造：\n"
                f"市場狀態：{regime}\n"
                f"組合明細：\n{row_txt}\n"
                f"再平衡指令：\n{act_txt}\n"
                f"壓力測試損失：{loss_pct:.1f}%（S&P500下跌20%模擬）\n\n"
                f"【近期各ETF相關新聞】\n{_p_news_str}\n\n"
                f"輸出：\n"
                f"1.【組合健康度】分散度、集中風險點\n"
                f"2.【再平衡必要性】是否緊急，原因\n"
                f"3.【總經視角】依{regime}市場狀態，調整方向\n"
                f"4.【一句話結論】立即行動 or 繼續觀察\n"
                f"⚠️ 僅供學術研究，非投資建議"
            )
            with st.spinner('AI 分析中...'):
                result = gemini_fn(prompt, max_tokens=900)
            if result and not result.startswith('⚠️'):
                st.session_state['etf_ai_p_result'] = result
                st.rerun()
            else:
                st.session_state['etf_ai_p_result'] = None
                st.warning(result or 'AI 回傳為空')
        _p_saved = st.session_state.get('etf_ai_p_result')
        if _p_saved:
            st.markdown(_p_saved)
            if st.button('🔄 清除', key='etf_ai_p_clear'):
                st.session_state.pop('etf_ai_p_result', None)
                st.rerun()

def _render_monte_carlo(port_val: pd.Series, initial: float, ann_vol: float,
                        n_paths: int = 10_000, n_days: int = 252) -> None:
    """
    蒙地卡羅模擬 10,000 路徑，1 年期
    使用歷史年化波動率計算日報酬標準差，幾何布朗運動隨機遊走
    顯示 10th/50th/90th percentile 區間與最終分布直方圖
    """
    try:
        daily_ret  = port_val.pct_change().dropna()
        mu_daily   = float(daily_ret.mean())
        sig_daily  = float(daily_ret.std())
        if sig_daily == 0:
            st.info('波動率為 0，無法執行蒙地卡羅模擬')
            return

        rng      = np.random.default_rng(42)
        # shape: (n_paths, n_days)
        shocks   = rng.normal(mu_daily, sig_daily, size=(n_paths, n_days))
        paths    = np.cumprod(1 + shocks, axis=1) * float(port_val.iloc[-1])

        p10  = np.percentile(paths[:, -1], 10)
        p50  = np.percentile(paths[:, -1], 50)
        p90  = np.percentile(paths[:, -1], 90)
        prob_profit = float((paths[:, -1] > float(port_val.iloc[-1])).mean() * 100)

        ca, cb, cc, cd = st.columns(4)
        ca.metric('P10（悲觀）',  f'{(p10/float(port_val.iloc[-1])-1)*100:+.1f}%')
        cb.metric('P50（中位）',  f'{(p50/float(port_val.iloc[-1])-1)*100:+.1f}%')
        cc.metric('P90（樂觀）',  f'{(p90/float(port_val.iloc[-1])-1)*100:+.1f}%')
        cd.metric('獲利機率',     f'{prob_profit:.1f}%')

        # 繪製路徑分布（取前100條 + 百分位帶）
        days_axis = list(range(n_days))
        sample_paths = paths[:100]
        fig = go.Figure()
        for i, sp in enumerate(sample_paths):
            fig.add_trace(go.Scatter(
                x=days_axis, y=sp.tolist(),
                mode='lines',
                line=dict(color='rgba(88,166,255,0.05)', width=1),
                showlegend=False,
            ))
        for label, pct, color in [
            ('P10', 10, '#f85149'), ('P50', 50, '#e3b341'), ('P90', 90, '#3fb950'),
        ]:
            band = np.percentile(paths, pct, axis=0)
            fig.add_trace(go.Scatter(
                x=days_axis, y=band.tolist(),
                mode='lines', name=label,
                line=dict(color=color, width=2),
            ))
        fig.add_hline(y=float(port_val.iloc[-1]),
                      line_dash='dot', line_color='#ffffff',
                      annotation_text='目前淨值')
        fig.update_layout(
            template='plotly_dark', height=320,
            xaxis_title='交易日', yaxis_title='資產價值（元）',
            margin=dict(l=0, r=0, t=20, b=0),
            paper_bgcolor='#0d1117', plot_bgcolor='#0d1117',
            legend=dict(orientation='h', yanchor='bottom', y=1.01),
        )
        st.plotly_chart(fig, width='stretch')
        st.caption(f'模擬條件：{n_paths:,} 路徑，日均報酬 μ={mu_daily*100:.4f}%，σ={sig_daily*100:.3f}%（基於歷史資料）⚠️ 僅供參考')
    except Exception as e:
        st.warning(f'蒙地卡羅模擬失敗：{e}')

# ═══════════════════════════════════════════════════════════════
# Tab ⑧：ETF 歷史回測與績效視覺化
# ═══════════════════════════════════════════════════════════════

def render_etf_backtest(gemini_fn=None):
    mkt_info = st.session_state.get('mkt_info', {})
    regime   = mkt_info.get('regime', 'neutral')

    st.markdown('#### 📋 回測組合設定（格式：代號,權重%）')
    default_bt = "0050.TW,50\nBND,30\n00878.TW,20"
    raw_bt = st.text_area('回測組合', value=default_bt, height=100,
                           key='etf_bt_input', label_visibility='collapsed')
    col_p, col_i, col_b = st.columns(3)
    period  = col_p.selectbox('回測期間', ['3y', '5y', '10y', '1y'],
                               index=1, key='etf_bt_period')
    initial = col_i.number_input('初始資金（元）', value=100000,
                                  step=10000, key='etf_bt_init')
    col_b.markdown('<br>', unsafe_allow_html=True)
    if col_b.button('🚀 開始回測', key='etf_bt_btn', use_container_width=True):
        st.session_state['etf_bt_active'] = True

    if not st.session_state.get('etf_bt_active'):
        st.info('💡 設定組合與期間後點擊「開始回測」')
        return

    # 解析權重
    rows = []
    for line in raw_bt.strip().splitlines():
        parts = [p.strip() for p in line.split(',')]
        if len(parts) >= 2:
            try:
                rows.append({'ticker': parts[0].upper(),
                              'weight': float(parts[1]) / 100})
            except ValueError:
                pass
    if not rows:
        st.error('❌ 請輸入有效的回測組合'); return

    # 正規化權重
    w_sum = sum(r['weight'] for r in rows)
    if abs(w_sum - 1.0) > 0.05:
        st.warning(f'⚠️ 權重合計 {w_sum*100:.0f}%，已自動正規化')
        for r in rows:
            r['weight'] /= w_sum

    # 載入資料
    with st.spinner('載入回測資料中（請稍候）...'):
        price_dict = {}
        for r in rows:
            df_t = fetch_etf_price(r['ticker'], period=period)
            if not df_t.empty:
                price_dict[r['ticker']] = df_t['Close']

    if not price_dict:
        st.error('❌ 無法取得任何ETF資料'); return

    # 對齊資料
    prices = pd.DataFrame(price_dict).ffill().dropna()
    if len(prices) < 20:
        st.error('❌ 有效資料不足，請確認代號或縮短回測期間'); return

    # ── 配息稅費磨損（台灣二代健保 × 0.95）─────────────────────
    # 所有含「.TW」的 ETF 配息乘以 0.95 扣除二代健保補充費
    apply_tax = any(t.endswith('.TW') for t in [r['ticker'] for r in rows])
    TAX_FACTOR = 0.95  # 二代健保補充費磨損（約 2.11%，取保守 5%）

    # 加權組合資產價值（含稅費磨損）
    norm     = prices / prices.iloc[0]
    weights  = {r['ticker']: r['weight'] for r in rows if r['ticker'] in norm.columns}

    # 計算各ETF配息貢獻並套用稅費磨損
    div_adjustment = {}
    for r in rows:
        t = r['ticker']
        if t not in norm.columns:
            continue
        if apply_tax and t.endswith('.TW'):
            try:
                divs_t = fetch_etf_dividends(t)
                if not divs_t.empty:
                    annual_div = float(divs_t.resample('Y').sum().mean())
                    avg_price  = float(prices[t].mean())
                    div_yield  = annual_div / avg_price if avg_price > 0 else 0
                    # 稅後磨損 = 配息 × (1 - TAX_FACTOR) 每年從報酬扣除
                    div_adjustment[t] = div_yield * (1 - TAX_FACTOR)
                else:
                    div_adjustment[t] = 0.0
            except Exception:
                div_adjustment[t] = 0.0
        else:
            div_adjustment[t] = 0.0

    port_val = sum(norm[t] * w for t, w in weights.items()) * initial

    # 套用稅費磨損（每日複利扣除）
    if apply_tax:
        n_years = len(prices) / 252
        for t, w in weights.items():
            loss_factor = (1 - div_adjustment.get(t, 0)) ** n_years
            port_val = port_val - (norm[t] * w * initial * (1 - loss_factor))

    total_tax_drag = sum(div_adjustment.get(t, 0) * w for t, w in weights.items()) * 100

    # 基準
    bench_ticker = '0050.TW' if any(t.endswith('.TW') for t in weights) else '^GSPC'
    with st.spinner(f'載入基準 {bench_ticker}...'):
        bench_df = fetch_etf_price(bench_ticker, period=period)
    bench_val = None
    if not bench_df.empty:
        bc = bench_df['Close'].reindex(prices.index).ffill().dropna()
        bench_val = bc / bc.iloc[0] * initial

    # ── 資金成長曲線 ──────────────────────────────────────────
    st.markdown('#### 📈 資金成長曲線')
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=port_val.index, y=port_val.values,
                              name='📦 ETF組合',
                              line=dict(color='#58a6ff', width=2.5)))
    if bench_val is not None:
        fig.add_trace(go.Scatter(x=bench_val.index, y=bench_val.values,
                                  name=f'📊 {bench_ticker}（基準）',
                                  line=dict(color='#3fb950', width=1.5, dash='dash')))
    fig.update_layout(
        template='plotly_dark', height=380,
        yaxis_title='資產價值（元）',
        margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor='#0d1117', plot_bgcolor='#0d1117',
        legend=dict(orientation='h', yanchor='bottom', y=1.01),
    )
    st.plotly_chart(fig, width='stretch')

    # ── 年化績效指標 ──────────────────────────────────────────
    st.markdown('#### 🏆 年化績效指標')
    port_df    = pd.DataFrame({'Close': port_val})
    cagr       = calc_cagr(port_df)
    sharpe     = calc_sharpe(port_df)
    mdd        = calc_mdd(port_df)
    vol        = round(float(port_val.pct_change().dropna().std() * (252**0.5) * 100), 2)
    final_val  = float(port_val.iloc[-1])
    cum_ret    = round((final_val - initial) / initial * 100, 2)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric('累積報酬',    f'{cum_ret:.1f}%')
    c2.metric('CAGR（年化）', f'{cagr:.2f}%')
    c3.metric('年化波動率',   f'{vol:.2f}%')
    c4.metric('夏普值',       f'{sharpe:.2f}')
    c5.metric('最大回撤',     f'{mdd:.1f}%')

    # ── 績效評級總結卡（老師標準）──────────────────────────────
    _grade_pts = 0
    if cagr >= 10:   _grade_pts += 3
    elif cagr >= 6:  _grade_pts += 2
    elif cagr >= 3:  _grade_pts += 1
    if sharpe >= 1.0:  _grade_pts += 3
    elif sharpe >= 0.5: _grade_pts += 1
    if abs(mdd) <= 10: _grade_pts += 3
    elif abs(mdd) <= 20: _grade_pts += 1
    _grade_label = ('⭐⭐⭐ 優秀' if _grade_pts >= 7 else
                    '⭐⭐ 良好' if _grade_pts >= 4 else '⭐ 普通')
    _grade_color = ('#3fb950' if _grade_pts >= 7 else
                    '#d29922' if _grade_pts >= 4 else '#f85149')
    _sharpe_note = ('夏普值≥1.0，承擔風險有充分補償' if sharpe >= 1.0 else
                    '夏普值<0.5，波動大但報酬低，需檢視配置' if sharpe < 0.5 else
                    '夏普值介於0.5-1.0，風險報酬比尚可')
    _mdd_note = ('最大回撤≤10%，心理壓力小，適合長期持有' if abs(mdd) <= 10 else
                 '最大回撤>20%，空頭時需有足夠心理準備' if abs(mdd) > 20 else
                 '最大回撤10-20%，合理範圍，按計畫執行')
    st.markdown(
        f'<div style="background:#0d1117;border:2px solid {_grade_color};border-radius:10px;'
        f'padding:12px 16px;margin:10px 0;">'
        f'<div style="font-size:16px;font-weight:900;color:{_grade_color};">📊 績效評級：{_grade_label}</div>'
        f'<div style="font-size:12px;color:#c9d1d9;margin-top:6px;">'
        f'CAGR {cagr:.2f}% | 夏普值 {sharpe:.2f} | 最大回撤 {mdd:.1f}%</div>'
        f'<div style="font-size:11px;color:#8b949e;margin-top:4px;">💡 {_sharpe_note} ／ {_mdd_note}</div>'
        f'</div>', unsafe_allow_html=True)
    # 老師動態結論
    if cagr >= 10 and sharpe >= 1.0:
        _bt_concl = f'CAGR {cagr:.1f}% + 夏普值 {sharpe:.2f}，風報比頂尖，長期持有無疑'
        _bt_act   = '全倉持有，定期再平衡'
    elif cagr >= 6 and abs(mdd) <= 20:
        _bt_concl = f'CAGR {cagr:.1f}%，最大回撤 {mdd:.1f}%，穩健成長型組合'
        _bt_act   = '維持配置，夏普值 < 1.0 可優化標的'
    elif cagr < 3:
        _bt_concl = f'CAGR {cagr:.1f}%，報酬不如定存，需重新審視配置'
        _bt_act   = '更換低費率或高 CAGR 的 ETF，如 0050 / SPY'
    else:
        _bt_concl = f'CAGR {cagr:.1f}%，最大回撤 {mdd:.1f}%，表現普通'
        _bt_act   = '評估是否增加股票型 ETF 比例以提升 CAGR'
    _teacher_conclusion('春哥', f'回測評級 {_grade_label}', _bt_concl, _bt_act)

    # ── 個別 ETF 績效 ─────────────────────────────────────────
    st.markdown('#### 📋 個別 ETF 績效')
    indiv = []
    for t, w in weights.items():
        if t in prices.columns:
            df_i = pd.DataFrame({'Close': prices[t]})
            ret_series = prices[t].pct_change().dropna()
            indiv.append({
                'ETF': t, '權重': f'{w*100:.0f}%',
                'CAGR': f'{calc_cagr(df_i):.2f}%',
                '波動率': f'{round(float(ret_series.std()*(252**0.5)*100),2):.2f}%',
                '最大回撤': f'{calc_mdd(df_i):.1f}%',
                '夏普值': f'{calc_sharpe(df_i):.2f}',
            })
    st.dataframe(pd.DataFrame(indiv), use_container_width=True, hide_index=True)

    # ── 稅費磨損提示 ──────────────────────────────────────────
    if apply_tax and total_tax_drag > 0:
        _colored_box(
            f'💸 配息稅費磨損（台灣二代健保 ×0.95）：'
            f'加權年均磨損約 <b>{total_tax_drag:.3f}%</b>，'
            f'長期持有需列入報酬估算', 'yellow')

    # ── 蒙地卡羅模擬（10,000 路徑）──────────────────────────
    st.markdown('#### 🎲 蒙地卡羅模擬（10,000 路徑，1 年）')
    _render_monte_carlo(port_val, initial, vol)

    # 存入 session_state
    st.session_state['etf_backtest_data'] = {
        'weights': weights, 'period': period, 'initial': initial,
        'cagr': cagr, 'sharpe': sharpe, 'mdd': mdd, 'vol': vol,
        'cum_ret': cum_ret, 'regime': regime,
    }

    if gemini_fn:
        _etf_ai_backtest(gemini_fn, cagr, sharpe, mdd, vol, weights, regime)

    # ── 統一投資決策分析模組 ──────────────────────────────────
    render_unified_decision(gemini_fn, {
        'type': 'portfolio',
        'id':   'etf_backtest',
        'data': {
            '組合權重':   {t: f'{w*100:.0f}%' for t, w in weights.items()},
            'CAGR':       f'{cagr:.2f}%',
            'Sharpe比率': round(sharpe, 2),
            '最大回撤MDD': f'{mdd:.1f}%',
            '年化波動率':  f'{vol:.2f}%',
            '大盤狀態':    regime,
        },
    })

def _etf_ai_backtest(gemini_fn, cagr, sharpe, mdd, vol, weights, regime):
    with st.expander('🤖 AI 回測評斷（展開）', expanded=False):
        w_txt  = ' | '.join(f'{t}: {w*100:.0f}%' for t, w in weights.items())
        if st.button('🤖 生成回測AI評斷', key='etf_ai_bt_btn'):
            # 為回測組合中每檔 ETF 抓取新聞（最多各 2 則）
            _bt_news_lines = []
            for _tk in list(weights.keys())[:4]:
                _nn = _fetch_news_for(_tk, _tk, 2)
                if _nn and _nn != '（暫無相關新聞）':
                    _bt_news_lines.append(f'[{_tk}]\n{_nn}')
            _bt_news_str = '\n'.join(_bt_news_lines) if _bt_news_lines else '（暫無相關新聞）'
            prompt = (
                f"你是回測績效分析師，依據以下數字給出精準評斷，不超過300字，嚴禁捏造：\n"
                f"組合：{w_txt}\n"
                f"CAGR：{cagr:.2f}%\n"
                f"夏普值：{sharpe:.2f}\n"
                f"最大回撤：{mdd:.1f}%\n"
                f"年化波動率：{vol:.2f}%\n"
                f"當前市場狀態：{regime}\n\n"
                f"【近期各ETF相關新聞】\n{_bt_news_str}\n\n"
                f"輸出：\n"
                f"1.【績效評級】優秀/良好/普通/劣（請說明標準）\n"
                f"2.【風險評估】MDD和波動率是否在可接受範圍\n"
                f"3.【改善建議】基於春哥/郭俊宏/孫慶龍觀點，如何優化配置\n"
                f"4.【前瞻建議】在{regime}環境下，此組合的下一步行動\n"
                f"⚠️ 僅供學術研究，非投資建議"
            )
            with st.spinner('AI 分析中...'):
                result = gemini_fn(prompt, max_tokens=900)
            if result and not result.startswith('⚠️'):
                st.session_state['etf_ai_bt_result'] = result
                st.rerun()
            else:
                st.session_state['etf_ai_bt_result'] = None
                st.warning(result or 'AI 回傳為空')
        _bt_saved = st.session_state.get('etf_ai_bt_result')
        if _bt_saved:
            st.markdown(_bt_saved)
            if st.button('🔄 清除', key='etf_ai_bt_clear'):
                st.session_state.pop('etf_ai_bt_result', None)
                st.rerun()

# ═══════════════════════════════════════════════════════════════
# Tab ⑨：ETF AI 綜合評斷
# ═══════════════════════════════════════════════════════════════

def render_etf_ai(gemini_fn=None):
    mkt_info = st.session_state.get('mkt_info', {})
    regime   = mkt_info.get('regime', 'neutral')
    macro_allocation_banner(regime)

    st.markdown('### 🤖 ETF AI 綜合評斷')
    st.caption('整合 Tab ⑥⑦⑧ 分析結果，生成跨模組綜合建議。請先在各分頁執行分析。')

    # 讀取各 Tab 存入的資料
    single_d  = st.session_state.get('etf_single_data')
    port_d    = st.session_state.get('etf_portfolio_data')
    backtest_d= st.session_state.get('etf_backtest_data')

    has_data  = any([single_d, port_d, backtest_d])

    # ── 已有資料：顯示摘要 ───────────────────────────────────
    if has_data:
        st.markdown('#### 📊 已載入分析摘要')
        summary_rows = []
        if single_d:
            summary_rows.append({
                '來源': 'Tab⑥ 單支診斷',
                '內容': f'{single_d["ticker"]} | 殖利率:{single_d["cur_yield"]:.1f}% | 總報酬:{single_d["total_ret"]:.1f}% | VCP:{single_d["vcp"]["signal"]}',
            })
        if port_d:
            summary_rows.append({
                '來源': 'Tab⑦ 組合配置',
                '內容': f'總資產:{port_d["total_value"]:,.0f}元 | 壓力測試損失:{port_d["loss_pct"]:.1f}% | 再平衡:{len(port_d["rebal_actions"])}筆',
            })
        if backtest_d:
            summary_rows.append({
                '來源': 'Tab⑧ 回測',
                '內容': f'CAGR:{backtest_d["cagr"]:.1f}% | Sharpe:{backtest_d["sharpe"]:.2f} | MDD:{backtest_d["mdd"]:.1f}% | 期間:{backtest_d["period"]}',
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

        # 建立綜合 prompt
        sections = [
            f"你是頂尖ETF投資策略師，整合以下多維度資料，給出綜合評斷。",
            f"每個評斷項目不超過300字，條列式，嚴禁捏造未提供的數據。",
            f"\n當前總經市場狀態：{regime}",
            f"建議配置：{MACRO_ALLOC.get(regime, {})}",
        ]
        if single_d:
            sections.append(
                f"\n【Tab⑥ 單支ETF診斷】{single_d['ticker']} ({single_d['name']})\n"
                f"  含息總報酬={single_d['total_ret']:.1f}% | 殖利率={single_d['cur_yield']:.1f}% | "
                f"5年均殖利率={single_d['avg_yield']:.1f}% | VCP信號={single_d['vcp']['signal']} | "
                f"折溢價={single_d['premium']['premium_pct']}% | 追蹤誤差={single_d['te']}%"
            )
        if port_d:
            acts = ', '.join(f'{a["動作"]}{a["ETF"]}' for a in port_d['rebal_actions'])
            sections.append(
                f"\n【Tab⑦ 組合配置】{len(port_d['rows'])}檔ETF | 總資產={port_d['total_value']:,.0f}元\n"
                f"  壓力測試預估損失={port_d['loss_pct']:.1f}% | 再平衡指令：{acts or '無需調整'}"
            )
        if backtest_d:
            w_txt = ' | '.join(f'{t}:{w*100:.0f}%' for t, w in backtest_d['weights'].items())
            sections.append(
                f"\n【Tab⑧ 回測績效】{backtest_d['period']} 期間 | 組合：{w_txt}\n"
                f"  CAGR={backtest_d['cagr']:.1f}% | 夏普值={backtest_d['sharpe']:.2f} | "
                f"最大回撤={backtest_d['mdd']:.1f}% | 年化波動率={backtest_d['vol']:.1f}%"
            )
        sections += [
            f"\n請輸出：",
            f"1.【整體ETF組合評級】A+/A/B/C（綜合以上所有數據）",
            f"2.【最大機會點】目前最值得加碼的方向（附理由）",
            f"3.【最大風險點】需要立即處理的警示",
            f"4.【行動清單】依優先序列出3項具體行動",
            f"5.【總經連動建議】在{regime}市場下，ETF佈局應如何因應",
            f"⚠️ 僅供學術研究與教育用途，非投資建議，盈虧自負",
        ]
        _base_prompt = '\n'.join(sections)

        if st.button('🤖 生成 ETF 綜合 AI 評斷', key='etf_ai_comp_btn', use_container_width=True):
            if not gemini_fn:
                st.warning('⚠️ 請設定 GEMINI_API_KEY 才能使用 AI 功能')
            else:
                # 收集本頁所有 ETF ticker，抓取各自新聞
                _comp_tickers = []
                if single_d:
                    _comp_tickers.append((single_d['ticker'], single_d.get('name', '')))
                if port_d:
                    for _rr in port_d.get('rows', [])[:3]:
                        _tk = _rr.get('ticker', '')
                        if _tk and (_tk, '') not in _comp_tickers:
                            _comp_tickers.append((_tk, ''))
                if backtest_d:
                    for _tk in list(backtest_d.get('weights', {}).keys())[:3]:
                        if (_tk, '') not in _comp_tickers:
                            _comp_tickers.append((_tk, ''))
                _comp_news_lines = []
                for _tk, _nm in _comp_tickers[:4]:
                    _nn = _fetch_news_for(_tk, _nm, 2)
                    if _nn and _nn != '（暫無相關新聞）':
                        _comp_news_lines.append(f'[{_tk}]\n{_nn}')
                _comp_news_str = '\n'.join(_comp_news_lines) if _comp_news_lines else '（暫無相關新聞）'
                full_prompt = _base_prompt + f'\n\n【近期各ETF相關新聞】\n{_comp_news_str}'
                with st.spinner('AI 整合分析中...'):
                    result = gemini_fn(full_prompt, max_tokens=1500)
                if result and not result.startswith('⚠️'):
                    st.session_state['etf_ai_comp_result'] = result
                    st.rerun()
                else:
                    st.error(result or 'AI 回傳為空，請確認 API Key')

        saved_result = st.session_state.get('etf_ai_comp_result')
        if saved_result:
            st.markdown('---')
            st.markdown(saved_result)
            if st.button('🔄 清除結果', key='etf_ai_comp_clear'):
                st.session_state.pop('etf_ai_comp_result', None)
                st.rerun()
    else:
        st.info(
            '📋 尚未有分析資料\n\n'
            '請先到以下頁面執行分析：\n'
            '- **Tab ⑥** 單一 ETF 深度診斷\n'
            '- **Tab ⑦** ETF 組合配置\n'
            '- **Tab ⑧** ETF 歷史回測\n\n'
            '分析完成後回到此頁，即可生成跨模組綜合評斷。'
        )

    # ── 自由提問區 ────────────────────────────────────────────
    st.markdown('---')
    st.markdown('#### 💬 ETF 自由提問')
    st.caption('不需要先執行分析，直接輸入任何ETF相關問題')
    question = st.text_area('輸入問題', height=80, key='etf_ai_question',
                             placeholder='例如：台灣高股息ETF和美國債券ETF如何搭配？')
    if st.button('💬 提問', key='etf_ai_ask_btn', use_container_width=True):
        if not question.strip():
            st.warning('請輸入問題')
        elif not gemini_fn:
            st.warning('⚠️ 請設定 GEMINI_API_KEY')
        else:
            q_prompt = (
                f"你是ETF投資教育顧問，以春哥VCP、郭俊宏以息養股、孫慶龍7%估值框架回答，"
                f"不超過300字，嚴禁捏造數據：\n\n問題：{question}\n"
                f"⚠️ 僅供學術研究，非投資建議"
            )
            with st.spinner('AI 回答中...'):
                answer = gemini_fn(q_prompt, max_tokens=600)
            if answer and not answer.startswith('⚠️'):
                st.markdown(answer)
            else:
                st.warning(answer or 'AI 回傳為空')

# ═══════════════════════════════════════════════════════════════
# Tab ⑩：資料健診儀表板
# ═══════════════════════════════════════════════════════════════

# 系統內所有需要檢測的資料源定義
_HEALTH_CHECKS = {
    'session_state': [
        ('mkt_info',        '① 市場評估',      lambda v: bool(v and v.get('regime'))),
        ('li_latest',       '① 先行指標',      lambda v: v is not None and not v.empty),
        ('etf_single_data', '⑥ ETF診斷結果',   lambda v: bool(v and v.get('ticker'))),
        ('etf_portfolio_data', '⑦ 組合配置結果', lambda v: bool(v and v.get('rows'))),
        ('etf_backtest_data',  '⑧ 回測結果',    lambda v: bool(v and v.get('cagr') is not None)),
        ('warroom_summary', '④ 戰情摘要',      lambda v: bool(v)),
    ]
}

# 美股指標 ETF（健診用）
_HEALTH_ETF_US = ['SPY', 'QQQ', 'BND', 'GLD', 'TLT']
# 台股指標 ETF
_HEALTH_ETF_TW = ['0050.TW', '00878.TW', '00713.TW', '0056.TW', '00929.TW']

def _check_icon(ok: bool, warn: bool = False) -> str:
    if ok:    return '✅'
    if warn:  return '⚠️'
    return '❌'

def _check_etf_health(ticker: str) -> dict:
    """對單一 ETF 執行資料抓取健診"""
    result = {
        'ticker': ticker,
        'price_ok': False, 'price_rows': 0, 'price_last': None,
        'div_ok': False,   'div_count': 0,
        'info_ok': False,  'info_fields': 0,
        'error': None,
    }
    try:
        df = fetch_etf_price(ticker, period='1y')
        if not df.empty:
            result['price_ok']   = True
            result['price_rows']  = len(df)
            result['price_last']  = str(df.index[-1].date())
    except Exception as e:
        result['error'] = str(e)[:80]
    try:
        divs = fetch_etf_dividends(ticker)
        result['div_ok']    = not divs.empty
        result['div_count'] = len(divs)
    except Exception:
        pass
    try:
        info = fetch_etf_info(ticker)
        filled = sum(1 for v in info.values() if v is not None and v != '')
        result['info_ok']     = filled > 5
        result['info_fields'] = filled
    except Exception:
        pass
    return result

def render_data_health():
    import pandas as _pd_dh
    import os as _os_dh
    st.markdown('### 🔎 資料健診儀表板')
    st.caption('顯示全系統每項資料的實際數值，確認為真實市場資料（非沙盒/空值）。')

    # ── 系統配置狀態卡 ────────────────────────────────────────────
    with st.expander('⚙️ 系統配置狀態（⚫缺失原因請查此處）', expanded=True):
        _fm_tok_dh = _os_dh.environ.get('FINMIND_TOKEN', '')
        _proxy_url = ''
        try:
            _proxy_url = (st.secrets.get('PROXY_URL', '')
                          or st.secrets.get('PROXY_HOST', ''))
        except Exception:
            pass
        if not _proxy_url:
            _proxy_url = (_os_dh.environ.get('HTTP_PROXY') or
                          _os_dh.environ.get('HTTPS_PROXY') or '')
        _c1, _c2 = st.columns(2)
        with _c1:
            if _fm_tok_dh:
                st.success('✅ **FINMIND_TOKEN** 已設定')
            else:
                st.error(
                    '❌ **FINMIND_TOKEN 未設定** → 月營收、財報、現金流量、'
                    '資産負債將顯示 ⚫缺失\n\n'
                    '**修復步驟：**\n'
                    '1. 至 https://finmindtrade.com 免費註冊\n'
                    '2. 建立 `.streamlit/secrets.toml`\n'
                    '3. 加入：`FINMIND_TOKEN = "你的Token"`'
                )
        with _c2:
            if _proxy_url:
                # 遮蔽密碼，只顯示 host:port
                import re as _re_dh
                _disp = _re_dh.sub(r'://[^@]+@', '://***@', _proxy_url)
                st.success(f'✅ **Proxy** 已設定：`{_disp}`')
            else:
                st.warning(
                    '⚠️ **Proxy 未設定** → 若 BLS/NDC/PMI 等總經 API '
                    '無法連線，請在 Streamlit Cloud Secrets 加入：\n\n'
                    '```\nPROXY_URL = "http://user:pass@host:3128"\n```'
                )

    # ════════════════════════════════════════════════════════════════
    # §0  全域資料新鮮度診斷（動態域分組，無寫死類別）
    # ════════════════════════════════════════════════════════════════
    st.markdown('---')
    st.markdown(
        '<div style="padding:6px 14px;background:linear-gradient(90deg,#58a6ff18,#0d1117);'
        'border-left:4px solid #58a6ff;border-radius:0 6px 6px 0;margin-bottom:10px;">'
        '<span style="font-size:14px;font-weight:900;color:#58a6ff;">📋 資料新鮮度診斷</span>'
        '<span style="font-size:11px;color:#8b949e;margin-left:8px;">'
        '各資料源最新時間戳 × 更新頻率 → 自動判定是否為最新</span></div>',
        unsafe_allow_html=True
    )
    import datetime as _dt_dh
    _today     = _pd_dh.Timestamp.now().normalize()
    _today_str = _dt_dh.date.today().strftime('%Y-%m-%d')

    # ── 直接從 session_state 組裝 live registry（不再依賴 data_registry 是否建立）──
    _reg = dict(st.session_state.get('data_registry') or {})

    # 清除舊的 ETF/個股 key（本次直接重建）
    for _k in list(_reg.keys()):
        if (_k.startswith('[個股]') or _k.startswith('[比較]')
                or (_k.startswith('[ETF]') and '|' in _k)
                or '[ETF組合]' in _k or '[ETF回測]' in _k):
            del _reg[_k]

    def _df_date(_df):
        try:
            if not isinstance(_df, _pd_dh.DataFrame) or _df.empty: return None
            if isinstance(_df.index, _pd_dh.DatetimeIndex):
                return _pd_dh.Timestamp(_df.index.max()).strftime('%Y-%m-%d')
            for _c in _df.columns:
                _cl = str(_c)
                if _cl.lower() in ('_date','date','datetime','timestamp','日期','period','quarter'):
                    _lat = _pd_dh.to_datetime(_df[_c], errors='coerce').max()
                    if _lat and not _pd_dh.isna(_lat): return _lat.strftime('%Y-%m-%d')
                if _cl == '季度標籤':
                    _lq = str(_df[_c].dropna().iloc[-1])
                    _yr_q, _qn = _lq.split('Q')
                    _qe = {"1":"03-31","2":"06-30","3":"09-30","4":"12-31"}.get(_qn,"12-31")
                    return f'{_yr_q}-{_qe}'
        except: pass
        return None

    def _live(_val, _cat, _freq):
        if _val is not None:
            return {"last_updated": _today_str, "category": _cat, "frequency": _freq}
        return {"last_updated": "N/A", "category": _cat, "frequency": _freq, "missing": True}

    def _live_df(_df, _cat, _freq):
        _d = _df_date(_df)
        if _d: return {"last_updated": _d, "category": _cat, "frequency": _freq}
        return {"last_updated": "N/A", "category": _cat, "frequency": _freq, "missing": True}

    # ── ETF 單一 ──────────────────────────────────────────────────────────
    _e1 = st.session_state.get("etf_single_data") or {}
    if _e1.get("ticker"):
        _epfx = f'[ETF] {_e1["ticker"]} {_e1.get("name","")}'.strip()
        _reg[f'{_epfx} | 價格走勢']         = _live_df(_e1.get("price_df"), "ETF", "daily")
        _e1p = _e1.get("premium") or {}
        _reg[f'{_epfx} | 折溢價率']         = _live(_e1p.get("premium_pct"), "ETF", "daily")
        _reg[f'{_epfx} | 淨值 (NAV)']       = _live(_e1p.get("nav"),          "ETF", "daily")
        for _lbl, _key, _fr in [
            ("現金殖利率","cur_yield","daily"), ("近5年平均殖利率","avg_yield","yearly"),
            ("近1年含息總報酬","total_ret","daily"), ("追蹤誤差","te","daily"),
            ("VCP 波幅收縮","vcp","daily"),    ("內控費用率","expense","yearly"),
            ("Beta","beta","daily"),           ("AuM 規模","aum","daily"),
            ("KD 技術指標","k_val","daily"),   ("年線乖離率 BIAS240","bias240","daily"),
        ]:
            _reg[f'{_epfx} | {_lbl}'] = _live(_e1.get(_key), "ETF", _fr)
    else:
        _epfx0 = '[ETF] — 尚未搜尋'
        for _lbl0, _f0 in [
            ('價格走勢','daily'), ('折溢價率','daily'), ('淨值 (NAV)','daily'),
            ('現金殖利率','daily'), ('近5年平均殖利率','yearly'),
            ('近1年含息總報酬','daily'), ('追蹤誤差','daily'),
            ('VCP 波幅收縮','daily'), ('內控費用率','yearly'),
            ('Beta','daily'), ('AuM 規模','daily'),
            ('KD 技術指標','daily'), ('年線乖離率 BIAS240','daily'),
        ]:
            _reg[f'{_epfx0} | {_lbl0}'] = {
                "last_updated": "N/A", "category": "ETF", "frequency": _f0, "missing": True}

    # ── ETF 組合 / 回測 ───────────────────────────────────────────────────
    _e2 = st.session_state.get("etf_portfolio_data") or {}
    if _e2.get("rows"):
        _reg[f'[ETF組合] 再平衡分析（{len(_e2["rows"])}檔）'] = {"last_updated":_today_str,"category":"ETF","frequency":"daily"}
    else:
        _reg["[ETF組合] 再平衡分析"] = {"last_updated":"N/A","category":"ETF","frequency":"daily","missing":True}
    _e3 = st.session_state.get("etf_backtest_data") or {}
    if _e3.get("cagr") is not None:
        _reg[f'[ETF回測] 回測績效（{len(_e3.get("weights",{}))}檔）'] = {"last_updated":_today_str,"category":"ETF","frequency":"daily"}
    else:
        _reg["[ETF回測] 回測績效"] = {"last_updated":"N/A","category":"ETF","frequency":"daily","missing":True}

    # ── 個股 ──────────────────────────────────────────────────────────────
    _t2 = st.session_state.get("t2_data") or {}
    if _t2:
        _spfx = f'[個股] {_t2.get("sid","")} {_t2.get("name",_t2.get("sid",""))}'
        for _lbl, _key, _fr in [("價格走勢","df","daily"),("月營收","rev","monthly"),("季財報","qtr","quarterly")]:
            _reg[f'{_spfx} | {_lbl}'] = _live_df(_t2.get(_key), "個股", _fr)
        _reg[f'{_spfx} | 現金流量']         = _live(_t2.get("cl"), "個股", "quarterly")
        _reg[f'{_spfx} | 資產負債']         = _live(_t2.get("cx"), "個股", "quarterly")
        _yr = _t2.get("yearly") or []
        if _yr:
            _yr_raw = str(_yr[-1].get("year",""))[:4]
            _yr_d   = min(f'{_yr_raw}-12-31', _today_str) if _yr_raw.isdigit() else _today_str
            _reg[f'{_spfx} | 年度股利'] = {"last_updated":_yr_d,"category":"個股","frequency":"yearly"}
        else:
            _reg[f'{_spfx} | 年度股利'] = {"last_updated":"N/A","category":"個股","frequency":"yearly","missing":True}
        for _lbl, _key, _fr in [
            ("健康度評分","health","daily"),("RSI","rsi","daily"),("KD (K值)","k","daily"),
            ("IBS 內部強弱","ibs","daily"),("量比 VR","vr","daily"),("布林帶","bb","daily"),
            ("VCP 波幅收縮","vcp","daily"),
        ]:
            _reg[f'{_spfx} | {_lbl}'] = _live(_t2.get(_key), "個股", _fr)
        _reg[f'{_spfx} | 合約負債/資本支出'] = _live_df(_t2.get("qtr_extra"), "個股", "quarterly")
        # ── 衍生財務指標（從 qtr/rev 計算，不額外呼叫 API）──────
        _qtr_df2  = _t2.get("qtr")
        _qtr_date2 = _df_date(_qtr_df2) if (_qtr_df2 is not None and not _qtr_df2.empty) else None
        def _has_col2(_df, *names):
            if _df is None or _df.empty: return False
            return any(
                n in _df.columns and
                not _pd_dh.to_numeric(_df[n].dropna(), errors='coerce').dropna().empty
                for n in names)
        for _fl2, _cols2 in [
            ('EPS',       ('EPS', 'eps', '每股盈餘')),
            ('稅後淨利率', ('稅後淨利率', '淨利率', '稅後淨利')),
            ('營業利益率', ('營業利益率', '營益率', '營業利益')),
        ]:
            if _qtr_date2 and _has_col2(_qtr_df2, *_cols2):
                _reg[f'{_spfx} | {_fl2}'] = {"last_updated": _qtr_date2, "category": "個股", "frequency": "quarterly"}
            else:
                _reg[f'{_spfx} | {_fl2}'] = {"last_updated": "N/A", "category": "個股", "frequency": "quarterly", "missing": True}
        _rev_df2   = _t2.get("rev")
        _rev_date2 = _df_date(_rev_df2) if (_rev_df2 is not None and not _rev_df2.empty) else None
        if _rev_date2 and len(_rev_df2) >= 2:
            _reg[f'{_spfx} | 營收季增'] = {"last_updated": _rev_date2, "category": "個股", "frequency": "monthly"}
        else:
            _reg[f'{_spfx} | 營收季增'] = {"last_updated": "N/A", "category": "個股", "frequency": "monthly", "missing": True}
    else:
        _spfx0 = '[個股] — 尚未搜尋'
        for _lbl0, _f0 in [
            ('價格走勢','daily'), ('月營收','monthly'), ('季財報','quarterly'),
            ('現金流量','quarterly'), ('資產負債','quarterly'), ('年度股利','yearly'),
            ('健康度評分','daily'), ('RSI','daily'), ('KD (K值)','daily'),
            ('IBS 內部強弱','daily'), ('量比 VR','daily'), ('布林帶','daily'),
            ('VCP 波幅收縮','daily'), ('合約負債/資本支出','quarterly'),
            ('EPS','quarterly'), ('稅後淨利率','quarterly'), ('營業利益率','quarterly'),
            ('營收季增','monthly'),
        ]:
            _reg[f'{_spfx0} | {_lbl0}'] = {
                "last_updated": "N/A", "category": "個股", "frequency": _f0, "missing": True}

    # ── 比較排行 ──────────────────────────────────────────────────────────
    _t3 = st.session_state.get("t3_data") or {}
    if _t3.get("results"):
        _reg["[比較] 多股比較排行"] = {"last_updated":_today_str,"category":"個股","frequency":"daily"}
    else:
        _reg["[比較] 多股比較排行"] = {"last_updated":"N/A","category":"個股","frequency":"daily","missing":True}

    # 無大盤資料時加佔位提示
    if not any(v.get("category")=="大盤" for v in _reg.values()):
        _reg["[大盤] — 點擊「🔄 更新全部總經數據」載入市場資料"] = {
            "last_updated":"N/A","category":"大盤","frequency":"daily","missing":True}

    _today = _pd_dh.Timestamp.now().normalize()

    # ── 純時間戳新鮮度判定（依 frequency 欄位，不依名稱猜測）────────
    _FREQ_LBL = {'daily': '📈 日更新', 'monthly': '📅 月更新',
                 'quarterly': '📊 季更新', 'yearly': '📆 年更新'}
    _CAT_ICON = {'大盤': '📊', '個股': '🔬', 'ETF': '🏦'}

    def _freshness(date_str: str, frequency: str = 'daily'):
        try:
            _age = max(0, (_today - _pd_dh.Timestamp(date_str)).days)
        except Exception:
            return '⚪', '無法解析'
        if frequency == 'yearly':
            if _age <= 365:   return '🟢', f'{_age}天前'
            elif _age <= 548: return '🟡', f'{_age}天前'
            else:             return '🔴', f'{_age}天前 ⚠️'
        elif frequency == 'quarterly':
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

    def _build_table(items):
        """items = list of (display_name, rv); 回傳標準 5 欄 DataFrame。"""
        rows = []
        for _dn, _rv in items:
            _cat  = _rv.get('category', '大盤')
            _freq = _rv.get('frequency', 'daily')
            _cat_lbl  = f'{_CAT_ICON.get(_cat, "📁")} {_cat}'
            _freq_lbl = _FREQ_LBL.get(_freq, _freq)
            if _rv.get('missing'):
                rows.append({'資料項目': _dn, '所屬類別': _cat_lbl,
                             '更新頻率': _freq_lbl, '最新資料時間': '—',
                             '狀態': '⚫ 缺失'})
            else:
                _icon, _lbl = _freshness(_rv['last_updated'], _freq)
                _status_map = {'🟢': '🟢 最新', '🟡': '🟡 略舊', '🔴': '🔴 過期'}
                rows.append({'資料項目': _dn, '所屬類別': _cat_lbl,
                             '更新頻率': _freq_lbl,
                             '最新資料時間': f'{_rv["last_updated"]}（{_lbl}）',
                             '狀態': _status_map.get(_icon, _icon)})
        _df = _pd_dh.DataFrame(rows) if rows else _pd_dh.DataFrame()
        _cols = ['資料項目', '所屬類別', '更新頻率', '最新資料時間', '狀態']
        return _df[[c for c in _cols if c in _df.columns]] if not _df.empty else _df

    def _disp_name(rn):
        """Convert registry key to user-friendly display name."""
        if '[先行指標]' in rn:
            return rn.replace('[先行指標]', '').strip()
        if '| ' in rn:
            return rn.split('| ', 1)[-1]
        for _pfx in ('[ETF組合]', '[ETF回測]', '[ETF]', '[個股]', '[比較]', '[大盤]'):
            if rn.startswith(_pfx):
                return rn[len(_pfx):].strip()
        return rn

    # ── 動態掃描 registry 中實際存在的 category（不寫死）────────────
    _categories = sorted(set(v.get('category', '未分類') for v in _reg.values()))
    _TW_KW    = ('台股', 'ADL', '新台幣', '匯率', '上漲股票', '下跌股票')
    _BOND_KW  = ('公債', '殖利率', '利率')
    _INST_KW  = ('三大法人', '融資餘額')
    _MONEY_KW = ('M1B', 'M2', '旌旗', '乖離率')
    _MACRO_KW = ('VIX', 'CPI', 'PMI', '出口', 'NDC', '景氣先行')

    _tab_labels = []
    for _cat in _categories:
        _n = sum(1 for v in _reg.values() if v.get('category', '未分類') == _cat)
        _icon = _CAT_ICON.get(_cat, '📁')
        _tab_labels.append(f'{_icon} {_cat}（{_n}項）')

    _tabs = st.tabs(_tab_labels)
    _all_items: list = []

    for _tab, _cat in zip(_tabs, _categories):
        _cat_items = [(_disp_name(rn), rv) for rn, rv in sorted(_reg.items())
                      if rv.get('category', '未分類') == _cat]
        _all_items.extend(_cat_items)

        with _tab:
            if not _cat_items:
                st.info('此類別尚無資料。')
                continue

            if _cat == '大盤':
                _raw_keys = {_disp_name(rn): rn for rn in _reg
                             if _reg[rn].get('category', '未分類') == '大盤'}
                _tw    = [(dn, rv) for dn, rv in _cat_items
                          if any(k in _raw_keys.get(dn, dn) for k in _TW_KW)]
                _bond  = [(dn, rv) for dn, rv in _cat_items
                          if any(k in _raw_keys.get(dn, dn) for k in _BOND_KW)]
                _inst  = [(dn, rv) for dn, rv in _cat_items
                          if any(k in _raw_keys.get(dn, dn) for k in _INST_KW)]
                _money = [(dn, rv) for dn, rv in _cat_items
                          if any(k in _raw_keys.get(dn, dn) for k in _MONEY_KW)]
                _macro = [(dn, rv) for dn, rv in _cat_items
                          if any(k in _raw_keys.get(dn, dn) for k in _MACRO_KW)]
                _li    = [(dn, rv) for dn, rv in _cat_items
                          if '[先行指標]' in _raw_keys.get(dn, '')]
                _used  = set(id(rv) for _, rv in _tw + _bond + _inst + _money + _macro + _li)
                _intl  = [(dn, rv) for dn, rv in _cat_items if id(rv) not in _used]
                for _title, _grp in [
                    ('🇹🇼 台股市場',  _tw),
                    ('🌐 國際指數',    _intl),
                    ('💰 固定收益',    _bond),
                    ('💼 法人 / 籌碼', _inst),
                    ('🏦 資金 / 景氣', _money),
                    ('🌏 宏觀指標',    _macro),
                    ('📈 先行指標',    _li),
                ]:
                    if not _grp:
                        continue
                    _n_bad = sum(
                        1 for _, v in _grp
                        if v.get('missing') or
                        _freshness(v.get('last_updated', ''), v.get('frequency', 'daily'))[0] == '🔴'
                    )
                    _badge = f'  ⚠️ {_n_bad}項問題' if _n_bad else '  ✅'
                    st.markdown(f'**{_title}{_badge}**')
                    st.dataframe(_build_table(_grp), use_container_width=True, hide_index=True)
                if not any([_tw, _intl, _bond, _inst, _money, _macro, _li]):
                    st.info('請先點擊「🔄 更新全部總經數據」載入市場資料。')
            elif _cat == '個股':
                _raw_keys_s = {_disp_name(rn): rn for rn in _reg
                               if _reg[rn].get('category', '未分類') == '個股'}
                _stk_items  = [(dn, rv) for dn, rv in _cat_items
                               if not _raw_keys_s.get(dn, dn).startswith('[比較]')]
                _cmp_items  = [(dn, rv) for dn, rv in _cat_items
                               if _raw_keys_s.get(dn, dn).startswith('[比較]')]
                # 個股分析
                _sk = next((k for k in _reg if k.startswith('[個股]')), '')
                _sid = _sk.split('[個股]')[-1].split('|')[0].strip() if _sk else ''
                _stk_lbl = f'🔬 個股分析（{_sid.strip()}）' if _sid and '尚未' not in _sid else '🔬 個股分析'
                _n_bad_s = sum(1 for _, v in _stk_items if v.get('missing') or
                               _freshness(v.get('last_updated',''), v.get('frequency','daily'))[0] == '🔴')
                st.markdown(f'**{_stk_lbl}{"  ⚠️ " + str(_n_bad_s) + "項問題" if _n_bad_s else "  ✅"}**')
                st.dataframe(_build_table(_stk_items), use_container_width=True, hide_index=True)
                _n_miss_s = sum(1 for _, v in _stk_items if v.get('missing'))
                if _n_miss_s:
                    st.warning(f'⚫ {_n_miss_s} 項財報資料缺失 → DSO / 負債比等指標將顯示 N/A')
                # 比較排行
                if _cmp_items:
                    _n_bad_c = sum(1 for _, v in _cmp_items if v.get('missing'))
                    st.markdown(f'**🏆 比較排行{"  ⚠️ 尚未載入" if _n_bad_c else "  ✅"}**')
                    st.dataframe(_build_table(_cmp_items), use_container_width=True, hide_index=True)
            elif _cat == 'ETF':
                _raw_keys_e = {_disp_name(rn): rn for rn in _reg
                               if _reg[rn].get('category', '未分類') == 'ETF'}
                _etf1_items = [(dn, rv) for dn, rv in _cat_items
                               if not _raw_keys_e.get(dn, dn).startswith('[ETF組合]')
                               and not _raw_keys_e.get(dn, dn).startswith('[ETF回測]')]
                _etf2_items = [(dn, rv) for dn, rv in _cat_items
                               if _raw_keys_e.get(dn, dn).startswith('[ETF組合]')]
                _etf3_items = [(dn, rv) for dn, rv in _cat_items
                               if _raw_keys_e.get(dn, dn).startswith('[ETF回測]')]
                for _etitle, _egrp in [
                    ('🏦 ETF 單一診斷',  _etf1_items),
                    ('⚖️ ETF 組合分析',  _etf2_items),
                    ('📈 ETF 回測績效',  _etf3_items),
                ]:
                    if not _egrp:
                        continue
                    _n_total_e = len(_egrp)
                    _n_bad_e   = sum(1 for _, v in _egrp if v.get('missing'))
                    _etf_loaded = _n_bad_e < _n_total_e
                    _badge = ('  ✅' if _n_bad_e == 0
                              else (f'  ⚠️ {_n_bad_e}項缺失' if _etf_loaded
                                    else '  ⚠️ 尚未載入'))
                    st.markdown(f'**{_etitle}{_badge}**')
                    st.dataframe(_build_table(_egrp), use_container_width=True, hide_index=True)
            else:
                st.dataframe(_build_table(_cat_items), use_container_width=True, hide_index=True)

    # ── 全域摘要 Banner（按分類拆解，方便對應各頁數字）──────────
    _summary_b: dict = {}  # cat -> {miss, stale, yellow}
    for _dn_b, _v_b in _all_items:
        _cb = _v_b.get('category', '未分類')
        if _cb not in _summary_b:
            _summary_b[_cb] = {'miss': 0, 'stale': 0, 'yellow': 0}
        if _v_b.get('missing'):
            _summary_b[_cb]['miss'] += 1
        else:
            _ic_b, _ = _freshness(_v_b.get('last_updated', ''), _v_b.get('frequency', 'daily'))
            if _ic_b == '🔴':
                _summary_b[_cb]['stale'] += 1
            elif _ic_b == '🟡':
                _summary_b[_cb]['yellow'] += 1

    _n_miss   = sum(d['miss']   for d in _summary_b.values())
    _n_stale  = sum(d['stale']  for d in _summary_b.values())
    _n_yellow = sum(d['yellow'] for d in _summary_b.values())

    if _n_miss or _n_stale or _n_yellow:
        _blines = ['**📊 全站資料摘要**（數字涵蓋所有分類頁，非僅當前頁）']
        if _n_miss:
            _md = ' / '.join(
                f'{_CAT_ICON.get(c, "")}{c} {d["miss"]}筆'
                for c, d in _summary_b.items() if d['miss']
            )
            _miss_names = [dn for dn, v in _all_items if v.get('missing')]
            _miss_detail = '、'.join(_miss_names[:10]) + ('…' if len(_miss_names) > 10 else '')
            _blines.append(f'⚫ **{_n_miss}筆缺失** ← {_md}')
            _blines.append(f'　　缺失：{_miss_detail}')
        if _n_stale:
            _sd = ' / '.join(
                f'{_CAT_ICON.get(c, "")}{c} {d["stale"]}筆'
                for c, d in _summary_b.items() if d['stale']
            )
            _stale_names = [dn for dn, v in _all_items
                            if not v.get('missing') and
                            _freshness(v.get('last_updated', ''), v.get('frequency', 'daily'))[0] == '🔴']
            _stale_detail = '、'.join(_stale_names[:10]) + ('…' if len(_stale_names) > 10 else '')
            _blines.append(f'🔴 **{_n_stale}筆過期** ← {_sd}')
            _blines.append(f'　　過期：{_stale_detail}')
        if _n_yellow:
            _yd = ' / '.join(
                f'{_CAT_ICON.get(c, "")}{c} {d["yellow"]}筆'
                for c, d in _summary_b.items() if d['yellow']
            )
            _yellow_names = [dn for dn, v in _all_items
                             if not v.get('missing') and
                             _freshness(v.get('last_updated', ''), v.get('frequency', 'daily'))[0] == '🟡']
            _yellow_detail = '、'.join(_yellow_names[:10]) + ('…' if len(_yellow_names) > 10 else '')
            _blines.append(f'🟡 **{_n_yellow}筆略舊** ← {_yd}')
            _blines.append(f'　　略舊：{_yellow_detail}')
        # 針對性建議
        if _summary_b.get('大盤', {}).get('stale', 0) > 0 or _summary_b.get('大盤', {}).get('yellow', 0) > 0:
            _blines.append('💡 **大盤過期/略舊** → 點擊上方「🔄 更新全部總經數據」按鈕')
        _fin_miss = _summary_b.get('個股', {}).get('miss', 0) + _summary_b.get('ETF', {}).get('miss', 0)
        if _fin_miss:
            _blines.append('💡 **個股/ETF缺失** → 確認 FINMIND_TOKEN 已設定（詳見頁頂「系統配置狀態」）')
        st.warning('\n\n'.join(_blines))
    elif _all_items:
        st.success(f'✅ 全部 {len(_all_items)} 筆資料均為最新')


    st.markdown('---')

    _cl    = st.session_state.get('cl_data', {})
    _cl_ts = st.session_state.get('cl_ts', '尚未更新')

    # ── 整體健康度概覽 ────────────────────────────────────────
    _chk = [
        bool(_cl.get('intl')), bool(_cl.get('tw')), bool(_cl.get('tech')),
        bool(_cl.get('inst')), _cl.get('margin') is not None,
        _cl.get('adl') is not None and not (hasattr(_cl.get('adl'), 'empty') and _cl['adl'].empty),
        st.session_state.get('li_latest') is not None,
        bool(st.session_state.get('m1b_m2_info')),
        bool(st.session_state.get('bias_info')),
        bool(st.session_state.get('macro_info')),
        bool(st.session_state.get('mkt_info')),
    ]
    _n_ok = sum(_chk); _n_total = len(_chk)
    _hclr = '#3fb950' if _n_ok >= _n_total * 0.8 else ('#d29922' if _n_ok >= _n_total * 0.5 else '#f85149')
    st.markdown(
        f'<div style="background:#0d1117;border:2px solid {_hclr};border-radius:10px;'
        f'padding:12px 16px;margin-bottom:16px;">'
        f'<span style="font-size:15px;font-weight:900;color:{_hclr};">系統資料健康度：{_n_ok}/{_n_total} 項已載入</span>'
        f'<span style="font-size:11px;color:#8b949e;margin-left:12px;">最後更新：{_cl_ts}</span>'
        f'<div style="font-size:11px;color:#8b949e;margin-top:4px;">'
        f'{"✅ 全部就緒" if _n_ok == _n_total else "⚠️ 部分未載入，請先點擊「更新全部總經數據」"}</div>'
        f'</div>', unsafe_allow_html=True)

    # ── 1. 國際市場指數 ───────────────────────────────────────
    _intl = _cl.get('intl', {})
    with st.expander(f'🌍 國際市場指數（DJI/SOX/TNX/DXY）  {"✅" if _intl else "❌ 尚未載入"}', expanded=bool(_intl)):
        if _intl:
            _rows = []
            for _name, _df in _intl.items():
                _s = calc_stats(_df)
                if _s is None:
                    _rows.append({'名稱': _name, '最新值': '❌', '漲跌%': '-', '狀態': '無資料'})
                    continue
                _rows.append({
                    '名稱': _name,
                    '最新值': f"{_s['last']:,.2f}",
                    '漲跌%': f"{_s['pct']:+.2f}%",
                    '狀態': _s.get('status', '-'),
                })
            st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)
        else:
            st.warning('尚未載入，請點擊「🔄 更新全部總經數據」')

    # ── 2. 台股大盤 ──────────────────────────────────────────
    _tw = _cl.get('tw', {})
    with st.expander(f'🇹🇼 台股大盤（加權/OTC/匯率）  {"✅" if _tw else "❌ 尚未載入"}', expanded=bool(_tw)):
        if _tw:
            _rows = []
            for _name, _df in _tw.items():
                _s = calc_stats(_df)
                if _s is None:
                    _rows.append({'名稱': _name, '最新值': '❌', '漲跌%': '-', '狀態': '無資料'})
                    continue
                _rows.append({
                    '名稱': _name,
                    '最新值': f"{_s['last']:,.2f}",
                    '漲跌%': f"{_s['pct']:+.2f}%",
                    '狀態': _s.get('status', '-'),
                })
            st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)
        else:
            st.warning('尚未載入')

    # ── 3. 科技股 ────────────────────────────────────────────
    _tech = _cl.get('tech', {})
    with st.expander(f'🖥️ 科技股（NVDA/MSFT/AAPL/GOOGL/AMD/TSM）  {"✅" if _tech else "❌ 尚未載入"}', expanded=bool(_tech)):
        if _tech:
            _rows = []
            for _name, _df in _tech.items():
                _s = calc_stats(_df)
                if _s is None:
                    _rows.append({'名稱': _name, '最新值': '❌', '漲跌%': '-', '狀態': '無資料'})
                    continue
                _rows.append({
                    '名稱': _name,
                    '最新值': f"{_s['last']:,.2f}",
                    '漲跌%': f"{_s['pct']:+.2f}%",
                    '狀態': _s.get('status', '-'),
                })
            st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)
        else:
            st.warning('尚未載入')

    # ── 4. 三大法人籌碼 ───────────────────────────────────────
    _inst = _cl.get('inst', {})
    _inst_date = _cl.get('inst_date', '-')
    with st.expander(f'💼 三大法人籌碼  {"✅" if _inst else "❌ 尚未載入"}  {_inst_date or ""}', expanded=bool(_inst)):
        if _inst:
            _rows = []
            for _nm, _v in _inst.items():
                _net = _v.get('net') if isinstance(_v, dict) else _v
                _dir = '🔴 買超' if (_net or 0) > 0 else ('🟢 賣超' if (_net or 0) < 0 else '─ 持平')
                _rows.append({'法人': _nm, '淨買賣（億）': f'{_net:+.1f}' if _net is not None else '-',
                               '日期': str(_inst_date or '-'), '方向': _dir})
            st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)
        else:
            st.warning('尚未載入（TWSE 封鎖，FinMind 備援）')

    # ── 5. 融資餘額 ──────────────────────────────────────────
    _margin = _cl.get('margin')
    with st.expander(f'📊 融資餘額  {"✅" if _margin is not None else "❌ 尚未載入"}', expanded=False):
        if _margin is not None:
            _mc = '#f85149' if _margin > 3400 else ('#d29922' if _margin > 2500 else '#3fb950')
            st.markdown(
                f'<div style="text-align:center;padding:12px;">'
                f'<div style="font-size:11px;color:#484f58;">融資餘額</div>'
                f'<div style="font-size:40px;font-weight:900;color:{_mc};">{_margin:,.0f}'
                f'<span style="font-size:16px;"> 億元</span></div>'
                f'<div style="font-size:11px;color:#8b949e;">>3400億=危險 ／ >2500億=警戒</div>'
                f'</div>', unsafe_allow_html=True)
        else:
            st.warning('尚未載入（TWSE 封鎖，FinMind 備援）')

    # ── 6. ADL 廣度 ──────────────────────────────────────────
    _adl = _cl.get('adl')
    _adl_ok = _adl is not None and hasattr(_adl, 'empty') and not _adl.empty
    with st.expander(f'📉 ADL 廣度指標  {"✅" if _adl_ok else "❌ 尚未載入"}', expanded=False):
        if _adl_ok:
            st.dataframe(_adl.tail(3), use_container_width=True)
            if 'ad_ratio' in _adl.columns:
                _r = float(_adl['ad_ratio'].iloc[-1])
                _rc = '#3fb950' if _r > 60 else ('#d29922' if _r > 30 else '#f85149')
                st.markdown(f'最新 ADR = <b style="color:{_rc};">{_r:.1f}%</b>（>70 市場健康 ／ <30 廣度不足）', unsafe_allow_html=True)
        else:
            _adbg = st.session_state.get('adl_debug_msg', '')
            st.warning(f'尚未載入{f"（{_adbg}）" if _adbg else ""}')

    # ── 7. 先行指標 ──────────────────────────────────────────
    _li = st.session_state.get('li_latest')
    _li_ok = _li is not None and hasattr(_li, 'empty') and not _li.empty
    with st.expander(f'📈 先行指標（期貨/選PCR/ADL/韭菜指數）  {"✅" if _li_ok else "❌ 尚未載入"}', expanded=_li_ok):
        if _li_ok:
            st.dataframe(_li.tail(3), use_container_width=True)
        else:
            st.warning('尚未載入（需 FinMind token 且已更新數據）')

    # ── 8. M1B-M2 貨幣 ───────────────────────────────────────
    _mi = st.session_state.get('m1b_m2_info', {})
    with st.expander(f'💰 M1B-M2 貨幣動能  {"✅" if _mi else "❌ 尚未載入"}', expanded=bool(_mi)):
        if _mi:
            _m1b = _mi.get('m1b_yoy'); _m2 = _mi.get('m2_yoy')
            _gap = round(_m1b - _m2, 2) if (_m1b is not None and _m2 is not None) else None
            _gc  = '#3fb950' if (_gap or 0) >= 1 else ('#d29922' if (_gap or 0) >= 0 else '#f85149')
            _rows = [
                {'指標': 'M1B YoY',  '數值': f'{_m1b:.2f}%' if _m1b is not None else '-', '說明': '狹義貨幣供給年增率'},
                {'指標': 'M2 YoY',   '數值': f'{_m2:.2f}%'  if _m2  is not None else '-', '說明': '廣義貨幣供給年增率'},
                {'指標': 'Gap',      '數值': f'{_gap:+.2f}%' if _gap is not None else '-', '說明': '>1%=熱錢進場訊號'},
                {'指標': '資料來源', '數值': _mi.get('source', '-'), '說明': 'CBC / FinMind'},
            ]
            st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)
            if _gap is not None:
                st.markdown(f'<b style="color:{_gc};">M1B-M2 Gap = {_gap:+.2f}%</b>', unsafe_allow_html=True)
        else:
            st.warning('尚未載入（CBC/FinMind，序列任務，需完整更新）')

    # ── 9. 乖離率 ────────────────────────────────────────────
    _bi = st.session_state.get('bias_info', {})
    with st.expander(f'📐 年線乖離率（BIAS）  {"✅" if _bi else "❌ 尚未載入"}', expanded=bool(_bi)):
        if _bi:
            _rows = [
                {'項目': 'BIAS20',   '值': f'{_bi.get("bias_20",  0):+.2f}%', '說明': '20日乖離率'},
                {'項目': 'BIAS60',   '值': f'{_bi.get("bias_60",  0):+.2f}%', '說明': '60日乖離率'},
                {'項目': 'BIAS240',  '值': f'{_bi.get("bias_240", 0):+.2f}%', '說明': '>15%偏貴 <-10%低估'},
                {'項目': 'MA240',    '值': f'{_bi.get("ma240",    0):,.0f}',   '說明': '年線點位'},
                {'項目': '大盤現價', '值': f'{_bi.get("price",    0):,.0f}',   '說明': '台股加權收盤'},
                {'項目': '資料天數', '值': str(_bi.get('data_days', '-')),     '說明': ''},
            ]
            st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)
        else:
            st.warning('尚未載入（yfinance TWII 2年資料）')

    # ── 10. 總經快照 ─────────────────────────────────────────
    _ma = st.session_state.get('macro_info', {})
    with st.expander(f'🌏 總經快照（VIX / CPI / PMI / NDC / 外銷訂單）  {"✅" if _ma else "❌ 尚未載入"}', expanded=bool(_ma)):
        if _ma:
            _vix = _ma.get('vix') or {}; _cpi = _ma.get('us_core_cpi') or {}
            _pmi = _ma.get('ism_pmi') or {}; _ndc = _ma.get('ndc_signal') or {}
            _exp = _ma.get('tw_export') or {}
            _rows = [
                {'指標': 'VIX 恐慌指數',
                 '數值': str(_vix.get('current', '-')),
                 '日期': str(_vix.get('dates', ['-'])[-1])[:10] if _vix.get('dates') else '-',
                 '來源': 'Yahoo Finance'},
                {'指標': 'VIX MA20',
                 '數值': str(_vix.get('ma20', '-')),
                 '日期': '-', '來源': '-'},
                {'指標': '美國核心 CPI YoY',
                 '數值': f'{_cpi["yoy"]:+.1f}%' if _cpi.get('yoy') is not None else '-',
                 '日期': str(_cpi.get('date', '-')),
                 '來源': 'FRED / DB.nomics'},
                {'指標': 'ISM PMI / OECD CLI',
                 '數值': str(_pmi.get('value', '-')),
                 '日期': str(_pmi.get('date', '-')),
                 '來源': 'OECD CLI' if _pmi.get('is_oecd_cli') else 'FRED ISM'},
                {'指標': 'NDC 景氣燈號分數',
                 '數值': f'{_ndc["score"]:.0f}/45' if _ndc.get('score') is not None else '-',
                 '日期': str(_ndc.get('date', '-')),
                 '來源': 'OECD代理估算' if _ndc.get('_is_proxy') else 'data.gov.tw'},
                {'指標': '台灣外銷訂單 YoY',
                 '數值': f'{_exp["yoy"]:+.1f}%' if _exp.get('yoy') is not None else '-',
                 '日期': str(_exp.get('date', '-')),
                 '來源': str(_exp.get('source', '-'))},
            ]
            st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)
        else:
            st.warning('尚未載入，請點擊「更新全部總經數據」')

    # ── 11. 旌旗指數 + 市場評估 ─────────────────────────────
    _jq = st.session_state.get('jingqi_info', {})
    _mk = st.session_state.get('mkt_info', {})
    with st.expander(f'🎌 旌旗指數 + 市場評估  {"✅" if _mk else "❌ 尚未載入"}', expanded=bool(_mk)):
        c_jq, c_mk = st.columns(2)
        with c_jq:
            st.markdown('**旌旗指數（市場廣度）**')
            if _jq:
                st.markdown(f'廣度均值 = **{_jq.get("avg", 0):.1f}%**（>60% 多頭健康）')
                st.markdown(f'Regime = **{_jq.get("regime", "-")}**')
            else:
                st.caption('尚未載入')
        with c_mk:
            st.markdown('**市場評估**')
            if _mk:
                _rows2 = [
                    {'項目': 'Regime',   '值': str(_mk.get('regime', '-'))},
                    {'項目': '市場評分', '值': str(_mk.get('market_score', _mk.get('score', '-')))},
                    {'項目': '建議曝險', '值': f'{_mk.get("exposure_pct", _mk.get("exposure_limit_pct", "-"))}%'},
                    {'項目': '大盤 MA5', '值': str(_mk.get('ma5', '-'))},
                    {'項目': '跌破MA5',  '值': '是 ⚠️' if _mk.get('index_below_ma5') else '否'},
                ]
                st.dataframe(pd.DataFrame(_rows2), use_container_width=True, hide_index=True)
            else:
                st.caption('尚未載入')

    # ── 12. AI 裁決報告狀態 ─────────────────────────────────
    _ai_ts  = st.session_state.get('_macro_ai_ts', '')
    _ai_rpt = st.session_state.get('_macro_ai_report', '')
    with st.expander(f'🤖 AI 裁決報告  {"✅ " + _ai_ts if _ai_rpt else "❌ 尚未執行"}', expanded=False):
        if _ai_rpt:
            st.markdown(f'**分析時間：** {_ai_ts}')
            st.markdown('**報告預覽（前300字）：**')
            st.markdown(_ai_rpt[:300] + '...')
        else:
            st.info('尚未執行 AI 裁決，前往「🌍 總經」Tab → Section 十 → 點擊「執行 AI 裁決」')

    # ── 13. 個股分析（Tab 2）────────────────────────────────
    _t2d = st.session_state.get('t2_data', {})
    _t2_sid  = _t2d.get('sid', '')
    _t2_name = _t2d.get('name', '')
    _t2_ok   = bool(_t2d and _t2_sid)
    with st.expander(
        f'🔬 個股分析 — {_t2_sid} {_t2_name}  {"✅" if _t2_ok else "❌ 尚未載入"}',
        expanded=_t2_ok):
        if _t2_ok:
            _t2_price  = _t2d.get('price', 0)
            _t2_health = _t2d.get('health', 0)
            _t2_rsi    = _t2d.get('rsi')
            _t2_k      = _t2d.get('k')
            _t2_d      = _t2d.get('d')
            _t2_vcp    = _t2d.get('vcp')
            _t2_div    = _t2d.get('avg_div', 0)
            _t2_cl     = _t2d.get('cl')
            _t2_cx     = _t2d.get('cx')
            _t2_df     = _t2d.get('df')
            _t2_rev    = _t2d.get('rev')
            _t2_qtr    = _t2d.get('qtr')
            # 技術指標表
            _rows_t2 = [
                {'項目': '現價',     '數值': f'{_t2_price:.2f}',        '說明': '最新收盤'},
                {'項目': '健康度',   '數值': f'{_t2_health:.0f}/100',   '說明': '多因子評分'},
                {'項目': 'RSI14',    '數值': f'{_t2_rsi:.1f}' if _t2_rsi else '-', '說明': '>70超買 <30超賣'},
                {'項目': 'KD-K',     '數值': f'{_t2_k:.1f}'  if _t2_k  else '-', '說明': '隨機指標 K'},
                {'項目': 'KD-D',     '數值': f'{_t2_d:.1f}'  if _t2_d  else '-', '說明': '隨機指標 D'},
                {'項目': 'VCP訊號',  '數值': '✅ 突破' if (isinstance(_t2_vcp, dict) and _t2_vcp.get('signal')) else ('整理中' if _t2_vcp else '-'), '說明': '波幅收縮型態'},
                {'項目': '平均股利',  '數值': f'{_t2_div:.2f}' if _t2_div else '-', '說明': '元/股'},
                {'項目': '合約負債',  '數值': f'{_t2_cl/1e8:.1f}億' if _t2_cl else '-', '說明': '預收款項'},
                {'項目': '資本支出',  '數值': f'{_t2_cx/1e8:.1f}億' if _t2_cx else '-', '說明': ''},
                {'項目': 'K線筆數',   '數值': f'{len(_t2_df)}筆' if _t2_df is not None and not _t2_df.empty else '-', '說明': ''},
                {'項目': '月營收筆數','數值': f'{len(_t2_rev)}筆' if _t2_rev is not None and not _t2_rev.empty else '-', '說明': ''},
                {'項目': '季財報筆數','數值': f'{len(_t2_qtr)}筆' if _t2_qtr is not None and not _t2_qtr.empty else '-', '說明': ''},
            ]
            st.dataframe(pd.DataFrame(_rows_t2), use_container_width=True, hide_index=True)
            # 財報體檢
            _fh = st.session_state.get(f'_fh_{_t2_sid}', {})
            if _fh and not _fh.get('error'):
                st.markdown('**MJ財報體檢：**')
                _rs = _fh.get('radar_scores', {})
                _fh_rows = [
                    {'項目': '現金水位', '燈號': _fh.get('cash_ratio_status', '-'), '數值': _fh.get('cash_ratio_value', '-')},
                    {'項目': 'OCF',      '燈號': _fh.get('ocf_status', '-'),        '數值': _fh.get('ocf_value', '-')},
                    {'項目': '負債比',   '燈號': _fh.get('debt_ratio_status', '-'), '數值': _fh.get('debt_ratio_value', '-')},
                    {'項目': '企業DNA',  '燈號': '',                                '數值': _fh.get('business_model_dna', '-')},
                    {'項目': '雷達均分', '燈號': '',                                '數值': f'{sum(_rs.values())/len(_rs):.1f}' if _rs else '-'},
                ]
                st.dataframe(pd.DataFrame(_fh_rows), use_container_width=True, hide_index=True)
        else:
            st.info('尚未載入個股。前往「🔬 台股 → 個股分析」輸入代碼並點擊「載入完整分析」')

    # ── 14. ETF 單支診斷 ──────────────────────────────────────
    _etf1 = st.session_state.get('etf_single_data', {})
    _etf1_ok = bool(_etf1 and _etf1.get('ticker'))
    with st.expander(
        f'🏦 ETF 單支診斷 — {_etf1.get("ticker","") if _etf1_ok else ""}  {"✅" if _etf1_ok else "❌ 尚未載入"}',
        expanded=False):
        if _etf1_ok:
            _e1_vcp  = _etf1.get('vcp', {})
            _e1_prem = _etf1.get('premium', {})
            _rows_e1 = [
                {'指標': 'ETF 代號',       '數值': _etf1.get('ticker', '-'),     '說明': ''},
                {'指標': '名稱',           '數值': _etf1.get('name', '-'),       '說明': ''},
                {'指標': '現金殖利率',     '數值': f'{_etf1.get("cur_yield", 0):.2f}%',  '說明': '最近一次配息換算'},
                {'指標': '近5年平均殖利率','數值': f'{_etf1.get("avg_yield", 0):.2f}%',  '說明': '357估值基礎'},
                {'指標': '近1年含息總報酬','數值': f'{_etf1.get("total_ret", 0):.2f}%',  '說明': ''},
                {'指標': '折溢價率',       '數值': f'{_e1_prem.get("premium_pct", "N/A")}%' if isinstance(_e1_prem, dict) else '-', '說明': 'NAV 偏離'},
                {'指標': '追蹤誤差 TE',    '數值': f'{_etf1.get("te", 0):.2f}%' if _etf1.get("te") is not None else '-', '說明': ''},
                {'指標': 'VCP 突破',       '數值': '✅ 有' if (isinstance(_e1_vcp, dict) and _e1_vcp.get('signal')) else '無', '說明': ''},
                {'指標': '大盤狀態',       '數值': _etf1.get('regime', '-'),     '說明': 'bull/neutral/bear'},
            ]
            st.dataframe(pd.DataFrame(_rows_e1), use_container_width=True, hide_index=True)
        else:
            st.info('尚未載入 ETF。前往「🏦 ETF → ETF 診斷」選擇 ETF 並點擊「開始診斷」')

    # ── 15. ETF 組合配置 ──────────────────────────────────────
    _etfp = st.session_state.get('etf_portfolio_data', {})
    _etfp_ok = bool(_etfp and _etfp.get('rows'))
    with st.expander(
        f'⚖️ ETF 組合配置  {"✅ " + str(len(_etfp.get("rows",[]))) + " 檔" if _etfp_ok else "❌ 尚未載入"}',
        expanded=False):
        if _etfp_ok:
            _p_rows = _etfp.get('rows', [])
            _display_p = [
                {'ETF': r.get('ticker','-'),
                 '目標%': f'{r.get("target_pct",0):.0f}%',
                 '實際%': f'{r.get("actual_pct",0):.1f}%',
                 '偏離%': f'{r.get("deviation",0):+.1f}%',
                 '再平衡': '⚠️ 需調整' if abs(r.get('deviation',0)) > 10 else '✅'}
                for r in _p_rows]
            st.dataframe(pd.DataFrame(_display_p), use_container_width=True, hide_index=True)
            c_tv, c_lp, c_rb = st.columns(3)
            c_tv.metric('總資產', f'{_etfp.get("total_value",0):,.0f}元')
            c_lp.metric('壓力測試損失', f'{_etfp.get("loss_pct",0):.1f}%')
            c_rb.metric('再平衡筆數', len(_etfp.get('rebal_actions',[])))
        else:
            st.info('尚未建立組合。前往「🏦 ETF → ETF 組合」設定並點擊「計算組合」')

    # ── 16. ETF 回測績效 ──────────────────────────────────────
    _etfb = st.session_state.get('etf_backtest_data', {})
    _etfb_ok = bool(_etfb and _etfb.get('cagr') is not None)
    with st.expander(
        f'📈 ETF 回測績效  {"✅ CAGR=" + str(round(_etfb.get("cagr",0),2)) + "%" if _etfb_ok else "❌ 尚未載入"}',
        expanded=False):
        if _etfb_ok:
            _w = _etfb.get('weights', {})
            _rows_b = [
                {'指標': '組合權重',   '數值': ' | '.join(f'{t}:{v*100:.0f}%' for t,v in _w.items()), '說明': ''},
                {'指標': '回測期間',   '數值': _etfb.get('period', '-'),    '說明': ''},
                {'指標': '初始資金',   '數值': f'{_etfb.get("initial",0):,.0f}元', '說明': ''},
                {'指標': 'CAGR',       '數值': f'{_etfb.get("cagr",0):.2f}%',     '說明': '年化報酬率'},
                {'指標': 'Sharpe',     '數值': f'{_etfb.get("sharpe",0):.2f}',     '說明': '>1 為優秀'},
                {'指標': 'MDD',        '數值': f'{_etfb.get("mdd",0):.1f}%',       '說明': '最大回撤'},
                {'指標': '年化波動率', '數值': f'{_etfb.get("vol",0):.2f}%',       '說明': ''},
                {'指標': '大盤狀態',   '數值': _etfb.get('regime', '-'),    '說明': ''},
            ]
            st.dataframe(pd.DataFrame(_rows_b), use_container_width=True, hide_index=True)
        else:
            st.info('尚未執行回測。前往「🏦 ETF → ETF 回測」設定並點擊「開始回測」')

    # ── 17. 財經新聞 RSS 即時驗證 ────────────────────────────

    st.markdown('---')
    st.markdown('#### 📰 財經新聞 RSS 即時驗證')
    st.caption('新聞來源（依優先順序）：Google News → Yahoo Finance → Reuters → CNBC Economy')
    if st.button('📡 即時抓取 RSS 驗證（繞過快取）', key='health_news_btn', use_container_width=True):
        try:
            import feedparser as _fp2, html as _h2
            _feeds2 = [
                ('Google News',  'https://news.google.com/rss/search?q=stock+market+economy+fed+interest+rate&hl=en-US&gl=US&ceid=US:en'),
                ('Yahoo Finance','https://finance.yahoo.com/news/rssindex'),
                ('Reuters Biz',  'https://feeds.reuters.com/reuters/businessNews'),
                ('CNBC Economy', 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258'),
            ]
            _nrows = []
            for _src2, _url2 in _feeds2:
                try:
                    _fd2 = _fp2.parse(_url2)
                    _cnt2 = len(_fd2.entries)
                    if _cnt2 > 0:
                        _t2 = _h2.unescape(_fd2.entries[0].get('title', '')).strip()[:80]
                        _nrows.append({'來源': _src2, '狀態': '✅ 正常', '則數': _cnt2, '最新標題': _t2})
                    else:
                        _nrows.append({'來源': _src2, '狀態': '⚠️ 空', '則數': 0, '最新標題': '-'})
                except Exception as _ne3:
                    _nrows.append({'來源': _src2, '狀態': f'❌ {str(_ne3)[:40]}', '則數': 0, '最新標題': '-'})
            st.dataframe(pd.DataFrame(_nrows), use_container_width=True, hide_index=True)
        except ImportError:
            st.error('feedparser 未安裝，執行 pip install feedparser')
    else:
        if _ai_ts:
            st.success(f'✅ 上次 AI 裁決執行於 {_ai_ts}（執行裁決時同步抓取新聞）')
        else:
            st.info('點擊按鈕執行即時 RSS 驗證，或前往總經 Tab 執行 AI 裁決。')

    # ── ② ETF yfinance 資料源健診（保留原版）────────────────
    st.markdown('---')
    st.markdown('#### 📡 ETF yfinance 資料源即時健診')

    custom_input   = st.text_input(
        '➕ 額外檢測代號（用逗號分隔，如 00919.TW,NVDA）',
        value='', key='health_custom')
    custom_tickers = [t.strip().upper() for t in custom_input.split(',') if t.strip()]

    used_tickers = set()
    if st.session_state.get('etf_portfolio_data'):
        for r in st.session_state['etf_portfolio_data'].get('rows', []):
            used_tickers.add(r['ticker'])
    if st.session_state.get('etf_backtest_data'):
        used_tickers.update(st.session_state['etf_backtest_data'].get('weights', {}).keys())
    if st.session_state.get('etf_single_data'):
        used_tickers.add(st.session_state['etf_single_data']['ticker'])

    scan_tickers = list(set(_HEALTH_ETF_TW + _HEALTH_ETF_US) | used_tickers | set(custom_tickers))

    if not st.button('🔬 開始全面掃描', key='health_scan_btn', use_container_width=True):
        st.info(f'將掃描 {len(scan_tickers)} 個 ETF，點擊「開始全面掃描」執行')
        st.caption('掃描列表：' + ' / '.join(scan_tickers))
    else:
        results = []
        progress = st.progress(0, text='掃描中...')
        for i, ticker in enumerate(scan_tickers):
            progress.progress((i + 1) / len(scan_tickers), text=f'掃描 {ticker}...')
            r = _check_etf_health(ticker)
            results.append(r)
        progress.empty()

        display_rows = []
        for r in results:
            p_icon = _check_icon(r['price_ok'])
            d_icon = _check_icon(r['div_ok'], warn=True)
            i_icon = _check_icon(r['info_ok'])
            overall = '✅' if (r['price_ok'] and r['info_ok']) else ('⚠️' if r['price_ok'] else '❌')
            display_rows.append({
                '整體': overall, 'ETF': r['ticker'],
                '價格資料': f"{p_icon} {r['price_rows']}筆 ({r['price_last'] or '-'})",
                '配息紀錄': f"{d_icon} {r['div_count']}筆",
                'Info欄位': f"{i_icon} {r['info_fields']}項",
                '異常': r['error'] or '-',
            })
        st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)

        ok_etf  = sum(1 for r in results if r['price_ok'] and r['info_ok'])
        warn_etf= sum(1 for r in results if r['price_ok'] and not r['info_ok'])
        fail_etf= sum(1 for r in results if not r['price_ok'])
        c1, c2, c3 = st.columns(3)
        c1.metric('✅ 完全正常',  ok_etf)
        c2.metric('⚠️ 部分缺失', warn_etf)
        c3.metric('❌ 資料抓取失敗', fail_etf)
        if fail_etf > 0:
            failed = [r['ticker'] for r in results if not r['price_ok']]
            _colored_box(f'⚠️ 以下代號無法抓取：<b>{", ".join(failed)}</b>', 'red')

    # ── ③ 快取管理 ───────────────────────────────────────────
    st.markdown('---')
    st.markdown('#### 🧹 快取管理')
    col_clr1, col_clr2 = st.columns(2)
    if col_clr1.button('🔄 清除 yfinance 快取（強制重新抓取）',
                        key='health_clear_cache', use_container_width=True):
        fetch_etf_price.clear()
        fetch_etf_dividends.clear()
        fetch_etf_info.clear()
        st.success('✅ yfinance 快取已清除，下次操作將重新從 API 抓取')
    if col_clr2.button('🗑️ 清除 ETF 分析 session（⑥⑦⑧⑨）',
                        key='health_clear_session', use_container_width=True):
        for k in ['etf_single_data', 'etf_portfolio_data',
                  'etf_backtest_data', 'etf_ai_comp_result']:
            st.session_state.pop(k, None)
        st.success('✅ ETF 分析結果已清除')
        st.rerun()

# ═══════════════════════════════════════════════════════════════
# Tab ⑪：產業熱力圖
# ═══════════════════════════════════════════════════════════════

# ── 美股 11 大 GICS 類股 ETF ─────────────────────────────────
_US_SECTORS = {
    'XLK':  {'name': '科技',        'sub': ['AAPL','MSFT','NVDA','AVGO','AMD']},
    'XLF':  {'name': '金融',        'sub': ['JPM','BAC','WFC','GS','MS']},
    'XLE':  {'name': '能源',        'sub': ['XOM','CVX','COP','SLB','MPC']},
    'XLV':  {'name': '醫療',        'sub': ['LLY','UNH','JNJ','ABBV','MRK']},
    'XLI':  {'name': '工業',        'sub': ['GE','CAT','HON','UPS','BA']},
    'XLP':  {'name': '必需消費',    'sub': ['PG','KO','PEP','COST','WMT']},
    'XLU':  {'name': '公用事業',    'sub': ['NEE','SO','DUK','AEP','D']},
    'XLB':  {'name': '原物料',      'sub': ['LIN','APD','ECL','NEM','FCX']},
    'XLRE': {'name': '房地產',      'sub': ['PLD','AMT','EQIX','CCI','SPG']},
    'XLY':  {'name': '非必需消費',  'sub': ['AMZN','TSLA','HD','MCD','NKE']},
    'XLC':  {'name': '通訊服務',    'sub': ['META','GOOGL','NFLX','DIS','T']},
}

# ── 台股類股代表 ETF/指數成分 ────────────────────────────────
_TW_SECTORS = {
    '2330.TW': {'name': '半導體',    'sub': ['2303.TW','2308.TW','2454.TW','3711.TW','2379.TW']},
    '2317.TW': {'name': '電子製造',  'sub': ['2354.TW','2356.TW','3008.TW','2382.TW','3034.TW']},
    '2412.TW': {'name': '電信',      'sub': ['3045.TW','4904.TW','2409.TW']},
    '2882.TW': {'name': '金融',      'sub': ['2881.TW','2883.TW','2884.TW','2886.TW','2891.TW']},
    '1301.TW': {'name': '塑化',      'sub': ['1303.TW','1326.TW','1402.TW']},
    '2002.TW': {'name': '鋼鐵',      'sub': ['2006.TW','2007.TW','2010.TW']},
    '1216.TW': {'name': '食品',      'sub': ['1201.TW','1210.TW','1225.TW']},
    '2603.TW': {'name': '航運',      'sub': ['2609.TW','2615.TW','2617.TW']},
    '9910.TW': {'name': '觀光',      'sub': ['2706.TW','2707.TW','2727.TW']},
    '3008.TW': {'name': '光電',      'sub': ['2409.TW','3481.TW','2475.TW']},
}

_PERIOD_MAP = {'1日': '5d', '5日': '1mo', '1月': '3mo', '3月': '6mo'}

@st.cache_data(ttl=1800)
def _fetch_sector_returns(tickers: tuple, period: str) -> dict:
    """批次抓取類股漲跌幅，回傳 {ticker: pct_change}"""
    result = {}
    try:
        raw = yf.download(list(tickers), period=period,
                          auto_adjust=True, progress=False, threads=True)
        if raw.empty:
            return result
        # yf.download 多 ticker 時 Close 為 MultiIndex
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw['Close'] if 'Close' in raw.columns.get_level_values(0) else raw.xs('Close', axis=1, level=0)
        else:
            close = raw[['Close']] if 'Close' in raw.columns else raw
        close = close.ffill().dropna(how='all')
        for t in tickers:
            if t in close.columns:
                series = close[t].dropna()
                if len(series) >= 2:
                    pct = round((float(series.iloc[-1]) / float(series.iloc[0]) - 1) * 100, 2)
                    result[t] = pct
    except Exception as e:
        st.warning(f'類股資料抓取部分失敗：{e}')
    return result

def _build_treemap_data(sectors: dict, returns: dict, market: str) -> go.Figure:
    """建立 Plotly Treemap 熱力圖"""
    ids, labels, parents, values, texts, colors = [], [], [], [], [], []

    # root
    ids.append(market)
    labels.append(market)
    parents.append('')
    values.append(0)
    texts.append('')
    colors.append(0)

    for ticker, meta in sectors.items():
        sec_ret = returns.get(ticker)
        sec_label = f"{meta['name']}<br>{sec_ret:+.1f}%" if sec_ret is not None else meta['name']
        ids.append(ticker)
        labels.append(sec_label)
        parents.append(market)
        values.append(max(abs(sec_ret) if sec_ret is not None else 1, 0.5))
        texts.append(ticker)
        colors.append(sec_ret if sec_ret is not None else 0)

        # sub-items
        for sub in meta.get('sub', []):
            sub_ret = returns.get(sub)
            sub_label = f"{sub.replace('.TW','')}<br>{sub_ret:+.1f}%" if sub_ret is not None else sub
            ids.append(f'{ticker}/{sub}')
            labels.append(sub_label)
            parents.append(ticker)
            values.append(max(abs(sub_ret) if sub_ret is not None else 0.5, 0.3))
            texts.append(sub)
            colors.append(sub_ret if sub_ret is not None else 0)

    # 顏色：最大值對稱
    max_abs = max(abs(c) for c in colors if c != 0) or 5
    fig = go.Figure(go.Treemap(
        ids=ids, labels=labels, parents=parents,
        values=values, text=texts,
        textinfo='label',
        marker=dict(
            colors=colors,
            colorscale=[[0, '#0f5132'], [0.35, '#1a6e36'], [0.5, '#1e2530'],
                        [0.65, '#c0392b'], [1, '#7b1212']],  # 台灣慣例：漲=紅 跌=綠
            cmid=0, cmin=-max_abs, cmax=max_abs,
            colorbar=dict(title='漲跌%', thickness=12),
            line=dict(width=1, color='#0d1117'),
        ),
        hovertemplate='<b>%{text}</b><br>漲跌：%{marker.color:+.2f}%<extra></extra>',
    ))
    fig.update_layout(
        template='plotly_dark',
        height=600,
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor='#0d1117',
    )
    return fig

def render_sector_heatmap():
    st.markdown('### 🗺️ 產業熱力圖')
    st.caption('即時抓取各類股漲跌幅，紅=漲 / 綠=跌（台灣慣例）。點選區塊可展開子類股。')

    col_m, col_p, col_r = st.columns([2, 2, 1])
    market = col_m.selectbox('市場', ['🇺🇸 美股（GICS 11大類）', '🇹🇼 台股（主要類股）'],
                              key='heatmap_market')
    period_label = col_p.selectbox('計算區間', list(_PERIOD_MAP.keys()),
                                    index=0, key='heatmap_period')
    col_r.markdown('<br>', unsafe_allow_html=True)
    refresh = col_r.button('🔄 刷新', key='heatmap_refresh', use_container_width=True)

    is_us = '美股' in market
    sectors = _US_SECTORS if is_us else _TW_SECTORS
    period  = _PERIOD_MAP[period_label]

    # 收集所有需抓取的 ticker（類股代表 + 子成分）
    all_tickers = list(sectors.keys())
    for meta in sectors.values():
        all_tickers.extend(meta.get('sub', []))
    all_tickers = tuple(set(all_tickers))

    if refresh:
        _fetch_sector_returns.clear()

    with st.spinner(f'抓取 {len(all_tickers)} 個標的資料（{period_label}）...'):
        returns = _fetch_sector_returns(all_tickers, period)

    if not returns:
        st.error('❌ 無法取得任何類股資料，請確認網路連線')
        return

    # ── Treemap 主圖 ──────────────────────────────────────────
    market_label = '美股 GICS' if is_us else '台股類股'
    fig = _build_treemap_data(sectors, returns, market_label)
    st.plotly_chart(fig, width='stretch')

    # ── 數值排行表（補充用）──────────────────────────────────
    st.markdown(f'#### 📊 {market_label} 類股漲跌排行（{period_label}）')
    rank_rows = []
    for ticker, meta in sectors.items():
        ret = returns.get(ticker)
        rank_rows.append({
            '類股': meta['name'],
            '代號': ticker,
            f'{period_label}漲跌%': ret if ret is not None else 'N/A',
            '方向': ('📈 上漲' if ret and ret > 0 else ('📉 下跌' if ret and ret < 0 else '➡️ 持平')),
        })
    rank_rows.sort(key=lambda x: x[f'{period_label}漲跌%']
                   if isinstance(x[f'{period_label}漲跌%'], float) else 0, reverse=True)
    rank_df = pd.DataFrame(rank_rows)
    st.dataframe(rank_df, use_container_width=True, hide_index=True)

    # 覆蓋率說明
    fetched = sum(1 for t in sectors if returns.get(t) is not None)
    total_s = len(sectors)
    if fetched < total_s:
        _colored_box(
            f'⚠️ 僅取得 {fetched}/{total_s} 個類股資料，部分可能因 yfinance 限速或市場休市而缺失',
            'yellow')
    else:
        _colored_box(f'✅ 全部 {total_s} 個類股資料取得完整', 'green')


# ══════════════════════════════════════════════════════════════════
# 資料診斷 v2：嚴格 Raw-only 版
# ══════════════════════════════════════════════════════════════════
def render_data_health_raw():
    """
    只顯示從網路 API 直接抓取的第一手原始資料。
    絕對禁止：均線 / RSI / 乖離率 / AI 評分等任何計算值。
    欄位：資料名稱 | 最後更新 | 狀態燈號
    """
    import pandas as _pd_r
    import datetime as _dt_r

    _today = _pd_r.Timestamp.now().normalize()

    def _last_date(df):
        """從 DataFrame 取最新日期字串 YYYY-MM-DD"""
        try:
            if df is None or (hasattr(df, 'empty') and df.empty):
                return None
            if isinstance(df.index, _pd_r.DatetimeIndex):
                v = _pd_r.Timestamp(df.index.max())
                return v.strftime('%Y-%m-%d') if not _pd_r.isna(v) else None
            for col in (['_date', 'date', 'Date', '日期', 'period', 'quarter', '季度標籤']
                        if hasattr(df, 'columns') else []):
                if col in df.columns:
                    v = _pd_r.to_datetime(df[col], errors='coerce').max()
                    if not _pd_r.isna(v):
                        return v.strftime('%Y-%m-%d')
        except Exception:
            pass
        return None

    def _light(date_str, freq='daily'):
        """回傳 (icon, label)；freq: daily / monthly / quarterly / yearly"""
        if not date_str:
            return '🔴', '未取得'
        try:
            age = max(0, (_today - _pd_r.Timestamp(date_str)).days)
        except Exception:
            return '🔴', '無法解析'
        th = {'daily': 3, 'monthly': 45, 'quarterly': 90, 'yearly': 365}
        limit = th.get(freq, 3)
        if age <= limit:
            lbl = '今天' if age == 0 else ('昨天' if age == 1 else f'{age}天前')
            return '🟢', lbl
        return '🔴', f'{age}天前 ⚠️'

    def _row(name, date_str, freq='daily'):
        icon, lbl = _light(date_str, freq)
        return {'資料名稱': name, '最後更新': lbl, '狀態': icon}

    def _tbl(rows):
        if not rows:
            st.info('尚無資料（請先觸發對應的抓取動作）')
            return
        st.dataframe(_pd_r.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── 標題 ─────────────────────────────────────────────────────
    st.markdown('### 🔎 原始資料健診儀表板')
    st.caption(
        '📌 **僅顯示從網路 API 直接抓取的第一手原始資料**。'
        '均線、RSI、乖離率、AI 評分等計算指標**不在此列**。'
    )

    # ════ 1. 總經 Raw ════════════════════════════════════════════
    with st.expander('🌍 總經 Raw Data', expanded=True):
        _ma = st.session_state.get('macro_info') or {}
        rows = []
        for label, key, freq in [
            ('VIX 恐慌指數（CBOE / dbnomics）',           'vix',       'daily'),
            ('CPI 消費者物價指數（IMF / dbnomics）',        'cpi',       'monthly'),
            ('ISM PMI / OECD CLI（dbnomics）',             'pmi',       'monthly'),
            ('NDC 景氣燈號分數（data.gov.tw / OECD CLI）',  'ndc',       'monthly'),
            ('台灣出口 YoY（FinMind TaiwanExportImport）',  'tw_export', 'monthly'),
        ]:
            item = _ma.get(key) or {}
            date = (item.get('date') or item.get('period') or
                    str(item.get('year', ''))[:7] or None)
            rows.append(_row(label, str(date)[:10] if date else None, freq))
        # M1B / M2
        _mi = st.session_state.get('m1b_m2_info') or {}
        _mi_date = str(_mi.get('date', '') or '')[:10] or None
        if not _mi_date and _mi.get('m1b_yoy') is not None:
            _mi_date = str(st.session_state.get('cl_ts', ''))[:10] or None
        rows.append(_row('M1B / M2 貨幣供給（CBC cpx.cbc.gov.tw / FinMind）', _mi_date, 'monthly'))
        _tbl(rows)
        st.caption('⚠️ M1B-M2 利差、年增率為計算值，不顯示於此。')

    # ════ 2. 大盤指數 & 籌碼 Raw ═════════════════════════════════
    with st.expander('📊 大盤指數 & 籌碼 Raw Data', expanded=True):
        _cl = st.session_state.get('cl_data') or {}
        _cl_ts = str(st.session_state.get('cl_ts', ''))[:10] or None
        rows = []
        for gkey, glabel in [
            ('intl',  '國際指數 OHLCV（yfinance：SPY/QQQ/MSCI 等）'),
            ('tw',    '台股指數 OHLCV（yfinance：^TWII/^TWOII 等）'),
            ('tech',  '科技股指數 OHLCV（yfinance：SOXX/SMH 等）'),
        ]:
            grp = _cl.get(gkey) or {}
            dates = [_last_date(df) for df in grp.values()
                     if isinstance(df, _pd_r.DataFrame)] if isinstance(grp, dict) else []
            dates = [d for d in dates if d]
            rows.append(_row(glabel, max(dates) if dates else _cl_ts, 'daily'))

        for key, label in [
            ('inst',         '三大法人現貨買賣超（TWSE BFI82U）'),
            ('margin',       '融資餘額（TWSE MI_MARGN）'),
            ('margin_ratio', '融資維持率%（TWSE MI_MARGN）'),
        ]:
            val = _cl.get(key)
            date = (_last_date(val) if isinstance(val, _pd_r.DataFrame)
                    else (_cl_ts if val is not None else None))
            rows.append(_row(label, date, 'daily'))

        _adl = _cl.get('adl')
        rows.append(_row(
            'ADL 漲跌家數（yfinance ^TWII 估算 + TWSE MI_INDEX 精確值）',
            _last_date(_adl) if isinstance(_adl, _pd_r.DataFrame) else _cl_ts,
            'daily'))
        _tbl(rows)
        st.caption('⚠️ ADL 累計值、年線乖離率為計算值，不顯示於此。')

    # ════ 3. 先行指標 Raw ════════════════════════════════════════
    with st.expander('📈 先行指標 Raw Data', expanded=False):
        _li = st.session_state.get('li_latest')
        _li_date = _last_date(_li) if isinstance(_li, _pd_r.DataFrame) else None
        rows = [
            _row('外資期貨留倉（FinMind TaiwanFuturesInstitutionalInvestors TX+MTX）',
                 _li_date, 'daily'),
            _row('選擇權法人部位（FinMind TaiwanOptionInstitutionalInvestors TXO）',
                 _li_date, 'daily'),
            _row('三大法人現貨（FinMind TaiwanStockTotalInstitutionalInvestors）',
                 _li_date, 'daily'),
        ]
        _tbl(rows)
        st.caption('⚠️ PCR 比率、外資期貨淨額（多−空×0.25）為計算值，不顯示於此。')

    # ════ 4. 個股 Raw ════════════════════════════════════════════
    with st.expander('🔬 個股 Raw Data', expanded=True):
        _t2 = st.session_state.get('t2_data') or {}
        if not _t2:
            st.info('尚未載入個股。前往「🔬 個股」Tab 輸入代碼並點擊「載入完整分析」')
        else:
            sid2 = _t2.get('sid', '')
            name2 = _t2.get('name', sid2)
            st.markdown(f'**當前個股：{name2}（{sid2}）**')
            rows = []
            rows.append(_row(f'K線 OHLCV（FinMind / yfinance）',
                             _last_date(_t2.get('df')), 'daily'))
            rows.append(_row(f'月營收（FinMind TaiwanStockMonthRevenue）',
                             _last_date(_t2.get('rev')), 'monthly'))
            rows.append(_row(f'季損益表 EPS/毛利率/利益率（FinMind TaiwanStockFinancialStatement）',
                             _last_date(_t2.get('qtr')), 'quarterly'))
            rows.append(_row(f'季 BS+CF 時序 存貨/合約負債/CapEx（FinMind）',
                             _last_date(_t2.get('qtr_extra')), 'quarterly'))
            # 合約負債（純 raw 值，非時序）
            _cl2 = _t2.get('cl')
            _cl2_date = (_last_date(_cl2) if isinstance(_cl2, _pd_r.DataFrame)
                         else (str(_dt_r.date.today()) if _cl2 is not None else None))
            rows.append(_row(f'合約負債（FinMind TaiwanStockBalanceSheet）',
                             _cl2_date, 'quarterly'))
            # 股利
            _yr = _t2.get('yearly') or []
            _yr_date = None
            if _yr:
                _yr_raw = str(_yr[-1].get('year', ''))[:4]
                _yr_date = f'{_yr_raw}-12-31' if _yr_raw.isdigit() else None
            rows.append(_row(f'股利歷史（FinMind TaiwanStockDividend）', _yr_date, 'yearly'))
            # MJ 體檢財報
            _fh2 = st.session_state.get(f'_fh_{sid2}')
            _fh2_date = (str(_dt_r.date.today())
                         if _fh2 and not _fh2.get('error') else None)
            rows.append(_row(f'MJ體檢財報原始 BS+CF+IS（FinMind 3 datasets）',
                             _fh2_date, 'quarterly'))
            _tbl(rows)
            st.caption('⚠️ RSI / KD / 布林帶 / 健康度評分 / FGMS / SQ 等由 K線/財報計算，不顯示於此。')

    # ════ 5. ETF Raw ═════════════════════════════════════════════
    with st.expander('🏦 ETF Raw Data', expanded=True):
        _e1 = st.session_state.get('etf_single_data') or {}
        if not _e1.get('ticker'):
            st.info('尚未載入 ETF。前往「🏦 ETF」Tab 輸入代號並診斷。')
        else:
            tk = _e1.get('ticker', '')
            nm = _e1.get('name', tk)
            st.markdown(f'**當前 ETF：{nm}（{tk}）**')
            rows = []
            _pdf = _e1.get('price_df')
            rows.append(_row(f'ETF K線 OHLCV {tk}（yfinance auto_adjust=True）',
                             _last_date(_pdf), 'daily'))
            # AUM / Beta / 費用率：原始 yfinance .info 欄位
            _has_info = bool(_e1.get('aum') or _e1.get('beta') or _e1.get('expense'))
            rows.append(_row(f'ETF 基本資訊 AUM/Beta/費用率（yfinance .info）',
                             str(_dt_r.date.today()) if _has_info else None, 'daily'))
            # NAV 淨值
            _prem = _e1.get('premium') or {}
            _nav_ok = _prem.get('nav') is not None
            rows.append(_row(f'NAV 淨值（FinMind TaiwanETFNetAssetValue / TWSE OpenAPI）',
                             str(_dt_r.date.today()) if _nav_ok else None, 'daily'))
            # ETF 組合：多標的 K線
            _ep = st.session_state.get('etf_portfolio_data') or {}
            _tickers_p = [r.get('ticker') for r in (_ep.get('rows') or [])]
            if _tickers_p:
                rows.append(_row(f'ETF 組合 K線 {_tickers_p}（yfinance）',
                                 str(_dt_r.date.today()), 'daily'))
            _tbl(rows)
            st.caption('⚠️ 殖利率、追蹤誤差、CAGR、Sharpe、折溢價率為計算值，不顯示於此。')
