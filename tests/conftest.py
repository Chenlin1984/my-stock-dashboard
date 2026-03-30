"""
共用測試夾具 (Fixtures)
提供 bull_df / bear_df / short_df / minimal_df 等標準 OHLCV DataFrame。
"""
import sys
import os

# 確保專案根目錄在 Python 路徑中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd


def _make_ohlcv(prices, atr_pct=0.01, volumes=None):
    """從收盤價列表建立最小 OHLCV DataFrame。
    high = close * (1 + atr_pct), low = close * (1 - atr_pct)
    """
    n = len(prices)
    return pd.DataFrame({
        "close":  [float(p) for p in prices],
        "open":   [float(p) for p in prices],
        "high":   [float(p) * (1 + atr_pct) for p in prices],
        "low":    [float(p) * (1 - atr_pct) for p in prices],
        "volume": volumes if volumes is not None else [1_000_000] * n,
    })


@pytest.fixture
def bull_df():
    """130 天穩定上漲序列（100→229）。所有 MA 趨勢條件均應成立。"""
    prices = [float(100 + i) for i in range(130)]
    return _make_ohlcv(prices, atr_pct=0.01)


@pytest.fixture
def bear_df():
    """130 天穩定下跌序列（229→100）。所有 MA 趨勢條件均不成立。"""
    prices = [float(229 - i) for i in range(130)]
    return _make_ohlcv(prices, atr_pct=0.01)


@pytest.fixture
def short_df():
    """59 天 DataFrame——不足以計算趨勢分數（需 >=60）。"""
    prices = [float(100 + i) for i in range(59)]
    return _make_ohlcv(prices)


@pytest.fixture
def minimal_df():
    """恰好 20 天 DataFrame——大多數評分函數的最小有效輸入。"""
    prices = [float(100 + i) for i in range(20)]
    return _make_ohlcv(prices)
