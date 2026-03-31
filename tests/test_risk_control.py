"""
風險控制模組單元測試 (risk_control.py)

涵蓋範圍：
  - portfolio_exposure()        組合曝險
  - stop_loss_trigger()         固定停損
  - trailing_stop_trigger()     移動停利（含回歸測試：已修正的舊邏輯漏洞）
  - RiskController              主控制器（position_size / stop_price /
                                 check_exit / update_drawdown / can_add_position
                                 / cash_check / full_report）
  - calc_position_size()        便利函數
  - calc_stop_loss()            便利函數
"""

import pytest
from risk_control import (
    portfolio_exposure,
    stop_loss_trigger,
    trailing_stop_trigger,
    RiskController,
    calc_position_size,
    calc_stop_loss,
)


# ══════════════════════════════════════════════════════════════
# 1. portfolio_exposure
# ══════════════════════════════════════════════════════════════

class TestPortfolioExposure:
    def test_bull_returns_080(self):
        assert portfolio_exposure("bull") == pytest.approx(0.80)

    def test_neutral_returns_050(self):
        assert portfolio_exposure("neutral") == pytest.approx(0.50)

    def test_bear_returns_020(self):
        assert portfolio_exposure("bear") == pytest.approx(0.20)

    def test_unknown_regime_falls_back_to_neutral(self):
        assert portfolio_exposure("sideways") == pytest.approx(0.50)

    def test_empty_string_falls_back_to_neutral(self):
        assert portfolio_exposure("") == pytest.approx(0.50)

    def test_case_sensitive_bull_uppercase_is_unknown(self):
        # 'BULL' ≠ 'bull'，應退回 neutral
        assert portfolio_exposure("BULL") == pytest.approx(0.50)


# ══════════════════════════════════════════════════════════════
# 2. stop_loss_trigger
# ══════════════════════════════════════════════════════════════

class TestStopLossTrigger:
    """預設 stop_pct=8%：觸發價 = buy_price × 0.92"""

    def test_exactly_at_stop_price_triggers(self):
        # 100 × (1 - 0.08) = 92.0 → True
        assert stop_loss_trigger(100, 92.0) is True

    def test_one_cent_below_stop_price_triggers(self):
        assert stop_loss_trigger(100, 91.99) is True

    def test_one_cent_above_stop_price_does_not_trigger(self):
        assert stop_loss_trigger(100, 92.01) is False

    def test_profitable_price_does_not_trigger(self):
        assert stop_loss_trigger(100, 115) is False

    def test_custom_stop_pct_10_triggers_at_90(self):
        assert stop_loss_trigger(100, 90.0, stop_pct=0.10) is True
        assert stop_loss_trigger(100, 90.01, stop_pct=0.10) is False

    def test_zero_stop_pct_triggers_at_buy_price(self):
        # stop_pct=0 → 觸發於 current <= buy_price
        assert stop_loss_trigger(100, 100.0, stop_pct=0.0) is True
        assert stop_loss_trigger(100, 100.01, stop_pct=0.0) is False


# ══════════════════════════════════════════════════════════════
# 3. trailing_stop_trigger
# ══════════════════════════════════════════════════════════════

class TestTrailingStopTrigger:
    """
    預設 trail_pct=7%, min_profit_pct=3%
    邏輯：
      1. peak < buy * 1.03 → 閘門未開，一律 False
      2. peak >= buy * 1.03 → 閘門開啟，current <= peak * 0.93 → True
    """

    def test_peak_below_min_threshold_never_triggers(self):
        """peak 僅漲 2%（<3% 閘門），即使現價大跌也不觸發"""
        assert trailing_stop_trigger(100, 102, 50) is False

    def test_peak_exactly_at_threshold_arms_trigger(self):
        """peak=103（剛達 3% 閘門）
        trail: 103 × 0.93 = 95.79 → 95.7 <= 95.79 → True"""
        assert trailing_stop_trigger(100, 103, 95.7) is True

    def test_peak_well_above_threshold_price_holds(self):
        """peak=120，現價 115 > 120×0.93=111.6 → 尚未觸發"""
        assert trailing_stop_trigger(100, 120, 115) is False

    def test_peak_above_threshold_price_hits_trail_triggers(self):
        """peak=120，現價=111.6（恰在移動停利線）→ True"""
        assert trailing_stop_trigger(100, 120, 111.6) is True

    def test_regression_old_bug_scenario(self):
        """
        回歸測試——已修正的舊邏輯漏洞（§6.2 docstring）：
          買入 100 → 最高漲至 120 → 現價跌回 95（低於成本）
          舊邏輯：因 95 < 100 而不觸發 → 讓利潤白白蒸發
          新邏輯：peak(120) >= 103 閘門開啟，95 <= 111.6 → 必須觸發
        """
        assert trailing_stop_trigger(100, 120, 95) is True

    def test_custom_trail_pct(self):
        # trail_pct=10%：peak=110 → 觸發線 110×0.90=99
        assert trailing_stop_trigger(100, 110, 99.0, trail_pct=0.10) is True
        assert trailing_stop_trigger(100, 110, 99.1, trail_pct=0.10) is False

    def test_custom_min_profit_pct(self):
        # min_profit_pct=5%：peak=104（<105）→ 閘門未開 → False
        assert trailing_stop_trigger(100, 104, 50, min_profit_pct=0.05) is False
        # peak=105（≥5% 閘門）：105×0.93=97.65 → 97 <= 97.65 → True
        assert trailing_stop_trigger(100, 105, 97, min_profit_pct=0.05) is True


# ══════════════════════════════════════════════════════════════
# 4. RiskController — 初始化與屬性
# ══════════════════════════════════════════════════════════════

class TestRiskControllerInit:
    def test_default_values(self):
        rc = RiskController()
        assert rc.portfolio_value == 1_000_000
        assert rc.regime == "neutral"
        assert rc.trading_suspended is False
        assert rc.peak_value == 1_000_000

    def test_custom_portfolio_value_and_regime(self):
        rc = RiskController(portfolio_value=500_000, regime="bull")
        assert rc.portfolio_value == 500_000
        assert rc.regime == "bull"

    def test_target_exposure_property_matches_regime(self):
        assert RiskController(regime="bull").target_exposure == pytest.approx(0.80)
        assert RiskController(regime="neutral").target_exposure == pytest.approx(0.50)
        assert RiskController(regime="bear").target_exposure == pytest.approx(0.20)

    def test_max_stock_budget_neutral(self):
        rc = RiskController(portfolio_value=1_000_000, regime="neutral")
        assert rc.max_stock_budget == pytest.approx(500_000)

    def test_max_stock_budget_bull(self):
        rc = RiskController(portfolio_value=1_000_000, regime="bull")
        assert rc.max_stock_budget == pytest.approx(800_000)


# ══════════════════════════════════════════════════════════════
# 5. RiskController.position_size
# ══════════════════════════════════════════════════════════════

class TestPositionSize:
    def setup_method(self):
        self.rc = RiskController(portfolio_value=1_000_000)

    def test_normal_price_rounds_to_correct_lots(self):
        # 10% × 1M = 100,000；price=50 → 100,000/50=2,000 股 = 2 張
        r = self.rc.position_size(price=50)
        assert r["shares"] == 2000
        assert r["lots"] == 2
        assert r["allocated"] == 100_000
        assert r["actual_cost"] == pytest.approx(100_000)

    def test_price_too_high_gives_zero_shares(self):
        # 100,000 / 110 = 909 股 → int(0.909) × 1000 = 0
        r = self.rc.position_size(price=110)
        assert r["shares"] == 0
        assert r["lots"] == 0

    def test_rounds_down_not_up(self):
        # 100,000 / 60 = 1,666.67 → 1 張（無條件捨去）
        r = self.rc.position_size(price=60)
        assert r["shares"] == 1000
        assert r["lots"] == 1

    def test_custom_weight_reduces_allocation(self):
        # 5% weight → 50,000；price=50 → 1,000 股 = 1 張
        r = self.rc.position_size(price=50, weight=0.05)
        assert r["shares"] == 1000
        assert r["lots"] == 1

    def test_actual_cost_consistent_with_shares_and_price(self):
        r = self.rc.position_size(price=50)
        assert r["actual_cost"] == r["shares"] * 50


# ══════════════════════════════════════════════════════════════
# 6. RiskController.stop_price
# ══════════════════════════════════════════════════════════════

class TestStopPrice:
    def test_8pct_stop_on_round_price(self):
        rc = RiskController()
        assert rc.stop_price(100) == pytest.approx(92.0)

    def test_8pct_stop_on_decimal_price(self):
        # 75.5 × 0.92 = 69.46
        rc = RiskController()
        assert rc.stop_price(75.5) == pytest.approx(69.46)


# ══════════════════════════════════════════════════════════════
# 7. RiskController.check_exit
# ══════════════════════════════════════════════════════════════

class TestCheckExit:
    def setup_method(self):
        self.rc = RiskController(portfolio_value=1_000_000)

    def test_hold_when_price_rises(self):
        r = self.rc.check_exit("2330", 100, 110)
        assert r["exit_type"] == "hold"
        assert r["pnl_pct"] == pytest.approx(10.0)

    def test_stop_loss_when_price_drops_exactly_8pct(self):
        r = self.rc.check_exit("2330", 100, 92.0)
        assert r["exit_type"] == "stop_loss"
        assert r["pnl_pct"] == pytest.approx(-8.0)

    def test_stop_loss_takes_priority_over_trailing(self):
        """
        先建立高峰（peak=150），讓移動停利閘門開啟。
        當現價跌至 85（同時觸發固定停損 AND 移動停利），
        固定停損應優先回傳。
        """
        self.rc.check_exit("2330", 100, 150)   # 建立 peak=150
        r = self.rc.check_exit("2330", 100, 85)
        # stop_loss: 85 <= 92 ✓
        # trailing: 85 <= 150×0.93=139.5 ✓ — 但停損先被檢查
        assert r["exit_type"] == "stop_loss"

    def test_trailing_stop_triggers_after_peak_established(self):
        self.rc.check_exit("2330", 100, 120)   # peak → 120
        # 110 < 120×0.93=111.6 → 移動停利
        r = self.rc.check_exit("2330", 100, 110)
        assert r["exit_type"] == "trailing"

    def test_peak_price_updates_on_new_high(self):
        self.rc.check_exit("2330", 100, 115)
        r = self.rc.check_exit("2330", 100, 120)
        assert r["peak_price"] == 120            # 新高更新

    def test_peak_price_does_not_decrease(self):
        self.rc.check_exit("2330", 100, 120)
        r = self.rc.check_exit("2330", 100, 105)
        assert r["peak_price"] == 120            # 回落後 peak 不變

    def test_different_stocks_tracked_independently(self):
        self.rc.check_exit("2330", 100, 150)
        self.rc.check_exit("2317", 100, 100)
        # 2317 的 peak 應仍為 100（無足夠漲幅開閘）
        r = self.rc.check_exit("2317", 100, 90)
        assert r["exit_type"] == "stop_loss"   # 非 trailing（閘未開）

    def test_result_contains_required_keys(self):
        r = self.rc.check_exit("2330", 100, 105)
        for key in ("exit_type", "action", "pnl_pct", "stop_price", "peak_price"):
            assert key in r


# ══════════════════════════════════════════════════════════════
# 8. RiskController.update_drawdown
# ══════════════════════════════════════════════════════════════

class TestUpdateDrawdown:
    def test_value_rises_above_peak_no_drawdown(self):
        rc = RiskController(portfolio_value=1_000_000)
        r = rc.update_drawdown(1_100_000)
        assert r["drawdown_pct"] == pytest.approx(0.0)
        assert r["trading_suspended"] is False
        assert rc.peak_value == 1_100_000

    def test_10pct_drawdown_does_not_suspend(self):
        rc = RiskController(portfolio_value=1_000_000)
        r = rc.update_drawdown(900_000)
        assert r["drawdown_pct"] == pytest.approx(10.0)
        assert r["trading_suspended"] is False

    def test_exactly_15pct_drawdown_suspends_trading(self):
        rc = RiskController(portfolio_value=1_000_000)
        r = rc.update_drawdown(850_000)
        assert r["drawdown_pct"] == pytest.approx(15.0)
        assert r["trading_suspended"] is True

    def test_hysteresis_zone_stays_suspended(self):
        """
        回撤觸發後（>15%），即使回升至 10%（介於 7.5%-15% 磁滯區），
        仍維持暫停交易——防止在震盪中頻繁切換狀態。
        """
        rc = RiskController(portfolio_value=1_000_000)
        rc.update_drawdown(850_000)   # 觸發暫停（15%）
        assert rc.trading_suspended is True
        rc.update_drawdown(900_000)   # 回升至 10%（仍在磁滯區）
        assert rc.trading_suspended is True

    def test_recovery_below_half_threshold_resumes_trading(self):
        """回撤降至 7.5% 以下（閾值的一半）→ 恢復交易"""
        rc = RiskController(portfolio_value=1_000_000)
        rc.update_drawdown(850_000)   # 暫停
        assert rc.trading_suspended is True
        rc.update_drawdown(935_000)   # peak=1M，回撤=6.5% < 7.5% → 恢復
        assert rc.trading_suspended is False

    def test_peak_value_updated_on_new_high(self):
        rc = RiskController(portfolio_value=1_000_000)
        rc.update_drawdown(1_200_000)
        assert rc.peak_value == 1_200_000


# ══════════════════════════════════════════════════════════════
# 9. RiskController.can_add_position
# ══════════════════════════════════════════════════════════════

class TestCanAddPosition:
    def test_zero_positions_can_add(self):
        assert RiskController().can_add_position(0) is True

    def test_nine_positions_can_add(self):
        assert RiskController().can_add_position(9) is True

    def test_ten_positions_cannot_add(self):
        assert RiskController().can_add_position(10) is False

    def test_over_max_cannot_add(self):
        assert RiskController().can_add_position(15) is False


# ══════════════════════════════════════════════════════════════
# 10. RiskController.cash_check
# ══════════════════════════════════════════════════════════════

class TestCashCheck:
    def test_sufficient_cash_20pct(self):
        rc = RiskController()
        r = rc.cash_check(equity_value=800_000, portfolio_total=1_000_000)
        assert r["ok"] is True
        assert r["cash_ratio"] == pytest.approx(20.0)

    def test_insufficient_cash_5pct(self):
        rc = RiskController()
        r = rc.cash_check(equity_value=950_000, portfolio_total=1_000_000)
        assert r["ok"] is False
        assert r["cash_ratio"] == pytest.approx(5.0)

    def test_exactly_at_min_cash_is_ok(self):
        # 10% 現金剛好等於下限 → OK（>=）
        rc = RiskController()
        r = rc.cash_check(equity_value=900_000, portfolio_total=1_000_000)
        assert r["ok"] is True

    def test_cash_amount_correct(self):
        rc = RiskController()
        r = rc.cash_check(equity_value=700_000, portfolio_total=1_000_000)
        assert r["cash"] == 300_000


# ══════════════════════════════════════════════════════════════
# 11. RiskController.full_report
# ══════════════════════════════════════════════════════════════

class TestFullReport:
    def test_empty_positions(self):
        rc = RiskController(portfolio_value=1_000_000)
        r = rc.full_report([])
        assert r["total_cost"] == 0
        assert r["total_value"] == 0
        assert r["positions"] == 0
        assert r["can_add"] is True

    def test_single_profitable_position(self):
        rc = RiskController(portfolio_value=1_000_000)
        positions = [{"stock_id": "2330", "buy_price": 100,
                      "current_price": 110, "lots": 5}]
        r = rc.full_report(positions)
        assert r["total_cost"] == 500_000    # 100 × 5 × 1000
        assert r["total_value"] == 550_000   # 110 × 5 × 1000
        assert r["total_pnl"] == 50_000
        assert r["total_pnl_pct"] == pytest.approx(10.0)

    def test_stop_loss_position_generates_alert(self):
        rc = RiskController(portfolio_value=1_000_000)
        positions = [{"stock_id": "9999", "buy_price": 100,
                      "current_price": 90, "lots": 2}]
        r = rc.full_report(positions)
        assert len(r["exit_alerts"]) == 1
        assert "9999" in r["exit_alerts"][0]


# ══════════════════════════════════════════════════════════════
# 12. 便利函數
# ══════════════════════════════════════════════════════════════

class TestConvenienceFunctions:
    def test_calc_position_size_default_weight(self):
        r = calc_position_size(1_000_000, 50)
        assert r["shares"] == 2000
        assert r["lots"] == 2

    def test_calc_stop_loss_default_8pct(self):
        # 100 × (1 - 0.08) = 92.0
        assert calc_stop_loss(100) == pytest.approx(92.0)

    def test_calc_stop_loss_custom_pct(self):
        # 100 × (1 - 0.10) = 90.0
        assert calc_stop_loss(100, stop_pct=0.10) == pytest.approx(90.0)


# ══════════════════════════════════════════════════════════════
# Additional: RiskController.check_stop_loss (backward-compat)
# ══════════════════════════════════════════════════════════════

class TestCheckStopLossCompat:
    """check_stop_loss 是 check_exit 的舊版相容包裝"""

    def setup_method(self):
        from risk_control import RiskController
        self.rc = RiskController()

    def test_check_stop_loss_no_exit(self):
        """持倉未觸停損 → exit_type 'hold'"""
        r = self.rc.check_stop_loss(100, 105)
        assert r['exit_type'] == 'hold'

    def test_check_stop_loss_triggers(self):
        """跌破停損 → exit_type 不為 'hold'"""
        r = self.rc.check_stop_loss(100, 91.0)
        assert r['exit_type'] != 'hold'
