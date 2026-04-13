"""
unified_decision.py  —  統一投資決策分析模組 v1.0
自動辨識 stock / etf / portfolio，輸出結構化 JSON → 3-Card UI
"""
import re as _re
import json as _json
import streamlit as st


# ════════════════════════════════════════════════════════════════
# 1. 提示工程
# ════════════════════════════════════════════════════════════════

_BASE_RULES = """
你是「台股 AI 戰情室」首席投資決策顧問，具備 CFA / CMT 雙認證。
你的輸出必須：
  ① 嚴格基於傳入數據，禁止捏造或推測未提供的數字
  ② 觀點鮮明，不模稜兩可，一句話定調
  ③ 只輸出合法 JSON，禁止任何 Markdown 代碼塊、多餘說明或換行前置文字

嚴格輸出格式（三個 key，值的語言為繁體中文）：
{
  "summary": "🟢/🟡/🔴 一句話標題，20字以內，定調當前狀態",
  "action_advice": ["具體可執行動作1（含數字依據）", "具體可執行動作2"],
  "precautions": ["隱憂或注意事項1（含數字依據）", "隱憂或注意事項2"]
}
"""

_STOCK_LOGIC = """
【個股分析邏輯】
- 健康度評分：≥80 強勢 / 60-79 中性 / <60 弱勢
- RSI：>70 超買警戒 / <30 超賣機會
- KD：K>80 高檔 / K<20 低檔 / 黃金/死亡交叉
- VCP 突破：量縮整理後放量突破為進場訊號
- 大盤狀態：空頭格局下個股先降倉至 20% 以下
- 籌碼：外資/投信持續買超 ≥3 日為多頭信號

【個股 JSON 輸出規範 — 嚴格對應以下四個面向】
- "summary"       → ① 目前技術面評價：一句話（≤25字）定調多空強弱
- "action_advice" → ② 具體進場條件（含觸發價格或指標條件）
                     ③ 停損價位設定（明確說出停損價或均線）
- "precautions"   → ④ 風控建議（倉位控制、市場狀態注意事項）
                     + 其他當前主要隱憂（≤1條）
"""

_ETF_LOGIC = """
【ETF 分析邏輯 — 嚴守「買跌不買漲（左側交易）」鐵血紀律】
- BIAS240（年線乖離率）
    ≤0% + 殖利率≥6%  → 極佳買點，加速扣款
    0% ~ 10%          → 正常存股，紀律扣款
    ≥10% + KD 高檔    → 停止買進，暫停扣款
    ≥10% KD 未高檔    → 謹慎觀望，減少扣款
- 折溢價率 >1% 有淨值回歸風險，需列入警示
- 殖利率 <3% 高息ETF意義不大，需說明
"""

_PORTFOLIO_LOGIC = """
【資產組合分析邏輯】
- VIX>25 恐慌期：股票倉位應 ≤40%，增債/現金比例
- CAGR：≥10% 優秀 / 5-10% 良好 / <5% 需優化
- Sharpe：≥1.0 優 / 0.5-1.0 可接受 / <0.5 風險報酬不佳
- MDD：≤15% 穩健 / 15-30% 注意 / >30% 高風險
- 再平衡：偏離目標 >5% 且市值 >50萬元 時具緊迫性
"""


def _build_prompt(context: dict) -> str:
    ctx_type = context.get('type', 'stock')
    data     = context.get('data', {})
    data_str = _json.dumps(data, ensure_ascii=False, indent=2)

    logic_map = {
        'stock':     _STOCK_LOGIC,
        'etf':       _ETF_LOGIC,
        'portfolio': _PORTFOLIO_LOGIC,
    }
    logic = logic_map.get(ctx_type, _STOCK_LOGIC)

    type_label = {'stock': '個股', 'etf': 'ETF', 'portfolio': '資產組合'}.get(ctx_type, '個股')

    return (
        _BASE_RULES + logic +
        f"\n\n【傳入數據類型】{type_label}\n"
        f"【傳入數據】\n{data_str}\n\n"
        "根據以上數據與分析邏輯，輸出投資決策 JSON（只輸出 JSON，不含其他任何文字）："
    )


# ════════════════════════════════════════════════════════════════
# 2. 前端 Card 渲染
# ════════════════════════════════════════════════════════════════

def _color_from_summary(summary: str) -> tuple:
    """回傳 (bg, border, text) 三色。"""
    s = summary or ''
    if any(x in s for x in ('🟢', '✅', '買點', '建倉', '多頭')):
        return '#0a1f10', '#3fb950', '#3fb950'
    if any(x in s for x in ('🔴', '❌', '減碼', '停止', '賣出', '空頭', '過熱')):
        return '#200a0a', '#f85149', '#f85149'
    return '#141200', '#d29922', '#d29922'   # 🟡 中性/謹慎


def _list_html(items, bullet_color: str) -> str:
    if isinstance(items, str):
        items = [items]
    rows = []
    for item in items:
        rows.append(
            f'<div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:10px;">'
            f'<span style="color:{bullet_color};font-size:13px;flex-shrink:0;margin-top:1px;">▶</span>'
            f'<span style="font-size:13px;color:#c9d1d9;line-height:1.65;">{item}</span>'
            f'</div>'
        )
    return ''.join(rows)


def _render_cards(parsed: dict, ctx_type: str = 'stock') -> None:
    summary  = parsed.get('summary', '⚠️ 分析結果不完整')
    actions  = parsed.get('action_advice', [])
    risks    = parsed.get('precautions', [])

    bg, border, text = _color_from_summary(summary)

    # ── Card 1：戰情總結（全寬）────────────────────────────────
    card1_label = '① 目前技術面評價' if ctx_type == 'stock' else '📊 AI 戰情總結'
    st.markdown(
        f'<div style="background:{bg};border:2px solid {border};border-radius:12px;'
        f'padding:20px 26px;margin:14px 0 10px;">'
        f'<div style="font-size:10px;font-weight:700;color:#8b949e;letter-spacing:2px;'
        f'text-transform:uppercase;margin-bottom:8px;">{card1_label}</div>'
        f'<div style="font-size:20px;font-weight:900;color:{text};line-height:1.4;">{summary}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Cards 2 & 3：並排────────────────────────────────────────
    if ctx_type == 'stock':
        left_label  = '② 具體進場條件 ／ ③ 停損設定'
        right_label = '④ 風控建議 ／ 注意事項'
    else:
        left_label  = '💡 具體投資建議'
        right_label = '⚠️ 風險與注意事項'

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            f'<div style="background:#0a1a0e;border:1px solid #238636;border-radius:10px;'
            f'padding:18px 20px;min-height:150px;">'
            f'<div style="font-size:10px;font-weight:700;color:#3fb950;letter-spacing:2px;'
            f'margin-bottom:14px;">{left_label}</div>'
            f'{_list_html(actions, "#3fb950")}'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            f'<div style="background:#1a1200;border:1px solid #9e6a03;border-radius:10px;'
            f'padding:18px 20px;min-height:150px;">'
            f'<div style="font-size:10px;font-weight:700;color:#d29922;letter-spacing:2px;'
            f'margin-bottom:14px;">{right_label}</div>'
            f'{_list_html(risks, "#d29922")}'
            f'</div>',
            unsafe_allow_html=True,
        )


# ════════════════════════════════════════════════════════════════
# 3. 主入口
# ════════════════════════════════════════════════════════════════

def render_unified_decision(gemini_fn, context: dict) -> None:
    """
    統一投資決策分析模組 — 放在任何分析 Tab 的最下方。

    context 格式：
      {'type': 'stock'|'etf'|'portfolio',
       'id':   唯一識別字串（sid / ticker / 'portfolio' 等）,
       'data': dict  ← 傳給 LLM 的數據}
    """
    if not gemini_fn:
        return

    ctx_type  = context.get('type', 'stock')
    ctx_id    = context.get('id', ctx_type)
    _sess_key = f'unified_{ctx_type}_{ctx_id}'
    _btn_key  = f'unified_btn_{ctx_type}_{ctx_id}'
    _clr_key  = f'unified_clr_{ctx_type}_{ctx_id}'

    st.markdown('---')
    st.markdown('### 🧠 AI 首席顧問決策中心')
    st.caption(
        f'整合多維度數據（{"個股技術面＋籌碼" if ctx_type=="stock" else "ETF 存股節奏" if ctx_type=="etf" else "組合風險＋績效"}），'
        '輸出結構化三維投資決策。⚠️ 僅供學術研究，非投資建議。'
    )

    col_btn, col_clr = st.columns([5, 1])
    with col_btn:
        if st.button('🧠 啟動 AI 首席顧問分析', key=_btn_key, use_container_width=True):
            prompt = _build_prompt(context)
            with st.spinner('AI 首席顧問分析中...'):
                raw = gemini_fn(prompt, max_tokens=700)
            if raw and not raw.startswith('⚠️'):
                m = _re.search(r'\{[\s\S]+\}', raw)
                try:
                    parsed = _json.loads(m.group()) if m else {}
                    if not parsed.get('summary'):
                        parsed = {
                            'summary': '⚠️ JSON 解析失敗，原始回傳如下',
                            'action_advice': [raw[:300]],
                            'precautions': [],
                        }
                except Exception:
                    parsed = {
                        'summary': '⚠️ JSON 解析失敗，原始回傳如下',
                        'action_advice': [raw[:300]],
                        'precautions': [],
                    }
                st.session_state[_sess_key] = parsed
                st.rerun()
            else:
                st.warning(raw or 'AI 回傳為空，請確認 GEMINI_API_KEY')

    _saved = st.session_state.get(_sess_key)
    with col_clr:
        if _saved:
            if st.button('🔄', key=_clr_key, help='清除結果', use_container_width=True):
                st.session_state.pop(_sess_key, None)
                st.rerun()

    if _saved:
        _render_cards(_saved, ctx_type=ctx_type)
