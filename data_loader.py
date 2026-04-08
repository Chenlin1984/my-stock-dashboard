try:
    import nest_asyncio as _nest; _nest.apply()
except Exception:
    pass

import yfinance as yf
import pandas as pd
import datetime
try:
    from FinMind.data import DataLoader        # [Fixed] try/except 避免 Cloud 因版本問題崩潰
except ImportError as _e:
    DataLoader = None
    import warnings
    warnings.warn(f"FinMind 未安裝或版本不相容，FinMind 功能將停用：{_e}")
import streamlit as st
import requests as _req_dl
from stock_names import get_stock_name


_T86_DAY_CACHE: dict = {}  # {日期字串: {股票代碼: {外資,投信,自營商}}} 進程級快取，多股共用


def _get_t86_day(ds: str) -> dict:
    """抓取 T86 特定日期的全市場法人資料，進程內快取避免重複請求。
    回傳 {股票代碼: {'外資':float, '投信':float, '自營商':float}}，單位：張"""
    if ds in _T86_DAY_CACHE:
        return _T86_DAY_CACHE[ds]
    HDR = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
    try:
        r = _req_dl.get('https://www.twse.com.tw/fund/T86',
                        params={'response': 'json', 'date': ds, 'selectType': 'ALL'},
                        headers=HDR, timeout=10)
        j = r.json()
        if j.get('stat') != 'OK' or not j.get('data'):
            _T86_DAY_CACHE[ds] = {}
            return {}
        fields = [str(f) for f in j.get('fields', [])]
        fi = {n: i for i, n in enumerate(fields)}
        # T86 欄位名稱用「買賣超」而非「淨」，例如「外陸資買賣超股數」「投信買賣超股數」
        f_idx = next((v for k, v in fi.items() if '外' in k and '買賣超' in k and '自營' not in k), None)
        t_idx = next((v for k, v in fi.items() if '投信' in k and '買賣超' in k), None)
        d_idx = next((v for k, v in fi.items() if '自營' in k and '買賣超' in k and '自行' in k), None)
        print(f'[T86] {ds} fields={fields[:5]} f_idx={f_idx} t_idx={t_idx} d_idx={d_idx}')

        def _pn(row, idx):
            if idx is None or idx >= len(row): return 0.0
            try: return round(int(str(row[idx]).replace(',', '').replace('+', '') or 0) / 1000, 1)
            except: return 0.0

        day_data = {}
        for row in j['data']:
            code = str(row[0]).strip()
            if code:
                day_data[code] = {'外資': _pn(row, f_idx), '投信': _pn(row, t_idx), '自營商': _pn(row, d_idx)}
        _T86_DAY_CACHE[ds] = day_data
        print(f'[TWSE T86] {ds}: {len(day_data)} 支')
        return day_data
    except Exception as e:
        print(f'[TWSE T86] {ds} 失敗: {e}')
        _T86_DAY_CACHE[ds] = {}
        return {}


def _fetch_twse_inst_fallback(stock_id: str, df: pd.DataFrame) -> pd.DataFrame:
    """TWSE T86 備援：T86 一次抓全市場，多股共用同一份進程快取，不重複發請求。"""
    try:
        rows = []
        base = datetime.date.today()
        checked = 0
        for delta in range(20):
            if checked >= 10: break
            d = base - datetime.timedelta(days=delta)
            if d.weekday() >= 5: continue
            day = _get_t86_day(d.strftime('%Y%m%d'))
            checked += 1
            if stock_id in day:
                rows.append({'date': d, **day[stock_id]})
        if rows:
            _df_tw = pd.DataFrame(rows)
            _df_tw['主力合計'] = _df_tw['外資'] + _df_tw['投信'] + _df_tw['自營商']
            df = pd.merge(df, _df_tw, on='date', how='left')
            print(f'[TWSE T86] {stock_id} 補充 {len(rows)} 日')
    except Exception as e:
        print(f'[TWSE T86] {stock_id} 失敗: {e}')
    return df


_TPEX_DAY_CACHE: dict = {}  # {日期字串: {股票代碼: {外資,投信,自營商}}} TPEx 進程級快取


def _get_tpex_day(ds: str) -> dict:
    """抓取 TPEx 特定日期的全市場法人資料（上櫃股），進程內快取。
    回傳 {股票代碼: {'外資':float, '投信':float, '自營商':float}}，單位：張"""
    if ds in _TPEX_DAY_CACHE:
        return _TPEX_DAY_CACHE[ds]
    HDR = {'User-Agent': 'Mozilla/5.0', 'Accept': '*/*',
           'Referer': 'https://www.tpex.org.tw/'}
    try:
        dt = datetime.date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
        roc_year = dt.year - 1911
        roc_date = f'{roc_year}/{dt.month:02d}/{dt.day:02d}'
        r = _req_dl.get(
            'https://www.tpex.org.tw/web/stock/3insti/daily_report/3itrade_hedge_result.php',
            params={'l': 'zh-tw', 'se': 'EW', 't': 'D', 'd': roc_date, 'o': 'json'},
            headers=HDR, timeout=15)
        j = r.json()
        rows_data = j.get('aaData', [])
        if not rows_data:
            _TPEX_DAY_CACHE[ds] = {}
            return {}

        def _pn_tp(row, idx):
            if idx is None or idx >= len(row): return 0.0
            try: return round(int(str(row[idx]).replace(',', '').replace('+', '') or 0) / 1000, 1)
            except: return 0.0

        def _int_tp(row, idx):
            try: return int(str(row[idx]).replace(',', '').replace('+', '') or 0)
            except: return 0

        # ── 動態偵測欄位索引（sColumns 或 buy-sell-net 驗證）──────────
        # TPEx 標準格式：[0]代號 [1]名稱
        # 外資 [2]買 [3]賣 [4]淨  投信 [5]買 [6]賣 [7]淨
        # 自營(自行) [8]買 [9]賣 [10]淨  [11..13]避險  [14]合計
        f_idx, t_idx, d_idx = 4, 7, 10  # 預設索引

        # 用第一筆有效資料驗證 buy - sell ≈ net（容許 1 張以內誤差）
        for _sample in rows_data[:5]:
            if len(_sample) < 11: continue
            _f_buy = _int_tp(_sample, 2); _f_sell = _int_tp(_sample, 3); _f_net = _int_tp(_sample, 4)
            _t_buy = _int_tp(_sample, 5); _t_sell = _int_tp(_sample, 6); _t_net = _int_tp(_sample, 7)
            if abs(_f_net - (_f_buy - _f_sell)) <= 1000 and abs(_t_net - (_t_buy - _t_sell)) <= 1000:
                break  # 驗證通過，使用預設索引
        else:
            # 若驗證全失敗，嘗試欄位較少的格式（部分 TPEx API 版本省略避險欄）
            # [0]代號 [1]名稱 [2]外買 [3]外賣 [4]外淨 [5]投買 [6]投賣 [7]投淨 [8]自買 [9]自賣 [10]自淨
            print(f'[TPEx] {ds} 欄位驗證失敗，row長度={len(rows_data[0]) if rows_data else 0}，使用預設索引')

        day_data = {}
        for row in rows_data:
            code = str(row[0]).strip()
            if not code or len(row) < 11: continue
            day_data[code] = {
                '外資': _pn_tp(row, f_idx),
                '投信': _pn_tp(row, t_idx),
                '自營商': _pn_tp(row, d_idx),
            }
        _TPEX_DAY_CACHE[ds] = day_data
        print(f'[TPEx] {ds} ({roc_date}): {len(day_data)} 支 idx=({f_idx},{t_idx},{d_idx})')
        return day_data
    except Exception as e:
        print(f'[TPEx] {ds} 失敗: {e}')
        _TPEX_DAY_CACHE[ds] = {}
        return {}


def _fetch_tpex_inst_fallback(stock_id: str, df: pd.DataFrame) -> pd.DataFrame:
    """TPEx 上櫃股法人備援，邏輯同 TWSE T86，使用 TPEx 三大法人 API。"""
    try:
        rows = []
        base = datetime.date.today()
        checked = 0
        for delta in range(20):
            if checked >= 10: break
            d = base - datetime.timedelta(days=delta)
            if d.weekday() >= 5: continue
            day = _get_tpex_day(d.strftime('%Y%m%d'))
            checked += 1
            if stock_id in day:
                rows.append({'date': d, **day[stock_id]})
        if rows:
            _df_tp = pd.DataFrame(rows)
            _df_tp['主力合計'] = _df_tp['外資'] + _df_tp['投信'] + _df_tp['自營商']
            df = pd.merge(df, _df_tp, on='date', how='left')
            print(f'[TPEx] {stock_id} 補充 {len(rows)} 日')
    except Exception as e:
        print(f'[TPEx] {stock_id} 失敗: {e}')
    return df


class StockDataLoader:
    """台股數據引擎 - FinMind 優先，Yahoo 備援"""

    def __init__(self):
        import os
        self.dl = DataLoader() if DataLoader is not None else None  # [Fixed] DataLoader 未安裝時不崩潰
        _fm_token    = os.environ.get('FINMIND_TOKEN', '')
        _fm_user     = os.environ.get('FINMIND_USER', '')
        _fm_password = os.environ.get('FINMIND_PASSWORD', '')
        try:
            if _fm_token:
                self.dl.login_by_token(api_token=_fm_token)
                print(f'[FinMind] ✅ Token 登入成功（{_fm_token[:12]}...）')
                self._token = _fm_token
            elif _fm_user and _fm_password:
                self.dl.login(user_id=_fm_user, password=_fm_password)
                print('[FinMind] ✅ 帳號登入成功')
                self._token = ''
            else:
                print('[FinMind] ℹ️  匿名模式（每小時600次）')
                self._token = ''
        except Exception as e:
            print(f'[FinMind] ⚠️  登入失敗：{e}')
            self._token = ''

    @st.cache_data(ttl=3600)
    def get_combined_data(_self, stock_id, days, use_adjusted=True):
        """完整數據載入流程

        Args:
            stock_id: 股票代碼
            days: 載入天數
            use_adjusted: True=還原K線(復權,預設), False=一般K線
        """
        try:
            end_date = datetime.date.today()
            start_date = end_date - datetime.timedelta(days=days + 150)
            start_str = start_date.strftime('%Y-%m-%d')

            # ========== 1. 股價數據 ==========

            df = None

            # 還原K線(復權)：優先直接用 Yahoo auto_adjust=True 生成「已復權 OHLC」
            if use_adjusted:
                try:
                    yf_symbol = f"{stock_id}.TW"
                    df_yf_adj = yf.download(
                        yf_symbol,
                        start=start_date,
                        end=end_date + datetime.timedelta(days=1),
                        auto_adjust=True,
                        progress=False
                    )
                    # 若 .TW 查無資料，嘗試 .TWO（上櫃股票）
                    if df_yf_adj.empty:
                        yf_symbol = f"{stock_id}.TWO"
                        df_yf_adj = yf.download(
                            yf_symbol,
                            start=start_date,
                            end=end_date + datetime.timedelta(days=1),
                            auto_adjust=True,
                            progress=False
                        )
                    if not df_yf_adj.empty:
                        df_yf_adj = df_yf_adj.reset_index()

                        # 處理 MultiIndex
                        if isinstance(df_yf_adj.columns, pd.MultiIndex):
                            df_yf_adj.columns = df_yf_adj.columns.get_level_values(0)

                        df_yf_adj.columns = [str(c).lower() for c in df_yf_adj.columns]

                        # reset_index 後通常是 date 欄位
                        if 'date' not in df_yf_adj.columns and 'datetime' in df_yf_adj.columns:
                            df_yf_adj = df_yf_adj.rename(columns={'datetime': 'date'})

                        df_yf_adj['date'] = pd.to_datetime(df_yf_adj['date']).dt.date

                        # 成交量：股 -> 張
                        if 'volume' in df_yf_adj.columns:
                            df_yf_adj['volume'] = (df_yf_adj['volume'] / 1000).round().astype(int)
                        else:
                            df_yf_adj['volume'] = 0

                        df = df_yf_adj[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
                        print("✅ 還原K線：Yahoo auto_adjust=True（直接生成還原 OHLC）")
                except Exception as e:
                    print(f"⚠️ 還原K線：Yahoo auto_adjust 失敗，改用 FinMind 原始價：{e}")
                    df = None

            # 若未使用還原K線或 Yahoo 失敗，則走 FinMind（一般K線 / 備援）
            if df is None:
                df_price = _self.dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_str)

                if df_price.empty:
                    # Yahoo 備援（先 .TW，再試 .TWO 上櫃）
                    yf_symbol = f"{stock_id}.TW"
                    df_yf = yf.download(yf_symbol, start=start_date, progress=False)
                    if df_yf.empty:
                        yf_symbol = f"{stock_id}.TWO"
                        df_yf = yf.download(yf_symbol, start=start_date, progress=False)
                    if df_yf.empty:
                        return None, "❌ 查無資料", None

                    df_yf = df_yf.reset_index()

                    # ========== 先處理復權（在轉小寫之前）==========
                    has_adj = False
                    adj_ratio_values = None
                    if isinstance(df_yf.columns, pd.MultiIndex):
                        df_yf.columns = df_yf.columns.get_level_values(0)

                    # 檢查並計算復權比例（先儲存起來）
                    if 'Adj Close' in df_yf.columns and 'Close' in df_yf.columns and use_adjusted:
                        adj_ratio_values = (df_yf['Adj Close'] / df_yf['Close']).values
                        adj_close_values = df_yf['Adj Close'].values
                        has_adj = True
                        print("✅ Yahoo 備援：使用復權資料")

                    # 轉小寫
                    df_yf.columns = [str(c).lower() for c in df_yf.columns]
                    df_yf['date'] = pd.to_datetime(df_yf['date']).dt.date

                    # 應用復權
                    if has_adj and use_adjusted and adj_ratio_values is not None:
                        df_yf['open'] = df_yf['open'] * adj_ratio_values
                        df_yf['high'] = df_yf['high'] * adj_ratio_values
                        df_yf['low'] = df_yf['low'] * adj_ratio_values
                        df_yf['close'] = adj_close_values

                    df_yf['volume'] = (df_yf['volume'] / 1000).round().astype(int)
                    df = df_yf[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
                else:
                    # FinMind 數據
                    df = df_price.rename(columns={
                        'Trading_Volume': 'volume',
                        'max': 'high',
                        'min': 'low'
                    })[['date', 'open', 'high', 'low', 'close', 'volume']].copy()

                    df['date'] = pd.to_datetime(df['date']).dt.date
                    df['volume'] = (df['volume'] / 1000).astype(int)

                    # ========== 復權處理（從 Yahoo 獲取）==========
                    if use_adjusted:
                        try:
                            yf_symbol = f"{stock_id}.TW"
                            df_adj = yf.download(yf_symbol, start=start_date, progress=False)

                            if not df_adj.empty:
                                df_adj = df_adj.reset_index()

                                # 處理 MultiIndex
                                if isinstance(df_adj.columns, pd.MultiIndex):
                                    df_adj.columns = df_adj.columns.get_level_values(0)

                                # 計算復權比例
                                if 'Adj Close' in df_adj.columns and 'Close' in df_adj.columns:
                                    df_adj['date_key'] = pd.to_datetime(df_adj['Date']).dt.date
                                    df_adj['adj_ratio'] = df_adj['Adj Close'] / df_adj['Close']

                                    # 合併復權比例
                                    df = df.merge(df_adj[['date_key', 'adj_ratio']],
                                                  left_on='date', right_on='date_key', how='left')

                                    # 填補缺失值為 1.0（不調整）
                                    df['adj_ratio'] = df['adj_ratio'].fillna(1.0)

                                    # 應用復權到所有價格
                                    df['open'] = df['open'] * df['adj_ratio']
                                    df['high'] = df['high'] * df['adj_ratio']
                                    df['low'] = df['low'] * df['adj_ratio']
                                    df['close'] = df['close'] * df['adj_ratio']

                                    # 清理欄位
                                    df = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()
                                    print("✅ FinMind：復權成功")
                                else:
                                    print("⚠️ Yahoo 無 Adj Close，使用原始價格")
                            else:
                                print("⚠️ Yahoo 無資料，使用原始價格")
                        except Exception as e:
                            print(f"⚠️ 復權失敗: {e}")
                            # 失敗時確保 df 只有基本欄位
                            df = df[['date', 'open', 'high', 'low', 'close', 'volume']].copy()

            # ========== 2. 股票名稱 ==========

            stock_name = stock_id
            try:
                stock_info = _self.dl.taiwan_stock_info()
                if not stock_info.empty:
                    match = stock_info[stock_info['stock_id'] == stock_id]
                    if not match.empty:
                        stock_name = match.iloc[0]['stock_name']
            except:
                pass

            if stock_name == stock_id:
                stock_name = get_stock_name(stock_id)

            # ========== 3. 均線 ==========
            for period in [5, 10, 20, 60, 100, 120, 240]:
                df[f'MA{period}'] = df['close'].rolling(window=period).mean()

            # ========== 4. 三大法人 ==========
            try:
                df_inst = _self.dl.taiwan_stock_institutional_investors(
                    stock_id=stock_id,
                    start_date=start_str
                )

                if not df_inst.empty:
                    # 計算淨買賣（股）
                    df_inst['net_buy'] = (df_inst['buy'] - df_inst['sell'])
                    df_inst['date'] = pd.to_datetime(df_inst['date']).dt.date

                    # 透視表
                    df_pivot = df_inst.pivot_table(
                        index='date',
                        columns='name',
                        values='net_buy',
                        aggfunc='sum'
                    ).reset_index()

                    # 股 → 張
                    for col in df_pivot.columns:
                        if col != 'date':
                            df_pivot[col] = (df_pivot[col] / 1000)

                    # 標準化欄位（支援中文名稱和英文名稱）
                    rename_dict = {}
                    for col in df_pivot.columns:
                        col_lower = col.lower()
                        col_str = str(col)
                        # 中文名稱判斷（FinMind 'name' 欄位為中文）
                        if '外資' in col_str and '自營' not in col_str:
                            rename_dict[col] = '外資'
                        elif '投信' in col_str:
                            rename_dict[col] = '投信'
                        elif '自營商' in col_str:
                            rename_dict[col] = '自營商'
                        # 英文名稱判斷
                        elif 'foreign' in col_lower and 'dealer' not in col_lower:
                            rename_dict[col] = '外資'
                        elif 'investment' in col_lower or 'trust' in col_lower:
                            rename_dict[col] = '投信'
                        elif 'dealer' in col_lower and 'self' in col_lower:
                            rename_dict[col] = '自營商'
                    print(f'[籌碼] {stock_id} 欄位:{list(df_pivot.columns[:8])}, rename:{rename_dict}', flush=True)

                    df_pivot.rename(columns=rename_dict, inplace=True)

                    # ✅ 防呆：rename 後可能產生「重複欄名」，會讓後續 pd.to_numeric 爆掉
                    if df_pivot.columns.duplicated().any():
                        date_part = df_pivot[['date']]
                        num_part = df_pivot.drop(columns=['date'])
                        # 重複欄名合併加總（同一法人不同名稱歸類到同一欄時）
                        num_part = num_part.groupby(level=0, axis=1).sum()
                        df_pivot = pd.concat([date_part, num_part], axis=1)


                    # 主力合計
                    main_cols = [c for c in ['外資', '投信', '自營商'] if c in df_pivot.columns]
                    if main_cols:
                        df_pivot['主力合計'] = df_pivot[main_cols].sum(axis=1)

                    df = pd.merge(df, df_pivot, on='date', how='left')
                else:
                    # FinMind 無資料 → fallback: TWSE T86（上市）→ TPEx（上櫃）
                    df = _fetch_twse_inst_fallback(stock_id, df)
                    if '外資' not in df.columns:
                        df = _fetch_tpex_inst_fallback(stock_id, df)

            except Exception as e:
                print(f"法人數據錯誤: {e}")
                try:
                    df = _fetch_twse_inst_fallback(stock_id, df)
                    if '外資' not in df.columns:
                        df = _fetch_tpex_inst_fallback(stock_id, df)
                except Exception:
                    pass

            # ========== 5. 融資融券 ==========
            try:
                df_margin = _self.dl.taiwan_stock_margin_purchase_short_sale(
                    stock_id=stock_id,
                    start_date=start_str
                )

                if not df_margin.empty:
                    df_margin['date'] = pd.to_datetime(df_margin['date']).dt.date

                    margin_data = df_margin[['date', 'MarginPurchaseTodayBalance', 'ShortSaleTodayBalance']].copy()
                    margin_data.rename(columns={
                        'MarginPurchaseTodayBalance': '融資餘額',
                        'ShortSaleTodayBalance': '融券餘額'
                    }, inplace=True)

                    margin_data['融資餘額'] = pd.to_numeric(margin_data['融資餘額'], errors='coerce')
                    margin_data['融券餘額'] = pd.to_numeric(margin_data['融券餘額'], errors='coerce')

                    df = pd.merge(df, margin_data, on='date', how='left')

            except Exception as e:
                print(f"融資數據錯誤: {e}")

            # ========== 6. 數據清洗 ==========
            # 填補0
            fill_cols = ['volume', '外資', '投信', '自營商', '主力合計']
            for col in fill_cols:
                if col in df.columns:
                    df[col] = df[col].fillna(0)

            # ✅ 防呆：若合併後仍有重複欄名，先處理掉（避免 pd.to_numeric 收到 DataFrame）
            if df.columns.duplicated().any():
                # 同名欄位以加總合併（常見於三大法人欄位 rename 撞名）
                df = df.groupby(level=0, axis=1).sum()

            # 強制轉數值
            numeric_cols = ['open', 'high', 'low', 'close', 'volume',
                          '外資', '投信', '自營商', '主力合計', '融資餘額', '融券餘額']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            # ========== 7. 最終輸出 ==========
            df = df.sort_values('date').tail(days).reset_index(drop=True)

            # 除錯
            k_type = "還原K線(復權)" if use_adjusted else "一般K線(未復權)"
            print(f"\n【數據載入成功】{stock_id} {stock_name} - {k_type}")
            print(f"資料筆數: {len(df)}")
            if '外資' in df.columns:
                print(f"外資欄位類型: {df['外資'].dtype}")
                print(f"最後3筆外資數據: {df['外資'].tail(3).tolist()}")

            return df, None, stock_name

        except Exception as e:
            import traceback
            traceback.print_exc()
            return None, f"系統錯誤: {str(e)}", None

    @st.cache_data(ttl=3600)
    def get_monthly_revenue(_self, stock_id):
        """月營收【再修正版】優先順序：MOPS(官方) → FinMind → Goodinfo"""
        import os as _os_rv, datetime as _dt_rv, time as _t_rv
        import requests as _rq_rv, pandas as _pd_rv
        _tok = (_os_rv.environ.get('FINMIND_TOKEN','') or
                _os_rv.environ.get('FM_TOKEN',''))
        end_date   = _dt_rv.date.today()
        start_date = end_date - _dt_rv.timedelta(days=1095)
        start_str  = start_date.strftime('%Y-%m-%d')
        df_revenue = None

        # ── 方案0: FinMind TaiwanStockMonthRevenue（優先，MOPS year-file全部404）
        if _tok and df_revenue is None:
            try:
                _r_fm0 = _rq_rv.get(
                    'https://api.finmindtrade.com/api/v4/data',
                    params={'dataset':'TaiwanStockMonthRevenue',
                            'data_id':stock_id, 'start_date':start_str,
                            'token':_tok},
                    headers={'Authorization':f'Bearer {_tok}'}, timeout=20)
                _j0r = _r_fm0.json()
                print(f'[FM-Rev0] {stock_id}: status={_j0r.get("status")} rows={len(_j0r.get("data",[]))}')
                if _j0r.get('status')==200 and _j0r.get('data'):
                    _df0r = _pd_rv.DataFrame(_j0r['data'])
                    if 'revenue' in _df0r.columns:
                        if 'date' not in _df0r.columns:
                            _df0r['date'] = (_df0r['revenue_year'].astype(str)+'-'+
                                             _df0r['revenue_month'].astype(str).str.zfill(2)+'-01')
                        _df0r['date'] = _pd_rv.to_datetime(_df0r['date'])
                        df_revenue = _df0r.sort_values('date').reset_index(drop=True)
                        print(f'[FM-Rev0] {stock_id}: ✅ {len(df_revenue)}筆')
            except Exception as _e0r:
                print(f'[FM-Rev0] {stock_id}: ❌ {type(_e0r).__name__}: {_e0r}')


        # ── 方案0: FinMind 月營收（優先，因MOPS 年份HTML全部404）────
        if df_revenue is None and _tok:
            try:
                _rfm0 = _rq_rv.get(
                    'https://api.finmindtrade.com/api/v4/data',
                    params={'dataset':'TaiwanStockMonthRevenue',
                            'data_id':stock_id,'start_date':start_str,'token':_tok},
                    headers={'Authorization':f'Bearer {_tok}'}, timeout=20)
                _jfm0 = _rfm0.json()
                print(f'[FM-Rev] {stock_id}: status={_jfm0.get("status")} rows={len(_jfm0.get("data",[]))}')
                if _jfm0.get('status')==200 and _jfm0.get('data'):
                    _dffm0 = _pd_rv.DataFrame(_jfm0['data'])
                    if 'revenue' in _dffm0.columns:
                        if 'date' not in _dffm0.columns:
                            _dffm0['date'] = (_dffm0['revenue_year'].astype(str)+'-'+
                                              _dffm0['revenue_month'].astype(str).str.zfill(2)+'-01')
                        _dffm0['date'] = _pd_rv.to_datetime(_dffm0['date'])
                        df_revenue = _dffm0.sort_values('date').reset_index(drop=True)
                        print(f'[FM-Rev] {stock_id}: ✅ {len(df_revenue)}筆')
            except Exception as _efm0:
                print(f'[FM-Rev] {stock_id}: ❌ {type(_efm0).__name__}: {_efm0}')

        # ── 方案A: MOPS 月營收（官方來源，無需 Token）──────────
        try:
            import pandas as _pd_mops
            _today_rv = _dt_rv.date.today()
            for _y_offset_rv in range(3):
                _yr = _today_rv.year - _y_offset_rv
                for _mops_url_rv in [
                    f'https://mops.twse.com.tw/nas/t21/sii/t21sc03_{_yr}_0.html',
                    f'https://mops.twse.com.tw/nas/t21/otc/t21sc03_{_yr}_0.html',
                    f'https://mops.twse.com.tw/nas/t21/sii/t21sc03_{_yr-1}_0.html',
                    f'https://mops.twse.com.tw/nas/t21/otc/t21sc03_{_yr-1}_0.html',
                ]:
                    try:
                        import requests as _rq_mops
                        _rm2 = _rq_mops.get(_mops_url_rv,
                                            headers={'User-Agent':'Mozilla/5.0'},
                                            timeout=12)
                        if _rm2.status_code != 200: continue
                        _dfs_m2 = _pd_mops.read_html(_rm2.text)
                        _mops_rows2 = []
                        for _dm2 in _dfs_m2:
                            _dm2.columns = [str(c) for c in _dm2.columns]
                            _id_c = next((c for c in _dm2.columns if
                                any(k in c for k in ['代號','股票代碼','公司代號'])), None)
                            _rv_c = next((c for c in _dm2.columns if
                                '當月' in c and ('收' in c or '營收' in c)), None)
                            _yoy_c = next((c for c in _dm2.columns if
                                'YoY' in c or '年增' in c), None)
                            if not _id_c or not _rv_c: continue
                            _row2 = _dm2[_dm2[_id_c].astype(str).str.strip()==str(stock_id)]
                            if _row2.empty: continue
                            for _, _r2 in _row2.iterrows():
                                try:
                                    _rv2 = float(str(_r2[_rv_c]).replace(',',''))
                                    _yoy2 = float(str(_r2.get(_yoy_c,0)).replace(',','').replace('%','')) if _yoy_c else None
                                    if _rv2 > 0:
                                        _mops_rows2.append({
                                            'revenue': _rv2 * 1000,
                                            'date': f'{_yr}-{_today_rv.month:02d}-01',
                                            'yoy': _yoy2})
                                except: pass
                        if _mops_rows2:
                            df_revenue = _pd_mops.DataFrame(_mops_rows2)
                            df_revenue['date'] = _pd_mops.to_datetime(df_revenue['date'])
                            print(f'[MOPS-Rev] {stock_id}: ✅ {len(df_revenue)} 筆')
                            break
                    except: continue
                if df_revenue is not None: break
        except Exception as _eM_rv:
            print(f'[MOPS-Rev] {stock_id}: {_eM_rv}')

        # ── 方案B: FinMind TaiwanStockMonthRevenue（API，需Token）──
        if df_revenue is None and _tok:
            try:
                import requests as _rq_fm_rv
                _r = _rq_fm_rv.get(
                    'https://api.finmindtrade.com/api/v4/data',
                    params={'dataset': 'TaiwanStockMonthRevenue',
                            'data_id': stock_id,
                            'start_date': start_str,
                            'token': _tok},
                    headers={'Authorization': f'Bearer {_tok}'},
                    timeout=20)
                _j = _r.json()
                print(f'[FM-Rev] {stock_id}: status={_j.get("status")} rows={len(_j.get("data",[]))}')
                if _j.get('status') == 200 and _j.get('data'):
                    _df = _pd_rv.DataFrame(_j['data'])
                    # 欄位：date, revenue, revenue_year, revenue_month
                    # 統一欄位名
                    _rename = {}
                    for _c in _df.columns:
                        if 'revenue' == _c.lower(): _rename[_c] = 'revenue'
                        elif 'year'  in _c.lower(): _rename[_c] = 'revenue_year'
                        elif 'month' in _c.lower(): _rename[_c] = 'revenue_month'
                    _df = _df.rename(columns=_rename)
                    if 'date' not in _df.columns and 'revenue_year' in _df.columns:
                        _df['date'] = _df['revenue_year'].astype(str) + '-' + _df['revenue_month'].astype(str).str.zfill(2) + '-01'
                    if 'revenue' in _df.columns:
                        _df['date'] = _pd_rv.to_datetime(_df['date'])
                        _df = _df.sort_values('date')
                        df_revenue = _df
                        print(f'[FM-Rev] {stock_id}: ✅ {len(df_revenue)} 筆')
            except Exception as _eF:
                print(f'[FM-Rev] {stock_id}: {_eF}')

        # ── 方案B2: MOPS 每年月份統計表（備援方式）───────────────
        if df_revenue is None:
            try:
                _mops_rows = []
                _today = _dt_rv.date.today()
                for _y_offset in range(3):
                    _y = _today.year - _y_offset
                    _url_mops = ('https://mops.twse.com.tw/nas/t21/sii/'
                                 f't21sc03_{_y}_0.html')
                    _rm = _rq_rv.get(_url_mops,
                                     headers={'User-Agent':'Mozilla/5.0'},
                                     timeout=15)
                    if _rm.status_code != 200: continue
                    _dfs_m = _pd_rv.read_html(_rm.text)
                    for _dm in _dfs_m:
                        _dm.columns = [str(c) for c in _dm.columns]
                        # 找代碼欄
                        _id_col = next((c for c in _dm.columns
                                        if any(k in c for k in ['代號','股票代碼','公司代號'])), None)
                        _rv_col = next((c for c in _dm.columns
                                        if '當月' in c and ('收' in c or '營收' in c)), None)
                        if not _id_col or not _rv_col: continue
                        _row = _dm[_dm[_id_col].astype(str).str.strip() == str(stock_id)]
                        if _row.empty: continue
                        for _, _r in _row.iterrows():
                            try:
                                _rv = float(str(_r[_rv_col]).replace(',',''))
                                if _rv > 0:
                                    _mops_rows.append({'revenue': _rv * 1000,
                                                       'date': f'{_y}-{_today.month:02d}-01'})
                            except: pass
                if _mops_rows:
                    df_revenue = _pd_rv.DataFrame(_mops_rows)
                    df_revenue['date'] = _pd_rv.to_datetime(df_revenue['date'])
                    print(f'[MOPS-Rev] {stock_id}: ✅ {len(df_revenue)} 筆')
            except Exception as _eM:
                print(f'[MOPS-Rev] {stock_id}: {_eM}')

        # ── 方案C: Goodinfo.tw（最後備援）──────────────────────
        if df_revenue is None:
            try:
                _gi_hdr = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                           'Referer':'https://goodinfo.tw/tw/index.asp',
                           'Accept-Language':'zh-TW,zh;q=0.9'}
                # 嘗試兩個月營收頁面
                for _gi_url in [
                    f'https://goodinfo.tw/tw/StockBzPerformance.asp?STOCK_ID={stock_id}',
                    f'https://goodinfo.tw/tw/StockMonthlyBizStatus.asp?STOCK_ID={stock_id}',
                ]:
                  try:
                    _rgi = _rq_rv.get(_gi_url, headers=_gi_hdr, timeout=20)
                    _rgi.encoding = 'utf-8'
                    if _rgi.status_code != 200 or len(_rgi.text) < 1000: continue
                    _gi_tables = _pd_rv.read_html(_rgi.text, encoding='utf-8')
                    _rows_gi = []
                    for _gt in _gi_tables:
                        _col_strs = [str(c) for c in _gt.columns]
                        # 放寬條件：含「月/YoY/營收/Revenue」或欄位多為數字（1~12月資料）
                        _has_rev_kw = any(any(k in str(c) for k in ['月','YoY','營收','Revenue','revenue']) for c in _col_strs)
                        _has_num_cols = sum(1 for c in _col_strs if str(c).isdigit()) >= 6
                        if not (_has_rev_kw or _has_num_cols): continue
                        if any(any(k in str(c) for k in ['月','YoY','營收','Revenue','revenue']) for c in _col_strs):
                            for _, _row_gi in _gt.iterrows():
                                _yc = str(_row_gi.iloc[0]).split('/')[0].split('(')[0].strip()
                                try:
                                    _y = int(_yc)
                                    if _y < 2000: _y += 1911
                                    for _mi, _mo in enumerate(range(1,13)):
                                        if _mi+1 < len(_row_gi):
                                            try:
                                                _rv = float(str(_row_gi.iloc[_mi+1]).replace(',','').replace('--',''))
                                                if _rv > 0:
                                                    _rows_gi.append({'revenue_year':_y,
                                                                     'revenue_month':_mo,
                                                                     'revenue':_rv*1e6,
                                                                     'date':f'{_y}-{_mo:02d}-01'})
                                            except: pass
                                except: pass
                    if _rows_gi:
                        df_revenue = _pd_rv.DataFrame(_rows_gi)
                        df_revenue['date'] = _pd_rv.to_datetime(df_revenue['date'])
                        df_revenue = df_revenue.sort_values('date')
                        print(f'[Goodinfo-Rev] {stock_id} ({_gi_url.split("?")[0].split("/")[-1]}): ✅ {len(df_revenue)} 筆')
                        break  # 成功就跳出 URL 迴圈
                  except Exception as _eGi:
                    print(f'[Goodinfo-Rev] {_gi_url}: {_eGi}')
            except Exception as _eG:
                print(f'[Goodinfo-Rev] {stock_id}: {_eG}')

        if df_revenue is not None and not df_revenue.empty:
            # 計算 YoY
            if 'revenue' in df_revenue.columns:
                df_revenue['yoy'] = df_revenue['revenue'].pct_change(12) * 100
            return df_revenue, None
        return None, '月營收：三來源均失敗（FinMind/MOPS/Goodinfo）'

    def get_quarterly_data(_self, stock_id):
        """載入近3年季度財務數據（季營收、季毛利率）

        為了避免不同資料源的「type」欄位格式不一致（例如：Q1/Q2、季報、Quarter 等），
        這裡採用「先寬鬆取回 → 再用規則辨識季度」的方式，提高成功率。
        """
        try:
            import re
            # 取回近 3 年資料（約 12 季 + buffer）
            end_date = datetime.date.today()
            start_date = end_date - datetime.timedelta(days=1200)
            start_str = start_date.strftime('%Y-%m-%d')

            # 先試 FinMind REST API
            df_fin = None
            try:
                import os as _os_q; import requests as _rq_q
                _tok_q = _os_q.environ.get('FINMIND_TOKEN', '')
                # 免費版：TaiwanStockFinancialStatement（無s）；付費版：有s；兩個都試
                _df_q_tmp = None
                for _ds_q in ['TaiwanStockFinancialStatement', 'TaiwanStockFinancialStatements']:
                    try:
                        _resp_q = _rq_q.get('https://api.finmindtrade.com/api/v4/data',
                            params={'dataset': _ds_q, 'data_id': stock_id, 'start_date': start_str},
                            headers={'Authorization': f'Bearer {_tok_q}'} if _tok_q else {},
                            timeout=25)
                        _jd_q = _resp_q.json()
                        print(f'[季財報REST/{_ds_q}] {stock_id} status={_jd_q.get("status")}, rows={len(_jd_q.get("data",[]))}')
                        if _jd_q.get('status') == 200 and _jd_q.get('data'):
                            _df_q_tmp = pd.DataFrame(_jd_q['data'])
                            break
                    except Exception as _eq2:
                        print(f'[季財報REST/{_ds_q}] {_eq2}')
                if _df_q_tmp is not None and not _df_q_tmp.empty:
                    df_fin = _df_q_tmp
            except Exception as _eq: print(f'[季財報REST] {_eq}')

            # 備援: FinMind Library
            if df_fin is None or df_fin.empty:
                try:
                    df_fin = _self.dl.taiwan_stock_financial_statement(
                        stock_id=stock_id, start_date=start_str)
                except Exception: pass

            if df_fin is None or df_fin.empty:
                # ── 備援: Goodinfo 季財報 ──
                try:
                    import requests as _rq_gi_q, pandas as _pd_gi_q
                    _gi_hdr_q = {'User-Agent':'Mozilla/5.0','Accept':'text/html,application/xhtml+xml',
                                  'Referer':'https://goodinfo.tw/tw/index.asp'}
                    _gi_url_q = f"https://goodinfo.tw/tw/StockFinDetail.asp?RPT_CAT=IS_M_QUAR&STOCK_ID={stock_id}"
                    _gi_r_q   = _rq_gi_q.get(_gi_url_q, headers=_gi_hdr_q, timeout=25)
                    _gi_r_q.encoding = 'utf-8'
                    if _gi_r_q.status_code == 200 and len(_gi_r_q.text) > 500:
                        _gi_tables_q = _pd_gi_q.read_html(_gi_r_q.text, encoding='utf-8')
                        _rows_q = []
                        for _tb_q in _gi_tables_q:
                            _cols_q = [str(c) for c in _tb_q.columns]
                            # 找有季度標籤的表（如 113Q4 / 2024Q4 / Q1）
                            if not any(re.search(r'Q[1-4]|\d{3}Q|\d{4}Q', c) for c in _cols_q):
                                continue
                            for _, _row_q in _tb_q.iterrows():
                                _lbl_q = str(_row_q.iloc[0])
                                # 營收列
                                if any(k in _lbl_q for k in ['營業收入','收入合計','Revenue']):
                                    for _ci_q, _col_q in enumerate(_cols_q[1:], 1):
                                        _qm = re.search(r'(\d{3,4})Q([1-4])', str(_col_q))
                                        if not _qm: continue
                                        _yr_q = int(_qm.group(1)); _qt_q = int(_qm.group(2))
                                        if _yr_q < 1000: _yr_q += 1911  # ROC
                                        _v_q = float(str(_row_q.iloc[_ci_q]).replace(',','').replace('--','').replace('N/A','')) if _ci_q < len(_row_q) else float('nan')
                                        if not pd.isna(_v_q):
                                            _rows_q.append({'date': f'{_yr_q}-{_qt_q*3:02d}-01',
                                                             'type': f'Q{_qt_q}', 'value': _v_q * 1e6,
                                                             'origin_name': '營業收入合計', 'stock_id': stock_id})
                        if _rows_q:
                            df_fin = pd.DataFrame(_rows_q)
                            print(f"[Goodinfo QTR] {stock_id}: ✅ {len(df_fin)}筆")
                except Exception as _eGI_q:
                    print(f"[Goodinfo QTR] {stock_id}: {_eGI_q}")

            if df_fin is None or df_fin.empty:
                # ── 最終備援: yfinance 季度 EPS ──
                try:
                    import yfinance as _yf_q, pandas as _pd_yf_q
                    _tk_q = _yf_q.Ticker(f"{stock_id}.TW")
                    _qf_q = _tk_q.quarterly_financials
                    if _qf_q is not None and not _qf_q.empty:
                        _rows_yf = []
                        for _col_q in _qf_q.columns:
                            _dt_q = pd.Timestamp(_col_q)
                            _qt_num = ((_dt_q.month - 1) // 3) + 1
                            _rev_row = None
                            for _idx_q in _qf_q.index:
                                if any(k in str(_idx_q) for k in ['Revenue','Total Revenue','revenue']):
                                    _rev_row = _idx_q; break
                            _rev_val = float(_qf_q.loc[_rev_row, _col_q]) if _rev_row is not None else float('nan')
                            _rows_yf.append({'date': _dt_q.strftime('%Y-%m-%d'),
                                              'type': f'Q{_qt_num}', 'value': _rev_val,
                                              'origin_name': '營業收入合計', 'stock_id': stock_id})
                        if _rows_yf:
                            df_fin = pd.DataFrame(_rows_yf)
                            print(f"[yfinance QTR] {stock_id}: ✅ {len(df_fin)}筆")
                except Exception as _eYF_q:
                    print(f"[yfinance QTR] {stock_id}: {_eYF_q}")

            if df_fin is None or df_fin.empty:
                return None, f"{stock_id} 季財報：所有來源（FinMind/Goodinfo/yfinance）均無資料"

            # ===== 0) 判斷是否金融股（避免把一般公司邏輯套到金融股）=====
            def _is_financial_stock(_sid: str) -> bool:
                try:
                    info = _self.dl.taiwan_stock_info()
                    if info is not None and not info.empty and 'stock_id' in info.columns:
                        m2 = info[info['stock_id'] == _sid]
                        if not m2.empty:
                            row = m2.iloc[0].to_dict()
                            # 嘗試從可能的產業欄位判斷
                            for k in ['industry_category', 'industry', 'category', 'type', '產業別', '產業類別', '產業分類', 'industry_category_zh']:
                                if k in row and row[k] is not None:
                                    s = str(row[k])
                                    if any(w in s for w in ['金融', '保險', '金控', '銀行', '證券']):
                                        return True
                except Exception:
                    pass
                # 保底：台股金融族群常見代碼前綴
                return str(_sid).startswith(('28', '58'))

            is_finance = _is_financial_stock(stock_id)

            # ===== 金融股：季營收改用「月營收加總」；毛利率不計算 =====
            if is_finance:
                try:
                    df_m, err_m = _self.get_monthly_revenue(stock_id)
                    if err_m is None and df_m is not None and not df_m.empty:
                        df_m = df_m.copy()
                        col_date = '日期' if '日期' in df_m.columns else ('date' if 'date' in df_m.columns else None)
                        col_rev  = '營收' if '營收' in df_m.columns else ('revenue' if 'revenue' in df_m.columns else None)
                        if col_date is not None and col_rev is not None:
                            df_m[col_date] = pd.to_datetime(df_m[col_date], errors='coerce')
                            df_m = df_m.dropna(subset=[col_date]).sort_values(col_date)
                            df_m['_y'] = df_m[col_date].dt.year.astype('int64')
                            df_m['_q'] = (((df_m[col_date].dt.month - 1) // 3) + 1).astype('int64')
                            df_m[col_rev] = pd.to_numeric(df_m[col_rev], errors='coerce')
                            qsum = df_m.groupby(['_y', '_q'])[col_rev].sum().reset_index()
                            qsum = qsum.rename(columns={'_y': '年度', '_q': '季度', col_rev: '營收'})
                            qsum['季度標籤'] = qsum['年度'].astype(str) + 'Q' + qsum['季度'].astype(str)
                            qsum['毛利率'] = pd.NA
                            qsum['毛利率名稱'] = '毛利率'
                            qsum['是否金融股'] = True
                            return qsum, None
                except Exception:
                    # 若月營收加總也失敗，才繼續走下面的原本邏輯（避免整段中斷）
                    pass


            # ===== 除錯資訊（保留，用來判斷 API 欄位格式）=====
            print(f"\n=== 季度財報除錯資訊 ({stock_id}) ===")
            print(f"欄位: {df_fin.columns.tolist()}")
            print(f"總筆數: {len(df_fin)}")

            # ===== 1) 先嘗試辨識「季度」資料 =====
            df_work = df_fin.copy()

            # 有些資料會用 type 表示季度/年度；先把 type 轉成字串便於判斷
            if 'type' in df_work.columns:
                df_work['type'] = df_work['type'].astype(str)
                type_uniques = sorted(df_work['type'].dropna().unique().tolist())
                print(f"type 唯一值(前 20): {type_uniques[:20]}")

                # 常見季度型態：Q1/Q2/Q3/Q4、1Q/2Q...、季報、Quarter、季
                q_mask = df_work['type'].str.contains(r"(?:^Q[1-4]$|^[1-4]Q$|季|季報|quarter)", case=False, na=False)
                df_q = df_work[q_mask].copy()

                # 若過濾後反而全空，代表 type 不是這種格式（例如根本沒有區分），就退回用全量資料
                if not df_q.empty:
                    df_work = df_q
                    print(f"✓ 以 type 規則辨識季度後筆數: {len(df_work)}")
                else:
                    print("⚠️ type 欄位未能辨識季度格式，改用全量資料繼續嘗試（避免誤殺）")

            # ===== 2) Pivot：date x 科目 =====
            need_cols = {'date', 'origin_name', 'value'}
            if not need_cols.issubset(set(df_work.columns)):
                # 缺欄位就直接回報，並附上目前欄位，方便定位
                return None, f"季度財報欄位不足（需要 date/origin_name/value），目前只有: {', '.join(df_work.columns.astype(str).tolist()[:20])}"

            df_pivot = df_work.pivot_table(
                index=['date'],
                columns='origin_name',
                values='value',
                aggfunc='first'
            ).reset_index()

            # date 轉時間
            df_pivot['date'] = pd.to_datetime(df_pivot['date'], errors='coerce')
            df_pivot = df_pivot[df_pivot['date'].notna()].copy()
            if df_pivot.empty:
                return None, "季度財報日期欄位無法解析"

            # ===== 3) 建立季度標籤 =====
            df_quarterly = pd.DataFrame()
            df_quarterly['年度'] = df_pivot['date'].dt.year
            df_quarterly['季度'] = ((df_pivot['date'].dt.month - 1) // 3) + 1
            df_quarterly['季度標籤'] = df_quarterly['年度'].astype(int).astype(str) + 'Q' + df_quarterly['季度'].astype(int).astype(str)

            # ===== 4) 找「營收」欄位（一般公司優先；金融股/金控用月營收加總作為季度營收）=====
            is_finance = False
            revenue_candidates = []
            for col in df_pivot.columns:
                c = str(col)
                if any(k in c for k in ['營業收入', '收入合計', '營收']) or re.search(r"\brevenue\b", c, re.I):
                    revenue_candidates.append(col)

            # 金融/保險常見的「營收代理」欄位（不一定等於營收，但可用來判斷是否為金融股）
            finance_candidates = []
            for col in df_pivot.columns:
                c = str(col)
                if any(k in c for k in ['淨收益', '利息淨收益', '利息以外淨收益', '保險負債準備淨變動']) or re.search(r"interest\s*net\s*income|net\s*interest|net\s*revenue", c, re.I):
                    finance_candidates.append(col)

            if revenue_candidates:
                rev_col = revenue_candidates[0]
                print(f"✓ 營收欄位(一般): {rev_col}")
                df_quarterly['營收'] = pd.to_numeric(df_pivot[rev_col], errors='coerce')
            else:
                # 找不到一般營收欄位：很可能是金融股/金控
                is_finance = True if finance_candidates else True
                # 先用財報中的代理欄位墊底（避免空值），後續會用「月營收加總」覆蓋季度營收
                if finance_candidates:
                    rev_col = finance_candidates[0]
                    print(f"✓ 營收欄位(金融代理): {rev_col}")
                    df_quarterly['營收'] = pd.to_numeric(df_pivot[rev_col], errors='coerce')
                else:
                    df_quarterly['營收'] = pd.NA
                    print("⚠️ 財報找不到一般營收欄位，改用月營收加總計算季度營收")

            # 金融股：季度營收一律以「月營收 3 個月加總」為準（對齊看盤軟體的季營收）
            if is_finance:
                df_month, _merr = _self.get_monthly_revenue(stock_id)
                if df_month is not None and not df_month.empty:
                    dfm = df_month[['年', '月', '營收']].copy()
                    dfm['日期'] = pd.to_datetime(dfm['年'].astype(str) + '-' + dfm['月'].astype(int).astype(str).str.zfill(2) + '-01', errors='coerce')
                    dfm = dfm[dfm['日期'].notna()].copy()
                    dfm['年度'] = dfm['日期'].dt.year.astype(int)
                    dfm['季度'] = (((dfm['日期'].dt.month - 1) // 3) + 1).astype(int)
                    qsum = dfm.groupby(['年度', '季度'], as_index=False)['營收'].sum()
                    # 用字串鍵合併，避免 pandas 在不同平台發生 int/int64 factorize mismatch
                    df_quarterly['yq_key'] = df_quarterly['年度'].astype(int).astype(str) + 'Q' + df_quarterly['季度'].astype(int).astype(str)
                    qsum['yq_key'] = qsum['年度'].astype(int).astype(str) + 'Q' + qsum['季度'].astype(int).astype(str)
                    df_quarterly = df_quarterly.merge(qsum[['yq_key', '營收']].rename(columns={'營收': '營收_月加總'}), on='yq_key', how='left')
                    df_quarterly['營收'] = pd.to_numeric(df_quarterly['營收_月加總'], errors='coerce').fillna(pd.to_numeric(df_quarterly['營收'], errors='coerce'))
                    df_quarterly = df_quarterly.drop(columns=['營收_月加總'])
                else:
                    print(f"⚠️ 月營收加總失敗: {_merr}")

            # 預設指標名稱
            df_quarterly['毛利率名稱'] = '毛利率'
            # ===== 5) 毛利率：優先用毛利，沒有就用(營收-成本) =====
            # 金融股：不計算毛利率，改用稅後純益率(%) 取代；若算不出則留空
            if is_finance:
                net_col = None
                for col in df_pivot.columns:
                    c = str(col)
                    if any(k in c for k in ['本期稅後淨利', '稅後淨利', '淨利（淨損）', '繼續營業單位本期淨利']) or re.search(r"income\s*after\s*tax|net\s*income", c, re.I):
                        net_col = col
                        break
                if net_col is not None:
                    net_income = pd.to_numeric(df_pivot[net_col], errors='coerce')
                    df_quarterly['毛利率'] = (net_income / pd.to_numeric(df_quarterly['營收'], errors='coerce') * 100).round(2)
                    df_quarterly['毛利率名稱'] = '稅後純益率'
                    print(f"✓ 金融股：以稅後純益率取代毛利率（欄位: {net_col}）")
                else:
                    df_quarterly['毛利率'] = float('nan')
                    df_quarterly['毛利率名稱'] = '稅後純益率'
                    print("⚠️ 金融股：找不到稅後淨利欄位，稅後純益率留空")

            # 一般公司：照舊計算毛利率
            gp_col = None
            for col in df_pivot.columns:
                c = str(col)
                if any(k in c for k in ['毛利', '營業毛利']) or re.search(r"gross\s*profit", c, re.I):
                    gp_col = col
                    break

            if gp_col is not None:
                print(f"✓ 毛利欄位: {gp_col}")
                gp = pd.to_numeric(df_pivot[gp_col], errors='coerce')
                df_quarterly['毛利率'] = (gp / df_quarterly['營收'] * 100).round(2)
            else:
                cost_col = None
                for col in df_pivot.columns:
                    c = str(col)
                    if any(k in c for k in ['營業成本', '成本合計']) or re.search(r"cost\s+of\s+revenue|cost\s+of\s+goods", c, re.I):
                        cost_col = col
                        break

                if cost_col is not None:
                    print(f"✓ 成本欄位: {cost_col}")
                    cost = pd.to_numeric(df_pivot[cost_col], errors='coerce')
                    df_quarterly['毛利率'] = ((df_quarterly['營收'] - cost) / df_quarterly['營收'] * 100).round(2)
                else:
                    df_quarterly['毛利率'] = float('nan')
                    print("⚠️ 無法找到毛利/成本欄位，毛利率將顯示空值")

            # ===== 5b) EPS：每股盈餘 =====
            eps_col = None
            for col in df_pivot.columns:
                c = str(col)
                if any(k in c for k in ['每股盈餘', '基本每股', 'EPS']) or re.search(r"basic\s*eps|earnings\s*per\s*share", c, re.I):
                    eps_col = col
                    break
            if eps_col is not None:
                print(f"✓ EPS 欄位: {eps_col}")
                df_quarterly['EPS'] = pd.to_numeric(df_pivot[eps_col], errors='coerce')
            else:
                df_quarterly['EPS'] = float('nan')
                print("⚠️ 無法找到 EPS 欄位")

            # ===== 5c) 毛利率備援：Goodinfo 季損益 =====
            # FinMind 無毛利/成本欄位（毛利率全 NaN）時，改從 Goodinfo 直接抓取季度毛利率
            if not is_finance and df_quarterly['毛利率'].isna().all():
                try:
                    import requests as _rq_gi_gp
                    _gi_hdr_gp = {'User-Agent': 'Mozilla/5.0',
                                  'Accept': 'text/html,application/xhtml+xml',
                                  'Referer': 'https://goodinfo.tw/tw/index.asp'}
                    _gi_url_gp = (f'https://goodinfo.tw/tw/StockFinDetail.asp'
                                  f'?RPT_CAT=IS_M_QUAR&STOCK_ID={stock_id}')
                    _gi_r_gp = _rq_gi_gp.get(_gi_url_gp, headers=_gi_hdr_gp, timeout=25)
                    _gi_r_gp.encoding = 'utf-8'
                    if _gi_r_gp.status_code == 200 and len(_gi_r_gp.text) > 500:
                        _gi_tbls_gp = pd.read_html(_gi_r_gp.text, encoding='utf-8')
                        _found_gp = False
                        for _tb_gp in _gi_tbls_gp:
                            if _found_gp: break
                            _cols_gp = [str(c) for c in _tb_gp.columns]
                            # 只處理含季度標籤的表（如 113Q4 / 2024Q4）
                            if not any(re.search(r'Q[1-4]|\d{3}Q|\d{4}Q', c) for c in _cols_gp):
                                continue
                            for _, _row_gp in _tb_gp.iterrows():
                                if '毛利率' not in str(_row_gp.iloc[0]): continue
                                _updated_gp = 0
                                for _ci_gp, _col_gp in enumerate(_cols_gp[1:], 1):
                                    _qm_gp = re.search(r'(\d{3,4})Q([1-4])', str(_col_gp))
                                    if not _qm_gp: continue
                                    _yr_gp = int(_qm_gp.group(1))
                                    _qt_gp = int(_qm_gp.group(2))
                                    if _yr_gp < 1000: _yr_gp += 1911  # ROC → 西元
                                    _v_s = (str(_row_gp.iloc[_ci_gp])
                                            .replace(',', '').replace('%', '')
                                            .replace('N/A', '').replace('--', '').strip())
                                    try:
                                        _v_gp = float(_v_s)
                                        _mk = ((df_quarterly['年度'].astype(int) == _yr_gp) &
                                               (df_quarterly['季度'].astype(int) == _qt_gp))
                                        if _mk.any():
                                            df_quarterly.loc[_mk, '毛利率'] = _v_gp
                                            _updated_gp += 1
                                    except Exception:
                                        pass
                                if _updated_gp > 0:
                                    print(f'[Goodinfo 毛利率] {stock_id}: ✅ {_updated_gp} 季')
                                    _found_gp = True
                                    break
                except Exception as _e_gp:
                    print(f'[Goodinfo 毛利率] {stock_id}: {_e_gp}')

            # ===== 6) 清洗與排序 =====
            df_quarterly = df_quarterly.dropna(subset=['營收']).copy()
            # ✅ 金融股：允許負數營收（投資損失等）；一般公司：過濾負數
            if not is_finance:
                df_quarterly = df_quarterly[df_quarterly['營收'] > 0].copy()
            df_quarterly = df_quarterly.drop_duplicates(subset=['季度標籤'], keep='last')
            df_quarterly = df_quarterly.sort_values(['年度', '季度']).tail(12).reset_index(drop=True)

            if df_quarterly.empty:
                return None, "查無有效季度資料（可能該公司/資料源未提供近年季報）"

            print(f"✓ 成功載入 {len(df_quarterly)} 筆季度資料")
            df_quarterly['是否金融股'] = is_finance

            # ✅ 除錯：檢查是否有負數營收
            if (df_quarterly['營收'] < 0).any():
                print(f"⚠️ 發現負數營收（金融股={is_finance}）:")
                neg_data = df_quarterly[df_quarterly['營收'] < 0][['季度標籤', '營收']]
                print(neg_data.to_string(index=False))

            return df_quarterly, None

        except Exception as e:
            import traceback
            traceback.print_exc()
            return None, f"載入錯誤: {str(e)}"""