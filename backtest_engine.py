"""
回測引擎 v3.0 (§7)
單策略回測 + Walk Forward Test + CAGR + 平均盈虧比
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

try:
    from config import BACKTEST_INIT_CASH, BACKTEST_COMMISSION, WFT_TRAIN_YEARS, WFT_TEST_MONTHS
except ImportError:
    BACKTEST_INIT_CASH=1_000_000; BACKTEST_COMMISSION=0.001425
    WFT_TRAIN_YEARS=3; WFT_TEST_MONTHS=12

try:
    from backtesting import Backtest, Strategy
    from backtesting.lib import crossover
    _BACKTEST_AVAILABLE = True
except ImportError:
    _BACKTEST_AVAILABLE = False
    print('[BacktestEngine] ⚠️  backtesting 套件未安裝，請執行 Cell 2')


# ── 策略定義 ─────────────────────────────────────────────────
if _BACKTEST_AVAILABLE:
    class MA_Cross_Strategy(Strategy):
        """均線交叉策略（MA20/MA60）"""
        ma_short = 20
        ma_long  = 60
        def init(self):
            self.ma_s = self.I(lambda x: pd.Series(x).rolling(self.ma_short).mean().values, self.data.Close)
            self.ma_l = self.I(lambda x: pd.Series(x).rolling(self.ma_long).mean().values,  self.data.Close)
        def next(self):
            if crossover(self.ma_s, self.ma_l):    self.buy()
            elif crossover(self.ma_l, self.ma_s):  self.position.close()

    class MA_RSI_Strategy(Strategy):
        """MA + RSI 複合策略（§9 選股條件：MA20>MA60 且 RSI<70）"""
        ma_short=20; ma_long=60; rsi_overbought=70
        def init(self):
            close = self.data.Close
            def _rsi(prices, n=14):
                s=pd.Series(prices); d=s.diff()
                g=d.clip(lower=0).rolling(n).mean(); l=(-d.clip(upper=0)).rolling(n).mean()
                return (100-100/(1+g/(l+1e-10))).values
            self.ma_s = self.I(lambda x: pd.Series(x).rolling(self.ma_short).mean().values, close)
            self.ma_l = self.I(lambda x: pd.Series(x).rolling(self.ma_long).mean().values,  close)
            self.rsi  = self.I(_rsi, close)
        def next(self):
            if self.ma_s[-1]>self.ma_l[-1] and self.rsi[-1]<self.rsi_overbought and not self.position:
                self.buy()
            elif self.rsi[-1]>self.rsi_overbought and self.position:
                self.position.close()


# ── 資料格式轉換 ──────────────────────────────────────────────
def prepare_bt_data(df: pd.DataFrame) -> pd.DataFrame:
    """將 StockDataLoader DataFrame 轉為 backtesting.py 格式"""
    bt = df[['date','open','high','low','close','volume']].copy()
    bt.columns = ['Date','Open','High','Low','Close','Volume']
    bt['Date'] = pd.to_datetime(bt['Date'])
    bt = bt.set_index('Date').dropna()
    for col in ['Open','High','Low','Close','Volume']:
        bt[col] = pd.to_numeric(bt[col], errors='coerce')
    return bt.dropna(subset=['Open','High','Low','Close'])


# ── 績效指標計算 ──────────────────────────────────────────────
def calc_cagr(start_value: float, end_value: float, years: float) -> float:
    """計算年化複合成長率 CAGR"""
    if years <= 0 or start_value <= 0:
        return 0.0
    return round(((end_value / start_value) ** (1 / years) - 1) * 100, 2)


def calc_avg_pnl_ratio(stats) -> float:
    """計算平均盈虧比（平均獲利 / 平均虧損絕對值）"""
    try:
        avg_win  = float(stats.get('Avg. Winning Trade [%]') or 0)
        avg_loss = abs(float(stats.get('Avg. Losing Trade [%]') or 1))
        return round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0
    except Exception:
        return 0.0


# ── 單次回測 ─────────────────────────────────────────────────
def run_backtest(df, strategy='ma_cross',
                 cash=BACKTEST_INIT_CASH,
                 commission=BACKTEST_COMMISSION) -> dict:
    """
    執行單次回測（§7.2）

    Args:
        df       : 股價 DataFrame（來自 StockDataLoader）
        strategy : 'ma_cross' | 'ma_rsi'
        cash     : 初始資金（預設100萬）
        commission: 手續費（台股0.1425%）
    Returns:
        dict: 回測結果摘要，含 CAGR + 平均盈虧比
    """
    if not _BACKTEST_AVAILABLE:
        return {'error': 'backtesting 套件未安裝，請執行 pip install backtesting'}
    if df is None or df.empty:
        return {'error': '無效的股價資料'}
    bt_df = prepare_bt_data(df)
    if len(bt_df) < 100:
        return {'error': f'資料筆數不足（{len(bt_df)} < 100）'}

    strat_cls  = MA_Cross_Strategy if strategy == 'ma_cross' else MA_RSI_Strategy
    strat_name = 'MA均線交叉策略' if strategy == 'ma_cross' else 'MA+RSI複合策略'

    try:
        bt  = Backtest(bt_df, strat_cls, cash=cash,
                       commission=commission, exclusive_orders=True)
        res = bt.run()

        start_dt = bt_df.index[0]
        end_dt   = bt_df.index[-1]
        years    = (end_dt - start_dt).days / 365.25
        final_eq = float(res['Equity Final [$]'])

        return {
            'strategy':            strat_name,
            'start':               str(start_dt.date()),
            'end':                 str(end_dt.date()),
            'years':               round(years, 1),
            'initial_cash':        cash,
            'final_equity':        round(final_eq, 2),
            'return_pct':          round(float(res['Return [%]']), 2),
            'cagr_pct':            calc_cagr(cash, final_eq, years),
            'buy_hold_return_pct': round(float(res['Buy & Hold Return [%]']), 2),
            'max_drawdown_pct':    round(float(res['Max. Drawdown [%]']), 2),
            'sharpe':              round(float(res.get('Sharpe Ratio') or 0), 3),
            'win_rate':            round(float(res.get('Win Rate [%]') or 0), 2),
            'total_trades':        int(res.get('# Trades') or 0),
            'avg_pnl_ratio':       calc_avg_pnl_ratio(res),
            'error':               None
        }
    except Exception as e:
        return {'error': f'回測失敗: {str(e)}'}


# ── Walk Forward Test (§7.3) ──────────────────────────────────
def walk_forward_test(df, strategy='ma_cross',
                      train_years=WFT_TRAIN_YEARS,
                      test_months=WFT_TEST_MONTHS,
                      cash=BACKTEST_INIT_CASH,
                      commission=BACKTEST_COMMISSION) -> dict:
    """
    滾動式 Walk Forward Test（§7.3）

    目的：避免過度擬合，驗證策略在不同時間段的穩定性。

    流程（範例3年訓練/1年測試）：
      2018-2021 訓練 → 2022 測試
      2019-2022 訓練 → 2023 測試
      2020-2023 訓練 → 2024 測試

    Returns:
        dict: 各期測試結果 + 彙總統計
    """
    if not _BACKTEST_AVAILABLE:
        return {'error': 'backtesting 套件未安裝'}
    if df is None or df.empty:
        return {'error': '無效的股價資料'}

    bt_df = prepare_bt_data(df)
    total_years = (bt_df.index[-1] - bt_df.index[0]).days / 365.25

    min_needed = train_years + test_months / 12
    if total_years < min_needed:
        return {'error': f'資料不足（需 {min_needed:.1f} 年，現有 {total_years:.1f} 年）'}

    strat_cls  = MA_Cross_Strategy if strategy == 'ma_cross' else MA_RSI_Strategy
    strat_name = 'MA均線交叉策略' if strategy == 'ma_cross' else 'MA+RSI複合策略'

    periods = []
    start = bt_df.index[0]
    end   = bt_df.index[-1]

    test_start = start + pd.DateOffset(years=train_years)
    while test_start + pd.DateOffset(months=test_months) <= end + pd.DateOffset(days=1):
        test_end  = test_start + pd.DateOffset(months=test_months) - pd.DateOffset(days=1)
        train_start = test_start - pd.DateOffset(years=train_years)

        train_df = bt_df[(bt_df.index >= train_start) & (bt_df.index < test_start)]
        test_df  = bt_df[(bt_df.index >= test_start)  & (bt_df.index <= test_end)]

        if len(train_df) < 60 or len(test_df) < 20:
            test_start += pd.DateOffset(months=test_months)
            continue

        try:
            bt_test = Backtest(test_df, strat_cls, cash=cash,
                               commission=commission, exclusive_orders=True)
            res = bt_test.run()
            periods.append({
                'train_period': f"{train_start.strftime('%Y-%m')} ~ {(test_start-pd.DateOffset(days=1)).strftime('%Y-%m')}",
                'test_period':  f"{test_start.strftime('%Y-%m')} ~ {test_end.strftime('%Y-%m')}",
                'return_pct':   round(float(res['Return [%]']), 2),
                'max_dd_pct':   round(float(res['Max. Drawdown [%]']), 2),
                'sharpe':       round(float(res.get('Sharpe Ratio') or 0), 3),
                'win_rate':     round(float(res.get('Win Rate [%]') or 0), 2),
                'trades':       int(res.get('# Trades') or 0),
            })
        except Exception as e:
            periods.append({'test_period': str(test_start.strftime('%Y-%m')), 'error': str(e)})

        test_start += pd.DateOffset(months=test_months)

    if not periods:
        return {'error': '無法生成任何測試期間'}

    valid = [p for p in periods if 'error' not in p]
    if valid:
        returns = [p['return_pct'] for p in valid]
        summary = {
            'strategy':      strat_name,
            'periods_tested': len(valid),
            'avg_return_pct': round(np.mean(returns), 2),
            'positive_periods': sum(1 for r in returns if r > 0),
            'negative_periods': sum(1 for r in returns if r <= 0),
            'win_rate_wft':   round(sum(1 for r in returns if r > 0) / len(returns) * 100, 1),
            'avg_sharpe':     round(np.mean([p['sharpe'] for p in valid]), 3),
            'avg_max_dd':     round(np.mean([p['max_dd_pct'] for p in valid]), 2),
            'consistency':    '✅ 策略穩定' if sum(1 for r in returns if r > 0)/len(returns) >= 0.6 else '⚠️ 策略不穩定',
        }
    else:
        summary = {'error': '所有期間回測失敗'}

    return {
        'summary': summary,
        'periods': periods,
        'error':   None
    }


# ── 選股條件篩選 (§9 選股條件) ───────────────────────────────
def stock_selector(df) -> tuple:
    """
    選股條件篩選：MA20>MA60、RSI<70、成交量>20日均量
    Returns: (filtered_df, passed: bool, details: dict)
    """
    if df is None or df.empty:
        return df, False, {}
    for p in [20, 60]:
        if f'MA{p}' not in df.columns:
            df[f'MA{p}'] = df['close'].rolling(p).mean()
    if 'RSI' not in df.columns:
        d=df['close'].diff(); g=d.clip(lower=0).rolling(14).mean()
        l=(-d.clip(upper=0)).rolling(14).mean()
        df['RSI'] = 100-100/(1+g/(l+1e-10))
    latest  = df.iloc[-1]
    vol_avg = df['volume'].rolling(20).mean().iloc[-1]
    cond1 = bool(latest.get('MA20', 0) > latest.get('MA60', 0))
    cond2 = bool(latest.get('RSI', 100) < 70)
    cond3 = bool(latest.get('volume', 0) > vol_avg) if not pd.isna(vol_avg) else False
    details = {
        'MA20>MA60': {'pass': cond1, 'value': f"MA20={latest.get('MA20',0):.1f}/MA60={latest.get('MA60',0):.1f}"},
        'RSI<70':    {'pass': cond2, 'value': f"RSI={latest.get('RSI',0):.1f}"},
        '量能放大':   {'pass': cond3, 'value': f"今={latest.get('volume',0):.0f}/均={vol_avg:.0f}"},
    }
    filtered = df[df['MA20']>df['MA60']].copy() if 'MA20' in df.columns else df.copy()
    return filtered, cond1 and cond2 and cond3, details
