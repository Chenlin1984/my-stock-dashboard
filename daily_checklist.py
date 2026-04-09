"""
daily_checklist.py v4 — 完全無需Token版
三大法人: TWSE /fund/BFI82U (逐日回溯，收盤後更新)
融資餘額: TWSE /rwd/zh/marginTrading/MI_MARGN
其他: yfinance
"""
import requests, pandas as pd, datetime, os, time
import urllib3; urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_TWSE_CK = requests.Session(); _TWSE_CK.verify = False  # TWSE SSL fix (Python 3.14)
import streamlit as st
import plotly.graph_objects as go

FINMIND_TOKEN = os.environ.get('FINMIND_TOKEN', '')
HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.twse.com.tw/",
    "X-Requested-With": "XMLHttpRequest",
}
COLORS_7 = ["#58a6ff","#3fb950","#ffd700","#f85149","#bc8cff","#79c0ff","#ff9f43"]
INTL_MAP = {"道瓊工業 DJI":"^DJI","納斯達克 IXIC":"^IXIC","費城半導體 SOX":"^SOX","10Y公債殖利率":"^TNX","美元指數 DXY":"DX=F"}
INTL_UNIT = {k:("%" if "殖利率" in k else "指數") for k in INTL_MAP}
TW_MAP   = {"台股加權指數":"^TWII","新台幣匯率":"TWD=X"}
TW_UNIT  = {"台股加權指數":"pts","新台幣匯率":"TWD/USD"}
TECH_MAP = {"台積電 ADR":"TSM","微軟 MSFT":"MSFT","蘋果 AAPL":"AAPL","谷歌 GOOGL":"GOOGL","輝達 NVDA":"NVDA","AMD":"AMD","博通 AVGO":"AVGO"}

def _num(s):
    try: return float(str(s).replace(",","").replace(" ","").replace("+",""))
    except: return None

_TW_TZ_DL = datetime.timezone(datetime.timedelta(hours=8))

def _tw_today_dl():
    return datetime.datetime.now(_TW_TZ_DL).date()

def _recent_date(fmt="%Y%m%d"):
    d = _tw_today_dl()
    # 週末直接退到週五
    while d.weekday() >= 5: d -= datetime.timedelta(days=1)
    return d.strftime(fmt)

# ═══════════════════════════════════════════════
# 三大法人 — TWSE /fund/BFI82U
# 收盤後15:30才有當日資料
# ═══════════════════════════════════════════════
def fetch_institutional(date_str=None):
    if date_str is None: date_str = _recent_date()
    base = datetime.datetime.strptime(date_str, "%Y%m%d").date()

    _bfi_urls = [
        "https://www.twse.com.tw/rwd/zh/fund/BFI82U",  # 新版優先
        "https://www.twse.com.tw/fund/BFI82U",          # 舊版備援
    ]

    for delta in range(5):   # 最多找 5 個交易日（避免 timeout）
        d = base - datetime.timedelta(days=delta)
        if d.weekday() >= 5: continue
        ds = d.strftime("%Y%m%d")
        try:
            _bfi_j = None
            for _bfi_url in _bfi_urls:
                try:
                    _bfi_r = _TWSE_CK.get(_bfi_url, params={"response":"json","dayDate":ds},
                                          headers=HDR, timeout=10)
                    _bfi_j = _bfi_r.json()
                    if _bfi_j.get("stat") == "OK" and _bfi_j.get("data"):
                        print(f"[BFI82U] ✅ {_bfi_url.split('/')[-3]}")
                        break
                except Exception as _be:
                    print(f"[BFI82U] {_bfi_url}: {_be}")
            j = _bfi_j or {}
            # (舊版殘留的 j = r.json() 已移除，r 在新架構下未定義)
            if j.get("stat")=="OK" and j.get("data"):
                result = {}
                fields = [str(f) for f in j.get("fields", [])]
                print(f"[TWSE法人] {ds} fields={fields}")
                # BFI82U 欄位: 單位名稱/買進金額/賣出金額/買賣差額/買進張數/賣出張數/買賣差張數
                # 金額單位：千元；買賣差額 = row[3]；/1e5 → 億
                _diff_idx = 3  # 買賣差額(千元)
                if fields:
                    _diff_idx = next((i for i,f in enumerate(fields)
                                     if '差額' in f and '張' not in f), 3)
                _raw = {}
                for row in j["data"]:
                    name = str(row[0]).strip()
                    if "合計" in name: continue
                    if len(row) > _diff_idx:
                        v = _num(row[_diff_idx])
                        if v is not None:
                            _raw[name] = round(v/1e8, 2)
                            print(f'[BFI82U] {name}: {v:,.0f}元 → {v/1e8:.2f}億')
                # 合併/重命名成統一 key 名稱
                if _raw:
                    # 自營商 = 自行買賣 + 避險
                    _dealer = sum(v for k,v in _raw.items() if '自營商' in k)
                    # 外資 = 外資及陸資(不含外資自營商)
                    _foreign = next((v for k,v in _raw.items()
                                     if '外資' in k and '陸資' in k), None)
                    if _foreign is None:
                        _foreign = next((v for k,v in _raw.items()
                                         if '外資' in k), 0)
                    # 投信
                    _trust = next((v for k,v in _raw.items() if '投信' in k), 0)
                    result = {
                        '外資及陸資': {'net': round(_foreign, 2)},
                        '投信':       {'net': round(_trust, 2)},
                        '自營商':     {'net': round(_dealer, 2)},
                    }
                    print(f'[TWSE法人] ✅ {ds}: 外資={_foreign:.1f} 投信={_trust:.1f} 自營={_dealer:.1f}億')
                    return result, ds
            else:
                print(f"[TWSE法人] {ds}: stat={j.get('stat')}, 嘗試往前一日")
        except Exception as e:
            print(f"[TWSE法人] {ds}: {e}")
        pass  # removed sleep for speed

    # ── 備援1: TWSE OpenAPI /v1/fund/BFI82U（新版，無需 Cookie）
    try:
        _r_oa = _TWSE_CK.get(
            'https://openapi.twse.com.tw/v1/fund/BFI82U',
            headers={'Accept':'application/json','User-Agent':'Mozilla/5.0'}, timeout=10)
        if _r_oa.status_code == 200:
            _j_oa = _r_oa.json()
            if isinstance(_j_oa, list) and _j_oa:
                _result_oa = {}
                for _row_oa in _j_oa:
                    _nm = str(_row_oa.get('InvestorType','')).strip()
                    if not _nm or '合計' in _nm: continue
                    _net_oa = None
                    for _k in ['buy','BuyAmount','NetBuySell','diff']:
                        if _k in _row_oa:
                            try: _net_oa = float(str(_row_oa[_k]).replace(',',''))
                            except: pass
                            if _net_oa is not None: break
                    if _net_oa is not None:
                        _result_oa[_nm] = {'net': round(_net_oa/1e8, 2)}
                if _result_oa:
                    _ds_oa = today.strftime('%Y%m%d')
                    print(f'[TWSE-OpenAPI法人] ✅ {_ds_oa}: {list(_result_oa.keys())}')
                    return _result_oa, _ds_oa
    except Exception as _e_oa:
        print(f'[TWSE-OpenAPI法人] ❌ {type(_e_oa).__name__}: {_e_oa}')

    # ── 備援2: FinMind TaiwanStockTotalInstitutionalInvestors（公開資料，無需 Token）
    try:
        start = (datetime.date.today()-datetime.timedelta(days=7)).strftime('%Y-%m-%d')
        _fm_p2 = {"dataset":"TaiwanStockTotalInstitutionalInvestors","start_date":start}
        if FINMIND_TOKEN: _fm_p2["token"] = FINMIND_TOKEN
        r2 = requests.get("https://api.finmindtrade.com/api/v4/data",
                          params=_fm_p2,
                          headers={"Authorization":f"Bearer {FINMIND_TOKEN}"} if FINMIND_TOKEN else {},
                          timeout=20)
        j2 = r2.json()
        if j2.get("status")==200 and j2.get("data"):
            df = pd.DataFrame(j2["data"]); last = df["date"].max()
            dd = df[df["date"]==last]; result={}
            _dealer_net = 0.0
            for _,row in dd.iterrows():
                nm=str(row.get("name",""))
                b=float(pd.to_numeric(row.get("buy",0),errors='coerce') or 0)
                s=float(pd.to_numeric(row.get("sell",0),errors='coerce') or 0)
                net_v = round((b-s)/1e8, 2)
                # 相容 FinMind 英文名稱（Foreign_Investor）與中文名稱（外資及陸資）
                _is_foreign = nm == 'Foreign_Investor' or ('外資' in nm and '自營' not in nm)
                _is_trust   = nm == 'Investment_Trust'  or '投信' in nm
                _is_dealer  = nm in ('Dealer_self', 'Dealer_Hedging') or '自營' in nm
                if _is_foreign:
                    result['外資及陸資'] = {'net': net_v}
                elif _is_trust:
                    result['投信'] = {'net': net_v}
                elif _is_dealer:
                    _dealer_net += net_v
            if _dealer_net != 0:
                result['自營商'] = {'net': round(_dealer_net, 2)}
            if result:
                print(f"[FM法人] ✅ {last}: 外資={result.get('外資及陸資',{}).get('net',0):.1f} 投信={result.get('投信',{}).get('net',0):.1f} 自營={result.get('自營商',{}).get('net',0):.1f}億")
                return result, str(last)
    except Exception as e:
        print(f"[FM法人] {e}")
    return {}, date_str


# ═══════════════════════════════════════════════
# 融資餘額 — TWSE /rwd/zh/marginTrading/MI_MARGN
# ═══════════════════════════════════════════════
def fetch_margin_balance(date_str=None):
    """
    融資餘額抓取 v2 — 三層備援：
    1. TWSE MI_MARGN (selectType=MS 上市，抓最後合計行)
    2. TWSE MI_MARGN (selectType=ALL 全市場)
    3. FinMind TaiwanStockTotalMarginPurchaseShortSale
    單位：億元
    """
    today = _tw_today_dl()
    # 往前最多找15個交易日
    candidates = []
    d = today
    for _ in range(20):
        if d.weekday() < 5:
            candidates.append(d)
        d -= datetime.timedelta(days=1)
        if len(candidates) >= 15: break

    for _d in candidates:
        ds = _d.strftime('%Y%m%d')
        for _sel in ['MS', 'ALL']:
            try:
                r = _TWSE_CK.get(
                    'https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN',
                    params={'date': ds, 'selectType': _sel, 'response': 'json'},
                    headers={**HDR, 'Referer': 'https://www.twse.com.tw/zh/trading/margin/mi-margn.html'},
                    timeout=15)
                j = r.json()
                if j.get('stat') != 'OK':
                    continue
                data = j.get('data', [])
                if not data:
                    continue
                # 找 fields 確認欄位
                fields = [str(f) for f in j.get('fields', [])]
                print(f'[融資/{_sel}/{ds}] fields={fields[:8]}')
                # 動態找「融資餘額」欄位 index
                margin_col = next(
                    (i for i, f in enumerate(fields)
                     if '融資' in f and '餘額' in f and '限' not in f), None)
                if margin_col is None:
                    # 嘗試固定 index（舊格式 index=6）
                    margin_col = 6
                # 全市場合計通常在最後一行（台股總計）
                for row in reversed(data):
                    if len(row) <= margin_col: continue
                    raw = str(row[margin_col]).replace(',', '').replace(' ', '')
                    try:
                        v = float(raw)
                    except:
                        continue
                    # TWSE 融資餘額單位：千元
                    # 2500億 = 250,000,000千元
                    if v > 100_000_000:   # > 1兆千元 → 太大，跳過
                        continue
                    if v > 10_000_000:    # > 100億千元 = > 1000億元 → 合理
                        result = round(v / 100_000, 1)  # 千元→億元
                        print(f'[融資/{_sel}/{ds}] ✅ col{margin_col}: {v:.0f}千元 = {result}億')
                        return result
                    elif v > 1_000_000:   # > 10億千元 = > 100億元 → 也可能是對的（單位可能是萬元）
                        result = round(v / 10_000, 1)   # 萬元→億元
                        if 500 < result < 10000:        # 合理範圍 500~10000億
                            print(f'[融資/{_sel}/{ds}] ✅ col{margin_col}(萬元): {v:.0f} = {result}億')
                            return result
            except Exception as _e:
                print(f'[融資/{_sel}/{ds}] {_e}')
        pass  # removed sleep for speed：0.3→0.1

    # FinMind 備援
    # Token 優先順序：1.傳入參數 2.環境變數 3.模組變數
    _fm_tok = (os.environ.get('FINMIND_TOKEN', '') or
               FINMIND_TOKEN or
               os.environ.get('FM_TOKEN', ''))
    if not _fm_tok:
        print('[融資] ⚠️ 未設定 FinMind Token，跳過 FinMind 備援')
    if _fm_tok:
        try:
            start = (today - datetime.timedelta(days=10)).strftime('%Y-%m-%d')
            r2 = requests.get(
                'https://api.finmindtrade.com/api/v4/data',
                params={'dataset': 'TaiwanStockTotalMarginPurchaseShortSale',
                        'start_date': start, 'token': _fm_tok},
                headers={'Authorization': f'Bearer {_fm_tok}'}, timeout=20)
            j2 = r2.json()
            print(f'[FM融資] status={j2.get("status")} rows={len(j2.get("data",[]))}')
            if j2.get('status') == 200 and j2.get('data'):
                df2 = pd.DataFrame(j2['data'])
                print(f'[FM融資] columns={list(df2.columns)}')
                # 篩選融資行
                if 'name' in df2.columns:
                    df2 = df2[df2['name'].str.contains('融資|MarginPurchase', na=False, case=False)]
                if not df2.empty:
                    last_date = df2['date'].max()
                    row2 = df2[df2['date'] == last_date].iloc[-1]
                    # 嘗試多個欄位名稱
                    for col in ['TodayBalance', 'today_balance', 'balance',
                                'MarginPurchaseBalance', 'marginBalance']:
                        if col in row2.index:
                            v2 = float(pd.to_numeric(row2[col], errors='coerce') or 0)
                            if v2 > 0:
                                # FinMind 單位通常是元，需轉億
                                if v2 > 1e12:    result2 = round(v2 / 1e8, 1)
                                elif v2 > 1e9:   result2 = round(v2 / 1e8, 1)
                                elif v2 > 1e4:   result2 = round(v2 / 100, 1)  # 可能是萬元
                                else:            result2 = round(v2, 1)
                                if 500 < result2 < 10000:  # 合理範圍
                                    print(f'[FM融資] ✅ {col}={v2} → {result2}億')
                                    return result2
        except Exception as _e2:
            print(f'[FM融資 ERROR] {_e2}')

    print('[融資] 所有來源均無資料')
    return None


# ═══════════════════════════════════════════════
# yfinance
# ═══════════════════════════════════════════════
def fetch_single(symbol, period="60d"):
    import os as _os2, pickle as _pk2, hashlib as _hs2
    _ck2 = '/tmp/stock_cache/' + _hs2.md5(f'yf_{symbol}_{period}'.encode()).hexdigest() + '.pkl'
    _os2.makedirs('/tmp/stock_cache', exist_ok=True)
    if _os2.path.exists(_ck2) and (time.time()-_os2.path.getmtime(_ck2))/60 < 10:
        try:
            with open(_ck2,'rb') as _f: return _pk2.load(_f)
        except: pass
    # 美元指數備援 symbol 清單
    _sym_list = [symbol]
    if symbol in ('DX-Y.NYB', 'DX=F'):
        _sym_list = ['DX=F', 'DX-Y.NYB', 'UUP']  # 期貨→NYB→ETF
    try:
        import yfinance as yf
        h = None
        for _sym in _sym_list:
            try:
                _h = yf.Ticker(_sym).history(period=period)
                if _h is not None and not _h.empty:
                    h = _h; break
            except: continue
        if h is None or h.empty: return None
        h.index = pd.DatetimeIndex(h.index).tz_localize(None)
        h.columns = [c.lower().replace(' ','_') for c in h.columns]
        # 移除全 NaN 行（某些 symbol 最新一筆可能是 NaN）
        if 'close' in h.columns:
            h = h.dropna(subset=['close'])
        elif 'Close' in h.columns:
            h = h.dropna(subset=['Close'])
        if h.empty: return None
        with open(_ck2,'wb') as _f: _pk2.dump(h, _f)
        return h
    except Exception as e:
        print(f'[yf:{symbol}] {e}'); return None

def _fetch_otc_via_finmind(token=""):
    if not FINMIND_TOKEN: return None
    try:
        start=(datetime.date.today()-datetime.timedelta(days=90)).strftime('%Y-%m-%d')
        r=requests.get("https://api.finmindtrade.com/api/v4/data",
                       params={"dataset":"TaiwanStockDaily","data_id":"OTC","start_date":start},
                       headers={"Authorization":f"Bearer {FINMIND_TOKEN}"},timeout=20)
        j=r.json()
        if j.get("status")==200 and j.get("data"):
            df=pd.DataFrame(j["data"])
            if 'close' in df.columns:
                df['Date']=pd.to_datetime(df['date'])
                return df.sort_values('Date').set_index('Date')[['close']].rename(columns={'close':'Close'})
    except Exception as e: print(f"[OTC] {e}")
    return None



# ═════════════════════════════════════════════════════
# 騰落指標（ADL）— TWSE MI_INDEX + FMTQIK
# ═════════════════════════════════════════════════════

# ═════════════════════════════════════════════════════
# 騰落指標（ADL）— 完整重寫版
# 不用 @st.cache_data（在 thread 中失敗），改用 pickle cache
# 資料來源: FinMind + TWSE MI_INDEX（精確解析漲跌家數）
# ═════════════════════════════════════════════════════
def fetch_adl(days=60, token=None):
    """
    騰落指標 ADL v5 — 雙層架構
    ① yfinance ^TWII  — 立即可用估算值（Colab 無封鎖問題）
    ② TWSE MI_INDEX   — 精確上漲/下跌家數（table[7] 漲跌證券數合計）
       並發 5 線程逐日抓取；精確值自動覆蓋估算值

    根本原因修正：TaiwanStockMarketCondition 不在 FinMind v4 有效資料集中
    """
    import datetime as _dt
    import pickle as _pk
    import os as _os2
    import time as _tm2
    import re as _re
    import pandas as _pd_adl
    from concurrent.futures import ThreadPoolExecutor, as_completed as _afc

    # ── 日誌 helper ──────────────────────────────────────────────
    _log_path = '/tmp/_adl_log.txt'
    def _alog(msg):
        print(msg, flush=True)
        try:
            with open(_log_path, 'a', encoding='utf-8') as _f:
                _f.write(msg + '\n')
        except Exception:
            pass
    try:
        open(_log_path, 'w').close()
    except Exception:
        pass

    # ── Cache ────────────────────────────────────────────────────
    _ck = '/tmp/stock_cache/adl_data.pkl'
    _os2.makedirs('/tmp/stock_cache', exist_ok=True)
    if _os2.path.exists(_ck):
        _age = _tm2.time() - _os2.path.getmtime(_ck)
        if _age < 1800:
            try:
                _c = _pk.load(open(_ck, 'rb'))
                if _c is not None and not _c.empty:
                    _alog(f'[ADL] 快取命中 {len(_c)} 筆 (age={_age/60:.1f}min)')
                    return _c
            except Exception:
                pass

    today  = _dt.date.today()
    s_date = today - _dt.timedelta(days=days + 14)
    s_dash = s_date.strftime('%Y-%m-%d')
    e_dash = today.strftime('%Y-%m-%d')
    rows: dict = {}   # {ymd: {'up':int, 'down':int, 'is_proxy':bool}}

    # ════════════════════════════════════════════════════════════════
    # ① yfinance ^TWII — 估算（立即可用，is_proxy=True）
    # 公式：漲跌幅 ±1% ≈ ±150 家，以 900/900 為基準
    # ════════════════════════════════════════════════════════════════
    _alog('[ADL-①] yfinance ^TWII 估算...')
    try:
        import yfinance as _yf_adl
        _twii = _yf_adl.download(
            '^TWII', start=s_dash, end=e_dash,
            progress=False, auto_adjust=True
        )
        if not _twii.empty:
            # [Fix] yfinance 新版可能回傳 MultiIndex columns，需先攤平
            if isinstance(_twii.columns, pd.MultiIndex):
                _twii.columns = _twii.columns.get_level_values(0)
            _twii = _twii.dropna(subset=['Close'])
            for _ix in _twii.index:
                _dk = str(_ix)[:10].replace('-', '')
                _cl = float(_twii.loc[_ix, 'Close'])
                _op = float(_twii.loc[_ix, 'Open'])
                _pct = (_cl - _op) / _op if _op > 0 else 0.0
                # 估算公式：中性=900，每±1%約±150家，限制在50~1750
                _up = max(50, min(1750, int(900 + _pct * 15000)))
                rows[_dk] = {'up': _up, 'down': max(50, 1800 - _up), 'is_proxy': True}
            _alog(f'[ADL-①] ✅ {len(rows)} 天估算完成')
        else:
            _alog('[ADL-①] ⚠️ yfinance 回傳空資料')
    except Exception as _e1:
        _alog(f'[ADL-①] ❌ {type(_e1).__name__}: {_e1}')

    # ════════════════════════════════════════════════════════════════
    # ② TWSE MI_INDEX 精確值（並發 5 線程）
    # 端點：https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX
    # Table[7]: 漲跌證券數合計 → 整體市場欄（含上漲/下跌家數）
    # 解析："7,768(403)" → 取括號前的數字 → 7768
    # ════════════════════════════════════════════════════════════════
    def _parse_tw_num(s: str) -> int:
        """解析 TWSE 數字格式，如 '7,768(403)' → 7768"""
        s = str(s).strip()
        m = _re.match(r'^([\d,]+)', s)
        if m:
            try:
                return int(m.group(1).replace(',', ''))
            except ValueError:
                pass
        return 0

    def _fetch_mi_index_day(date_ymd: str) -> tuple:
        """
        抓取單日 TWSE MI_INDEX 的上漲/下跌家數
        回傳 (ymd, up, down) 或 None（休市/失敗）
        """
        try:
            _r = _TWSE_CK.get(
                'https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX',
                params={'response': 'json', 'date': date_ymd},
                headers={'User-Agent': 'Mozilla/5.0'},
                timeout=12
            )
            # Edge Case 1: HTTP 非 200
            if _r.status_code != 200:
                return None
            _j = _r.json()
            # Edge Case 2: 休市日 stat != OK
            if _j.get('stat') != 'OK':
                return None
            _tables = _j.get('tables', [])
            # Edge Case 3: table 結構不足
            if len(_tables) < 8:
                return None
            _t7 = _tables[7]
            _data = _t7.get('data', [])
            # Edge Case 4: 資料列不足（至少需要上漲/下跌兩列）
            if len(_data) < 2:
                return None
            # 整體市場欄（index 1）包含上漲/下跌家數
            # row[0] = 上漲(漲停), row[1] = 下跌(跌停)
            _up   = _parse_tw_num(_data[0][1])  # 整體市場 上漲
            _down = _parse_tw_num(_data[1][1])  # 整體市場 下跌
            # Edge Case 5: 解析後數值不合理（應 > 0）
            if _up <= 0 or _down <= 0:
                return None
            return (date_ymd, _up, _down)
        except Exception:
            return None

    # 產生需要抓取的日期清單（工作日）
    _dates_to_fetch = []
    _cur = s_date
    while _cur <= today:
        if _cur.weekday() < 5:   # 週一到週五
            _ymd = _cur.strftime('%Y%m%d')
            # 只抓取尚無精確資料的日期
            if rows.get(_ymd, {}).get('is_proxy', True):
                _dates_to_fetch.append(_ymd)
        _cur += _dt.timedelta(days=1)

    _alog(f'[ADL-②] 準備並發抓取 {len(_dates_to_fetch)} 個交易日...')
    _exact_count = 0
    _skip_count  = 0

    with ThreadPoolExecutor(max_workers=5) as _ex:
        _futures = {_ex.submit(_fetch_mi_index_day, d): d for d in _dates_to_fetch}
        for _fut in _afc(_futures, timeout=60):
            _res = _fut.result()
            if _res is not None:
                _ymd2, _up2, _down2 = _res
                rows[_ymd2] = {'up': _up2, 'down': _down2, 'is_proxy': False}
                _exact_count += 1
            else:
                _skip_count += 1

    _alog(f'[ADL-②] ✅ 精確={_exact_count} 休市/失敗={_skip_count}')

    # Edge Case 6: 完全沒有資料
    if not rows:
        _alog('[ADL] ⚠️ 所有來源均失敗，回傳 None')
        return None

    # ── 組合 DataFrame ──────────────────────────────────────────
    _records = []
    for _dk in sorted(rows):
        if not (s_date.strftime('%Y%m%d') <= _dk <= today.strftime('%Y%m%d')):
            continue
        _v = rows[_dk]
        _records.append({
            'date':     _dk,
            'up':       _v['up'],
            'down':     _v['down'],
            'is_proxy': _v['is_proxy'],
        })

    # Edge Case 7: 過濾後仍無記錄
    if not _records:
        _alog('[ADL] ⚠️ 有效記錄為空')
        return None

    df = _pd_adl.DataFrame(_records)
    df['ad']       = df['up'] - df['down']
    df['adl']      = df['ad'].cumsum()
    df['adl_ma20'] = df['adl'].rolling(20, min_periods=1).mean()
    df['ad_ratio'] = (df['up'] / (df['up'] + df['down']).replace(0, 1) * 100).round(1)
    df['date']     = _pd_adl.to_datetime(df['date'], format='%Y%m%d')

    _proxy_n = int(df['is_proxy'].sum())
    _exact_n = int((~df['is_proxy']).sum())
    _alog(
        f'[ADL] ✅ 完成 {len(df)} 筆 '
        f'精確={_exact_n} 估算={_proxy_n} '
        f'上漲佔比:{df["ad_ratio"].iloc[-1]:.1f}%'
    )

    # ── 快取 ────────────────────────────────────────────────────
    try:
        with open(_ck, 'wb') as _f:
            _pk.dump(df.tail(days).reset_index(drop=True), _f)
    except Exception:
        pass

    return df.tail(days).reset_index(drop=True)


# ── 4. Self-Test（邊界測試）────────────────────────────────────
def _adl_selftest():
    """在 Colab 外部可執行此函數驗證解析邏輯"""
    import re

    def _parse(s):
        m = re.match(r'^([\d,]+)', str(s).strip())
        return int(m.group(1).replace(',', '')) if m else 0

    # Test 1: 正常格式
    assert _parse('7,768(403)') == 7768, "Test1 failed"
    # Test 2: 無括號
    assert _parse('3,644') == 3644, "Test2 failed"
    # Test 3: 空字串
    assert _parse('') == 0, "Test3 failed"
    # Test 4: 只有漢字（類型欄誤傳）
    assert _parse('上漲') == 0, "Test4 failed"
    # Test 5: 大值
    assert _parse('19,039') == 19039, "Test5 failed"
    print("[ADL selftest] ✅ 全部通過")




def _hex2rgba(color, alpha=0.12):
    try:
        c=color.lstrip('#'); r,g,b=int(c[0:2],16),int(c[2:4],16),int(c[4:6],16)
        return f"rgba({r},{g},{b},{alpha})"
    except: return "rgba(88,166,255,0.12)"

def _base_layout(title="", height=260):
    return dict(title=dict(text=title,font=dict(color="#8b949e",size=12)),
                height=height,plot_bgcolor="#0e1117",paper_bgcolor="#0e1117",
                font=dict(color="#e6edf3",size=11),
                margin=dict(l=8,r=8,t=35,b=20),
                xaxis=dict(gridcolor="#21262d",showgrid=True,zeroline=False),
                yaxis=dict(gridcolor="#21262d",showgrid=True,zeroline=False),
                legend=dict(bgcolor="rgba(0,0,0,0)",font=dict(size=10)))

def sparkline(df, title="", color="#58a6ff"):
    col=next((c for c in ['close','Close'] if c in df.columns),None)
    if col is None: return go.Figure()
    s=df[col].dropna().tail(45)
    fig=go.Figure(go.Scatter(x=list(s.index),y=list(s.values),mode='lines',
                             line=dict(color=color,width=2),fill='tozeroy',
                             fillcolor=_hex2rgba(color) if color.startswith('#') else color))
    fig.update_layout(**_base_layout(title,200)); return fig

def multi_chart(data_dict, title="", norm=False, height=250):
    fig=go.Figure()
    for i,(name,df) in enumerate(data_dict.items()):
        col=next((c for c in ['close','Close'] if c in df.columns),None)
        if col is None: continue
        s=df[col].dropna().tail(45)
        y=(s/s.iloc[0]*100).round(2) if (norm and len(s)>0) else s
        fig.add_trace(go.Scatter(x=list(s.index),y=list(y.values),mode='lines',name=name,
                                 line=dict(color=COLORS_7[i%len(COLORS_7)],width=2)))
    fig.update_layout(**_base_layout(title,height)); return fig

def bar_chart_institutional(inst_dict, title="三大法人買賣超（堆疊柱狀圖）", height=300):
    """升級版：堆疊柱狀圖（三大法人各自一欄，顏色區分）"""
    import datetime as _dt_bar
    # 分離三個法人
    _inst_keys = ['外資', '投信', '自營商']
    _inst_colors = {'外資': '#58a6ff', '投信': '#3fb950', '自營商': '#bc8cff'}
    # 初始化為 float（修復：原為 [] 導致 >= 比較 TypeError）
    _data_by = {k: 0.0 for k in _inst_keys}
    # inst_dict 格式: {法人名: {net, buy, sell, ...}}
    if inst_dict and isinstance(inst_dict, dict):
        for _name, _val in inst_dict.items():
            if '合計' in _name: continue
            if not isinstance(_val, dict): continue
            _matched = next((k for k in _inst_keys if k in str(_name)), None)
            if _matched:
                try: _data_by[_matched] = float(_val.get('net', 0) or 0)
                except: pass
    # 若無日期維度，做單日橫向堆疊
    fig = go.Figure()
    for _ik in _inst_keys:
        _v = float(_data_by.get(_ik, 0.0))  # 確保是 float
        _c = '#da3633' if _v > 0 else ('#2ea043' if _v < 0 else '#388bfd')
        fig.add_trace(go.Bar(
            name=_ik, x=[_ik], y=[_v],
            marker_color=_inst_colors.get(_ik, _c),
            text=[f'{_v:+.1f}億'],
            textposition='auto',
            opacity=0.9,
        ))
    # 合計線
    _total = sum(float(v) for v in _data_by.values())
    _layout = _base_layout(title, height)
    _layout.update({
        'barmode': 'group',
        'showlegend': True,
        'legend': {'orientation': 'h', 'y': 1.08, 'font': {'size': 10, 'color': '#8b949e'}},
        'shapes': [{'type': 'line', 'x0': -0.5, 'x1': 2.5, 'y0': 0, 'y1': 0,
                    'line': {'color': '#484f58', 'width': 1, 'dash': 'dot'}}],
        'annotations': [{'text': f'合計: {_total:+.1f}億',
                         'xref': 'paper', 'yref': 'paper', 'x': 0.98, 'y': 0.95,
                         'showarrow': False, 'font': {'size': 12, 'color': '#da3633' if _total > 0 else ('#2ea043' if _total < 0 else '#388bfd')}}]
    })
    fig.update_layout(**_layout)
    return fig

def stat_card(name, stats, unit="", has_data=True):
    if not has_data or stats is None:
        return (f'<div style="background:#161b22;border:1px solid #21262d;border-radius:8px;'
                f'padding:12px;text-align:center;opacity:0.5;"><div style="font-size:10px;color:#484f58;">{name}</div>'
                f'<div style="font-size:13px;color:#484f58;">載入中...</div></div>')
    pct=stats.get('pct',0); pc='#da3633' if pct>0 else ('#2ea043' if pct<0 else '#388bfd'); arrow='▲' if pct>0 else ('▼' if pct<0 else '─')
    return (f'<div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:12px;text-align:center;">'
            f'<div style="font-size:10px;color:#484f58;">{name}</div>'
            f'<div style="font-size:18px;font-weight:900;color:#e6edf3;">{stats.get("last","?")} '
            f'<span style="font-size:10px;color:#8b949e;">{unit}</span></div>'
            f'<div style="font-size:12px;font-weight:700;color:{pc};">{arrow} {abs(pct):.2f}%</div>'
            f'<div style="font-size:10px;color:#484f58;">{stats.get("status","")}</div></div>')

def margin_card(margin):
    if margin is None:
        return ('<div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px;">'
                '<div style="font-size:11px;color:#484f58;">融資餘額</div>'
                '<div style="font-size:12px;color:#d29922;margin-top:6px;">⏳ 抓取中（TWSE 15:30後更新）</div>'
                '<div style="font-size:10px;color:#484f58;margin-top:4px;">收盤後點「更新全部總經數據」重試</div></div>')
    mc='#f85149' if margin>3400 else ('#d29922' if margin>2500 else '#3fb950')
    label='🔴超過3400億高危' if margin>3400 else ('⚡超過2500億警戒' if margin>2500 else '✅安全水位')
    return (f'<div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px;">'
            f'<div style="font-size:11px;color:#484f58;">融資餘額</div>'
            f'<div style="font-size:28px;font-weight:900;color:{mc};">{margin:.0f}'
            f'<span style="font-size:12px;">億</span></div>'
            f'<div style="font-size:10px;color:#8b949e;">{label}</div></div>')

def section_header(num, title, icon=""):
    return (f'<div style="background:linear-gradient(90deg,#161b22,transparent);'
            f'border-left:3px solid #1f6feb;border-radius:0 6px 6px 0;'
            f'padding:8px 14px;margin:16px 0 10px 0;">'
            f'<span style="color:#1f6feb;font-weight:700;">{icon} {num}、{title}</span></div>')

def calc_stats(df):
    """計算股票統計數據（last/pct/status）"""
    if df is None or df.empty: return None
    col = next((c for c in ['close','Close'] if c in df.columns), None)
    if not col: return None
    s = df[col].dropna()
    if len(s) < 2: return None
    last = float(s.iloc[-1])
    prev = float(s.iloc[-2])
    pct  = (last - prev) / prev * 100 if prev else 0
    ma5  = float(s.tail(5).mean())
    ma20 = float(s.tail(20).mean()) if len(s) >= 20 else ma5
    if last > ma5 > ma20:   status = '多頭排列↑'
    elif last < ma5 < ma20: status = '空頭排列↓'
    else:                   status = '整理中'
    return {'last': round(last,2), 'pct': round(pct,2),
            'status': status, 'chg': round(last-prev,2)}
