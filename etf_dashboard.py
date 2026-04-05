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


def calc_premium_discount(info: dict, df: pd.DataFrame) -> dict:
    """折溢價率 = (市價 - NAV) / NAV"""
    try:
        nav   = info.get('navPrice') or info.get('regularMarketNAV')
        price = float(df['Close'].iloc[-1]) if not df.empty else None
        if nav and price:
            prem = round((price - nav) / nav * 100, 2)
            return {'nav': nav, 'price': price, 'premium_pct': prem, 'warning': prem > 1.0}
    except Exception:
        pass
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


def _plot_etf_chart(df: pd.DataFrame, ticker: str,
                    benchmark: str, bench_df: pd.DataFrame) -> None:
    """ETF 走勢圖 + MA50/MA200 + 標準化基準"""
    fig  = go.Figure()
    close = df['Close']
    fig.add_trace(go.Scatter(x=df.index, y=close,
                              name=ticker, line=dict(color='#58a6ff', width=2)))
    fig.add_trace(go.Scatter(x=df.index, y=close.rolling(50).mean(),
                              name='MA50', line=dict(color='#ffa657', width=1, dash='dot')))
    fig.add_trace(go.Scatter(x=df.index, y=close.rolling(200).mean(),
                              name='MA200', line=dict(color='#f85149', width=1, dash='dash')))
    if not bench_df.empty:
        bench_norm = (bench_df['Close'] / bench_df['Close'].iloc[0]
                      * float(close.iloc[0])).reindex(df.index).ffill()
        fig.add_trace(go.Scatter(x=df.index, y=bench_norm,
                                  name=f'{benchmark}（基準）',
                                  line=dict(color='#3fb950', width=1.2, dash='dash')))
    fig.update_layout(
        template='plotly_dark', height=380,
        margin=dict(l=0, r=0, t=20, b=0),
        paper_bgcolor='#0d1117', plot_bgcolor='#0d1117',
        legend=dict(orientation='h', yanchor='bottom', y=1.01),
    )
    st.plotly_chart(fig, use_container_width=True)


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
    st.plotly_chart(fig, use_container_width=True)


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

    if not st.button('🔍 開始診斷', key='etf_s_btn', use_container_width=True):
        st.info('💡 輸入 ETF 代號後點擊「開始診斷」')
        return

    with st.spinner(f'載入 {ticker} 資料中...'):
        df       = fetch_etf_price(ticker)
        divs     = fetch_etf_dividends(ticker)
        info     = fetch_etf_info(ticker)
        bench_df = fetch_etf_price(benchmark)

    if df.empty:
        st.error(f'❌ 找不到 {ticker}，請確認代號（台灣ETF需加 .TW）')
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
    elif cur_yield > 0:
        _colored_box(f'✅ 含息總報酬({total_ret:.1f}%) > 殖利率({cur_yield:.1f}%)，核心資產條件通過', 'green')
    else:
        st.info('ℹ️ 無配息紀錄（成長型ETF），以價差報酬評估')

    # ── 策略二：孫慶龍 7% ─────────────────────────────────────
    st.markdown('#### 🧠 策略二：孫慶龍 — 7% 存股聖經估值買賣點')
    avg_yield = calc_avg_yield(df, divs, years=5)
    cc, cd    = st.columns(2)
    cc.metric('近5年平均殖利率', f'{avg_yield:.2f}%' if avg_yield else 'N/A')
    cd.metric('現今殖利率', f'{cur_yield:.2f}%')
    if avg_yield > 0:
        if cur_yield >= 7:
            _colored_box('🟢 <b>強烈買進（特價）</b>：殖利率 ≥ 7%，現值低估，值得分批佈局', 'green')
        elif cur_yield <= 3:
            _colored_box('🔴 <b>獲利了結（昂貴）</b>：殖利率 ≤ 3%，現值高估，考慮減碼', 'red')
        elif cur_yield <= 5:
            _colored_box('🟡 <b>適度減碼（合理）</b>：殖利率 ≤ 5%，估值合理偏高', 'yellow')
        else:
            st.info(f'殖利率 {cur_yield:.1f}% 位於 5%~7% 合理區間，中性持有')
    else:
        st.info('ℹ️ 無充足配息歷史，套用回測頁評估價差績效')

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
    else:
        missing = []
        if not vcp['above_ma50']:  missing.append('未站上50MA')
        if not vcp['above_ma200']: missing.append('未站上200MA')
        if not vcp['vol_confirm']: missing.append('量能不足')
        if len(df) < 210:         missing.append('資料不足210天')
        st.info('⏳ VCP 條件未滿足：' + (' | '.join(missing) if missing else '波幅尚未收縮'))

    # ── ETF 防呆：折溢價 + 追蹤誤差 ─────────────────────────
    st.markdown('#### 🛡️ ETF 專屬防呆機制')
    prem = calc_premium_discount(info, df)
    te   = calc_tracking_error(df, bench_df)
    ch, ci = st.columns(2)
    if prem['premium_pct'] is not None:
        ch.metric('折溢價率', f'{prem["premium_pct"]:+.2f}%')
        if prem['warning']:
            ch.markdown('<small style="color:#f85149;">⚠️ 溢價 >1%，拒絕追高</small>',
                        unsafe_allow_html=True)
    else:
        ch.metric('折溢價率', 'N/A（yfinance 未提供 NAV）')
    if te is not None:
        ci.metric(f'追蹤誤差 vs {benchmark}', f'{te:.2f}%')
        if te > 1.5:
            ci.markdown('<small style="color:#d29922;">⚠️ 追蹤誤差 >1.5%，注意隱藏成本</small>',
                        unsafe_allow_html=True)
    else:
        ci.metric('追蹤誤差', 'N/A')

    # ── 走勢圖 ────────────────────────────────────────────────
    st.markdown(f'#### 📈 {ticker} 近5年走勢')
    _plot_etf_chart(df, ticker, benchmark, bench_df)

    # ── 存入 session_state 供 Tab⑨ 使用 ─────────────────────
    st.session_state['etf_single_data'] = {
        'ticker': ticker, 'name': etf_name,
        'cur_yield': cur_yield, 'avg_yield': avg_yield,
        'total_ret': total_ret, 'vcp': vcp,
        'premium': prem, 'te': te, 'regime': regime,
    }

    # ── AI 大師評斷 ───────────────────────────────────────────
    if gemini_fn:
        _etf_ai_single(gemini_fn, ticker, etf_name, cur_yield,
                       avg_yield, total_ret, vcp, prem, te, regime)


def _etf_ai_single(gemini_fn, ticker, name, cur_yield, avg_yield,
                   total_ret, vcp, prem, te, regime):
    with st.expander('🤖 AI 大師評斷（展開）', expanded=False):
        prompt = (
            f"你是專業ETF投資顧問，嚴格依據以下數據分析，每項不超過200字，"
            f"條列式，禁止憑空捏造未提供的數據:\n\n"
            f"ETF：{name} ({ticker})\n"
            f"總經市場狀態：{regime}\n"
            f"近1年含息總報酬：{total_ret:.2f}%\n"
            f"現金殖利率（近12M）：{cur_yield:.2f}%\n"
            f"近5年平均殖利率：{avg_yield:.2f}%\n"
            f"VCP突破訊號：{'是' if vcp['signal'] else '否'}"
            f"（50MA:{vcp['above_ma50']}, 200MA:{vcp['above_ma200']}, 量能:{vcp['vol_confirm']}）\n"
            f"折溢價率：{prem['premium_pct'] if prem['premium_pct'] is not None else 'N/A'}%\n"
            f"追蹤誤差：{te if te is not None else 'N/A'}%\n\n"
            f"請輸出：\n"
            f"1.【郭俊宏評斷】本金侵蝕風險判斷\n"
            f"2.【孫慶龍評斷】目前估值位置（特價/合理/昂貴）\n"
            f"3.【春哥評斷】技術面切入時機\n"
            f"4.【綜合行動建議】買進/觀望/減碼（一句話+具體理由）\n"
            f"⚠️ 僅供學術研究，非投資建議"
        )
        if st.button('🤖 生成 AI 評斷', key='etf_ai_s_btn'):
            with st.spinner('AI 分析中...'):
                result = gemini_fn(prompt, max_tokens=900)
            if result and not result.startswith('⚠️'):
                st.markdown(result)
            else:
                st.warning(result or 'AI 回傳為空，請確認 API Key')


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

    if not st.button('📊 計算組合', key='etf_p_btn', use_container_width=True):
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
    overview_df = pd.DataFrame([{
        'ETF': r['ticker'], '目標權重%': r['target_pct'],
        '實際權重%': r['actual_pct'], '偏離度%': r['deviation'],
        '現值(元)': f'{r["current_value"]:,.0f}',
    } for r in rows])
    st.dataframe(overview_df, use_container_width=True, hide_index=True)

    # ── 再平衡交易指令 ────────────────────────────────────────
    st.markdown('#### ⚖️ 再平衡交易指令')
    rebal_actions = []
    for r in rows:
        if abs(r['deviation']) > tolerance:
            target_val = total_value * r['target_pct'] / 100
            adj        = target_val - r['current_value']
            action     = '買進' if adj > 0 else '賣出'
            rebal_actions.append({
                'ETF': r['ticker'], '動作': action,
                '金額(元)': abs(adj), '偏離度%': r['deviation'],
            })

    if rebal_actions:
        ra_df = pd.DataFrame([{'ETF': a['ETF'], '動作': a['動作'],
                                '金額(元)': f'{a["金額(元)"]:,.0f}',
                                '偏離度%': a['偏離度%']} for a in rebal_actions])
        st.dataframe(ra_df, use_container_width=True, hide_index=True)
        for act in rebal_actions:
            color = 'green' if act['動作'] == '買進' else 'red'
            icon  = '📈' if act['動作'] == '買進' else '📉'
            _colored_box(
                f'{icon} <b>{act["動作"]} {act["ETF"]}</b> 共 '
                f'<b>{act["金額(元)"]:,.0f} 元</b>（偏離 {act["偏離度%"]:+.1f}%）',
                color)
    else:
        _colored_box(f'✅ 所有標的偏離度均在 ±{tolerance}% 內，無需再平衡', 'green')

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

    # 存入 session_state
    st.session_state['etf_portfolio_data'] = {
        'rows': rows, 'rebal_actions': rebal_actions,
        'total_value': total_value, 'regime': regime,
        'loss_pct': loss_pct,
    }

    if gemini_fn:
        _etf_ai_portfolio(gemini_fn, rows, rebal_actions, regime, loss_pct)


def _etf_ai_portfolio(gemini_fn, rows, rebal_actions, regime, loss_pct):
    with st.expander('🤖 AI 組合評斷（展開）', expanded=False):
        row_txt = '\n'.join(
            f'  {r["ticker"]}：目標{r["target_pct"]}% 實際{r["actual_pct"]}% 偏離{r["deviation"]:+.1f}%'
            for r in rows)
        act_txt = '\n'.join(
            f'  {a["動作"]} {a["ETF"]} {a["金額(元)"]:,.0f}元'
            for a in rebal_actions) if rebal_actions else '  無需再平衡'
        prompt = (
            f"你是ETF組合管理專家，依據以下資料給出精準建議，每項不超過200字，嚴禁捏造：\n"
            f"市場狀態：{regime}\n"
            f"組合明細：\n{row_txt}\n"
            f"再平衡指令：\n{act_txt}\n"
            f"壓力測試損失：{loss_pct:.1f}%（S&P500下跌20%模擬）\n\n"
            f"輸出：\n"
            f"1.【組合健康度】分散度、集中風險點\n"
            f"2.【再平衡必要性】是否緊急，原因\n"
            f"3.【總經視角】依{regime}市場狀態，調整方向\n"
            f"4.【一句話結論】立即行動 or 繼續觀察\n"
            f"⚠️ 僅供學術研究，非投資建議"
        )
        if st.button('🤖 生成組合AI評斷', key='etf_ai_p_btn'):
            with st.spinner('AI 分析中...'):
                result = gemini_fn(prompt, max_tokens=900)
            if result and not result.startswith('⚠️'):
                st.markdown(result)
            else:
                st.warning(result or 'AI 回傳為空')


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
    if not col_b.button('🚀 開始回測', key='etf_bt_btn', use_container_width=True):
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

    # 加權組合資產價值
    norm     = prices / prices.iloc[0]
    weights  = {r['ticker']: r['weight'] for r in rows if r['ticker'] in norm.columns}
    port_val = sum(norm[t] * w for t, w in weights.items()) * initial

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
    st.plotly_chart(fig, use_container_width=True)

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

    # 存入 session_state
    st.session_state['etf_backtest_data'] = {
        'weights': weights, 'period': period, 'initial': initial,
        'cagr': cagr, 'sharpe': sharpe, 'mdd': mdd, 'vol': vol,
        'cum_ret': cum_ret, 'regime': regime,
    }

    if gemini_fn:
        _etf_ai_backtest(gemini_fn, cagr, sharpe, mdd, vol, weights, regime)


def _etf_ai_backtest(gemini_fn, cagr, sharpe, mdd, vol, weights, regime):
    with st.expander('🤖 AI 回測評斷（展開）', expanded=False):
        w_txt  = ' | '.join(f'{t}: {w*100:.0f}%' for t, w in weights.items())
        prompt = (
            f"你是回測績效分析師，依據以下數字給出精準評斷，不超過300字，嚴禁捏造：\n"
            f"組合：{w_txt}\n"
            f"CAGR：{cagr:.2f}%\n"
            f"夏普值：{sharpe:.2f}\n"
            f"最大回撤：{mdd:.1f}%\n"
            f"年化波動率：{vol:.2f}%\n"
            f"當前市場狀態：{regime}\n\n"
            f"輸出：\n"
            f"1.【績效評級】優秀/良好/普通/劣（請說明標準）\n"
            f"2.【風險評估】MDD和波動率是否在可接受範圍\n"
            f"3.【改善建議】基於春哥/郭俊宏/孫慶龍觀點，如何優化配置\n"
            f"4.【前瞻建議】在{regime}環境下，此組合的下一步行動\n"
            f"⚠️ 僅供學術研究，非投資建議"
        )
        if st.button('🤖 生成回測AI評斷', key='etf_ai_bt_btn'):
            with st.spinner('AI 分析中...'):
                result = gemini_fn(prompt, max_tokens=900)
            if result and not result.startswith('⚠️'):
                st.markdown(result)
            else:
                st.warning(result or 'AI 回傳為空')


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
        full_prompt = '\n'.join(sections)

        if st.button('🤖 生成 ETF 綜合 AI 評斷', key='etf_ai_comp_btn', use_container_width=True):
            if not gemini_fn:
                st.warning('⚠️ 請設定 GEMINI_API_KEY 才能使用 AI 功能')
            else:
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
    st.markdown('### 🔎 資料健診儀表板')
    st.caption('掃描全系統資料源狀態，確認每個資料均有真實抓取，避免沙盒/空值假象。')

    # ── ① Session State 資料檢查 ──────────────────────────────
    st.markdown('#### 🧠 系統快取資料（session_state）')
    ss_rows = []
    for key, label, checker in _HEALTH_CHECKS['session_state']:
        val  = st.session_state.get(key)
        ok   = False
        note = '尚未載入'
        try:
            ok = checker(val)
            if ok:
                if key == 'mkt_info':
                    note = f'regime={val.get("regime")} score={val.get("score")}' 
                elif key == 'li_latest':
                    note = f'{len(val)} 筆指標，最新={str(val.index[-1].date()) if hasattr(val.index[-1], "date") else val.index[-1]}' if not val.empty else '空表'
                elif key == 'etf_single_data':
                    note = f'{val.get("ticker")} | 殖利率={val.get("cur_yield"):.1f}%'
                elif key == 'etf_portfolio_data':
                    note = f'{len(val.get("rows",[]))} 檔ETF | 總資產={val.get("total_value",0):,.0f}元'
                elif key == 'etf_backtest_data':
                    note = f'CAGR={val.get("cagr"):.1f}% | MDD={val.get("mdd"):.1f}%'
                else:
                    note = '有資料'
            else:
                note = '空值或格式異常'
        except Exception as e:
            note = f'檢查失敗：{e}'
        ss_rows.append({'狀態': '✅ 正常' if ok else '❌ 未載入',
                         '模組': label, 'Key': key, '說明': note})
    ss_df = pd.DataFrame(ss_rows)
    st.dataframe(ss_df, use_container_width=True, hide_index=True)

    ok_count = sum(1 for r in ss_rows if '✅' in r['狀態'])
    total    = len(ss_rows)
    bar_color = 'green' if ok_count == total else ('yellow' if ok_count > total // 2 else 'red')
    _colored_box(
        f'系統快取健康度：<b>{ok_count}/{total}</b> 項正常'
        + (' — 全部就緒 🎉' if ok_count == total else ' — 請先到對應 Tab 執行分析'),
        bar_color)

    # ── ② ETF 資料源即時健診 ─────────────────────────────────
    st.markdown('---')
    st.markdown('#### 📡 ETF 資料源即時健診（yfinance）')

    col_tw, col_us = st.columns(2)
    custom_input   = st.text_input(
        '➕ 額外檢測代號（用逗號分隔，如 00919.TW,NVDA）',
        value='', key='health_custom')
    custom_tickers = [t.strip().upper() for t in custom_input.split(',') if t.strip()]

    # 讀取已在其他 Tab 使用的 tickers
    used_tickers = set()
    if st.session_state.get('etf_portfolio_data'):
        for r in st.session_state['etf_portfolio_data'].get('rows', []):
            used_tickers.add(r['ticker'])
    if st.session_state.get('etf_backtest_data'):
        used_tickers.update(st.session_state['etf_backtest_data'].get('weights', {}).keys())
    if st.session_state.get('etf_single_data'):
        used_tickers.add(st.session_state['etf_single_data']['ticker'])

    scan_tickers = list(set(_HEALTH_ETF_TW + _HEALTH_ETF_US)
                        | used_tickers | set(custom_tickers))

    if not st.button('🔬 開始全面掃描', key='health_scan_btn', use_container_width=True):
        st.info(f'將掃描 {len(scan_tickers)} 個 ETF，點擊「開始全面掃描」執行')
        st.caption('掃描列表：' + ' / '.join(scan_tickers))
        return

    results = []
    progress = st.progress(0, text='掃描中...')
    for i, ticker in enumerate(scan_tickers):
        progress.progress((i + 1) / len(scan_tickers), text=f'掃描 {ticker}...')
        r = _check_etf_health(ticker)
        results.append(r)
    progress.empty()

    # 顯示結果表
    display_rows = []
    for r in results:
        p_icon = _check_icon(r['price_ok'])
        d_icon = _check_icon(r['div_ok'], warn=True)   # 無配息是正常的（成長型ETF）
        i_icon = _check_icon(r['info_ok'])
        overall = '✅' if (r['price_ok'] and r['info_ok']) else ('⚠️' if r['price_ok'] else '❌')
        display_rows.append({
            '整體': overall,
            'ETF': r['ticker'],
            '價格資料': f"{p_icon} {r['price_rows']}筆 ({r['price_last'] or '-'})",
            '配息紀錄': f"{d_icon} {r['div_count']}筆",
            'Info欄位': f"{i_icon} {r['info_fields']}項",
            '異常': r['error'] or '-',
        })

    result_df = pd.DataFrame(display_rows)
    st.dataframe(result_df, use_container_width=True, hide_index=True)

    ok_etf  = sum(1 for r in results if r['price_ok'] and r['info_ok'])
    warn_etf= sum(1 for r in results if r['price_ok'] and not r['info_ok'])
    fail_etf= sum(1 for r in results if not r['price_ok'])

    c1, c2, c3 = st.columns(3)
    c1.metric('✅ 完全正常',  ok_etf)
    c2.metric('⚠️ 部分缺失', warn_etf)
    c3.metric('❌ 資料抓取失敗', fail_etf)

    if fail_etf > 0:
        failed = [r['ticker'] for r in results if not r['price_ok']]
        _colored_box(
            f'⚠️ 以下代號無法抓取，請確認代號正確或網路連線：<b>{", ".join(failed)}</b>',
            'red')

    # ── ③ 快取清除工具 ───────────────────────────────────────
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
            colorscale=[[0, '#7b1212'], [0.35, '#c0392b'], [0.5, '#1e2530'],
                        [0.65, '#1a6e36'], [1, '#0f5132']],
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
    st.caption('即時抓取各類股漲跌幅，紅=跌 / 綠=漲。點選區塊可展開子類股。')

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
    st.plotly_chart(fig, use_container_width=True)

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
