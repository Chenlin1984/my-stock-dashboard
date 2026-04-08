"""
台股股票名稱查詢模組
優先級：動態快取（TWSE/TPEx OpenAPI）> 靜態字典 > yfinance > 回傳代碼
"""

import os
import pickle
import hashlib
import datetime
import requests

_CACHE_DIR = '/tmp/st_cache'
os.makedirs(_CACHE_DIR, exist_ok=True)

_DYNAMIC_CACHE_PATH = os.path.join(_CACHE_DIR, 'tw_stock_names_v1.pkl')
_DYNAMIC_CACHE_TTL  = 24  # 小時

# ── 靜態備援字典（常用股，動態快取失敗時使用）────────────────
_STATIC_NAMES = {
    '2330': '台積電', '2454': '聯發科', '2317': '鴻海', '2382': '廣達',
    '2308': '台達電', '2303': '聯電', '2882': '國泰金', '2881': '富邦金',
    '2886': '兆豐金', '2891': '中信金', '2603': '長榮', '2609': '陽明',
    '2615': '萬海', '3711': '日月光投控', '2357': '華碩', '2376': '技嘉',
    '6669': '緯穎', '3017': '奇鋐', '6770': '力積電', '6239': '力成',
    '2344': '華邦電', '2337': '旺宏', '3034': '聯詠', '5274': '信驊',
    '3661': '世芯-KY', '2409': '友達', '3481': '群創', '2327': '國巨',
    '2301': '光寶科', '3008': '大立光', '2412': '中華電', '2379': '瑞昱',
    '1301': '台塑', '1303': '南亞', '2002': '中鋼', '1519': '華城',
    '2884': '玉山金', '2885': '元大金', '2890': '永豐金', '5880': '合庫金',
    '2383': '台光電', '3533': '嘉澤', '6488': '環球晶', '6269': '台郡',
    '2049': '上銀', '1590': '亞德客-KY', '2207': '和泰車',
    # ETF
    '0050': '元大台灣50', '0056': '元大高股息', '006208': '富邦台50',
    '00878': '國泰永續高股息', '00919': '群益台灣精選高息',
    '00929': '復華台灣科技優息', '00940': '元大台灣價值高息',
    '00713': '元大台灣高息低波', '00982A': '中信優先金融債',
    '00720B': '元大投資級公司債', '00751B': '元大美債20年',
}


# ── 動態快取：TWSE + TPEx OpenAPI ───────────────────────────
def _load_dynamic_cache() -> dict:
    """從磁碟讀取動態名稱快取（無論是否過期皆載入）"""
    if os.path.exists(_DYNAMIC_CACHE_PATH):
        try:
            with open(_DYNAMIC_CACHE_PATH, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass
    return {}


def _is_cache_stale() -> bool:
    """回傳 True 若快取檔不存在或已超過 TTL。"""
    if not os.path.exists(_DYNAMIC_CACHE_PATH):
        return True
    age_h = (datetime.datetime.now().timestamp()
             - os.path.getmtime(_DYNAMIC_CACHE_PATH)) / 3600
    return age_h >= _DYNAMIC_CACHE_TTL


def _save_dynamic_cache(name_dict: dict) -> None:
    try:
        with open(_DYNAMIC_CACHE_PATH, 'wb') as f:
            pickle.dump(name_dict, f)
    except Exception:
        pass


def _build_dynamic_name_cache() -> dict:
    """從 TWSE + TPEx 免費 OpenAPI 抓取全市場股票名稱。
    回傳 {股票代碼: 中文名稱} dict。"""
    HDR = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
    result = {}

    # 1. TWSE 上市（含ETF）
    _twse_urls = [
        'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_AVG_ALL',
        'https://openapi.twse.com.tw/v1/opendata/t187ap03_L',
    ]
    for _url in _twse_urls:
        try:
            r = requests.get(_url, headers=HDR, timeout=12)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    for item in data:
                        code = str(item.get('Code', item.get('公司代號', ''))).strip()
                        name = str(item.get('Name', item.get('公司簡稱', ''))).strip()
                        if code and name and code not in result:
                            result[code] = name
                    print(f'[股名快取] TWSE {_url.split("/")[-1]}: {len(result)} 筆')
                    if len(result) > 100:
                        break  # 第一個 URL 就夠就不再試
        except Exception as e:
            print(f'[股名快取] TWSE 抓取失敗: {e}')

    # 2. TPEx 上櫃
    try:
        r2 = requests.get(
            'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes',
            headers=HDR, timeout=12)
        if r2.status_code == 200:
            data2 = r2.json()
            if isinstance(data2, list):
                before = len(result)
                for item in data2:
                    code = str(item.get('SecuritiesCompanyCode', '')).strip()
                    name = str(item.get('CompanyName', '')).strip()
                    if code and name and code not in result:
                        result[code] = name
                print(f'[股名快取] TPEx: +{len(result)-before} 筆')
    except Exception as e:
        print(f'[股名快取] TPEx 抓取失敗: {e}')

    # 3. 合併靜態備援（不覆蓋動態結果）
    for k, v in _STATIC_NAMES.items():
        if k not in result:
            result[k] = v

    return result


# 啟動時嘗試載入快取（不阻塞，快取失敗靜默）
_dynamic_cache: dict = _load_dynamic_cache()


def _ensure_cache() -> dict:
    """確保動態快取存在；若空白或過期則嘗試重新抓取。
    只有在新快取筆數多於舊快取時才取代，避免 API 失敗時以少量靜態資料覆蓋大快取。"""
    global _dynamic_cache
    if not _dynamic_cache or _is_cache_stale():
        new_cache = _build_dynamic_name_cache()
        if len(new_cache) > len(_dynamic_cache):
            _dynamic_cache = new_cache
            _save_dynamic_cache(_dynamic_cache)
    return _dynamic_cache


def get_stock_name(stock_id: str) -> str:
    """根據股票代碼取得中文名稱。
    優先級：動態快取（TWSE/TPEx）> 靜態字典 > yfinance > 代碼本身
    """
    # 1. 動態快取
    cache = _ensure_cache()
    if stock_id in cache:
        return cache[stock_id]

    # 2. 靜態備援
    if stock_id in _STATIC_NAMES:
        return _STATIC_NAMES[stock_id]

    # 3. yfinance 最終備援（慢，僅在前兩層都失敗時觸發）
    try:
        import yfinance as yf
        for suffix in ['.TW', '.TWO']:
            _info = yf.Ticker(f'{stock_id}{suffix}').fast_info
            _n = getattr(_info, 'company_name', None)
            if _n and _n not in (f'{stock_id}{suffix}', stock_id, ''):
                # 存入動態快取供下次使用
                _dynamic_cache[stock_id] = _n
                return _n
    except Exception:
        pass

    return stock_id  # 最終 fallback


def refresh_name_cache() -> int:
    """強制重新抓取並更新快取。回傳新快取大小。"""
    global _dynamic_cache
    _dynamic_cache = _build_dynamic_name_cache()
    _save_dynamic_cache(_dynamic_cache)
    return len(_dynamic_cache)
