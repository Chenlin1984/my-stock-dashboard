"""
portfolio_manager.py — 核心衛星動態配資引擎 v4.0
目標：資金的防彈衣。強制劃分核心（ETF）與衛星（個股），
      衛星超標 10% 時自動發出再平衡警報。
"""
from __future__ import annotations
from typing import Optional

try:
    from config import EXPOSURE_BULL, EXPOSURE_NEUTRAL, EXPOSURE_BEAR
except ImportError:
    EXPOSURE_BULL = 0.80; EXPOSURE_NEUTRAL = 0.50; EXPOSURE_BEAR = 0.20


# ── 預設核心/衛星比例（依市場狀態浮動）────────────────────────────
_CORE_RATIO = {
    'bull':    0.60,   # 多頭：核心 60%  衛星 40%
    'neutral': 0.70,   # 中性：核心 70%  衛星 30%
    'caution': 0.80,   # 保守：核心 80%  衛星 20%
    'bear':    0.85,   # 空頭：核心 85%  衛星 15%
}
_REBALANCE_THRESHOLD = 0.10   # 衛星超標 10% 觸發再平衡警報


class CoreSatelliteManager:
    """
    核心衛星動態配資引擎。

    Parameters
    ----------
    total_capital : float
        總資金（台幣元）
    regime : str
        市場狀態 'bull' | 'neutral' | 'caution' | 'bear'
    core_ratio_override : float | None
        手動覆蓋核心比例（0–1），None 則按 regime 自動選取
    """

    def __init__(
        self,
        total_capital: float,
        regime: str = 'neutral',
        core_ratio_override: Optional[float] = None,
    ):
        if total_capital <= 0:
            raise ValueError('total_capital 必須大於 0')
        self.total_capital = float(total_capital)
        self.regime        = regime
        self.core_ratio    = (
            float(core_ratio_override)
            if core_ratio_override is not None
            else _CORE_RATIO.get(regime, 0.70)
        )
        self.satellite_ratio = round(1.0 - self.core_ratio, 4)

    # ── 基本額度 ────────────────────────────────────────────────
    @property
    def core_budget(self) -> float:
        """核心資金（ETF 定期定額）"""
        return round(self.total_capital * self.core_ratio, 0)

    @property
    def satellite_budget(self) -> float:
        """衛星資金（個股波段）"""
        return round(self.total_capital * self.satellite_ratio, 0)

    # ── 再平衡檢查 ───────────────────────────────────────────────
    def check_rebalance(
        self,
        satellite_current_value: float,
        satellite_used: float = 0.0,
    ) -> dict:
        """
        檢查衛星倉位是否超標，發出再平衡警報。

        Parameters
        ----------
        satellite_current_value : float
            衛星持股當前市值（含未實現損益）
        satellite_used : float
            衛星已投入成本（選填，用於計算損益）

        Returns
        -------
        dict
            rebalance_needed : bool
            excess_value     : float  超標金額（元）
            excess_pct       : float  超標百分點
            action           : str    建議動作
            message          : str    完整說明
        """
        actual_ratio  = satellite_current_value / self.total_capital
        target_ratio  = self.satellite_ratio
        excess_ratio  = actual_ratio - target_ratio
        excess_value  = round(excess_ratio * self.total_capital, 0)
        rebalance_ok  = excess_ratio >= _REBALANCE_THRESHOLD

        if rebalance_ok:
            action  = 'SELL_EXCESS'
            message = (
                f'🚨 再平衡警報！衛星倉位佔比 {actual_ratio*100:.1f}%，'
                f'超標目標 {target_ratio*100:.0f}% 達 {excess_ratio*100:.1f}%。'
                f'建議減持約 NT${excess_value:,.0f}，轉入核心 ETF。'
            )
        elif actual_ratio > target_ratio:
            action  = 'MONITOR'
            message = (
                f'⚠️ 衛星佔比 {actual_ratio*100:.1f}%，略超目標 {target_ratio*100:.0f}%，'
                f'尚未達再平衡門檻（{_REBALANCE_THRESHOLD*100:.0f}%），持續觀察。'
            )
        else:
            action  = 'HOLD'
            message = (
                f'✅ 衛星佔比 {actual_ratio*100:.1f}%，在目標 {target_ratio*100:.0f}% 以內，配置正常。'
            )

        return {
            'rebalance_needed': rebalance_ok,
            'actual_ratio':     round(actual_ratio, 4),
            'target_ratio':     round(target_ratio, 4),
            'excess_pct':       round(excess_ratio * 100, 2),
            'excess_value':     excess_value,
            'action':           action,
            'message':          message,
        }

    # ── 單筆衛星部位試算 ─────────────────────────────────────────
    def calc_position(
        self,
        price: float,
        weight: float,
        satellite_used: float = 0.0,
    ) -> dict:
        """
        計算單筆衛星股票的建議買進量。

        Parameters
        ----------
        price          : 目標股價（元）
        weight         : 此標的佔衛星資金比例（0–1，建議 ≤ 0.3）
        satellite_used : 已使用衛星資金（元）

        Returns
        -------
        dict
            budget       : float  此筆可用預算
            shares       : int    建議股數
            lots         : int    建議張數（千股）
            cost         : float  實際成本
            remaining    : float  本筆後衛星剩餘額度
            message      : str
        """
        if price <= 0:
            return {'shares': 0, 'lots': 0, 'cost': 0.0, 'message': '⚪ 股價無效'}

        available     = max(self.satellite_budget - satellite_used, 0)
        budget        = min(available * weight, available)
        shares        = int(budget // price)
        lots          = shares // 1000
        actual_cost   = round(shares * price, 0)
        remaining     = round(available - actual_cost, 0)

        if shares == 0:
            message = f'⚠️ 衛星額度不足（剩餘 NT${available:,.0f}），無法建倉'
        else:
            message = (
                f'📊 建議買進 {shares} 股（{lots} 張），成本約 NT${actual_cost:,.0f}，'
                f'衛星資金剩餘 NT${remaining:,.0f}'
            )

        return {
            'budget':    round(budget, 0),
            'shares':    shares,
            'lots':      lots,
            'cost':      actual_cost,
            'remaining': remaining,
            'message':   message,
        }

    # ── 摘要看板 ─────────────────────────────────────────────────
    def summary(self, satellite_current_value: float = 0.0) -> dict:
        """
        輸出資金配置摘要，供 Streamlit 渲染使用。

        Returns
        -------
        dict
            total / core_budget / satellite_budget /
            core_ratio / satellite_ratio / regime /
            rebalance : dict（check_rebalance 結果）
        """
        return {
            'total':             self.total_capital,
            'core_budget':       self.core_budget,
            'satellite_budget':  self.satellite_budget,
            'core_ratio':        self.core_ratio,
            'satellite_ratio':   self.satellite_ratio,
            'regime':            self.regime,
            'rebalance':         self.check_rebalance(satellite_current_value),
        }
