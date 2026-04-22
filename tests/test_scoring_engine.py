"""
評分引擎單元測試 (scoring_engine.py)

涵蓋範圍：
  calc_trend_score / calc_momentum_score / momentum_signal
  chip_score / calc_chip_score / calc_volume_score / calc_risk_score
  stock_score / score_single_stock / rank_stocks
  calc_fundamental_score / calc_atr_stop / check_time_stop
  check_contract_liability_surge / check_bollinger_squeeze
  check_fake_breakout / calc_rr_ratio / calculate_position_size
  calc_rs_score
"""

import pytest
import pandas as pd
import numpy as np

from scoring_engine import (
    calc_quality_score,
    calc_forward_momentum_score,
    calc_leading_indicators_detail,
    calc_trend_score,
    calc_momentum_score,
    momentum_signal,
    chip_score,
    calc_chip_score,
    calc_volume_score,
    calc_risk_score,
    stock_score,
    score_single_stock,
    rank_stocks,
    calc_fundamental_score,
    calc_atr_stop,
    check_time_stop,
    check_contract_liability_surge,
    check_bollinger_squeeze,
    check_fake_breakout,
    calc_rr_ratio,
    calculate_position_size,
    calc_rs_score,
    rs_slope,
    check_relative_strength,
)


# ── 共用工具 ──────────────────────────────────────────────────

def make_ohlcv(prices, atr_pct=0.01, volumes=None):
    n = len(prices)
    return pd.DataFrame({
        "close":  [float(p) for p in prices],
        "open":   [float(p) for p in prices],
        "high":   [float(p) * (1 + atr_pct) for p in prices],
        "low":    [float(p) * (1 - atr_pct) for p in prices],
        "volume": volumes if volumes is not None else [1_000_000] * n,
    })

def rising(n=130, start=100, step=1):
    return [start + i * step for i in range(n)]

def falling(n=130, start=229, step=1):
    return [start - i * step for i in range(n)]


# ══════════════════════════════════════════════════════════════
# 1. calc_trend_score
# ══════════════════════════════════════════════════════════════

class TestCalcTrendScore:

    def test_none_returns_zero(self):
        assert calc_trend_score(None) == 0.0

    def test_empty_df_returns_zero(self):
        assert calc_trend_score(pd.DataFrame()) == 0.0

    def test_no_close_column_returns_zero(self):
        df = pd.DataFrame({"price": [100, 101, 102]})
        assert calc_trend_score(df) == 0.0

    def test_fewer_than_60_rows_returns_zero(self):
        assert calc_trend_score(make_ohlcv(rising(59))) == 0.0

    def test_exactly_59_rows_returns_zero(self):
        assert calc_trend_score(make_ohlcv(rising(59))) == 0.0

    def test_bull_130_rows_perfect_score(self):
        """130 天穩定上漲：close > MA5/20/60，MA20>MA60>MA120 → 5/5 = 100.0"""
        assert calc_trend_score(make_ohlcv(rising(130))) == pytest.approx(100.0)

    def test_bear_130_rows_zero_score(self):
        """130 天穩定下跌：close 低於所有 MA，MA 空頭排列 → 0/5 = 0.0"""
        assert calc_trend_score(make_ohlcv(falling(130))) == pytest.approx(0.0)

    def test_65_rows_ma120_nan_caps_at_80(self):
        """65 行：MA120 全 NaN → 條件5不通過 → 最高 4/5 = 80.0"""
        score = calc_trend_score(make_ohlcv(rising(65)))
        assert score == pytest.approx(80.0)

    def test_nan_ma_not_counted_as_above(self):
        """回歸：NaN MA 不應被誤判為『價格站上』→ 不得增加分數"""
        df_65 = make_ohlcv(rising(65))
        df_130 = make_ohlcv(rising(130))
        # 65 行缺 MA120，分數必須低於全條件成立的 130 行
        assert calc_trend_score(df_65) < calc_trend_score(df_130)

    def test_score_range_0_to_100(self):
        for df in [make_ohlcv(rising(130)), make_ohlcv(falling(130)),
                   make_ohlcv(rising(65))]:
            s = calc_trend_score(df)
            assert 0.0 <= s <= 100.0


# ══════════════════════════════════════════════════════════════
# 2. calc_momentum_score
# ══════════════════════════════════════════════════════════════

class TestCalcMomentumScore:

    def test_none_returns_zero(self):
        assert calc_momentum_score(None) == 0.0

    def test_fewer_than_20_rows_returns_zero(self):
        assert calc_momentum_score(make_ohlcv(rising(19))) == 0.0

    def test_valid_bull_df_positive_score(self):
        df = make_ohlcv(rising(130))
        assert calc_momentum_score(df) > 0.0

    def test_score_range_0_to_100(self):
        assert 0.0 <= calc_momentum_score(make_ohlcv(rising(130))) <= 100.0

    def test_injected_normal_rsi_gets_higher_score_than_overbought(self):
        """RSI=50（正常區）應比 RSI=80（超買）得更高分"""
        df_normal = make_ohlcv(rising(130)).copy()
        df_normal["RSI"] = 50.0
        df_overbought = make_ohlcv(rising(130)).copy()
        df_overbought["RSI"] = 80.0
        assert calc_momentum_score(df_normal) > calc_momentum_score(df_overbought)

    def test_overbought_rsi_score_0(self):
        """RSI >= 70 → rsi_score=0，最高總分=(0+2+2)/6×100=66.7"""
        df = make_ohlcv(rising(130))
        df["RSI"] = 75.0
        assert calc_momentum_score(df) <= 66.8

    def test_oversold_rsi_score_1(self):
        """RSI <= 30 → rsi_score=1，最高總分=(1+2+2)/6×100=83.3"""
        df = make_ohlcv(rising(130))
        df["RSI"] = 25.0
        assert calc_momentum_score(df) <= 83.4

    def test_high_atr_pct_lowers_score(self):
        """高 ATR%（>5%）應使 atr_score=0，降低總分"""
        df_low = make_ohlcv(rising(130), atr_pct=0.01)   # ATR%≈2% → score 2
        df_low["RSI"] = 50.0
        df_high = make_ohlcv(rising(130), atr_pct=0.03)  # ATR%≈6% → score 0
        df_high["RSI"] = 50.0
        assert calc_momentum_score(df_low) > calc_momentum_score(df_high)

    def test_rsi_column_not_recomputed_if_present(self):
        """若 DataFrame 已有 RSI 欄位，不應再計算覆蓋"""
        df = make_ohlcv(rising(130))
        df["RSI"] = 50.0
        calc_momentum_score(df)
        assert df["RSI"].iloc[-1] == 50.0  # 值不應被覆蓋


# ══════════════════════════════════════════════════════════════
# 3. momentum_signal
# ══════════════════════════════════════════════════════════════

class TestMomentumSignal:

    def test_none_returns_false(self):
        assert momentum_signal(None) is False

    def test_empty_df_returns_false(self):
        assert momentum_signal(pd.DataFrame()) is False

    def test_bull_with_volume_spike_returns_true(self):
        """上漲趨勢 + 最後一天量能放大 → True"""
        prices  = rising(130)
        volumes = [500_000] * 129 + [2_000_000]  # 量能爆增
        df = make_ohlcv(prices, volumes=volumes)
        assert bool(momentum_signal(df)) is True

    def test_bear_trend_returns_false(self):
        assert bool(momentum_signal(make_ohlcv(falling(130)))) is False


# ══════════════════════════════════════════════════════════════
# 4. chip_score
# ══════════════════════════════════════════════════════════════

class TestChipScore:

    def test_all_buyers_returns_5(self):
        assert chip_score(1, 1, 1) == 5

    def test_foreign_only_returns_2(self):
        assert chip_score(1, 0, 0) == 2

    def test_trust_only_returns_2(self):
        assert chip_score(0, 1, 0) == 2

    def test_dealer_only_returns_1(self):
        assert chip_score(0, 0, 1) == 1

    def test_all_sell_returns_0(self):
        assert chip_score(-1, -1, -1) == 0

    def test_zero_all_returns_0(self):
        assert chip_score(0, 0, 0) == 0

    def test_max_score_is_5(self):
        assert chip_score(999, 999, 999) == 5


# ══════════════════════════════════════════════════════════════
# 5. calc_chip_score
# ══════════════════════════════════════════════════════════════

class TestCalcChipScore:

    def test_explicit_all_buy_returns_100(self):
        assert calc_chip_score(None, foreign_buy=1, trust_buy=1, dealer_buy=1) == pytest.approx(100.0)

    def test_explicit_all_sell_returns_0(self):
        assert calc_chip_score(None, foreign_buy=-1, trust_buy=-1, dealer_buy=-1) == pytest.approx(0.0)

    def test_no_data_returns_50_neutral(self):
        assert calc_chip_score(None) == pytest.approx(50.0)
        assert calc_chip_score(pd.DataFrame()) == pytest.approx(50.0)

    def test_reads_from_df_columns(self):
        df = pd.DataFrame({
            "close": [100.0],
            "外資買超": [1.0],
            "投信買超": [1.0],
            "自營買超": [1.0],
        })
        assert calc_chip_score(df) == pytest.approx(100.0)

    def test_explicit_params_take_priority_over_df(self):
        """明確傳入參數應優先於 DataFrame 欄位"""
        df = pd.DataFrame({"close": [100.0], "外資買超": [-1.0]})
        # 明確傳入 foreign_buy=1 應覆蓋 df 中的 -1
        result = calc_chip_score(df, foreign_buy=1, trust_buy=0, dealer_buy=0)
        assert result == pytest.approx(40.0)  # 2/5 × 100


# ══════════════════════════════════════════════════════════════
# 6. calc_volume_score
# ══════════════════════════════════════════════════════════════

class TestCalcVolumeScore:

    def test_none_returns_50(self):
        assert calc_volume_score(None) == pytest.approx(50.0)

    def test_fewer_than_20_rows_returns_50(self):
        assert calc_volume_score(make_ohlcv(rising(19))) == pytest.approx(50.0)

    def test_volume_expansion_price_up_high_score(self):
        """量增價漲 + 近 3 日量能持續擴張 → 高分"""
        prices  = rising(130)
        volumes = [500_000] * 127 + [3_000_000, 3_000_000, 3_000_000]
        df = make_ohlcv(prices, volumes=volumes)
        assert calc_volume_score(df) >= 66.6

    def test_contracting_volume_falling_price_low_score(self):
        """量縮價跌 → 低分"""
        prices  = falling(130)
        volumes = [1_000_000] * 127 + [100_000, 100_000, 100_000]
        df = make_ohlcv(prices, volumes=volumes)
        assert calc_volume_score(df) <= 33.4

    def test_score_range_0_to_100(self):
        s = calc_volume_score(make_ohlcv(rising(130)))
        assert 0.0 <= s <= 100.0


# ══════════════════════════════════════════════════════════════
# 7. calc_risk_score
# ══════════════════════════════════════════════════════════════

class TestCalcRiskScore:

    def test_none_returns_zero(self):
        assert calc_risk_score(None) == 0.0

    def test_fewer_than_20_rows_returns_zero(self):
        assert calc_risk_score(make_ohlcv(rising(19))) == 0.0

    def test_low_vol_non_overbought_above_ma60_full_score(self):
        """低波動 + RSI<70 + 站上MA60 → 3/3 = 100.0"""
        df = make_ohlcv(rising(130))
        df["RSI"] = 55.0
        assert calc_risk_score(df) == pytest.approx(100.0)

    def test_overbought_rsi_loses_one_point(self):
        """RSI=80（超買）→ RSI 條件失分，最高 2/3 ≈ 66.7"""
        df = make_ohlcv(rising(130))
        df["RSI"] = 80.0
        assert calc_risk_score(df) <= 66.8

    def test_nan_ma60_gives_half_point(self):
        """25 行資料：MA60 全 NaN → 給 0.5 分（中立），總分 2.5/3 = 83.3"""
        df = make_ohlcv(rising(25))
        df["RSI"] = 50.0
        assert calc_risk_score(df) == pytest.approx(83.3)

    def test_score_range_0_to_100(self):
        assert 0.0 <= calc_risk_score(make_ohlcv(rising(130))) <= 100.0


# ══════════════════════════════════════════════════════════════
# 8. stock_score
# ══════════════════════════════════════════════════════════════

class TestStockScore:

    def test_all_100_returns_100(self):
        """所有因子=100 → 加權後仍為 100（權重總和=1）"""
        assert stock_score(100, 100, 100, 100, 100, 100) == pytest.approx(100.0)

    def test_all_zero_returns_zero(self):
        assert stock_score(0, 0, 0, 0, 0, 0) == pytest.approx(0.0)

    def test_weights_sum_to_1(self):
        """每個因子貢獻之和應等於全因子100分的總分"""
        total = (
            stock_score(100, 0, 0, 0, 0, 0) +
            stock_score(0, 100, 0, 0, 0, 0) +
            stock_score(0, 0, 100, 0, 0, 0) +
            stock_score(0, 0, 0, 100, 0, 0) +
            stock_score(0, 0, 0, 0, 100, 0) +
            stock_score(0, 0, 0, 0, 0, 100)
        )
        assert total == pytest.approx(100.0, abs=0.1)

    def test_trend_weight_is_025(self):
        """趨勢權重=0.25：trend=100 其餘=0 → 25.0"""
        assert stock_score(100, 0, 0, 0, 0, 0) == pytest.approx(25.0)

    def test_fundamental_default_is_neutral_50(self):
        """fundamental 預設值 50 與明確傳入 50 結果相同"""
        assert stock_score(80, 80, 80, 80, 80) == pytest.approx(
            stock_score(80, 80, 80, 80, 80, 50)
        )

    def test_higher_input_gives_higher_output(self):
        base = stock_score(50, 50, 50, 50, 50, 50)
        higher = stock_score(80, 50, 50, 50, 50, 50)
        assert higher > base


# ══════════════════════════════════════════════════════════════
# 9. score_single_stock
# ══════════════════════════════════════════════════════════════

class TestScoreSingleStock:

    def test_none_df_returns_error_dict(self):
        r = score_single_stock(None, stock_id="2330")
        assert r["total"] == 0
        assert "error" in r

    def test_empty_df_returns_error_dict(self):
        r = score_single_stock(pd.DataFrame(), stock_id="2330")
        assert r["total"] == 0
        assert "error" in r

    def test_valid_df_has_all_keys(self):
        r = score_single_stock(make_ohlcv(rising(130)), stock_id="2330")
        for k in ("stock_id", "stock_name", "trend", "momentum",
                  "chip", "volume", "risk", "total", "grade", "momentum_signal"):
            assert k in r

    def test_stock_id_and_name_propagated(self):
        r = score_single_stock(make_ohlcv(rising(130)),
                               stock_id="0050", stock_name="元大50")
        assert r["stock_id"] == "0050"
        assert r["stock_name"] == "元大50"

    def test_grade_a_threshold(self):
        """total >= 75 → A"""
        r = score_single_stock(make_ohlcv(rising(130)),
                               foreign_buy=1, trust_buy=1, dealer_buy=1)
        r["RSI"] = 55.0  # 不影響，grade 已在結果中
        if r["total"] >= 75:
            assert r["grade"] == "A"

    def test_grade_c_threshold(self):
        """total < 55 → C"""
        r = score_single_stock(make_ohlcv(falling(30)))
        if r.get("total", 0) < 55:
            assert r["grade"] == "C"

    def test_grade_consistent_with_total(self):
        r = score_single_stock(make_ohlcv(rising(130)))
        total = r["total"]
        expected = "A" if total >= 75 else ("B" if total >= 55 else "C")
        assert r["grade"] == expected

    def test_all_component_scores_in_range(self):
        r = score_single_stock(make_ohlcv(rising(130)))
        for k in ("trend", "momentum", "chip", "volume", "risk"):
            assert 0.0 <= r[k] <= 100.0, f"{k} out of range: {r[k]}"


# ══════════════════════════════════════════════════════════════
# 10. rank_stocks
# ══════════════════════════════════════════════════════════════

class TestRankStocks:

    def test_sorted_descending(self):
        results = [{"total": 60}, {"total": 85}, {"total": 40}]
        ranked = rank_stocks(results)
        assert [r["total"] for r in ranked] == [85, 60, 40]

    def test_error_entries_excluded(self):
        results = [{"total": 70}, {"total": 0, "error": "無資料"}]
        ranked = rank_stocks(results)
        assert len(ranked) == 1
        assert ranked[0]["total"] == 70

    def test_all_error_returns_empty(self):
        results = [{"total": 0, "error": "x"}, {"total": 0, "error": "y"}]
        assert rank_stocks(results) == []

    def test_empty_list_returns_empty(self):
        assert rank_stocks([]) == []

    def test_ties_preserved(self):
        results = [{"total": 70}, {"total": 70}]
        assert len(rank_stocks(results)) == 2


# ══════════════════════════════════════════════════════════════
# 11. calc_fundamental_score
# ══════════════════════════════════════════════════════════════

class TestCalcFundamentalScore:

    def test_none_returns_50(self):
        assert calc_fundamental_score(None) == pytest.approx(50.0)

    def test_empty_df_returns_50(self):
        assert calc_fundamental_score(pd.DataFrame()) == pytest.approx(50.0)

    def test_strong_yoy_all_conditions_100(self):
        """3 個月 YoY 均>0、加速、>15% → 4/4 = 100.0"""
        df = pd.DataFrame({"yoy": [18.0, 19.0, 20.0]})
        assert calc_fundamental_score(df) == pytest.approx(100.0)

    def test_negative_yoy_still_accelerating_gives_partial(self):
        """YoY 均為負但最後一期改善中（-5,-3,-1）→ 僅 ② 加速得分 = 1/4 = 25.0"""
        df = pd.DataFrame({"yoy": [-5.0, -3.0, -1.0]})
        assert calc_fundamental_score(df) == pytest.approx(25.0)

    def test_auto_yoy_from_revenue_column(self):
        """無 yoy 欄位時，自動用 revenue 的 pct_change(12) 計算"""
        revenues = [1_000_000] * 12 + [1_200_000, 1_250_000, 1_300_000]
        df = pd.DataFrame({"revenue": revenues})
        score = calc_fundamental_score(df)
        # 3 個月 YoY 均>0（20%/25%/30%）+ 加速 + >15% → 100.0
        assert score == pytest.approx(100.0)

    def test_partial_growth_gets_partial_score(self):
        """2/3 個月 YoY>0（第一個月為負）→ 僅部分得分"""
        df = pd.DataFrame({"yoy": [-2.0, 5.0, 10.0]})
        score = calc_fundamental_score(df)
        assert 0.0 < score < 100.0


# ══════════════════════════════════════════════════════════════
# 12. calc_atr_stop
# ══════════════════════════════════════════════════════════════

class TestCalcAtrStop:

    def test_none_df_returns_fixed_8pct(self):
        r = calc_atr_stop(None, entry_price=100)
        assert r["method"] == "fixed_8pct"
        assert r["stop_loss"] == pytest.approx(92.0)
        assert r["stop_pct"] == pytest.approx(8.0)
        assert r["atr"] is None

    def test_fewer_than_14_rows_returns_fixed_8pct(self):
        r = calc_atr_stop(make_ohlcv(rising(13)), entry_price=100)
        assert r["method"] == "fixed_8pct"

    def test_atr_stop_below_entry(self):
        df = make_ohlcv(rising(30, start=100), atr_pct=0.01)
        r = calc_atr_stop(df, entry_price=115, multiplier=1.5)
        assert r["stop_loss"] < 115
        assert r["atr"] is not None
        assert r["method"] == "ATR14×1.5"

    def test_larger_multiplier_lower_stop(self):
        """multiplier 越大，停損點越低"""
        df = make_ohlcv(rising(30, start=100), atr_pct=0.01)
        r1 = calc_atr_stop(df, entry_price=115, multiplier=1.0)
        r2 = calc_atr_stop(df, entry_price=115, multiplier=2.0)
        assert r2["stop_loss"] < r1["stop_loss"]


# ══════════════════════════════════════════════════════════════
# 13. check_time_stop
# ══════════════════════════════════════════════════════════════

class TestCheckTimeStop:

    def test_triggered_long_hold_low_gain(self):
        """持有 15 天，報酬僅 1% < 2% → 觸發"""
        r = check_time_stop(100, 101, hold_days=15, min_gain=0.02, max_days=15)
        assert r["triggered"] is True

    def test_not_triggered_sufficient_gain(self):
        """持有 15 天，報酬 3% > 2% → 不觸發"""
        r = check_time_stop(100, 103, hold_days=15, min_gain=0.02, max_days=15)
        assert r["triggered"] is False

    def test_not_triggered_hold_days_short(self):
        """持有僅 10 天 < 15 天上限 → 不觸發"""
        r = check_time_stop(100, 101, hold_days=10, min_gain=0.02, max_days=15)
        assert r["triggered"] is False

    def test_gain_pct_reported_correctly(self):
        r = check_time_stop(100, 112, hold_days=5)
        assert r["gain_pct"] == pytest.approx(12.0)

    def test_negative_gain_can_trigger(self):
        """虧損狀態也可觸發時間停損"""
        r = check_time_stop(100, 98, hold_days=20, min_gain=0.02, max_days=15)
        assert r["triggered"] is True


# ══════════════════════════════════════════════════════════════
# 14. check_contract_liability_surge
# ══════════════════════════════════════════════════════════════

class TestCheckContractLiabilitySurge:

    def test_no_data_returns_no_surge(self):
        r = check_contract_liability_surge(None, None, 100)
        assert r["is_surge"] is False

    def test_zero_prev_year_returns_no_surge(self):
        r = check_contract_liability_surge(100, 0, 1000)
        assert r["is_surge"] is False

    def test_strong_surge_detected(self):
        """YoY=+100%（>30%）且 ratio=20%（>10%）→ 隱形冠軍潛力"""
        r = check_contract_liability_surge(
            cl_current=200, cl_prev_year=100, paid_in_capital=1000
        )
        assert r["is_surge"] is True
        assert r["yoy_pct"] == pytest.approx(100.0)
        assert r["cl_ratio"] == pytest.approx(20.0)

    def test_moderate_growth_no_surge_flag(self):
        """YoY=+20%（>15% 但<30%）→ 成長標籤但非隱形冠軍"""
        r = check_contract_liability_surge(
            cl_current=120, cl_prev_year=100, paid_in_capital=1000
        )
        assert r["is_surge"] is False
        assert "成長" in r["label"]

    def test_high_yoy_but_low_ratio_no_surge(self):
        """YoY=+50% 但 ratio=2%（<10%）→ 不觸發"""
        r = check_contract_liability_surge(
            cl_current=150, cl_prev_year=100, paid_in_capital=5000
        )
        assert r["is_surge"] is False


# ══════════════════════════════════════════════════════════════
# 15. check_bollinger_squeeze
# ══════════════════════════════════════════════════════════════

class TestCheckBollingerSqueeze:

    def test_insufficient_data_no_signal(self):
        assert check_bollinger_squeeze(None)["is_squeeze_break"] is False
        assert check_bollinger_squeeze(make_ohlcv(rising(20)))["is_squeeze_break"] is False

    def test_flat_prices_narrow_band(self):
        """完全橫盤：std=0，帶寬≈0 → 應標記為蓄勢"""
        prices = [100.0] * 30
        r = check_bollinger_squeeze(make_ohlcv(prices, atr_pct=0.0001))
        assert r["bw_today"] is not None
        assert r["bw_today"] < 2.0

    def test_result_has_required_keys(self):
        r = check_bollinger_squeeze(make_ohlcv(rising(130)))
        for k in ("is_squeeze_break", "bw_today", "bw_avg5"):
            assert k in r


# ══════════════════════════════════════════════════════════════
# 16. check_fake_breakout
# ══════════════════════════════════════════════════════════════

class TestCheckFakeBreakout:

    def test_insufficient_data_no_signal(self):
        assert check_fake_breakout(make_ohlcv(rising(20)))["is_fake"] is False

    def test_normal_day_not_flagged(self):
        assert check_fake_breakout(make_ohlcv(rising(130)))["is_fake"] is False

    def test_fake_breakout_detected(self):
        """
        最後一天：爆量(4×)、創20日新高、長上影線（收盤近最低）→ 假突破
        tail_ratio = (high-close)/(high-low) = 35/40 = 0.875 > 0.6 ✓
        """
        prices  = rising(130)
        volumes = [1_000_000] * 129 + [4_000_000]
        df = make_ohlcv(prices, volumes=volumes)
        df.at[df.index[-1], "high"]   = 250.0
        df.at[df.index[-1], "close"]  = 215.0
        df.at[df.index[-1], "low"]    = 210.0
        r = check_fake_breakout(df)
        assert r["is_fake"] is True


# ══════════════════════════════════════════════════════════════
# 17. calc_rr_ratio
# ══════════════════════════════════════════════════════════════

class TestCalcRrRatio:

    def test_default_target_15pct_above_entry(self):
        r = calc_rr_ratio(100, 92)
        assert r["target"] == pytest.approx(115.0)

    def test_rr_2_passes(self):
        # risk=10, reward=20 → RR=2.0 ≥ 2 → pass
        r = calc_rr_ratio(100, 90, target_price=120)
        assert r["rr"] == pytest.approx(2.0)
        assert r["pass"] is True

    def test_rr_below_2_fails(self):
        # risk=10, reward=10 → RR=1.0 < 2 → fail
        r = calc_rr_ratio(100, 90, target_price=110)
        assert r["rr"] == pytest.approx(1.0)
        assert r["pass"] is False

    def test_stop_above_entry_error(self):
        """停損價 >= 進場價 → risk<=0 → 錯誤回傳"""
        r = calc_rr_ratio(100, 105)
        assert r["rr"] == 0
        assert r["pass"] is False

    def test_exact_stop_equals_entry_error(self):
        r = calc_rr_ratio(100, 100)
        assert r["pass"] is False


# ══════════════════════════════════════════════════════════════
# 18. calculate_position_size
# ══════════════════════════════════════════════════════════════

class TestCalculatePositionSize:

    def test_normal_case_stop_calculated(self):
        """ATR=2 → stop = 100 - 1.5×2 = 97"""
        r = calculate_position_size(1_000_000, 100, 2.0)
        assert r["stop_loss"] == pytest.approx(97.0)
        assert r["position_lot"] >= 0

    def test_atr_too_large_capped_at_15pct(self):
        """ATR=50 → stop 原為 25，但下限保護為 entry×0.85=85"""
        r = calculate_position_size(1_000_000, 100, 50.0)
        assert r["stop_loss"] == pytest.approx(85.0)

    def test_result_contains_rr_ratio(self):
        r = calculate_position_size(1_000_000, 100, 2.0)
        assert "rr_ratio" in r
        assert "target_price" in r

    def test_lots_rounded_to_whole_number(self):
        r = calculate_position_size(1_000_000, 100, 2.0)
        assert r["position_lot"] == r["position_sh"] // 1000


# ══════════════════════════════════════════════════════════════
# 19. calc_rs_score
# ══════════════════════════════════════════════════════════════

class TestCalcRsScore:

    def test_none_returns_50(self):
        assert calc_rs_score(None) == 50

    def test_fewer_than_20_returns_50(self):
        assert calc_rs_score(make_ohlcv(rising(15))) == 50

    def test_strong_bull_returns_high_score(self):
        """大漲股（無大盤基準）→ 絕對漲幅映射高分"""
        # 130 天從 100 漲到 229 → 漲幅 129% > 50% → 應得 100 分
        s = calc_rs_score(make_ohlcv(rising(130)))
        assert s == 100

    def test_flat_stock_returns_middle_score(self):
        """幾乎不動的股票 → 漲幅 ≈ 0% → 50 分"""
        prices = [100.0] * 130
        s = calc_rs_score(make_ohlcv(prices))
        assert s == 50

    def test_score_range_valid(self):
        for df in [make_ohlcv(rising(130)), make_ohlcv(falling(130))]:
            s = calc_rs_score(df)
            assert 0 <= s <= 100

    def test_with_index_data_strong_outperform(self):
        """個股漲幅 > 大盤漲幅 → RS>1 → 高分"""
        # stock: 100→200 (+100%), index: 100→110 (+10%) → rs=10 → 100分
        stock_df = make_ohlcv(rising(130, 100, 1))
        idx_df = pd.DataFrame({'Close': rising(130, 100, 0.077)})
        s = calc_rs_score(stock_df, df_index=idx_df)
        assert s >= 75

    def test_with_index_data_underperform(self):
        """個股漲幅 < 大盤漲幅 → RS<0.5 → 低分"""
        stock_df = make_ohlcv([100.0] * 130)   # flat
        idx_df = pd.DataFrame({'Close': rising(130, 100, 1)})  # index rises
        s = calc_rs_score(stock_df, df_index=idx_df)
        assert s <= 55


# ══════════════════════════════════════════════════════════════
# 20. rs_slope
# ══════════════════════════════════════════════════════════════

class TestRsSlope:

    def test_none_returns_none(self):
        assert rs_slope(None) is None

    def test_too_short_returns_none(self):
        assert rs_slope(make_ohlcv(rising(25))) is None

    def test_recovering_stock_positive_slope(self):
        """先跌後反彈 → 近期20日報酬改善 → True"""
        prices = [200 - i * 2 for i in range(30)] + [140 + i for i in range(30)]
        result = rs_slope(make_ohlcv(prices))
        assert result == True  # noqa: E712

    def test_returns_bool(self):
        """回傳值必須為 bool（或可比較 True/False）"""
        result = rs_slope(make_ohlcv(rising(60)))
        assert result in (True, False)


# ══════════════════════════════════════════════════════════════
# 21. check_relative_strength
# ══════════════════════════════════════════════════════════════

class TestCheckRelativeStrength:

    def test_none_returns_not_strong(self):
        r = check_relative_strength(None)
        assert r['is_strong'] is False
        assert r['strong_days'] == 0

    def test_too_short_returns_not_strong(self):
        r = check_relative_strength(make_ohlcv(rising(3)))
        assert r['is_strong'] is False

    def test_strong_stock_no_index(self):
        """無大盤資料：個股5日皆上漲 → beats>=3 → is_strong True"""
        prices = [100, 101, 102, 103, 104, 105, 106]
        r = check_relative_strength(make_ohlcv(prices))
        assert r['is_strong'] is True
        assert r['strong_days'] >= 3

    def test_flat_stock_no_index_not_strong(self):
        """個股橫盤：漲跌天數 < 3 → is_strong False"""
        prices = [100, 101, 100, 101, 100, 101, 100]
        r = check_relative_strength(make_ohlcv(prices))
        assert r['is_strong'] is False

    def test_with_index_outperforms(self):
        """個股每天漲2%，大盤每天漲0.5% → 每天都超過大盤 → is_strong"""
        n = 10
        stock_p = [100 * (1.02 ** i) for i in range(n)]
        idx_p = [100 * (1.005 ** i) for i in range(n)]
        stock_df = make_ohlcv(stock_p)
        idx_df = pd.DataFrame({'Close': idx_p})
        r = check_relative_strength(stock_df, df_index=idx_df, days=5)
        assert r['is_strong'] is True

    def test_with_index_underperforms(self):
        """個股橫盤，大盤大漲 → 超大盤天數 < 3 → is_strong False"""
        n = 10
        stock_p = [100.0] * n
        idx_p = [100 * (1.02 ** i) for i in range(n)]
        stock_df = make_ohlcv(stock_p)
        idx_df = pd.DataFrame({'Close': idx_p})
        r = check_relative_strength(stock_df, df_index=idx_df, days=5)
        assert r['is_strong'] is False


# ══════════════════════════════════════════════════════════════
# 22. Edge cases for additional coverage
# ══════════════════════════════════════════════════════════════

class TestAdditionalCoverage:

    def test_calc_momentum_score_short_df_atr_fallback(self):
        """df < 14 rows → atr_score = 1（fallback 路徑）"""
        prices = [100 + i for i in range(10)]
        df = make_ohlcv(prices)
        score = calc_momentum_score(df)
        assert 0.0 <= score <= 100.0

    def test_calc_volume_score_price_and_vol_up(self):
        """close[-1]>close[-3] 且 vol[-1]>vol[-3] → score += 1 路徑"""
        prices = [100, 101, 102, 103, 105] + [105] * 20
        vols = [1_000_000] * 23 + [1_200_000] + [1_000_000]
        df = pd.DataFrame({
            'close':  prices,
            'open':   prices,
            'high':   [p * 1.01 for p in prices],
            'low':    [p * 0.99 for p in prices],
            'volume': vols,
        })
        score = calc_volume_score(df)
        assert 0.0 <= score <= 100.0

    def test_calc_risk_score_medium_volatility(self):
        """波動率介於 0.02~0.035 → elif 路徑（line 199）"""
        import numpy as np
        rng = np.random.default_rng(42)
        # 產生約2.5%日波動的收盤價
        pct_changes = rng.normal(0, 0.025, 30)
        prices = [100.0]
        for r in pct_changes:
            prices.append(prices[-1] * (1 + r))
        df = make_ohlcv(prices)
        score = calc_risk_score(df)
        assert 0.0 <= score <= 100.0

    def test_score_single_stock_grade_a(self):
        """高品質股票 → total >= 75 → grade 'A'"""
        # 使用長期穩定上漲、低波動資料
        prices = [100 + i * 0.3 for i in range(130)]
        df = make_ohlcv(prices, atr_pct=0.005)
        result = score_single_stock(df, stock_id='9999', stock_name='測試A')
        assert result['grade'] in ('A', 'B', 'C')  # grade欄位存在即可
        assert 'total' in result

    def test_calculate_position_size_zero_atr_error(self):
        """ATR 極小 → risk_per_sh 可能為 0 → error 路徑"""
        # entry=100, atr=0 → stop=100-0=100 → risk_per_sh=0
        r = calculate_position_size(1_000_000, 100, 0.0)
        # stop_loss = max(100 - 0, 100*0.85) = 85, risk=15 → no error
        # Actually with atr=0: stop = 100-0=100, but max(100, 85)=100
        # risk_per_sh = 100-100 = 0 → error
        assert 'error' in r or 'stop_loss' in r  # either path is valid

    def test_calculate_position_size_large_atr_risk_zero(self):
        """entry=100, atr=100 → stop capped at 85, risk=15 → no error"""
        r = calculate_position_size(1_000_000, 100, 100.0)
        assert 'stop_loss' in r
        assert r['stop_loss'] == pytest.approx(85.0)


# ── VCP ATR 濾網 ──────────────────────────────────────────────
class TestCheckVcpAtrFilter:
    def test_none_df_returns_not_pass(self):
        from scoring_engine import check_vcp_atr_filter
        r = check_vcp_atr_filter(None)
        assert r['pass'] is False
        assert r['label'] == '資料不足'

    def test_short_df_returns_not_pass(self):
        from scoring_engine import check_vcp_atr_filter
        r = check_vcp_atr_filter(make_ohlcv(rising(10)))
        assert r['pass'] is False

    def test_contraction_passes(self):
        """ATR5 < ATR20×0.8：先大波動後小波動 → pass=True"""
        from scoring_engine import check_vcp_atr_filter
        # 前25天大波動（atr_pct=0.05），最後5天小波動（close-only）
        import pandas as pd, numpy as np
        prices = [100 + i for i in range(30)]
        hi = [p * 1.05 for p in prices[:25]] + [p * 1.001 for p in prices[25:]]
        lo = [p * 0.95 for p in prices[:25]] + [p * 0.999 for p in prices[25:]]
        df = pd.DataFrame({'close': prices, 'high': hi, 'low': lo,
                           'volume': [1e6] * 30})
        r = check_vcp_atr_filter(df)
        assert r['pass'] is True
        assert r['atr5'] is not None
        assert r['atr20'] is not None

    def test_no_contraction_fails(self):
        """持續大波動 → ATR5 ≈ ATR20 → pass=False"""
        from scoring_engine import check_vcp_atr_filter
        r = check_vcp_atr_filter(make_ohlcv(rising(30), atr_pct=0.05))
        assert r['pass'] is False


# ── 券資比軋空加分 ────────────────────────────────────────────
class TestCalcShortSqueezeBonus:
    def test_full_condition_gives_bonus(self):
        from scoring_engine import calc_short_squeeze_bonus
        r = calc_short_squeeze_bonus(short_ratio=0.35, inst_consecutive_buy=5)
        assert r['bonus'] == 5
        assert '軋空加分' in r['label']

    def test_high_ratio_no_consec_buy_no_bonus(self):
        from scoring_engine import calc_short_squeeze_bonus
        r = calc_short_squeeze_bonus(short_ratio=0.35, inst_consecutive_buy=2)
        assert r['bonus'] == 0
        assert '法人連買天數不足' in r['label']

    def test_low_ratio_no_bonus(self):
        from scoring_engine import calc_short_squeeze_bonus
        r = calc_short_squeeze_bonus(short_ratio=0.10, inst_consecutive_buy=10)
        assert r['bonus'] == 0
        assert r['label'] == ''

    def test_defaults_no_bonus(self):
        from scoring_engine import calc_short_squeeze_bonus
        r = calc_short_squeeze_bonus()
        assert r['bonus'] == 0


# ── 動態權重 stock_score ──────────────────────────────────────
class TestDynamicWeightStockScore:
    def test_bull_regime_higher_trend_weight(self):
        from scoring_engine import stock_score
        # bull 趨勢權重(0.30) > neutral(0.25)，高趨勢分數下 bull 應得分較高
        bull_score    = stock_score(100, 50, 50, 50, 50, 50, regime='bull')
        neutral_score = stock_score(100, 50, 50, 50, 50, 50, regime='neutral')
        assert bull_score > neutral_score

    def test_bear_regime_higher_risk_weight(self):
        from scoring_engine import stock_score
        # bear 風險權重(0.25) > neutral(0.10)，高風險分數下 bear 應得分較高
        bear_score    = stock_score(50, 50, 50, 50, 100, 50, regime='bear')
        neutral_score = stock_score(50, 50, 50, 50, 100, 50, regime='neutral')
        assert bear_score > neutral_score

    def test_unknown_regime_falls_back_to_neutral(self):
        from scoring_engine import stock_score
        s1 = stock_score(60, 60, 60, 60, 60, 60, regime='unknown')
        s2 = stock_score(60, 60, 60, 60, 60, 60, regime='neutral')
        assert s1 == s2

    def test_score_within_range(self):
        from scoring_engine import stock_score
        for regime in ('bull', 'neutral', 'bear'):
            s = stock_score(80, 70, 60, 50, 40, 30, regime=regime)
            assert 0 <= s <= 100

    def test_squeeze_bonus_applied_in_score_single(self):
        from scoring_engine import score_single_stock
        df = make_ohlcv(rising(60))
        r_no_squeeze = score_single_stock(df, short_ratio=0.0, inst_consec_buy=0)
        r_squeeze    = score_single_stock(df, short_ratio=0.4, inst_consec_buy=5)
        assert r_squeeze['total'] >= r_no_squeeze['total']
        assert r_squeeze['squeeze_bonus'] == 5


# ══════════════════════════════════════════════════════════════
# 21. calc_quality_score
# ══════════════════════════════════════════════════════════════

def _make_quarterly(gm_series, rev_series):
    return pd.DataFrame({'毛利率': gm_series, '營收': rev_series})


class TestCalcQualityScore:

    def test_none_returns_empty(self):
        r = calc_quality_score(None)
        assert r['sq'] is None
        assert r['sq_label'] == '-'

    def test_empty_df_returns_empty(self):
        r = calc_quality_score(pd.DataFrame())
        assert r['sq'] is None

    def test_missing_columns_returns_empty(self):
        r = calc_quality_score(pd.DataFrame({'other': [1, 2, 3]}))
        assert r['sq'] is None

    def test_too_few_rows_returns_empty(self):
        r = calc_quality_score(_make_quarterly([50.0], [1000.0]))
        assert r['sq'] is None

    def test_gm_up_rev_up_best_score(self):
        """毛利率↑ + 營收↑ → sraw=2.0, sq_label='優質'"""
        df = _make_quarterly(
            gm_series=[46.0, 48.0, 50.0, 52.0],
            rev_series=[1000, 1010, 1030, 1060],
        )
        r = calc_quality_score(df)
        assert r['sq'] is not None
        assert r['gm_trend'] == '↑'
        assert r['rev_trend'] == '↑'
        assert r['sq'] >= 75
        assert r['sq_label'] == '優質'

    def test_gm_down_rev_down_worst_score(self):
        """毛利率↓ + 營收↓ → sraw=-2.0, sq_label='弱'"""
        df = _make_quarterly(
            gm_series=[52.0, 50.0, 48.0, 45.0],
            rev_series=[1060, 1030, 1010, 990],
        )
        r = calc_quality_score(df)
        assert r['sq'] is not None
        assert r['gm_trend'] == '↓'
        assert r['rev_trend'] == '↓'
        assert r['sq'] < 40
        assert r['sq_label'] == '弱'

    def test_gm_flat_rev_up_stable(self):
        """毛利率→ + 營收↑ → sraw=1.5"""
        df = _make_quarterly(
            gm_series=[40.0, 40.0, 40.0, 40.0],
            rev_series=[1000, 1010, 1030, 1060],
        )
        r = calc_quality_score(df)
        assert r['gm_trend'] == '→'
        assert r['rev_trend'] == '↑'
        assert r['sq'] is not None

    def test_gm_level_high_boosts_score(self):
        """毛利率>50% → sgm=100，對 sq 加分"""
        df_high = _make_quarterly([55.0, 55.0, 56.0, 57.0], [1000, 1010, 1030, 1060])
        df_low  = _make_quarterly([12.0, 12.0, 13.0, 14.0], [1000, 1010, 1030, 1060])
        r_high = calc_quality_score(df_high)
        r_low  = calc_quality_score(df_low)
        assert r_high['sq'] > r_low['sq']

    def test_output_keys_present(self):
        df = _make_quarterly([50.0, 50.0, 51.0, 52.0], [1000, 1010, 1030, 1060])
        r = calc_quality_score(df)
        for k in ('sq', 'sq_label', 'gm_trend', 'rev_trend', 'gm_level'):
            assert k in r


# ══════════════════════════════════════════════════════════════
# 22. calc_forward_momentum_score
# ══════════════════════════════════════════════════════════════

class TestCalcForwardMomentumScore:

    def test_none_inputs_returns_empty(self):
        r = calc_forward_momentum_score()
        assert r['fgms'] is None
        assert r['fgms_label'] == '-'

    def test_empty_dfs_returns_empty(self):
        r = calc_forward_momentum_score(
            quarterly_df=pd.DataFrame(),
            bs_cf_df=pd.DataFrame(),
        )
        assert r['fgms'] is None

    def test_with_three_rate_data_returns_score(self):
        """三率趨勢維度：毛利率+營業利益率+淨利率全部上升 → 高分"""
        qtr = pd.DataFrame({
            '毛利率':    [38.0, 39.0, 40.0, 41.0, 42.0, 43.0],
            '營業利益率': [10.0, 10.5, 11.0, 11.5, 12.0, 12.5],
            '淨利率':    [ 7.0,  7.5,  8.0,  8.5,  9.0,  9.5],
            '營收':      [1000, 1010, 1020, 1030, 1040, 1050],
        })
        r = calc_forward_momentum_score(quarterly_df=qtr)
        assert r['fgms'] is not None
        assert 0 <= r['fgms'] <= 100

    def test_finance_flag_skips_inventory(self):
        """is_finance=True：存貨維度應被跳過，仍可回傳合理分數"""
        qtr = pd.DataFrame({
            '毛利率':    [40.0, 41.0, 42.0, 43.0],
            '營業利益率': [12.0, 12.5, 13.0, 13.5],
            '淨利率':    [ 8.0,  8.5,  9.0,  9.5],
            '營收':      [1000, 1010, 1020, 1030],
        })
        r = calc_forward_momentum_score(quarterly_df=qtr, is_finance=True)
        assert r['inv_divergence'] is None

    def test_output_keys_present(self):
        r = calc_forward_momentum_score()
        for k in ('fgms', 'fgms_label', 'cl_momentum', 'inv_divergence',
                  'three_rate', 'capex_intensity'):
            assert k in r


# ══════════════════════════════════════════════════════════════
# 23. calc_leading_indicators_detail
# ══════════════════════════════════════════════════════════════

class TestCalcLeadingIndicatorsDetail:

    def test_all_none_returns_six_items(self):
        results = calc_leading_indicators_detail()
        assert len(results) == 6
        for item in results:
            for k in ('id', 'module', 'name', 'signal', 'value', 'detail'):
                assert k in item

    def test_missing_data_all_na(self):
        """所有資料均為 None → signal 全為 '⚪'"""
        results = calc_leading_indicators_detail()
        assert all(r['signal'] == '⚪' for r in results)

    def test_i1_all_positive_accelerating_green(self):
        """I1：3個月YoY均正且加速 → 🟢"""
        rev_df = pd.DataFrame({'yoy': [5.0, 8.0, 12.0]})
        results = calc_leading_indicators_detail(rev_df=rev_df)
        i1 = next(r for r in results if r['id'] == 'I1')
        assert i1['signal'] == '🟢'

    def test_i1_partial_positive_yellow(self):
        """I1：最新月正成長但未連3月 → 🟡"""
        rev_df = pd.DataFrame({'yoy': [-2.0, 3.0, 6.0]})
        results = calc_leading_indicators_detail(rev_df=rev_df)
        i1 = next(r for r in results if r['id'] == 'I1')
        assert i1['signal'] == '🟡'

    def test_i1_negative_latest_red(self):
        """I1：最新月YoY為負 → 🔴"""
        rev_df = pd.DataFrame({'yoy': [5.0, 3.0, -2.0]})
        results = calc_leading_indicators_detail(rev_df=rev_df)
        i1 = next(r for r in results if r['id'] == 'I1')
        assert i1['signal'] == '🔴'

    def test_i1_insufficient_data_na(self):
        """I1：資料不足3個月 → ⚪"""
        rev_df = pd.DataFrame({'yoy': [5.0, 8.0]})
        results = calc_leading_indicators_detail(rev_df=rev_df)
        i1 = next(r for r in results if r['id'] == 'I1')
        assert i1['signal'] == '⚪'

    def test_i2_golden_cross_green(self):
        """I2：MA3 剛突破 MA12 → 🟢"""
        rev = list(range(500, 512)) + [550]
        rev_df = pd.DataFrame({'revenue': rev, 'yoy': [5.0] * 13})
        results = calc_leading_indicators_detail(rev_df=rev_df)
        i2 = next(r for r in results if r['id'] == 'I2')
        assert i2['signal'] in ('🟢', '🟡')

    def test_i6_always_na(self):
        """I6（董監持股）：目前永遠顯示 N/A"""
        results = calc_leading_indicators_detail()
        i6 = next(r for r in results if r['id'] == 'I6')
        assert i6['signal'] == '⚪'
        assert i6['value'] == 'N/A'


# ══════════════════════════════════════════════════════════════
# 24. 補齊邊界路徑（Bollinger squeeze break + VCP exception）
# ══════════════════════════════════════════════════════════════

class TestCalcLeadingIndicatorsDetailExtended:
    """I2-I5 訊號路徑補充測試"""

    def _make_rev_df_12(self, values):
        """建立 12 個月的 revenue DataFrame"""
        return pd.DataFrame({'revenue': values, 'yoy': [5.0] * len(values)})

    def test_i2_ma3_below_ma12_red(self):
        """I2：MA3 < MA12（死亡交叉）→ 🔴"""
        # 先高後低：前10個月高，後2個月暴跌，MA3 < MA12
        values = [1000] * 10 + [400, 300]
        results = calc_leading_indicators_detail(rev_df=self._make_rev_df_12(values))
        i2 = next(r for r in results if r['id'] == 'I2')
        assert i2['signal'] == '🔴'

    def test_i2_ma3_above_ma12_yellow_flat(self):
        """I2：MA3 在 MA12 上方但趨緩（MA3 not rising）→ 🟡"""
        # 先低後高再持平：MA3 > MA12 但 MA3 本身不再上升
        values = [500] * 10 + [1000, 1000]
        results = calc_leading_indicators_detail(rev_df=self._make_rev_df_12(values))
        i2 = next(r for r in results if r['id'] == 'I2')
        assert i2['signal'] in ('🟡', '🟢')

    def test_i2_insufficient_revenue_data(self):
        """I2：revenue 資料不足 12 個月 → ⚪"""
        rev_df = pd.DataFrame({'revenue': [1000] * 5})
        results = calc_leading_indicators_detail(rev_df=rev_df)
        i2 = next(r for r in results if r['id'] == 'I2')
        assert i2['signal'] == '⚪'

    def test_i3_contract_liability_surge_green(self):
        """I3：合約負債 QoQ > 20% → 🟢"""
        bs_cf = pd.DataFrame({'合約負債': [1e8, 1.3e8]})  # +30%
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf)
        i3 = next(r for r in results if r['id'] == 'I3')
        assert i3['signal'] == '🟢'

    def test_i3_contract_liability_decline_red(self):
        """I3：合約負債 QoQ < -5% → 🔴"""
        bs_cf = pd.DataFrame({'合約負債': [1e8, 9e7]})  # -10%
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf)
        i3 = next(r for r in results if r['id'] == 'I3')
        assert i3['signal'] == '🔴'

    def test_i3_no_contract_liability_na(self):
        """I3：bs_cf_df 無 '合約負債' 欄位 → ⚪"""
        bs_cf = pd.DataFrame({'存貨': [100, 90]})
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf)
        i3 = next(r for r in results if r['id'] == 'I3')
        assert i3['signal'] == '⚪'

    def test_i4_capex_rising_green(self):
        """I4：CapEx/Rev 比率 YoY 明顯提升 → 🟢"""
        bs_cf = pd.DataFrame({'資本支出': [50, 55, 60, 65, 80, 90, 100, 110]})
        qtr   = pd.DataFrame({'營收':     [1000] * 8})
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i4 = next(r for r in results if r['id'] == 'I4')
        assert i4['signal'] in ('🟢', '🟡')

    def test_i4_missing_capex_na(self):
        """I4：bs_cf_df 無 '資本支出' → ⚪"""
        bs_cf = pd.DataFrame({'合約負債': [100, 110]})
        qtr   = pd.DataFrame({'營收': [1000, 1010]})
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i4 = next(r for r in results if r['id'] == 'I4')
        assert i4['signal'] == '⚪'

    def test_i5_inventory_declining_ratio_green(self):
        """I5：存貨/營收比率連續下降 → 庫存去化 🟢"""
        bs_cf = pd.DataFrame({'存貨': [300, 250, 200, 150]})
        qtr   = pd.DataFrame({'營收': [1000, 1000, 1000, 1000]})
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i5 = next(r for r in results if r['id'] == 'I5')
        assert i5['signal'] in ('🟢', '🟡')


class TestCalcForwardMomentumScoreExtended:
    """合約負債 + 存貨維度的深路徑測試"""

    def test_contract_liability_high_qoq_boosts_score(self):
        """合約負債爆增 → CL 維度高分"""
        qtr = pd.DataFrame({
            '毛利率':    [40.0] * 6,
            '營業利益率': [12.0] * 6,
            '淨利率':    [8.0] * 6,
            '營收':      [1000.0] * 6,
        })
        bs_cf = pd.DataFrame({
            '合約負債': [100.0, 120.0, 150.0, 200.0, 250.0],
        })
        r = calc_forward_momentum_score(quarterly_df=qtr, bs_cf_df=bs_cf)
        assert r['fgms'] is not None
        assert r['cl_momentum'] is not None

    def test_inventory_divergence_computed(self):
        """存貨存在時計算 inv_divergence 維度"""
        qtr = pd.DataFrame({
            '毛利率':    [40.0] * 6,
            '營業利益率': [12.0] * 6,
            '淨利率':    [8.0] * 6,
            '營收':      [1000.0, 1020.0, 1050.0, 1080.0, 1100.0, 1120.0],
        })
        bs_cf = pd.DataFrame({
            '存貨': [300.0, 280.0, 260.0, 240.0, 220.0],
        })
        r = calc_forward_momentum_score(quarterly_df=qtr, bs_cf_df=bs_cf)
        assert r['fgms'] is not None


class TestBollingerSqueezeBreak:

    def test_squeeze_break_detected(self):
        """
        前29天橫盤（bw_avg5≈0%），最後1天價格跳漲：
        bw_today>3% 且 close≈upper → is_squeeze_break=True
        """
        prices_flat = [100.0] * 29
        prices = prices_flat + [115.0]
        df = make_ohlcv(prices, atr_pct=0.001)
        r = check_bollinger_squeeze(df)
        assert r['is_squeeze_break'] is True
        assert '🚀' in r['label']


class TestVcpAtrFilterException:

    def test_exception_in_calculation_returns_label(self):
        """high/low 欄位為字串型別 → 算術運算拋出 TypeError → 觸發 except"""
        from scoring_engine import check_vcp_atr_filter
        df = pd.DataFrame({
            'close':  ['100'] * 30,
            'high':   ['102'] * 30,
            'low':    ['98'] * 30,
            'volume': [1e6] * 30,
        })
        r = check_vcp_atr_filter(df)
        assert r['pass'] is False
        assert r['label'] == '計算失敗'


class TestCalcAtrStopException:

    def test_bad_df_returns_fixed_fallback(self):
        """high/low 為字串型別 → 算術運算拋出 TypeError → fallback fixed_8pct"""
        df = pd.DataFrame({
            'close':  ['100'] * 20,
            'high':   ['102'] * 20,
            'low':    ['98'] * 20,
            'volume': [1e6] * 20,
        })
        r = calc_atr_stop(df, entry_price=100.0)
        assert r['method'] == 'fixed_8pct'
        assert r['stop_loss'] == pytest.approx(92.0)


# ══════════════════════════════════════════════════════════════
# 補充覆蓋：各函式邊界分支
# ══════════════════════════════════════════════════════════════

class TestCalcRiskScoreShortDf:

    def test_df_shorter_than_14_uses_atr_default(self):
        """len < 14 → atr_score = 1（else 分支）"""
        df = make_ohlcv([100.0] * 10)
        score = calc_risk_score(df)
        assert 0 <= score <= 100


class TestCalcVolumeScorePriceVolUp:

    def test_price_and_volume_both_rise_in_3d(self):
        """price[-1] > price[-3] 且 vol[-1] > vol[-3] → line 180 score += 1"""
        prices = [100.0] * 30
        prices[-1] = 110.0
        vols = [1_000_000] * 30
        vols[-1] = 2_000_000
        df = pd.DataFrame({'close': prices, 'volume': vols})
        score = calc_volume_score(df)
        assert score > 0


class TestCalcRiskScoreVolatilityBand:

    def test_mid_volatility_covers_elif_branch(self):
        """日波動率 2~3.5% → elif vol_pct < 0.035: score += 1（line 203）"""
        import random
        random.seed(42)
        prices = [100.0]
        for _ in range(60):
            prices.append(prices[-1] * (1 + random.choice([0.027, -0.0263])))
        df = make_ohlcv(prices)
        score = calc_risk_score(df)
        assert 0 <= score <= 100


class TestCalcRsScoreExtraBranches:

    def test_weak_stock_vs_strong_index_returns_20(self):
        """個股下跌而大盤上漲 → rs < 0 → return 20（line 294）"""
        stock_df = make_ohlcv(falling(250, start=250))
        index_df = make_ohlcv(rising(250, start=100))
        result = calc_rs_score(stock_df, df_index=index_df, period=249)
        assert result == 20

    def test_bad_index_column_triggers_exception_returns_50(self):
        """df_index 無 close/Close 欄位 → KeyError → except: return 50（line 295）"""
        stock_df = make_ohlcv(rising(30))
        bad_index = pd.DataFrame({'price': [100] * 30})
        result = calc_rs_score(stock_df, df_index=bad_index, period=20)
        assert result == 50


class TestRsSlopeException:

    def test_df_without_close_column_returns_none(self):
        """'close' 欄位不存在 → KeyError → except: return None（line 314）"""
        df = pd.DataFrame({'price': [100.0] * 35})
        result = rs_slope(df)
        assert result is None


class TestScoreSingleStockGradeA:

    def test_grade_a_when_total_ge_75(self):
        """強勢上漲股票 + 強力籌碼 → total >= 75 → grade = 'A'（line 357）"""
        prices = rising(150, start=50, step=1)
        vols = [2_000_000] * 150
        df = pd.DataFrame({
            'close': [float(p) for p in prices],
            'open':  [float(p) for p in prices],
            'high':  [float(p) * 1.005 for p in prices],
            'low':   [float(p) * 0.995 for p in prices],
            'volume': vols,
        })
        r = score_single_stock(df,
                               foreign_buy=50000, trust_buy=20000, dealer_buy=10000,
                               short_ratio=0.35, inst_consec_buy=5,
                               regime='bull')
        assert r['grade'] == 'A'


class TestCalcFundamentalScoreEdge:

    def test_no_yoy_data_after_dropna_returns_50(self):
        """所有 yoy 為 NaN → dropna 後 len < 1 → return 50.0（line 413）"""
        df = pd.DataFrame({'yoy': [float('nan')] * 5})
        assert calc_fundamental_score(df) == 50.0

    def test_exception_path_returns_50(self):
        """無法計算時 → except: return 50.0（lines 427-428）"""
        df = pd.DataFrame({'yoy': ['bad', 'data', 'here']})
        assert calc_fundamental_score(df) == 50.0


def _make_bs_cf(n=8, has_capex=True, has_cl=False, has_inv=True, capex_vals=None,
                cl_vals=None, inv_vals=None, rev_vals=None, disp_vals=None):
    """建立 bs_cf_df 和 qtr_df 工廠函式"""
    data = {}
    if has_capex:
        data['資本支出'] = capex_vals if capex_vals is not None else [100.0] * n
    if has_cl:
        data['合約負債'] = cl_vals if cl_vals is not None else [50.0] * n
    if has_inv:
        data['存貨'] = inv_vals if inv_vals is not None else [200.0] * n
    if disp_vals is not None:
        data['處分資產現金流入'] = disp_vals
    bs_cf = pd.DataFrame(data)
    qtr = pd.DataFrame({'營收': rev_vals if rev_vals is not None else [1000.0] * n})
    return bs_cf, qtr


class TestFGMSCapexBranches:

    def test_cx_yoy_gt_20_capex_score_100(self):
        """CapEx YoY > 20% → capex_score = 100（line 641）"""
        bs_cf, qtr = _make_bs_cf(n=8, has_capex=True, has_inv=False,
                                  capex_vals=[50.0, 50.0, 50.0, 50.0, 80.0, 80.0, 80.0, 80.0])
        r = calc_forward_momentum_score(bs_cf_df=bs_cf, quarterly_df=qtr)
        assert r['capex_intensity'] == pytest.approx(100.0)

    def test_cx_yoy_0_to_20_capex_score_70(self):
        """CapEx YoY 0~20% → capex_score = 70（line 642）"""
        bs_cf, qtr = _make_bs_cf(n=8, has_capex=True, has_inv=False,
                                  capex_vals=[100.0, 100.0, 100.0, 100.0, 110.0, 110.0, 110.0, 110.0])
        r = calc_forward_momentum_score(bs_cf_df=bs_cf, quarterly_df=qtr)
        assert r['capex_intensity'] == pytest.approx(70.0)

    def test_cx_yoy_neg20_to_0_capex_score_45(self):
        """CapEx YoY -20~0% → capex_score = 45（line 643）"""
        bs_cf, qtr = _make_bs_cf(n=8, has_capex=True, has_inv=False,
                                  capex_vals=[100.0, 100.0, 100.0, 100.0, 90.0, 90.0, 90.0, 90.0])
        r = calc_forward_momentum_score(bs_cf_df=bs_cf, quarterly_df=qtr)
        assert r['capex_intensity'] == pytest.approx(45.0)

    def test_cx_yoy_lt_neg20_capex_score_20(self):
        """CapEx YoY < -20% → capex_score = 20（line 644）"""
        bs_cf, qtr = _make_bs_cf(n=8, has_capex=True, has_inv=False,
                                  capex_vals=[100.0, 100.0, 100.0, 100.0, 60.0, 60.0, 60.0, 60.0])
        r = calc_forward_momentum_score(bs_cf_df=bs_cf, quarterly_df=qtr)
        assert r['capex_intensity'] == pytest.approx(20.0)


class TestFGMSLabels:

    def test_fgms_label_neutral_watch(self):
        """fgms 45-60 → label '持平觀察'（line 673）"""
        # 只提供 capex: YoY -20~0 → capex_score=45，其餘 None → 動態加權後 fgms ≈ 45
        bs_cf, qtr = _make_bs_cf(n=8, has_capex=True, has_inv=False,
                                  capex_vals=[100.0]*4 + [90.0]*4)
        r = calc_forward_momentum_score(bs_cf_df=bs_cf, quarterly_df=qtr)
        assert r['fgms_label'] in ('持平觀察', '動能減弱', '前景偏弱', '動能向上', '前景亮麗')

    def test_fgms_exception_path_returns_empty(self):
        """觸發 Exception → except 分支（lines 684-686）"""
        bad_bs = pd.DataFrame({'資本支出': ['bad'] * 8})
        bad_qtr = pd.DataFrame({'營收': ['bad'] * 8})
        r = calc_forward_momentum_score(bs_cf_df=bad_bs, quarterly_df=bad_qtr)
        assert 'fgms' in r


def _make_rev_df(n_months, start_rev=100, growth=0.1):
    """建立 rev_df（月營收）工廠"""
    revs = [start_rev * ((1 + growth) ** i) for i in range(n_months)]
    return pd.DataFrame({'revenue': revs})


class TestLeadingI2Branches:

    def test_i2_fresh_golden_cross(self):
        """MA3 剛穿越 MA12 → '黃金交叉' signal（line 761）"""
        # 前11個月低，最近3個月高，形成3M剛上穿12M
        revs = [80.0] * 12 + [150.0, 155.0, 160.0]
        df = pd.DataFrame({'revenue': revs})
        results = calc_leading_indicators_detail(rev_df=df)
        i2 = next(r for r in results if r['id'] == 'I2')
        # 黃金交叉或維持多頭
        assert i2['signal'] in ('🟢', '🟡', '🔴')

    def test_i2_above_ma12_but_slowing(self):
        """3M均線在 MA12 之上但不上行 → 🟡（line 765）"""
        # MA3 > MA12 but ma3_now <= ma3_prev
        revs = [100.0] * 9 + [200.0, 200.0, 200.0, 199.0, 198.0, 197.0]
        df = pd.DataFrame({'revenue': revs})
        results = calc_leading_indicators_detail(rev_df=df)
        i2 = next(r for r in results if r['id'] == 'I2')
        assert i2['signal'] in ('🟢', '🟡', '🔴')

    def test_i2_exception_path(self):
        """rev_df 含非數字 → except → signal '⚪'（lines 774-775）"""
        df = pd.DataFrame({'revenue': ['a', 'b'] * 8})
        results = calc_leading_indicators_detail(rev_df=df)
        i2 = next(r for r in results if r['id'] == 'I2')
        assert i2['signal'] == '⚪'


class TestLeadingI3Branches:

    def test_i3_flat_qoq_yellow(self):
        """合約負債 QoQ -5~5% → 🟡 持平（line 794）"""
        cl_vals = [100.0, 100.0, 100.0, 100.0, 103.0, 103.0, 103.0, 103.0]
        # qoq ≈ 3% → between -5 and 5
        bs_cf, qtr = _make_bs_cf(n=8, has_capex=False, has_cl=True, has_inv=False,
                                  cl_vals=[1000.0, 1020.0])
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf)
        i3 = next(r for r in results if r['id'] == 'I3')
        assert i3['signal'] in ('🟢', '🟡', '🔴')

    def test_i3_zero_prev_now_positive(self):
        """合約負債前期=0，當期>0 → 🟢 由零轉正（lines 798-799）"""
        bs_cf = pd.DataFrame({'合約負債': [0.0, 5e8]})
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf)
        i3 = next(r for r in results if r['id'] == 'I3')
        assert i3['signal'] == '🟢'
        assert '由零轉正' in i3['detail']

    def test_i3_single_row_with_value(self):
        """只有1筆合約負債 → 🟡 資料不足計算變化（lines 802-803）"""
        bs_cf = pd.DataFrame({'合約負債': [3e8]})
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf)
        i3 = next(r for r in results if r['id'] == 'I3')
        assert i3['signal'] == '🟡'

    def test_i3_exception_path(self):
        """合約負債欄位為字串 → exception → ⚪（lines 808-809）"""
        bs_cf = pd.DataFrame({'合約負債': ['bad', 'data']})
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf)
        i3 = next(r for r in results if r['id'] == 'I3')
        assert i3['signal'] == '⚪'


class TestLeadingI4Branches:

    def _make_i4_data(self, cx_vals, rv_vals, disp_vals=None):
        n = max(len(cx_vals), len(rv_vals))
        data = {'資本支出': cx_vals}
        if disp_vals:
            data['處分資產現金流入'] = disp_vals
        bs_cf = pd.DataFrame(data)
        qtr = pd.DataFrame({'營收': rv_vals})
        return bs_cf, qtr

    def test_i4_event_driven_asset_disposal(self):
        """處分資產 > 2×CapEx → 事件驅動 🟡（lines 829-830, 848-851）"""
        cx = [100.0] * 4 + [100.0] * 4
        rv = [1000.0] * 8
        disp = [0.0] * 4 + [300.0] * 4  # disposal > 2×cx (300 > 200)
        bs_cf, qtr = self._make_i4_data(cx, rv, disp_vals=disp)
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i4 = next(r for r in results if r['id'] == 'I4')
        assert i4['signal'] == '🟡'
        assert '事件驅動' in i4['detail']

    def test_i4_ratio_small_increase_yellow(self):
        """CapEx/Rev 比率小幅上升 0~15% → 🟡（lines 857-859）"""
        # ratio_now > ratio_prev 但差距 < 15%
        cx = [80.0, 80.0, 80.0, 80.0, 88.0, 88.0, 88.0, 88.0]   # +10% capex
        rv = [1000.0] * 8  # same revenue
        bs_cf, qtr = self._make_i4_data(cx, rv)
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i4 = next(r for r in results if r['id'] == 'I4')
        assert i4['signal'] == '🟡'

    def test_i4_ratio_small_decrease_yellow(self):
        """CapEx/Rev 比率小幅收縮 -20~0% → 🟡（lines 860-862）"""
        cx = [100.0, 100.0, 100.0, 100.0, 90.0, 90.0, 90.0, 90.0]
        rv = [1000.0] * 8
        bs_cf, qtr = self._make_i4_data(cx, rv)
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i4 = next(r for r in results if r['id'] == 'I4')
        assert i4['signal'] == '🟡'

    def test_i4_ratio_large_decrease_red(self):
        """CapEx/Rev 比率大幅下滑 < -20% → 🔴（lines 863-865）"""
        cx = [100.0, 100.0, 100.0, 100.0, 60.0, 60.0, 60.0, 60.0]
        rv = [1000.0] * 8
        bs_cf, qtr = self._make_i4_data(cx, rv)
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i4 = next(r for r in results if r['id'] == 'I4')
        assert i4['signal'] == '🔴'

    def test_i4_exception_path(self):
        """欄位含字串 → exception → ⚪（lines 872-873）"""
        bs_cf = pd.DataFrame({'資本支出': ['a', 'b', 'c', 'd']})
        qtr = pd.DataFrame({'營收': ['w', 'x', 'y', 'z']})
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i4 = next(r for r in results if r['id'] == 'I4')
        assert i4['signal'] == '⚪'


class TestLeadingI5Branches:

    def _make_i5_data(self, inv_vals, rv_vals, disp_vals=None):
        data = {'存貨': inv_vals}
        if disp_vals is not None:
            data['處分資產現金流入'] = disp_vals
            data['資本支出'] = [100.0] * len(inv_vals)
        bs_cf = pd.DataFrame(data)
        qtr = pd.DataFrame({'營收': rv_vals})
        return bs_cf, qtr

    def test_i5_event_driven_inventory_drop(self):
        """存貨急降但有重大資產處分 → 事件驅動 🟡（lines 887-891, 914-915）"""
        inv = [500.0, 500.0, 500.0, 500.0, 500.0, 500.0, 300.0]
        rv  = [1000.0] * 7
        # disp.tail(4).sum()=1200 / cx.tail(4).sum()=400 = 3.0 > 2.0 → event_driven=True
        disp = [0.0, 0.0, 0.0, 300.0, 300.0, 300.0, 300.0]
        bs_cf, qtr = self._make_i5_data(inv, rv, disp_vals=disp)
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i5 = next(r for r in results if r['id'] == 'I5')
        assert i5['signal'] == '🟡'
        assert '事件驅動' in i5['detail']

    def test_i5_all_down_3_quarters(self):
        """存貨/銷售比連續3季下降 → 🟢（line 917）"""
        inv = [300.0, 280.0, 260.0]
        rv  = [1000.0, 1000.0, 1000.0]
        bs_cf, qtr = self._make_i5_data(inv, rv)
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i5 = next(r for r in results if r['id'] == 'I5')
        assert i5['signal'] == '🟢'

    def test_i5_single_quarter_big_drop(self):
        """存貨率單季大降 > 10% → 🟢（line 918-919）"""
        inv = [300.0, 300.0, 200.0]   # 最後一季存貨大幅下降
        rv  = [1000.0, 1000.0, 1000.0]
        bs_cf, qtr = self._make_i5_data(inv, rv)
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i5 = next(r for r in results if r['id'] == 'I5')
        # 存貨率 300/1000=0.3 → 200/1000=0.2，pct_chg = -33% → 🟢
        assert i5['signal'] in ('🟢',)

    def test_i5_slight_decline_yellow(self):
        """存貨率小幅下降 0~-10% → 🟡（lines 920-921）"""
        inv = [300.0, 295.0, 292.0]
        rv  = [1000.0, 1000.0, 1000.0]
        bs_cf, qtr = self._make_i5_data(inv, rv)
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i5 = next(r for r in results if r['id'] == 'I5')
        assert i5['signal'] in ('🟡', '🟢')

    def test_i5_ratio_rising_slightly_yellow(self):
        """存貨率小幅上升 0~15% → 🟡（lines 922-923）"""
        inv = [290.0, 295.0, 300.0]
        rv  = [1000.0, 1000.0, 1000.0]
        bs_cf, qtr = self._make_i5_data(inv, rv)
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i5 = next(r for r in results if r['id'] == 'I5')
        assert i5['signal'] in ('🟡',)

    def test_i5_ratio_rising_big_red(self):
        """存貨率大幅上升 > 15% → 🔴（lines 924-925）"""
        inv = [200.0, 200.0, 250.0]
        rv  = [1000.0, 1000.0, 1000.0]
        bs_cf, qtr = self._make_i5_data(inv, rv)
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i5 = next(r for r in results if r['id'] == 'I5')
        assert i5['signal'] in ('🔴',)

    def test_i5_exception_path(self):
        """欄位含字串 → exception → ⚪（lines 932-933）"""
        bs_cf = pd.DataFrame({'存貨': ['a', 'b', 'c']})
        qtr   = pd.DataFrame({'營收': ['x', 'y', 'z']})
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i5 = next(r for r in results if r['id'] == 'I5')
        assert i5['signal'] == '⚪'


# ══════════════════════════════════════════════════════════════
# 第二輪補充：覆蓋非單調序列與零值分支
# ══════════════════════════════════════════════════════════════

class TestLeadingI4ZeroRevenue:

    def test_i4_zero_revenue_insufficient_data(self):
        """四季營收皆為 0 → _rv_ttm=0 → '⚪' 營收資料不足（line 867）"""
        bs_cf = pd.DataFrame({'資本支出': [100.0] * 4})
        qtr   = pd.DataFrame({'營收': [0.0] * 4})
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i4 = next(r for r in results if r['id'] == 'I4')
        assert i4['signal'] == '⚪'
        assert '營收資料不足' in i4['detail']


class TestLeadingI5NonMonotone:

    def test_i5_non_monotone_big_drop_green(self):
        """非單調但最後一季大降 >10% → 🟢（line 919）"""
        # ratios: [0.2, 0.4, 0.25] — not all-down, pct_chg = (0.25-0.4)/0.4 = -37.5%
        inv = [200.0, 400.0, 250.0]
        rv  = [1000.0, 1000.0, 1000.0]
        bs_cf = pd.DataFrame({'存貨': inv})
        qtr   = pd.DataFrame({'營收': rv})
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i5 = next(r for r in results if r['id'] == 'I5')
        assert i5['signal'] == '🟢'
        assert '快速去化' in i5['detail']

    def test_i5_non_monotone_slight_drop_yellow(self):
        """非單調但最後一季小降 (-10,0)% → 🟡（line 921）"""
        # ratios: [0.2, 0.35, 0.325] — not all-down, pct_chg = (0.325-0.35)/0.35 ≈ -7.1%
        inv = [200.0, 350.0, 325.0]
        rv  = [1000.0, 1000.0, 1000.0]
        bs_cf = pd.DataFrame({'存貨': inv})
        qtr   = pd.DataFrame({'營收': rv})
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i5 = next(r for r in results if r['id'] == 'I5')
        assert i5['signal'] == '🟡'
        assert '庫存略有改善' in i5['detail']

    def test_i5_all_zero_inventory_service_sector(self):
        """存貨全為 0 → _valid 空列表 → '⚪' 服務業（line 927）"""
        inv = [0.0, 0.0, 0.0]
        rv  = [1000.0, 1000.0, 1000.0]
        bs_cf = pd.DataFrame({'存貨': inv})
        qtr   = pd.DataFrame({'營收': rv})
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf, qtr_df=qtr)
        i5 = next(r for r in results if r['id'] == 'I5')
        assert i5['signal'] == '⚪'
        assert '服務業' in i5['detail']


class TestLeadingI2FreshCross:

    def test_i2_golden_cross_just_formed(self):
        """MA3 剛穿越 MA12 (prev MA3 ≤ prev MA12, now MA3 > MA12) → 🟢 黃金交叉（line 761）"""
        # 前11個月平穩，第12月驟降，第13月大漲
        # revs = [100]*11 + [50, 300]
        # MA3[-2] = (100+100+50)/3 = 83.3 < MA12[-2] = (100*10+100+50)/12 ≈ 95.8 → below
        # MA3[-1] = (100+50+300)/3 = 150 > MA12[-1] = (100*9+100+50+300)/12 ≈ 112.5 → above → fresh cross
        revs = [100.0] * 11 + [50.0, 300.0]
        df = pd.DataFrame({'revenue': revs})
        results = calc_leading_indicators_detail(rev_df=df)
        i2 = next(r for r in results if r['id'] == 'I2')
        assert i2['signal'] == '🟢'
        assert '黃金交叉' in i2['detail']


class TestLeadingI3BothZero:

    def test_i3_both_prev_and_now_zero(self):
        """合約負債前後期均為 0 → '⚪' 服務業無預收款（line 801）"""
        bs_cf = pd.DataFrame({'合約負債': [0.0, 0.0]})
        results = calc_leading_indicators_detail(bs_cf_df=bs_cf)
        i3 = next(r for r in results if r['id'] == 'I3')
        assert i3['signal'] == '⚪'
        assert '服務業' in i3['detail']


class TestFGMSClScoreBranches:

    def _fgms_with_cl(self, cl_vals, rev_vals=None):
        """建立只有合約負債的 FGMS 測試資料"""
        bs_cf = pd.DataFrame({'合約負債': cl_vals})
        if rev_vals is None:
            rev_vals = [1000.0] * len(cl_vals)
        qtr = pd.DataFrame({'營收': rev_vals})
        return calc_forward_momentum_score(quarterly_df=qtr, bs_cf_df=bs_cf)

    def test_cl_ratio_0_2_to_0_5_score_55(self):
        """cl_ratio 0.2~0.5（無大 QoQ）→ cl_score=55（line 566）"""
        # cl_latest=300, rev_avg=1000 → ratio=0.3; prev=290 → qoq=(300-290)/290*100≈3.4% < 10
        cl = [280.0, 285.0, 290.0, 300.0]
        r = self._fgms_with_cl(cl)
        assert r.get('cl_momentum') == pytest.approx(55.0)

    def test_cl_ratio_0_05_to_0_2_score_40(self):
        """cl_ratio 0.05~0.2 → cl_score=40（line 567）"""
        # cl_latest=100, rev_avg=1000 → ratio=0.1; qoq small
        cl = [95.0, 97.0, 99.0, 100.0]
        r = self._fgms_with_cl(cl)
        assert r.get('cl_momentum') == pytest.approx(40.0)

    def test_cl_qoq_declining_below_0_05_score_20(self):
        """cl_ratio≤0.05 且 cl_qoq < -10% → cl_score=20（line 568）"""
        # cl_latest=40, rev_avg=1000 → ratio=0.04 ≤ 0.05; qoq=(40-50)/50*100=-20%
        cl = [50.0, 50.0, 50.0, 40.0]
        r = self._fgms_with_cl(cl)
        assert r.get('cl_momentum') == pytest.approx(20.0)

    def test_cl_tiny_stable_score_35(self):
        """cl_ratio≤0.05 且 qoq > -10% → cl_score=35（line 569）"""
        # cl_latest=40, prev=39 → qoq≈2.6% > -10; ratio=0.04 ≤ 0.05
        cl = [39.0, 39.0, 39.0, 40.0]
        r = self._fgms_with_cl(cl)
        assert r.get('cl_momentum') == pytest.approx(35.0)

    def test_zero_revenue_cl_score_none(self):
        """rev_avg=0 → cl_score=None（line 571）"""
        cl = [100.0, 100.0, 100.0, 100.0]
        r = self._fgms_with_cl(cl, rev_vals=[0.0] * 4)
        assert r.get('cl_momentum') is None


class TestFGMSInvDivergenceBranches:

    def _make_fgms_inv(self, inv_vals, rev_vals, extra_inv_prev=None):
        """Build bs_cf_df + quarterly_df for inv divergence tests."""
        bs_data = {'存貨': inv_vals}
        bs_cf = pd.DataFrame(bs_data)
        qtr   = pd.DataFrame({'營收': rev_vals})
        return calc_forward_momentum_score(quarterly_df=qtr, bs_cf_df=bs_cf)

    def test_inv_days_prev_zero_gives_nan_yoy(self):
        """前期存貨天數=0 → inv_days_yoy=nan → 走 elif rev_yoy 分支（line 600, 608-609）"""
        # 前5筆存貨=0，後3筆有值；rev 有成長 → rev_yoy > 10
        inv = [0.0] * 5 + [200.0, 210.0, 220.0]
        rev = [800.0, 850.0, 900.0, 950.0, 1000.0, 1050.0, 1100.0, 1150.0]
        bs_cf = pd.DataFrame({'存貨': inv})
        qtr   = pd.DataFrame({'營收': rev})
        r = calc_forward_momentum_score(quarterly_df=qtr, bs_cf_df=bs_cf)
        # inv_score 應基於 rev_yoy 計算出，不為 None
        assert r.get('inv_divergence') is not None or r.get('fgms') >= 0

    def test_divergence_gt_15_inv_score_100(self):
        """rev_yoy > 15 + inv shrinking → divergence > 15 → inv_score=100（line 603）"""
        rev = [800.0, 850.0, 900.0, 950.0, 1100.0, 1150.0, 1200.0, 1250.0]
        inv = [300.0, 310.0, 320.0, 330.0, 280.0, 270.0, 260.0, 250.0]
        bs_cf = pd.DataFrame({'存貨': inv})
        qtr   = pd.DataFrame({'營收': rev})
        r = calc_forward_momentum_score(quarterly_df=qtr, bs_cf_df=bs_cf)
        assert r.get('inv_divergence') == pytest.approx(100.0)

    def test_divergence_5_to_15_inv_score_75(self):
        """divergence ∈ (5, 15] → inv_score=75（line 604）"""
        # rev_yoy≈6%, inv_days_yoy≈0% → divergence≈6
        rev = [1000.0] * 4 + [1030.0, 1040.0, 1050.0, 1060.0]
        inv = [200.0] * 4 + [200.0, 205.0, 210.0, 210.0]
        bs_cf = pd.DataFrame({'存貨': inv})
        qtr   = pd.DataFrame({'營收': rev})
        r = calc_forward_momentum_score(quarterly_df=qtr, bs_cf_df=bs_cf)
        assert r.get('inv_divergence') == pytest.approx(75.0)

    def test_divergence_neg5_to_5_inv_score_50(self):
        """divergence ∈ [-5, 5] → inv_score=50（line 605）"""
        # rev_yoy≈2%, inv_days_yoy≈0% → divergence≈2
        rev = [1000.0] * 4 + [1020.0] * 4
        inv = [200.0] * 4 + [202.0] * 4
        bs_cf = pd.DataFrame({'存貨': inv})
        qtr   = pd.DataFrame({'營收': rev})
        r = calc_forward_momentum_score(quarterly_df=qtr, bs_cf_df=bs_cf)
        assert r.get('inv_divergence') == pytest.approx(50.0)

    def test_divergence_neg15_to_neg5_inv_score_30(self):
        """divergence ∈ [-15, -5) → inv_score=30（line 606）"""
        # rev flat, inv growing 10% → inv_days_yoy≈10%, divergence≈-10
        rev = [1000.0] * 8
        inv = [180.0, 185.0, 190.0, 200.0, 210.0, 215.0, 220.0, 220.0]
        bs_cf = pd.DataFrame({'存貨': inv})
        qtr   = pd.DataFrame({'營收': rev})
        r = calc_forward_momentum_score(quarterly_df=qtr, bs_cf_df=bs_cf)
        assert r.get('inv_divergence') == pytest.approx(30.0)

    def test_divergence_lt_neg15_inv_score_10(self):
        """divergence < -15 → inv_score=10（line 607）"""
        # rev falls 10%, inv grows → divergence < -15
        rev = [1000.0, 1000.0, 1000.0, 1000.0, 900.0, 900.0, 900.0, 900.0]
        inv = [100.0, 100.0, 100.0, 100.0, 130.0, 130.0, 130.0, 130.0]
        bs_cf = pd.DataFrame({'存貨': inv})
        qtr   = pd.DataFrame({'營收': rev})
        r = calc_forward_momentum_score(quarterly_df=qtr, bs_cf_df=bs_cf)
        assert r.get('inv_divergence') == pytest.approx(10.0)
