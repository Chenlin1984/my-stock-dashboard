LI_VERSION = "v8-finmind-20260323"
print(f"[leading_indicators] loaded {LI_VERSION}")
"""
📊 法人買賣 + 先行指標系統 v8
=================================================
資料來源策略：
  外資大小 → FinMind API  TaiwanFuturesInstitutionalInvestors (TX)
  外(選)   → FinMind API  TaiwanOptionInstitutionalInvestors  (TXO)
  前五大/前十大/未平倉 → TAIFEX largeTraderFutQryTbl (GET) + POST
  選PCR    → TAIFEX pcRatio (POST, 已穩定)
  三大法人現貨 → TWSE BFI82U (JSON GET, 已穩定)
  成交量   → TWSE FMTQIK  (JSON GET, 已穩定)
=================================================
v5 修正：
  1. FinMind JSON API 取代 TAIFEX rowspan HTML 解析
  2. find_data_table(html, kw) 依關鍵字找正確資料表，不再依大小
  3. largeTraderFutQryTbl GET 解析 "43,469 (37,392)" 格式
"""
import os, re, time
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from io import StringIO
from datetime import datetime, timedelta, date
FINMIND_TOKEN = os.environ.get('FINMIND_TOKEN', '')

# st.set_page_config removed (module-level, causes error when imported)


# ── _safe_cache: st.cache_data の安全ラッパー ──────────────────────────
# 背景スレッド（ThreadPoolExecutor）から呼ばれても ScriptRunContext
# エラーを発生させないよう、セッションコンテキストの有無を実行時に判定する。
import functools as _fc
def _safe_cache(**kw):
    """
    st.cache_data を安全に使用するデコレータ。
    ・Streamlit のメインスレッド → キャッシュ有効
    ・バックグラウンドスレッド / 素の Python → キャッシュなしで直接実行
    """
    def decorator(fn):
        try:
            _cached = st.cache_data(**kw)(fn)
        except Exception:
            return fn
        @_fc.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                from streamlit.runtime.scriptrunner import get_script_run_ctx as _gctx
                if _gctx() is not None:
                    return _cached(*args, **kwargs)
            except Exception:
                pass
            return fn(*args, **kwargs)
        return wrapper
    return decorator
# ────────────────────────────────────────────────────────────────────────

TWSE_HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "application/json, */*",
    "Referer": "https://www.twse.com.tw/",
}
TAIFEX_HDR = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Referer": "https://www.taifex.com.tw/cht/3/futContractsDate",
    "Origin": "https://www.taifex.com.tw",
    "Content-Type": "application/x-www-form-urlencoded",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}
FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"

# ── 工具 ─────────────────────────────────────────────────
def roc_to_ymd(s):
    s = str(s).strip()
    # 已是 YYYYMMDD（8位西元，OpenAPI 直接回傳）
    if re.match(r"^\d{8}$", s):
        return s
    # ROC 格式: YYY/MM/DD 或 YY/MM/DD
    m = re.match(r"(\d{2,3})[/年](\d{1,2})[/月](\d{1,2})", s)
    return f"{int(m.group(1))+1911}{m.group(2).zfill(2)}{m.group(3).zfill(2)}" if m else ""

def ymd_to_slash(s): return f"{s[:4]}/{s[4:6]}/{s[6:]}"
def ymd_to_dash(s):  return f"{s[:4]}-{s[4:6]}-{s[6:]}"
def d2ymd(d): return d.strftime("%Y%m%d")
def ymd_display(s):
    dt = datetime.strptime(s, "%Y%m%d"); return f"{dt.month}月{dt.day}日"

def to_num(v, as_int=False):
    try:
        s = str(v).replace(",","").replace("+","").strip()
        # 去掉括號內容 "(37,392)" → ""
        s = re.sub(r"\(.*?\)", "", s).strip()
        if s in ("","-","nan","NaN","None","—","--","N/A"): return None
        f = float(s)
        return int(round(f)) if as_int else f
    except: return None

def first_num(cell, as_int=True):
    """從 '43,469  (37,392)' 或 '45.5%  (39.2%)' 取第一個數字"""
    m = re.search(r"[\d,]+", str(cell).replace(",",""))
    if not m: return None
    # 重新抓帶逗號版本
    m2 = re.search(r"[\d,]+", str(cell))
    if not m2: return None
    try:
        f = float(m2.group(0).replace(",",""))
        return int(round(f)) if as_int else f
    except: return None

def months_in_range(s, e):
    r, y, m = [], s.year, s.month
    while (y,m) <= (e.year, e.month):
        r.append(f"{y}{m:02d}"); m+=1
        if m>12: m,y=1,y+1
    return r

def extract_date(s):
    m = re.search(r"(20\d{2})[/\-](\d{1,2})[/\-](\d{1,2})", str(s))
    if m: return f"{m.group(1)}{m.group(2).zfill(2)}{m.group(3).zfill(2)}"
    m = re.search(r"(\d{3})[/\-](\d{1,2})[/\-](\d{1,2})", str(s))
    if m: return f"{int(m.group(1))+1911}{m.group(2).zfill(2)}{m.group(3).zfill(2)}"
    return None

# ────────────────────────────────────────────────────────
# ✅ 核心改進：依關鍵字找正確資料表（不再依大小）
# ────────────────────────────────────────────────────────
def find_data_table(html, keywords):
    """
    在 HTML 中找包含 keywords 的 <table>
    keywords: list of str，至少一個匹配即選中
    回傳 BeautifulSoup table element 或 None
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    for tbl in soup.find_all("table"):
        txt = tbl.get_text()
        score = sum(1 for kw in keywords if kw in txt)
        if score > 0:
            rows = tbl.find_all("tr")
            cells = sum(len(r.find_all(["td","th"])) for r in rows)
            candidates.append((score, cells, tbl))
    if not candidates: return None
    # 優先 score 高，其次 cell 數
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]

def expand_table_elem(tbl_elem):
    """手動展開 rowspan/colspan，回傳 list of list"""
    if tbl_elem is None: return []
    matrix = {}; max_col = 0
    for ri, tr in enumerate(tbl_elem.find_all("tr")):
        ci = 0
        for cell in tr.find_all(["td","th"]):
            while (ri, ci) in matrix: ci += 1
            txt = cell.get_text(separator=" ", strip=True)
            rs  = int(cell.get("rowspan", 1))
            cs  = int(cell.get("colspan", 1))
            for r in range(rs):
                for c in range(cs):
                    matrix[(ri+r, ci+c)] = txt
            ci += cs
            if ci > max_col: max_col = ci
    max_row = max(k[0] for k in matrix)+1 if matrix else 0
    return [[matrix.get((ri,ci),"") for ci in range(max_col)] for ri in range(max_row)]

# ── TAIFEX POST ──────────────────────────────────────────
def taifex_post(url, form, _timeout_get=2, _timeout_post=5, _max_retry=1):
    """
    POST 到 TAIFEX 並回傳 HTML。
    [BUG FIX] 縮短逾時：GET 4s + POST 8s × 2 retry = 最差 24s（舊版 105s）
    避免 ThreadPoolExecutor shutdown(wait=True) 長時間阻塞。
    """
    for attempt in range(_max_retry):
        try:
            sess = requests.Session()
            hdrs = dict(TAIFEX_HDR)
            hdrs["Referer"] = url
            sess.headers.update(hdrs)
            sess.get(url, timeout=_timeout_get)
            r = sess.post(url, data=form, timeout=_timeout_post)
            r.encoding = "utf-8"
            if len(r.text) > 200:
                return r.text
        except Exception:
            if attempt == _max_retry - 1:
                return ""
            time.sleep(0.3)
    return ""

# ════════════════════════════════════════════════════════
# FinMind API
# ════════════════════════════════════════════════════════
def finmind_get(dataset, data_id, start_ymd, end_ymd, token=""):
    """
    呼叫 FinMind API v4，回傳 DataFrame
    ・data_id 空字串不送出（避免 422）
    ・自動重試 2 次，每次獨立 Session
    """
    params = {
        "dataset":    dataset,
        "start_date": ymd_to_dash(start_ymd),
        "end_date":   ymd_to_dash(end_ymd),
    }
    if data_id:
        params["data_id"] = data_id
    if token:
        params["token"] = token
    hdrs = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    for _attempt in range(2):
        try:
            sess = requests.Session()
            sess.headers.update(hdrs)
            r = sess.get(FINMIND_URL, params=params, timeout=25)
            sess.close()
            d = r.json()
            status = d.get("status")
            if status == 200:
                df = pd.DataFrame(d.get("data", []))
                print(f"[FinMind] {dataset} ✅ {len(df)} rows")
                return df
            else:
                print(f"[FinMind] {dataset} HTTP={r.status_code} status={status} msg={d.get('msg','')}")
                return pd.DataFrame()
        except Exception as _fe:
            print(f"[FinMind] {dataset} attempt {_attempt+1} ❌ {_fe}")
            if _attempt == 1:
                return pd.DataFrame()
            time.sleep(1)
    return pd.DataFrame()

@_safe_cache(ttl=1800, show_spinner=False)
def finmind_fut_oi(start_ymd, end_ymd, token=""):
    """
    外資大小 = 外資大台淨多空口 + 外資小台淨多空口 × 0.25
    主要來源: FinMind TaiwanFuturesInstitutionalInvestors
    備援來源: TAIFEX 三大法人期貨留倉（官方，免Token）
    """
    result = {}

    # ── 主要: FinMind ──
    if token:
        df_tx  = finmind_get("TaiwanFuturesInstitutionalInvestors","TX", start_ymd,end_ymd,token)
        df_mtx = finmind_get("TaiwanFuturesInstitutionalInvestors","MTX",start_ymd,end_ymd,token)
        for df, factor in [(df_tx, 1.0), (df_mtx, 0.25)]:
            if df.empty: continue
            df_fi = df[df["institutional_investors"].str.contains("外資", na=False)]
            for _, row in df_fi.iterrows():
                dk = str(row["date"]).replace("-","")
                long_  = int(row.get("long_open_interest_balance_volume",  0) or 0)
                short_ = int(row.get("short_open_interest_balance_volume", 0) or 0)
                result[dk] = result.get(dk, 0) + (long_ - short_) * factor

    # ── 備援: TAIFEX 官方三大法人留倉（免Token）──
    if not result:
        try:
            _start_dt = datetime.strptime(start_ymd, "%Y%m%d")
            _end_dt   = datetime.strptime(end_ymd,   "%Y%m%d")
            _curr = _start_dt
            while _curr <= _end_dt:
                if _curr.weekday() < 5:  # 只查交易日
                    _d_ymd = _curr.strftime("%Y%m%d")
                    _taifex_inst = taifex_post(
                        "https://www.taifex.com.tw/cht/3/futContractsDate",
                        {"queryDate": ymd_to_slash(_d_ymd), "commodityId": "TX"}
                    )
                    if _taifex_inst:
                        _tbl_inst = find_data_table(_taifex_inst, ["外資", "留倉", "口數"])
                        _matrix_inst = expand_table_elem(_tbl_inst)
                        for _row_i in _matrix_inst:
                            if len(_row_i) < 5: continue
                            if "外資" not in " ".join(_row_i[:3]): continue
                            _net_i = first_num(_row_i[3]) if len(_row_i) > 3 else None
                            if _net_i is not None:
                                result[_d_ymd] = result.get(_d_ymd, 0) + _net_i
                                break
                _curr += timedelta(days=1)
        except Exception as _eTA:
            pass  # TAIFEX 備援靜默失敗

    return {k: round(v) for k, v in result.items()}

@_safe_cache(ttl=1800, show_spinner=False)
def taifex_calls_puts_day(date_ymd):
    """
    外(選) = (BC金額 - SC金額 - BP金額 + SP金額) / 10

    ✅ 瀏覽器 + expand_table_elem 雙重驗證（rowspan 展開後全部 16 欄）：
      col[2]  = 權別（買權 / 賣權）
      col[3]  = 身份別（外資）
      col[11] = 未平倉買方金額 ← OI Buy Amount
      col[13] = 未平倉賣方金額 ← OI Sell Amount

    3/3 驗證：BC=1,245,010  SC=891,558  BP=527,883  SP=410,474
    Net=236,043 → /10 = 23,604 ✅
    """
    url  = "https://www.taifex.com.tw/cht/3/callsAndPutsDate"
    form = {
        "queryType":   "1",
        "goDay":       "",
        "doQuery":     "1",
        "dateaddcnt":  "",
        "queryDate":   ymd_to_slash(date_ymd),
        "commodityId": "TXO",
    }
    try:
        html = taifex_post(url, form)
        if not html: return None
        tbl = find_data_table(html, ["買權", "賣權", "外資", "身份別"])
        matrix = expand_table_elem(tbl)  # rowspan 展開後：全部 16 欄
        call_buy_amt = call_sell_amt = put_buy_amt = put_sell_amt = None
        for row in matrix:
            if len(row) < 14: continue
            right_type = str(row[2]).strip()   # col[2] = 買權 / 賣權
            identity   = str(row[3]).strip()   # col[3] = 身份別
            if right_type not in ("買權", "賣權"): continue
            if "外資" not in identity or "自營商" in identity: continue
            buy_amt  = to_num(row[11], as_int=False)  # ✅ col[11] OI買方金額
            sell_amt = to_num(row[13], as_int=False)  # ✅ col[13] OI賣方金額
            if buy_amt is None or sell_amt is None: continue
            if right_type == "買權":
                call_buy_amt, call_sell_amt = buy_amt, sell_amt
            else:
                put_buy_amt, put_sell_amt = buy_amt, sell_amt
        if all(v is not None for v in [call_buy_amt, call_sell_amt, put_buy_amt, put_sell_amt]):
            net = call_buy_amt - call_sell_amt - put_buy_amt + put_sell_amt
            return round(net / 10)   # 金額÷10，與參考系統一致
    except: pass
    return None


@_safe_cache(ttl=1800, show_spinner=False)
def taifex_mtx_data(date_ymd):
    """
    韭菜指數 = (三大法人空方MTX OI - 三大法人多方MTX OI) / 小台全體OI × 100
    正值 = 散戶淨多（危險）；負值 = 散戶淨空（機會）

    ① futContractsDate（queryDate 單日）→ 三大法人 MTX 多/空 OI
       13欄行：col[0]=身份別  col[7]=未平倉多方口  col[9]=未平倉空方口
       15欄行：col[2]=身份別  col[9]=未平倉多方口  col[11]=未平倉空方口
    ② futDailyMarketReport（queryDate）→ MTX 各月未沖銷契約量加總（全體OI）
    """
    inst_long = inst_short = total_oi = None
    try:
        # ① futContractsDate - 正確參數（瀏覽器確認）
        url1 = "https://www.taifex.com.tw/cht/3/futContractsDate"
        html1 = taifex_post(url1, {
            "queryType":   "1",
            "goDay":       "",
            "doQuery":     "1",
            "dateaddcnt":  "",
            "queryDate":   ymd_to_slash(date_ymd),
            "commodityId": "",
        })
        if html1:
            tbl = find_data_table(html1, ["小型臺指期貨", "外資", "投信", "自營"])
            matrix = expand_table_elem(tbl)
            long_sum = short_sum = 0
            in_mtx = False
            for row in matrix:
                n = len(row)
                if n < 3: continue
                if n == 15 and "小型臺指期貨" in str(row[1]):
                    in_mtx = True
                if in_mtx and n == 15 and "小型臺指期貨" not in str(row[1]) and str(row[0]).strip().isdigit():
                    break  # 離開 MTX 區段
                if not in_mtx: continue
                if n == 15:
                    identity = str(row[2]).strip()
                    lo = to_num(row[9],  as_int=True) or 0
                    so = to_num(row[11], as_int=True) or 0
                elif n == 13:
                    identity = str(row[0]).strip()
                    lo = to_num(row[7],  as_int=True) or 0
                    so = to_num(row[9],  as_int=True) or 0
                else:
                    continue
                if identity in ("自營商","投信","外資","外資及陸資"):
                    long_sum  += lo
                    short_sum += so
            if long_sum + short_sum > 0:
                inst_long, inst_short = long_sum, short_sum
    except: pass

    try:
        # ② MTX 全體OI：futDailyMarketReport 各月 未沖銷契約量 加總
        url2 = "https://www.taifex.com.tw/cht/3/futDailyMarketReport"
        html2 = taifex_post(url2, {
            "queryDate":    ymd_to_slash(date_ymd),
            "commodity_id": "MTX",
            "MarketCode":   "0",
        })
        if html2:
            tbl = find_data_table(html2, ["MTX", "未沖銷"])
            matrix = expand_table_elem(tbl)
            total = 0
            for row in matrix:
                if len(row) < 13: continue
                if str(row[0]).strip() != "MTX": continue
                oi = to_num(row[12], as_int=True)
                if oi is not None: total += oi
            if total > 0: total_oi = total
    except: pass

    if inst_long is None or inst_short is None or total_oi is None:
        return None
    leek_val = round((inst_short - inst_long) / total_oi * 1000) / 10
    return (leek_val, total_oi)  # 同時回傳韭菜指數和全體MTX OI

# ════════════════════════════════════════════════════════
# TWSE 成交量
# ════════════════════════════════════════════════════════
@_safe_cache(ttl=1800, show_spinner=False)
def twse_volume(yyyymm):
    """
    成交量（億元）from TWSE FMTQIK，多 URL 備援。
    欄位: row[0]=日期(ROC), row[2]=成交金額(元) → /1e8 = 億元
    """
    def _parse_fmtqik(d):
        result = {}
        if d.get("stat") != "OK": return result
        for row in d.get("data", []):
            dk = roc_to_ymd(row[0])
            if not dk or len(row) < 3: continue
            # 嘗試 row[2]（成交金額）；若值不合理再試 row[1]
            for idx in [2, 1]:
                try:
                    v = round(float(str(row[idx]).replace(",", "")) / 1e8, 1)
                    if 100 < v < 20000:
                        result[dk] = v
                        break
                except: pass
        return result

    for _url in [
        "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK",
        "https://www.twse.com.tw/zh/afterTrading/FMTQIK",
        "https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK",
    ]:
        try:
            _p = {"response": "json", "date": yyyymm + "01"} if "openapi" not in _url else {}
            r = requests.get(_url, params=_p, headers=TWSE_HDR, timeout=15)
            j = r.json()
            # OpenAPI 回傳 list 格式，轉成相容 dict
            if isinstance(j, list):
                j = {"stat": "OK", "data": [[item.get("Date",""), item.get("TradeVolume",""),
                     item.get("TradeValue",""), "","",""] for item in j]}
            result = _parse_fmtqik(j)
            if result:
                print(f"[VOL] FMTQIK {yyyymm}: {len(result)} 天 ({_url.split('/')[2]})")
                return result
        except Exception as _e:
            print(f"[VOL] FMTQIK {yyyymm} {_url}: {_e}")
    print(f"[VOL] FMTQIK {yyyymm} 全部失敗")
    return {}


@_safe_cache(ttl=1800, show_spinner=False)
def twse_volume_daily(ymd8):
    """
    單日成交量 from TWSE MI_INDEX（搜尋所有 tables，row[2]=成交金額備援 row[1]）
    ymd8: YYYYMMDD (e.g., '20260320')
    """
    try:
        r = requests.get("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX",
                         params={"response":"json","date":ymd8},
                         headers=TWSE_HDR, timeout=12)
        d = r.json()
        if d.get("stat") != "OK": return None
        tables = d.get("tables", [])
        # 搜尋所有 tables，找「總計」列；row[2]=成交金額，row[1] 備援
        for tbl in tables:
            for row in tbl.get("data", []):
                if not row or "總計" not in str(row[0]): continue
                for idx in [2, 1]:
                    if idx >= len(row): continue
                    try:
                        amt = round(float(str(row[idx]).replace(",","")) / 1e8, 1)
                        if 100 < amt < 20000: return amt
                    except: pass
        return None
    except: return None

# ════════════════════════════════════════════════════════
# TWSE 三大法人 BFI82U
# ════════════════════════════════════════════════════════
@_safe_cache(ttl=1800, show_spinner=False)
def twse_institutional_day(date_ymd):
    try:
        r = requests.get("https://www.twse.com.tw/fund/BFI82U",
                         params={"response":"json","dayDate":date_ymd},
                         headers=TWSE_HDR, timeout=15)
        d = r.json()
        if d.get("stat") != "OK": return {}
        result = {}; self_diff = None; hedge_diff = None
        for row in d.get("data", [])[:-1]:
            if len(row) < 4: continue
            name = str(row[0]).strip()
            diff = to_num(row[3])
            if diff is None: continue
            diff_bn = round(diff / 1e8, 1)
            if "自行買賣" in name:   self_diff = diff_bn
            elif "避險" in name:     hedge_diff = diff_bn
            elif name == "投信":     result["投信"] = diff_bn
            elif "外資及陸資" in name and name != "外資自營商":
                result["外資"] = diff_bn
        if self_diff is not None and hedge_diff is not None:
            result["自營"] = round(self_diff + hedge_diff, 1)
        elif self_diff is not None:
            result["自營"] = self_diff
        return result
    except: return {}

# ════════════════════════════════════════════════════════
# TAIFEX 選擇權 PCR（批量）
# ✅ 已穩定，保持不變
# ════════════════════════════════════════════════════════
@_safe_cache(ttl=1800, show_spinner=False)
def taifex_pcr(start_ymd, end_ymd):
    url  = "https://www.taifex.com.tw/cht/3/pcRatio"
    form = {"queryStartDate":ymd_to_slash(start_ymd),"queryEndDate":ymd_to_slash(end_ymd)}
    result = {}
    try:
        html = taifex_post(url, form)
        if not html: return result
        # 找含「比率」的資料表
        tbl = find_data_table(html, ["比率", "Put", "Call"])
        matrix = expand_table_elem(tbl)
        for row in matrix:
            if len(row) < 3: continue
            d = extract_date(row[0])
            if not d: continue
            val = to_num(row[-1])
            if val is None: continue
            if 0.1 < val < 10: val = round(val * 100, 1)
            if 20 < val < 500 and d not in result:
                result[d] = round(val, 1)
    except: pass
    return result

# ════════════════════════════════════════════════════════
# TAIFEX 大額交易人（逐日）
# ✅ 修正：largeTraderFutQryTbl GET（今日）+ POST（歷史）
#    解析格式 "43,469  (37,392)" → 取 43,469
#    找「臺股期貨」+ 「所有」列
# ════════════════════════════════════════════════════════
@_safe_cache(ttl=1800, show_spinner=False)
def taifex_large_trader(date_ymd):
    # 嘗試 GET（今日）或 POST（歷史）
    html = ""
    today_ymd = date.today().strftime("%Y%m%d")
    if date_ymd == today_ymd:
        try:
            r = requests.get("https://www.taifex.com.tw/cht/3/largeTraderFutQryTbl",
                             headers=TAIFEX_HDR, timeout=15)
            r.encoding = "utf-8"
            if len(r.text) > 200: html = r.text
        except: pass
    if not html:
        html = taifex_post(
            "https://www.taifex.com.tw/cht/3/largeTraderFutQry",
            {
                "queryDate":   ymd_to_slash(date_ymd),
                "contractId":  "TX",    # ✅ 真實參數名：contractId（不是 commodityId）
                "contractId2": "",      # ✅ hidden field（必填，空字串）
                "datecount":   "",      # ✅ hidden field（必填，空字串）
            }
        )
    if not html: return {}
    try:
        # 找含「臺股期貨」+「前五大」+「全市場」的資料表
        # ✅ 加入「臺股期貨」確保不選到頁面導覽表格
        tbl = find_data_table(html, ["臺股期貨", "前五大交易人", "前十大交易人", "全市場未沖銷"])
        matrix = expand_table_elem(tbl)

        # 表格展開後欄位結構（rowspan 已展開，每列固定 11 欄）：
        # col[0] = 契約名稱  col[1] = 到期月份
        # col[2] = 前五大買方口數  col[3] = 前五大買方%
        # col[4] = 前十大買方口數  col[5] = 前十大買方%
        # col[6] = 前五大賣方口數  col[7] = 前五大賣方%
        # col[8] = 前十大賣方口數  col[9] = 前十大賣方%
        # col[10] = 全市場未沖銷部位數（未平倉）
        #
        # 計算：
        #   前五大  = col[2] - col[6]   (買方所有契約 - 賣方所有契約)
        #   前十大  = col[4] - col[8]
        #   未平倉  = col[10] 直接取

        for row in matrix:
            if len(row) < 11: continue
            row_str = " ".join(row)
            # 找「臺股期貨」且「所有契約」列
            if not re.search(r"臺股期貨|TX\+MTX", row_str): continue
            if not re.search(r"所有", row_str): continue

            # 使用固定欄位索引提取數值（格式如 "43,469  (37,392)"，取第一個數）
            top5_buy  = first_num(row[2])
            top10_buy = first_num(row[4])
            top5_sell = first_num(row[6])
            top10_sell= first_num(row[8])
            oi_total  = first_num(row[10])  # 全市場未沖銷（直接取，無需計算）

            if any(v is None for v in [top5_buy, top10_buy, top5_sell, top10_sell]):
                continue

            return {
                "前五大": top5_buy  - top5_sell,   # 買方所有契約 - 賣方所有契約
                "前十大": top10_buy - top10_sell,
                "未平倉": oi_total,                 # 直接取「全市場未沖銷部位數」
            }
    except: pass
    return {}

# ════════════════════════════════════════════════════════
# 數據組合
# ════════════════════════════════════════════════════════
def build_dataset(start, end, token, log):
    s_ymd, e_ymd = d2ymd(start), d2ymd(end)

    log.write("📊 **Step 1/4**　TWSE：市場成交量...")
    vol = {}
    for m in months_in_range(start, end): vol.update(twse_volume(m))

    log.write("📈 **Step 2/4**　FinMind：外資期貨留倉（外資大小）...")
    fut_dict = finmind_fut_oi(s_ymd, e_ymd, token)

    log.write("📈 **Step 3/4**　TAIFEX：選擇權 PCR（批量）...")
    pcr_dict = taifex_pcr(s_ymd, e_ymd)

    all_dates = sorted(d for d in vol if s_ymd <= d <= e_ymd)

    inst_data = {}; lt_data = {}; opt_data = {}; mtx_data = {}
    if all_dates:
        log.write(f"📊 **Step 4/4**　逐日查詢（{len(all_dates)} 日）：三大法人 + 大額交易人 + 外資選擇權 + 韭菜指數...")
        prog = st.progress(0, text="逐日查詢中...")
        for i, d in enumerate(all_dates):
            inst_data[d] = twse_institutional_day(d)
            lt_data[d]   = taifex_large_trader(d)
            opt_data[d]  = taifex_calls_puts_day(d)
            mtx_data[d]  = taifex_mtx_data(d)        # 韭菜指數
            time.sleep(0.3)
            prog.progress((i+1)/len(all_dates),
                          text=f"逐日查詢 {i+1}/{len(all_dates)} （{ymd_display(d)}）")
        prog.empty()

    rows = []
    for d in all_dates:
        inst = inst_data.get(d, {}); lt = lt_data.get(d, {})
        rows.append({
            "_date": d, "日期": ymd_display(d), "成交量": f"{vol[d]:.1f}億",
            "外資": inst.get("外資"), "投信": inst.get("投信"), "自營": inst.get("自營"),
            "外資大小": fut_dict.get(d),
            "前五大留倉": lt.get("前五大"), "前十大留倉": lt.get("前十大"),
            "選PCR": pcr_dict.get(d), "外(選)": opt_data.get(d),
            "未平倉口數": lt.get("未平倉"),
            "韭菜指數": mtx_data.get(d),
        })
    return pd.DataFrame(rows)

# ════════════════════════════════════════════════════════
# HTML 表格渲染
# ════════════════════════════════════════════════════════
def render_table(df):
    BRACKET = {"外資大小","前五大留倉","前十大留倉","外(選)"}
    SPOT    = {"外資","投信","自營"}
    COLS    = ["外資","投信","自營","外資大小","前五大留倉","前十大留倉","選PCR","外(選)","未平倉口數","韭菜指數"]
    def fmt(v, col):
        if v is None or (isinstance(v, float) and pd.isna(v)): return "-"
        if col in BRACKET:
            n = int(v); return f"({abs(n):,})" if n < 0 else f"{n:,}"
        if col in SPOT: return f"{float(v):+.1f}"
        if col == "選PCR": return f"{float(v):.1f}"
        if col == "未平倉口數": return f"{int(v):,}"
        if col == "韭菜指數": return f"{float(v):+.1f}%"
        return str(v)
    def sty(v, col):
        if v is None or (isinstance(v, float) and pd.isna(v)): return ""
        try: n = float(v)
        except: return ""
        if col in BRACKET:
            if n > 0: return "color:#da3633;font-weight:bold;"
            if n < 0: return "color:#2ea043;font-weight:bold;"
        if col in SPOT:
            if n > 0: return "color:#da3633;"
            if n < 0: return "color:#2ea043;"
        if col == "韭菜指數":
            if n > 10:  return "color:#2ea043;font-weight:bold;"   # 散戶淨多→危險(反向)
            if n < -10: return "color:#da3633;font-weight:bold;"   # 散戶淨空→機會(反向)
        if col == "選PCR":
            if n > 120: return "color:#da3633;"
            if n < 80:  return "color:#2ea043;"
        return ""
    h = """<style>
.it{width:100%;border-collapse:collapse;font-size:13px;font-family:Arial,"Microsoft JhengHei",sans-serif;}
.it th,.it td{border:1px solid #b0b0b0;padding:5px 10px;text-align:center;white-space:nowrap;}
.it tr:nth-child(even) td{background:#f5f7fa;}.it tr:hover td{background:#fffbe6;}
.hd{background:#4a90d9;color:#fff;font-weight:bold;}
.hfa{background:#FFD600;color:#1a1a1a;font-weight:bold;}
.hle{background:#FF9900;color:#1a1a1a;font-weight:bold;}
.hb{background:#e0e0e0;color:#1a1a1a;font-weight:bold;}
.dl{font-weight:bold;text-align:left;padding-left:10px;}
</style>
<table class="it"><thead>
<tr>
  <th rowspan="2" class="hd">日期</th><th rowspan="2" class="hd">成交量</th>
  <th colspan="4" class="hfa">法人買賣</th>
  <th colspan="6" class="hle">先行指標</th>
</tr>
<tr>
  <th class="hb">外資<br><small>億元</small></th>
  <th class="hb">投信<br><small>億元</small></th>
  <th class="hb">自營<br><small>億元</small></th>
  <th class="hb">外資大小<br><small>口</small></th>
  <th class="hb">前五大留倉<br><small>口</small></th>
  <th class="hb">前十大留倉<br><small>口</small></th>
  <th class="hb">選PCR</th>
  <th class="hb">外(選)<br><small>口</small></th>
  <th class="hb">未平倉口數<br><small>口</small></th>
  <th class="hb">韭菜指數<br><small>%</small></th>
</tr>
</thead><tbody>"""
    for _, row in df.iterrows():
        h += "<tr>"
        h += f'<td class="dl">{row.get("日期","-")}</td><td style="color:#58a6ff;">{row.get("成交量","-")}</td>'
        for col in COLS:
            v = row.get(col)
            h += f'<td style="{sty(v,col)}">{fmt(v,col)}</td>'
        h += "</tr>\n"
    return h + "</tbody></table>"



# ════════════════════════════════════════════════════════
# 輔助函式（供台股AI戰情室使用）
# ════════════════════════════════════════════════════════
def build_leading_indicators(start, end, token="", progress_cb=None):
    """
    主函式：抓取所有先行指標數據，回傳 DataFrame
    progress_cb(i, total, msg): 可選的進度回調
    """
    s_ymd, e_ymd = d2ymd(start), d2ymd(end)
    vol = {}
    for m in months_in_range(start, end): vol.update(twse_volume(m))
    fut_dict = finmind_fut_oi(s_ymd, e_ymd, token)
    pcr_dict = taifex_pcr(s_ymd, e_ymd)
    all_dates = sorted(d for d in vol if s_ymd <= d <= e_ymd)
    inst_data = {}; lt_data = {}; opt_data = {}; mtx_data = {}
    for i, d in enumerate(all_dates):
        if progress_cb: progress_cb(i, len(all_dates), f"逐日查詢 {i+1}/{len(all_dates)} （{ymd_display(d)}）")
        inst_data[d] = twse_institutional_day(d)
        lt_data[d]   = taifex_large_trader(d)
        opt_data[d]  = taifex_calls_puts_day(d)
        mtx_data[d]  = taifex_mtx_data(d)
        time.sleep(0.3)
    rows = []
    for d in all_dates:
        inst = inst_data.get(d, {}); lt = lt_data.get(d, {})
        rows.append({
            "_date":d, "日期":ymd_display(d), "成交量":f"{vol[d]:.1f}億",
            "外資":inst.get("外資"), "投信":inst.get("投信"), "自營":inst.get("自營"),
            "外資大小":fut_dict.get(d),
            "前五大留倉":lt.get("前五大"), "前十大留倉":lt.get("前十大"),
            "選PCR":pcr_dict.get(d), "外(選)":opt_data.get(d),
            "未平倉口數":lt.get("未平倉"), "韭菜指數":mtx_data.get(d),
        })
    return pd.DataFrame(rows)



# ════════════════════════════════════════════════════════════════
# 快速版先行指標（只用 FinMind 批次 API，無逐日爬蟲）
# 資料源：
#  ① 外資期貨留倉 → FinMind TaiwanFuturesInstitutionalInvestors (TX+MTX)
#  ② 選擇權 PCR  → TAIFEX pcRatio POST (批次，單次呼叫)
#  ③ 三大法人現貨 → TWSE BFI82U 逐日（最多抓5天，快速）
#  ④ 韭菜指數    → FinMind TaiwanFuturesInstitutionalInvestors 小台散戶淨多
#  備援：TAIFEX futContractsDate 外資留倉（免token，GET）
# ════════════════════════════════════════════════════════════════
def build_leading_fast(days=7, token=""):
    """
    先行指標 v8 — 純 FinMind，完全無 TAIFEX，零多線程
    所有資料從 FinMind 4 個 API 批次取得，不依賴任何爬蟲。
    """
    import datetime as _dt
    today  = _dt.date.today()
    s_date = today - _dt.timedelta(days=days + 14)
    s_ymd  = s_date.strftime("%Y%m%d")
    e_ymd  = today.strftime("%Y%m%d")
    print(f"[LI-v8] ===== 開始 {s_ymd}~{e_ymd} token={bool(token)} days={days} =====")
    import sys; sys.stdout.flush()

    # ═══ 1. FinMind 4 API 循序呼叫 ═════════════════════════════
    df_tx   = finmind_get("TaiwanFuturesInstitutionalInvestors", "TX",  s_ymd, e_ymd, token)
    df_mtx  = finmind_get("TaiwanFuturesInstitutionalInvestors", "MTX", s_ymd, e_ymd, token)
    df_txo  = finmind_get("TaiwanOptionInstitutionalInvestors",  "TXO", s_ymd, e_ymd, token)
    df_inst = finmind_get("TaiwanStockTotalInstitutionalInvestors", "", s_ymd, e_ymd, token)
    print(f"[LI-v8] FinMind TX={len(df_tx)} MTX={len(df_mtx)} TXO={len(df_txo)} inst={len(df_inst)}")
    import sys; sys.stdout.flush()
    if len(df_tx) == 0 and len(df_mtx) == 0 and len(df_txo) == 0 and len(df_inst) == 0:
        print("[LI-v8] ❌ 所有 FinMind API 均返回空 → 可能速率限制或網路問題")

    # ═══ 2. 外資期貨留倉 ════════════════════════════════════════
    fut_net = {}
    for df, factor in [(df_tx, 1.0), (df_mtx, 0.25)]:
        if df.empty: continue
        for _, row in df[df["institutional_investors"].str.contains("外資", na=False)].iterrows():
            dk = str(row["date"]).replace("-", "")
            lo = int(pd.to_numeric(row.get("long_open_interest_balance_volume",  0), errors="coerce") or 0)
            sh = int(pd.to_numeric(row.get("short_open_interest_balance_volume", 0), errors="coerce") or 0)
            fut_net[dk] = fut_net.get(dk, 0) + round((lo - sh) * factor)
    print(f"[LI-v8] 外資期貨 {len(fut_net)} 天")

    # ═══ 3. PCR + 外(選) 從 TXO 計算（FinMind 法人估算，無需 TAIFEX）
    pcr_dict = {}
    opt_dict = {}
    if not df_txo.empty:
        agg = {}
        for _, row in df_txo.iterrows():
            dk = str(row["date"]).replace("-", "")
            if dk not in agg:
                agg[dk] = dict(callV=0, putV=0, extBC=0.0, extSC=0.0, extBP=0.0, extSP=0.0)
            b   = agg[dk]
            cp  = str(row.get("call_put", ""))
            ii  = str(row.get("institutional_investors", ""))
            loV = int(pd.to_numeric(row.get("long_open_interest_balance_volume",  0), errors="coerce") or 0)
            shV = int(pd.to_numeric(row.get("short_open_interest_balance_volume", 0), errors="coerce") or 0)
            loA = float(pd.to_numeric(row.get("long_open_interest_balance_amount",  0), errors="coerce") or 0)
            shA = float(pd.to_numeric(row.get("short_open_interest_balance_amount", 0), errors="coerce") or 0)
            ext = ("外資" in ii) and ("自營" not in ii)
            if "買權" in cp:
                b["callV"] += loV + shV
                if ext: b["extBC"] += loA; b["extSC"] += shA
            elif "賣權" in cp:
                b["putV"]  += loV + shV
                if ext: b["extBP"] += loA; b["extSP"] += shA
        for dk, b in agg.items():
            if b["callV"] > 0:
                pcr_dict[dk] = round(b["putV"] / b["callV"] * 100, 1)
            opt_dict[dk] = round((b["extBC"] - b["extSC"] - b["extBP"] + b["extSP"]) / 10)
        print(f"[LI-v8] PCR(FinMind估算)={len(pcr_dict)} 天  外(選)={len(opt_dict)} 天")

    # ═══ 4. 三大法人現貨 ════════════════════════════════════════
    inst_dict = {}
    if not df_inst.empty:
        df_i = df_inst.copy()
        df_i["_ymd"] = df_i["date"].astype(str).str.replace("-", "")
        for dk, grp in df_i.groupby("_ymd"):
            if not (s_ymd <= dk <= e_ymd): continue
            rd = {}
            for _, r in grp.iterrows():
                nm  = str(r.get("name", ""))
                net = round((float(r.get("buy",  0) or 0) - float(r.get("sell", 0) or 0)) / 1e8, 1)
                if   nm == "Foreign_Investor":                rd["外資"] = round(rd.get("外資", 0) + net, 1)
                elif nm == "Investment_Trust":                 rd["投信"] = round(rd.get("投信", 0) + net, 1)
                elif nm in ("Dealer_self", "Dealer_Hedging"): rd["自營"] = round(rd.get("自營", 0) + net, 1)
            if rd: inst_dict[dk] = rd
        print(f"[LI-v8] 三大法人 {len(inst_dict)} 天")

    # ═══ 5. 成交量（選用）══════════════════════════════════════
    vol_dict = {}
    try:
        for m in months_in_range(s_date, today):
            vol_dict.update(twse_volume(m))
        print(f"[LI-v8] 成交量（FMTQIK）{len(vol_dict)} 天")
    except Exception as _ve:
        print(f"[LI-v8] 成交量FMTQIK略過: {_ve}")
    # 永遠補充近14天（MI_INDEX，盤後才有資料）
    import time as _vt2
    _mi_dates = []
    _ck = today
    while len(_mi_dates) < 14:
        if _ck.weekday() < 5:
            _mi_dates.append(_ck.strftime("%Y%m%d"))
        _ck -= _dt.timedelta(days=1)
    for _vd in _mi_dates:
        if _vd not in vol_dict:
            _v = twse_volume_daily(_vd)
            if _v: vol_dict[_vd] = _v
            _vt2.sleep(0.15)  # 只在實際發出 request 後才 sleep
    print(f"[LI-v8] 成交量（最終）{len(vol_dict)} 天")

    # ═══ 6. 確定日期範圍 ════════════════════════════════════════
    known = set(fut_net) | set(pcr_dict) | set(inst_dict) | set(opt_dict)
    known = {d for d in known if s_ymd <= d <= e_ymd}
    if not known:
        import datetime as _dt2
        c = s_date
        while c <= today:
            if c.weekday() < 5: known.add(c.strftime("%Y%m%d"))
            c += _dt2.timedelta(days=1)
    target = sorted(known)[-days:]
    print(f"[LI-v8] known={len(known)} 天, target(last {days})={target}")
    if not target:
        print("[LI-v8] ❌ target 為空！known={known} → 請確認 FinMind API 可達")
        return pd.DataFrame()

    # ═══ 6.5 快速嘗試 TAIFEX（前五大/前十大/未平倉/韭菜精確值）══════
    # 每個日期超時 12s，Colab 若 IP 被封鎖則快速跳過
    taifex_lt   = {}   # {ymd: {前五大, 前十大}}
    taifex_mtx_oi = {} # {ymd: total MTX OI}
    taifex_leek = {}   # {ymd: float}
    # ── TAIFEX 可達性探測（最先執行，1秒超時，失敗則跳過所有 TAIFEX）
    _taifex_reachable = False
    try:
        _probe = requests.get("https://www.taifex.com.tw",
                               headers=TAIFEX_HDR, timeout=2)
        _taifex_reachable = (_probe.status_code == 200)
        print(f"[TAIFEX] 連線測試 {'✅ 可達' if _taifex_reachable else '❌ 不通'}")
    except Exception as _probe_err:
        print(f"[TAIFEX] 連線測試 ❌ {type(_probe_err).__name__}（跳過所有 TAIFEX）")

    # ── TAIFEX PCR 精確值（全市場，只在 TAIFEX 可達時執行）────
    if _taifex_reachable:
        try:
            pcr_taifex = taifex_pcr(s_ymd, e_ymd)
            pcr_dict.update(pcr_taifex)
            print(f"[LI-v8] PCR(TAIFEX精確) {len(pcr_taifex)} 天 → 覆蓋 FinMind 估算")
        except Exception as _pe:
            print(f"[LI-v8] PCR(TAIFEX)略過: {_pe}")

    # TAIFEX: 嘗試 target 所有日期（最多14天），每天超時7s
    for _td in target:   # 全部 target 日期
        if _taifex_reachable:
            try:
                _lt_res = taifex_large_trader(_td)
                if _lt_res and isinstance(_lt_res, dict):
                    taifex_lt[_td] = _lt_res
                    print(f"[TAIFEX-LT] {_td} ✅ {_lt_res}")
            except Exception as _te:
                print(f"[TAIFEX-LT] {_td} ❌ {type(_te).__name__}: {_te}")
        if _taifex_reachable:
          try:
            # taifex_mtx_data returns (leek, total_oi) or just leek
            _mtx_result = taifex_mtx_data(_td)
            if isinstance(_mtx_result, tuple) and len(_mtx_result) == 2:
                _leek_val, _oi_val = _mtx_result
                if _oi_val: taifex_mtx_oi[_td] = _oi_val
            else:
                _leek_val = _mtx_result
            if _leek_val is not None:
                taifex_leek[_td] = _leek_val
                print(f"[TAIFEX-MTX] {_td} ✅ 韭菜={_leek_val}% OI={taifex_mtx_oi.get(_td,'-')}")
          except Exception as _me:
            print(f"[TAIFEX-MTX] {_td} ❌ {type(_me).__name__}: {_me}")

    # ═══ 7. 組合 DataFrame ══════════════════════════════════════
    rows = []
    for d in target:
        inst = inst_dict.get(d, {})
        _lt  = taifex_lt.get(d, {})
        # ── 法人空多比（估算韭菜方向）──────────────────────────
        # 精確韭菜指數需 TAIFEX 全體 OI，在 Colab 無法取得
        # 改用「法人淨空比 = (法人空 - 法人多) / (法人空 + 法人多) × 100」
        # 正值=法人淨空（散戶被迫多方，反向警戒）；負值=法人淨多（散戶悲觀）
        _leek = None
        if df_mtx is not None and not df_mtx.empty:
            _mtx_d = df_mtx[df_mtx["date"].astype(str).str.replace("-","") == d]
            if not _mtx_d.empty:
                _inst_l = _inst_s = 0
                for _, _mr in _mtx_d.iterrows():
                    if any(k in str(_mr.get("institutional_investors","")) for k in ["外資","投信","自營"]):
                        _inst_l += int(pd.to_numeric(_mr.get("long_open_interest_balance_volume",0), errors="coerce") or 0)
                        _inst_s += int(pd.to_numeric(_mr.get("short_open_interest_balance_volume",0), errors="coerce") or 0)
                _inst_total = _inst_l + _inst_s
                if _inst_total > 0:
                    # 法人淨空比（方向指標，非精確韭菜指數）
                    _leek = round((_inst_s - _inst_l) / _inst_total * 100, 1)
                    _leek = max(-99, min(99, _leek))
        rows.append({
            "_date":     d,
            "日期":       ymd_display(d),
            "成交量":     f"{vol_dict[d]:.1f}億" if vol_dict.get(d) else "-",
            "外資":       inst.get("外資"),
            "投信":       inst.get("投信"),
            "自營":       inst.get("自營"),
            "外資大小":   fut_net.get(d),
            "前五大留倉": _lt.get("前五大"),   # FinMind 免費版無此資料
            "前十大留倉": _lt.get("前十大"),
            "選PCR":      pcr_dict.get(d),
            "外(選)":     opt_dict.get(d),
            "未平倉口數": taifex_mtx_oi.get(d) or _lt.get("未平倉"),
            "韭菜指數":   taifex_leek.get(d) if taifex_leek.get(d) is not None else _leek,
        })
    if not rows:
        print("[LI-v8] ⚠️ 無資料")
        return None
    df = pd.DataFrame(rows)
    filled = sum(1 for _, r in df.iterrows()
                 if any(r.get(c) is not None for c in ["外資大小","選PCR","外(選)","外資"]))
    print(f"[LI-v8] ✅ {len(df)} 筆 ({filled} 筆有數據)")
    return df



def render_leading_table(df):
    """渲染先行指標 HTML 表格"""
    BRACKET = {"外資大小","前五大留倉","前十大留倉","外(選)"}
    SPOT    = {"外資","投信","自營"}
    COLS    = ["外資","投信","自營","外資大小","前五大留倉","前十大留倉","選PCR","外(選)","未平倉口數","韭菜指數"]
    def fmt(v, col):
        if v is None or (isinstance(v, float) and pd.isna(v)): return "-"
        if col in BRACKET:
            n = int(v); return f"({abs(n):,})" if n < 0 else f"{n:,}"
        if col in SPOT: return f"{float(v):+.1f}"
        if col == "選PCR": return f"{float(v):.1f}"
        if col == "未平倉口數": return f"{int(v):,}"
        if col == "韭菜指數": return f"{float(v):+.1f}%"
        return str(v)
    def sty(v, col):
        """回傳 CSS color 字串，給 <span style="..."> 使用"""
        if v is None: return ""
        try:
            if pd.isna(v): return ""
        except (TypeError, ValueError):
            pass
        try: n = float(v)
        except: return ""
        if col in BRACKET:
            if n > 0: return "color:#58a6ff;font-weight:bold;"
            if n < 0: return "color:#f85149;font-weight:bold;"
        if col in SPOT:
            if n > 0: return "color:#58a6ff;"
            if n < 0: return "color:#f85149;"
        if col == "選PCR":
            if n < 0.8: return "color:#58a6ff;"   # 偏多（Call 多）→ 藍
            if n > 1.2: return "color:#f85149;"   # 偏空（Put 多）→ 紅
        if col == "韭菜指數":
            if n > 10:  return "color:#f85149;font-weight:bold;"   # 散戶大幅看多→警戒
            if n < -10: return "color:#58a6ff;font-weight:bold;"   # 散戶大幅看空→機會
        return ""
    h = (
        "<style>\n"
        ".li-tbl{width:100%;border-collapse:collapse;font-size:14px;font-family:Arial,sans-serif;}\n"
        ".li-tbl th,.li-tbl td{border:1px solid #333;padding:6px 12px;text-align:center;white-space:nowrap;}\n"
        ".li-tbl tr:nth-child(even) td{background:rgba(255,255,255,0.04);}\n"
        ".li-tbl tr:hover td{background:rgba(255,215,0,0.08);}\n"
        ".li-hd{background:#1a3a5c;color:#fff;font-weight:bold;}\n"
        ".li-fa{background:#4a2060;color:#FFD700;font-weight:bold;}\n"
        ".li-li{background:#1a4a2a;color:#90EE90;font-weight:bold;}\n"
        ".li-hb{background:#1a1a2e;color:#ccc;font-weight:bold;}\n"
        ".li-dl{font-weight:bold;text-align:left;padding-left:12px;color:#9CDCFE;}\n"
        "</style>\n"
        "<table class=\"li-tbl\"><thead>\n"
        "<tr>\n"
        "  <th rowspan=\"2\" class=\"li-hd\">日期</th><th rowspan=\"2\" class=\"li-hd\">成交量</th>\n"
        "  <th colspan=\"4\" class=\"li-fa\">🏦 法人買賣</th>\n"
        "  <th colspan=\"6\" class=\"li-li\">📡 先行指標</th>\n"
        "</tr>\n"
        "<tr>\n"
        "  <th class=\"li-hb\">外資<br><small>億元</small></th>\n"
        "  <th class=\"li-hb\">投信<br><small>億元</small></th>\n"
        "  <th class=\"li-hb\">自營<br><small>億元</small></th>\n"
        "  <th class=\"li-hb\">外資大小<br><small>口</small></th>\n"
        "  <th class=\"li-hb\">前五大留倉<br><small>口</small></th>\n"
        "  <th class=\"li-hb\">前十大留倉<br><small>口</small></th>\n"
        "  <th class=\"li-hb\">選PCR</th>\n"
        "  <th class=\"li-hb\">外(選)<br><small>千元</small></th>\n"
        "  <th class=\"li-hb\">未平倉口數<br><small>口</small></th>\n"
        "  <th class=\"li-hb\">韭菜指數<br><small>%</small></th>\n"
        "</tr>\n"
        "</thead><tbody>"
    )
    for _, row in df.iterrows():
        h += "<tr>"
        h += f'<td class="li-dl">{row.get("日期","-")}</td><td><span style="color:#9CDCFE;">{row.get("成交量","-")}</span></td>'
        for col in COLS:
            v = row.get(col)
            _s = sty(v, col)
            _f = fmt(v, col)
            h += f'<td><span style="{_s}">{_f}</span></td>' if _s else f'<td>{_f}</td>'
        h += "</tr>\n"
    return h + "</tbody></table>"


def build_ai_data_table(df):
    """把 DataFrame 轉成給 AI 用的純文字表格"""
    COLS = ["日期","成交量","外資","投信","自營","外資大小","前五大留倉","前十大留倉","選PCR","外(選)","未平倉口數","韭菜指數"]
    lines = ["\t".join(COLS)]
    for _, row in df.iterrows():
        vals = []
        for c in COLS:
            v = row.get(c)
            if v is None or (isinstance(v, float) and pd.isna(v)): vals.append("-")
            elif isinstance(v, float): vals.append(f"{v:.1f}")
            elif isinstance(v, int): vals.append(f"{v:,}")
            else: vals.append(str(v))
        lines.append("\t".join(vals))
    return "\n".join(lines)
