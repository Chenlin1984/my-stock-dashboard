"""
Tests for leading_indicators.py — pure utility functions + bug regression tests.
No HTTP calls; all network-dependent functions are excluded.
"""
import sys
import types
import unittest
from datetime import date

# ── Streamlit stub ────────────────────────────────────────────────────────────
_st = types.ModuleType("streamlit")
_st.cache_data = lambda **kw: (lambda f: f)
_st.secrets = {}
sys.modules.setdefault("streamlit", _st)

import pandas as pd
from bs4 import BeautifulSoup

from leading_indicators import (
    roc_to_ymd, ymd_to_slash, ymd_to_dash, ymd_display,
    to_num, first_num, months_in_range, extract_date,
    find_data_table, expand_table_elem,
    render_leading_table,
)


# ─────────────────────────────────────────────────────────────────────────────
# roc_to_ymd
# ─────────────────────────────────────────────────────────────────────────────
class TestRocToYmd(unittest.TestCase):
    def test_8digit_passthrough(self):
        self.assertEqual(roc_to_ymd("20240401"), "20240401")

    def test_7digit_roc(self):
        # 1150401 = 民國115年4月1日 = 2026-04-01
        self.assertEqual(roc_to_ymd("1150401"), "20260401")

    def test_slash_3digit(self):
        self.assertEqual(roc_to_ymd("113/04/01"), "20240401")

    def test_slash_2digit(self):
        self.assertEqual(roc_to_ymd("99/01/05"), "20100105")

    def test_unmatched_returns_empty(self):
        self.assertEqual(roc_to_ymd("invalid"), "")

    def test_single_digit_day_zero_padded(self):
        self.assertEqual(roc_to_ymd("113/4/1"), "20240401")


# ─────────────────────────────────────────────────────────────────────────────
# ymd formatters
# ─────────────────────────────────────────────────────────────────────────────
class TestYmdFormatters(unittest.TestCase):
    def test_ymd_to_slash(self):
        self.assertEqual(ymd_to_slash("20240401"), "2024/04/01")

    def test_ymd_to_dash(self):
        self.assertEqual(ymd_to_dash("20240401"), "2024-04-01")

    def test_ymd_display(self):
        self.assertEqual(ymd_display("20240401"), "4月1日")

    def test_ymd_display_january(self):
        self.assertEqual(ymd_display("20240101"), "1月1日")


# ─────────────────────────────────────────────────────────────────────────────
# to_num
# ─────────────────────────────────────────────────────────────────────────────
class TestToNum(unittest.TestCase):
    def test_comma_stripped(self):
        self.assertEqual(to_num("43,469"), 43469.0)

    def test_plus_stripped(self):
        self.assertEqual(to_num("+1500"), 1500.0)

    def test_bracket_content_removed(self):
        # re.sub 去掉括號內容 → "" → None
        self.assertIsNone(to_num("(37,392)"))

    def test_null_strings_return_none(self):
        for v in ("", "-", "nan", "NaN", "None", "—", "--", "N/A"):
            self.assertIsNone(to_num(v), msg=f"expected None for {v!r}")

    def test_as_int_rounds_up(self):
        self.assertEqual(to_num("3.7", as_int=True), 4)

    def test_as_int_rounds_down(self):
        self.assertEqual(to_num("3.2", as_int=True), 3)

    def test_plain_float(self):
        self.assertAlmostEqual(to_num("1.5"), 1.5)

    def test_numeric_input(self):
        self.assertEqual(to_num(100), 100.0)

    def test_negative_number(self):
        self.assertEqual(to_num("-500"), -500.0)


# ─────────────────────────────────────────────────────────────────────────────
# first_num
# ─────────────────────────────────────────────────────────────────────────────
class TestFirstNum(unittest.TestCase):
    def test_plain_number(self):
        self.assertEqual(first_num("43469"), 43469)

    def test_comma_number(self):
        self.assertEqual(first_num("43,469"), 43469)

    def test_bracket_format_takes_first(self):
        # "43,469  (37,392)" → 取第一個數字 43469
        self.assertEqual(first_num("43,469  (37,392)"), 43469)

    def test_no_number_returns_none(self):
        self.assertIsNone(first_num("N/A"))

    def test_as_int_false_returns_float(self):
        result = first_num("45.5%", as_int=False)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, float)

    def test_empty_string_returns_none(self):
        self.assertIsNone(first_num(""))


# ─────────────────────────────────────────────────────────────────────────────
# months_in_range
# ─────────────────────────────────────────────────────────────────────────────
class TestMonthsInRange(unittest.TestCase):
    def test_single_month(self):
        self.assertEqual(
            months_in_range(date(2024, 3, 1), date(2024, 3, 31)),
            ["202403"]
        )

    def test_multi_month(self):
        self.assertEqual(
            months_in_range(date(2024, 1, 1), date(2024, 3, 31)),
            ["202401", "202402", "202403"]
        )

    def test_year_crossing(self):
        self.assertEqual(
            months_in_range(date(2023, 11, 1), date(2024, 2, 28)),
            ["202311", "202312", "202401", "202402"]
        )


# ─────────────────────────────────────────────────────────────────────────────
# extract_date
# ─────────────────────────────────────────────────────────────────────────────
class TestExtractDate(unittest.TestCase):
    def test_ad_slash(self):
        self.assertEqual(extract_date("2024/01/15"), "20240115")

    def test_ad_dash(self):
        self.assertEqual(extract_date("2024-04-01"), "20240401")

    def test_roc_slash(self):
        # 113/04/01 → 1911+113=2024
        self.assertEqual(extract_date("113/04/01"), "20240401")

    def test_no_match_returns_none(self):
        self.assertIsNone(extract_date("no date here"))

    def test_embedded_in_text(self):
        self.assertEqual(extract_date("查詢日期: 2024/03/15 結束"), "20240315")


# ─────────────────────────────────────────────────────────────────────────────
# find_data_table
# ─────────────────────────────────────────────────────────────────────────────
_SAMPLE_HTML = """<html><body>
<table><tr><td>導覽列</td></tr></table>
<table>
  <tr><th>外資</th><th>留倉</th><th>口數</th></tr>
  <tr><td>外資</td><td>1000</td><td>2000</td></tr>
</table>
<table>
  <tr><th>外資</th><th>投信</th><th>自營</th><th>留倉</th><th>口數</th><th>金額</th></tr>
  <tr><td>外資</td><td>投信</td><td>自營</td><td>留倉</td><td>口數</td><td>999</td></tr>
</table>
</body></html>"""

class TestFindDataTable(unittest.TestCase):
    def test_finds_matching_table(self):
        tbl = find_data_table(_SAMPLE_HTML, ["外資", "留倉"])
        self.assertIsNotNone(tbl)

    def test_no_match_returns_none(self):
        self.assertIsNone(find_data_table(_SAMPLE_HTML, ["不存在XYZ"]))

    def test_prefers_higher_score(self):
        # 第三個 table 有 外資+投信+自營+留倉+口數 共5個關鍵字命中
        tbl = find_data_table(_SAMPLE_HTML, ["外資", "投信", "自營", "留倉", "口數"])
        self.assertIn("自營", tbl.get_text())

    def test_empty_html_returns_none(self):
        self.assertIsNone(find_data_table("<html></html>", ["外資"]))


# ─────────────────────────────────────────────────────────────────────────────
# expand_table_elem
# ─────────────────────────────────────────────────────────────────────────────
class TestExpandTableElem(unittest.TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(expand_table_elem(None), [])

    def test_simple_table(self):
        html = "<table><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>"
        tbl = BeautifulSoup(html, "html.parser").find("table")
        result = expand_table_elem(tbl)
        self.assertEqual(result[0], ["A", "B"])
        self.assertEqual(result[1], ["C", "D"])

    def test_rowspan_filled(self):
        html = """<table>
            <tr><td rowspan="2">X</td><td>Y</td></tr>
            <tr><td>Z</td></tr>
        </table>"""
        tbl = BeautifulSoup(html, "html.parser").find("table")
        result = expand_table_elem(tbl)
        self.assertEqual(result[0][0], "X")
        self.assertEqual(result[1][0], "X")   # rowspan 展開
        self.assertEqual(result[1][1], "Z")

    def test_colspan_filled(self):
        html = """<table>
            <tr><td colspan="2">SPAN</td></tr>
            <tr><td>L</td><td>R</td></tr>
        </table>"""
        tbl = BeautifulSoup(html, "html.parser").find("table")
        result = expand_table_elem(tbl)
        self.assertEqual(result[0][0], "SPAN")
        self.assertEqual(result[0][1], "SPAN")   # colspan 展開

    def test_empty_table_returns_empty(self):
        html = "<table></table>"
        tbl = BeautifulSoup(html, "html.parser").find("table")
        self.assertEqual(expand_table_elem(tbl), [])


# ─────────────────────────────────────────────────────────────────────────────
# render_leading_table — Bug 2 regression (PCR 閾值 80/120)
# ─────────────────────────────────────────────────────────────────────────────
def _pcr_df(pcr_val):
    return pd.DataFrame([{
        "_date": "20240401", "日期": "4月1日", "成交量": "-",
        "外資": None, "投信": None, "自營": None,
        "外資大小": None, "前五大留倉": None, "前十大留倉": None,
        "選PCR": pcr_val,
        "外(選)": None, "未平倉口數": None, "韭菜指數": None,
    }])


class TestRenderLeadingTablePCR(unittest.TestCase):
    """PCR 顏色：< 80 → 藍(#58a6ff)；> 120 → 紅(#f85149)；80~120 → 無色"""

    def test_pcr_below_80_blue(self):
        html = render_leading_table(_pcr_df(65.0))
        self.assertIn("58a6ff", html)

    def test_pcr_above_120_red(self):
        html = render_leading_table(_pcr_df(135.0))
        self.assertIn("f85149", html)

    def test_pcr_neutral_no_data_color(self):
        # 100.0 在 80~120 之間，PCR 欄不應有顏色；其餘欄全 None
        html = render_leading_table(_pcr_df(100.0))
        self.assertNotIn("58a6ff", html)
        self.assertNotIn("f85149", html)

    def test_pcr_boundary_80_no_blue(self):
        # 剛好 80 不觸發藍色（n < 80 為假）
        html = render_leading_table(_pcr_df(80.0))
        self.assertNotIn("58a6ff", html)

    def test_pcr_boundary_120_no_red(self):
        # 剛好 120 不觸發紅色（n > 120 為假）
        html = render_leading_table(_pcr_df(120.0))
        self.assertNotIn("f85149", html)


if __name__ == "__main__":
    unittest.main()
