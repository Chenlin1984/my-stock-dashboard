"""
風險控制模組 v3.0 (§6)
單股風控 + 停損/移動停利 + 組合風控
"""
try:
    from config import (MAX_POSITION_PER_STOCK, MAX_PORTFOLIO_DRAWDOWN,
                        STOP_LOSS_PCT, TRAILING_STOP_PCT, MIN_CASH_RATIO,
                        MAX_POSITIONS, EXPOSURE_BULL, EXPOSURE_NEUTRAL, EXPOSURE_BEAR)
except ImportError:
    MAX_POSITION_PER_STOCK=0.10; MAX_PORTFOLIO_DRAWDOWN=0.15
    STOP_LOSS_PCT=0.08; TRAILING_STOP_PCT=0.07; MIN_CASH_RATIO=0.10
    MAX_POSITIONS=10; EXPOSURE_BULL=0.8; EXPOSURE_NEUTRAL=0.5; EXPOSURE_BEAR=0.2


# ── 組合曝險（依市場狀態）(§6.3) ─────────────────────────────
def portfolio_exposure(regime: str) -> float:
    """
    依市場狀態決定建議總股票曝險比例（§6.3）
    bull → 80%、neutral → 50%、bear → 20%
    """
    return {
        'bull':    EXPOSURE_BULL,
        'neutral': EXPOSURE_NEUTRAL,
        'bear':    EXPOSURE_BEAR,
    }.get(regime, EXPOSURE_NEUTRAL)


# ── 停損工具函數 (§6.2) ───────────────────────────────────────
def stop_loss_trigger(buy_price, current_price, stop_pct=None) -> bool:
    """
    固定停損觸發判斷（§6.2）
    現價跌到買進價以下固定比例 → True
    """
    pct = stop_pct if stop_pct is not None else STOP_LOSS_PCT
    return current_price <= buy_price * (1 - pct)


def trailing_stop_trigger(buy_price, peak_price, current_price,
                           trail_pct=None, min_profit_pct=0.03) -> bool:
    """
    移動停利觸發判斷（§6.2 修正版）
    修正：只要 peak_price 曾達到最小獲利門檻（預設3%），
          即使現價低於買入價也應觸發，防止回吐大波段利潤

    舊邏輯漏洞：買100→漲120→跌回95，因95<100不觸發，損失5%
    新邏輯：peak達到103（3%門檻），之後 peak*(1-7%)=111.6 觸發
    """
    pct = trail_pct if trail_pct is not None else TRAILING_STOP_PCT
    # 必須先達到最小獲利門檻才啟動移動停利
    if peak_price < buy_price * (1 + min_profit_pct):
        return False   # peak 尚未達到最小獲利門檻，不啟動
    return current_price <= peak_price * (1 - pct)


# ── 主控制器 ─────────────────────────────────────────────────
class RiskController:
    """
    風險控制器 v3.0

    規則（根據說明書 §6）：
      - 單一股票不超過投資組合 10%  (§6.1)
      - 固定停損 -8%                (§6.2)
      - 移動停利：獲利後回撤 7%     (§6.2)
      - 最大持股數：10 檔            (§6.3)
      - 現金部位下限：10%            (§6.3)
      - 最大回撤 15%，超過暫停交易  (§6.3)
      - 市場轉空時持股降至 20%       (§6.3)
    """

    def __init__(self, portfolio_value=1_000_000, regime='neutral'):
        self.portfolio_value   = portfolio_value
        self.regime            = regime
        self.max_single_weight = MAX_POSITION_PER_STOCK
        self.stop_loss_pct     = STOP_LOSS_PCT
        self.trail_pct         = TRAILING_STOP_PCT
        self.max_drawdown_pct  = MAX_PORTFOLIO_DRAWDOWN
        self.min_cash_ratio    = MIN_CASH_RATIO
        self.max_positions     = MAX_POSITIONS
        self.peak_value        = portfolio_value
        self.trading_suspended = False
        # 每個持倉的最高價記錄（移動停利用）
        self._peak_prices      = {}

    @property
    def target_exposure(self) -> float:
        """目前市場狀態建議持股比例"""
        return portfolio_exposure(self.regime)

    @property
    def max_stock_budget(self) -> float:
        """最大可用於股票的資金"""
        return self.portfolio_value * self.target_exposure

    def position_size(self, price, weight=None) -> dict:
        """計算單股可買張數（以投組 10% 為上限）"""
        w = weight if weight is not None else self.max_single_weight
        allocated = self.portfolio_value * w
        shares = int(allocated / price / 1000) * 1000
        return {
            'allocated': round(allocated, 0),
            'shares': shares,
            'lots': shares // 1000,
            'actual_cost': shares * price
        }

    def stop_price(self, buy_price) -> float:
        """固定停損價（-8%）"""
        return round(buy_price * (1 - self.stop_loss_pct), 2)

    def check_exit(self, stock_id, buy_price, current_price) -> dict:
        """
        整合停損 + 移動停利 出場判斷

        Returns:
            dict: exit_type ('stop_loss'/'trailing'/'hold'), action, pnl_pct
        """
        # 更新最高價記錄
        prev_peak = self._peak_prices.get(stock_id, buy_price)
        new_peak  = max(prev_peak, current_price)
        self._peak_prices[stock_id] = new_peak

        pnl_pct = (current_price - buy_price) / buy_price * 100
        sp      = self.stop_price(buy_price)

        # 固定停損（優先）
        if stop_loss_trigger(buy_price, current_price, self.stop_loss_pct):
            return {
                'exit_type': 'stop_loss',
                'action':    '🔴 固定停損出場',
                'pnl_pct':   round(pnl_pct, 2),
                'stop_price': sp,
                'peak_price': new_peak,
            }

        # 移動停利
        if trailing_stop_trigger(buy_price, new_peak, current_price, self.trail_pct):
            return {
                'exit_type': 'trailing',
                'action':    '🟡 移動停利出場',
                'pnl_pct':   round(pnl_pct, 2),
                'stop_price': sp,
                'peak_price': new_peak,
            }

        return {
            'exit_type': 'hold',
            'action':    '✅ 持倉正常',
            'pnl_pct':   round(pnl_pct, 2),
            'stop_price': sp,
            'peak_price': new_peak,
        }

    # 舊版相容
    def check_stop_loss(self, buy_price, current_price) -> dict:
        return self.check_exit('_', buy_price, current_price)

    def update_drawdown(self, current_value) -> dict:
        """更新最大回撤狀態"""
        if current_value > self.peak_value:
            self.peak_value = current_value
        drawdown = (self.peak_value - current_value) / self.peak_value
        if drawdown >= self.max_drawdown_pct:
            self.trading_suspended = True
        elif drawdown < self.max_drawdown_pct * 0.5:
            self.trading_suspended = False
        return {
            'peak_value':        self.peak_value,
            'current_value':     current_value,
            'drawdown_pct':      round(drawdown * 100, 2),
            'trading_suspended': self.trading_suspended,
            'status': '🔴 已暫停交易（回撤超15%）' if self.trading_suspended else '✅ 交易正常',
        }

    def can_add_position(self, current_positions: int) -> bool:
        """是否可以新增持倉（最大10檔）"""
        return current_positions < self.max_positions

    def cash_check(self, equity_value, portfolio_total) -> dict:
        """現金水位檢查（下限10%）"""
        cash = portfolio_total - equity_value
        cash_ratio = cash / portfolio_total if portfolio_total > 0 else 0
        ok = cash_ratio >= self.min_cash_ratio
        return {
            'cash': cash,
            'cash_ratio': round(cash_ratio * 100, 2),
            'ok': ok,
            'status': f"{'✅' if ok else '⚠️'} 現金比例 {cash_ratio*100:.1f}% （下限{self.min_cash_ratio*100:.0f}%）"
        }

    def full_report(self, positions: list) -> dict:
        """全倉風控報告"""
        total_cost  = sum(p['buy_price']     * p['lots'] * 1000 for p in positions)
        total_value = sum(p['current_price'] * p['lots'] * 1000 for p in positions)
        total_pnl   = total_value - total_cost
        pnl_pct     = total_pnl / total_cost * 100 if total_cost else 0
        alerts = []
        for p in positions:
            chk = self.check_exit(p.get('stock_id',''), p['buy_price'], p['current_price'])
            if chk['exit_type'] != 'hold':
                alerts.append(f"{chk['action']}：{p.get('stock_id','')} "
                               f"(現{p['current_price']} 成本{p['buy_price']})")
        dd = self.update_drawdown(total_value)
        return {
            'total_cost':        total_cost,
            'total_value':       total_value,
            'total_pnl':         total_pnl,
            'total_pnl_pct':     round(pnl_pct, 2),
            'drawdown':          dd,
            'exit_alerts':       alerts,
            'positions':         len(positions),
            'can_add':           self.can_add_position(len(positions)),
            'target_exposure':   f"{self.target_exposure*100:.0f}%",
        }


# ── 便利函數 ─────────────────────────────────────────────────
def calc_position_size(portfolio_value, price, weight=MAX_POSITION_PER_STOCK):
    return RiskController(portfolio_value).position_size(price, weight)

def calc_stop_loss(buy_price, stop_pct=STOP_LOSS_PCT):
    return round(buy_price * (1 - stop_pct), 2)
