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
