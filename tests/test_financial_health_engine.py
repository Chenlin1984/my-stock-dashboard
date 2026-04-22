"""
Tests for financial_health_engine.py — PR-introduced branches.
Covers _no_ai_survival (B項 logic) and _no_ai_financial_structure (is_finance + debt fallback).
"""
import sys
import types
import unittest

# ── Minimal Streamlit stub so financial_health_engine can import ──────────────
_st = types.ModuleType("streamlit")
_st.cache_data = lambda **kw: (lambda f: f)
_st.secrets = {}
sys.modules.setdefault("streamlit", _st)

# requests is a real dep; if missing the import will fail visibly
from financial_health_engine import (  # noqa: E402
    _no_ai_financial_structure,
    _no_ai_survival,
)


# ─────────────────────────────────────────────────────────────────────────────
# _no_ai_survival — B項 現金流量允當比率
# ─────────────────────────────────────────────────────────────────────────────
class TestNoAiSurvivalBItem(unittest.TestCase):
    """B項: 現金流量允當比率 (single-quarter estimate)"""

    def _get_rule(self, fd: dict) -> dict:
        return _no_ai_survival(fd)["Survival_Module"]["Rule_100_100_10"]

    # ── B項 Pass path: b_val >= 100 ───────────────────────────────────────
    def test_b_item_pass_when_ocf_covers_denom(self):
        fd = {
            "OCF(千)": 500,
            "流動負債(千)": 200,
            "資本支出(千)": 100,
            "存貨(千)": 150,
            "存貨前期(千)": 100,   # inv_inc = 50
            "現金股利(千)": 50,    # b_denom = 100+50+50 = 200; b_val = 500/200*100 = 250 → Pass
        }
        rule = self._get_rule(fd)
        self.assertIn("250.0%(1Q估)", rule["Cash_Flow_Adequacy"])
        self.assertEqual(rule["Status"], "Pass")

    # ── B項 Fail path: b_val < 100 ────────────────────────────────────────
    def test_b_item_fail_when_ocf_below_denom(self):
        fd = {
            "OCF(千)": 50,
            "流動負債(千)": 200,
            "資本支出(千)": 200,
            "存貨(千)": 100,
            "存貨前期(千)": 0,    # inv_inc = 100; b_denom = 200+100 = 300; b_val = 50/300*100 ≈ 16.7 → Fail
            "現金股利(千)": 0,
        }
        rule = self._get_rule(fd)
        self.assertIn("%(1Q估)", rule["Cash_Flow_Adequacy"])
        self.assertEqual(rule["Status"], "Fail")

    # ── B項 N/A path: b_denom == 0 ────────────────────────────────────────
    def test_b_item_na_when_denom_zero(self):
        fd = {
            "OCF(千)": 300,
            "流動負債(千)": 200,
            "資本支出(千)": 0,
            "存貨(千)": 0,
            "存貨前期(千)": 0,
            "現金股利(千)": 0,    # b_denom = 0 → N/A
        }
        rule = self._get_rule(fd)
        self.assertEqual(rule["Cash_Flow_Adequacy"], "N/A")

    # ── inv_inc clamped to 0 when inv < inv_p ─────────────────────────────
    def test_b_item_inv_decrease_clamped_to_zero(self):
        fd = {
            "OCF(千)": 300,
            "流動負債(千)": 200,
            "資本支出(千)": 100,
            "存貨(千)": 80,
            "存貨前期(千)": 200,  # inv_inc = max(80-200, 0) = 0; b_denom = 100; b_val = 300
            "現金股利(千)": 0,
        }
        rule = self._get_rule(fd)
        self.assertIn("300.0%(1Q估)", rule["Cash_Flow_Adequacy"])

    # ── B項 Fail cascades to rule_st="Fail" ───────────────────────────────
    def test_b_item_fail_propagates_to_rule_status(self):
        fd = {
            "OCF(千)": 10,
            "流動負債(千)": 500,  # a_val = 2.0 → Fail
            "資本支出(千)": 200,
            "存貨(千)": 0,
            "存貨前期(千)": 0,
            "現金股利(千)": 0,   # b_denom = 200; b_val = 5 → Fail
        }
        rule = self._get_rule(fd)
        self.assertEqual(rule["Status"], "Fail")

    # ── All items N/A → rule_st="Pass" (no data is not a fail) ───────────
    def test_all_na_gives_pass(self):
        fd = {
            "OCF(千)": 0,
            "流動負債(千)": 0,   # a → N/A
            "資本支出(千)": 0,
            "存貨(千)": 0,
            "存貨前期(千)": 0,
            "現金股利(千)": 0,   # b → N/A
            "固定資產(千)": 0,
            "長期投資(千)": 0,   # c → N/A
        }
        rule = self._get_rule(fd)
        self.assertEqual(rule["Status"], "Pass")


# ─────────────────────────────────────────────────────────────────────────────
# _no_ai_financial_structure — is_finance + debt fallback
# ─────────────────────────────────────────────────────────────────────────────
class TestNoAiFinancialStructureIsFinance(unittest.TestCase):
    """is_finance flag: skip normal debt ratio thresholds."""

    def _get_debt(self, fd: dict) -> dict:
        return _no_ai_financial_structure(fd)["Financial_Structure_Module"]["Debt_Ratio"]

    # ── is_finance=True, debt==0 → "N/A (金融特許行業)" ──────────────────
    def test_is_finance_debt_zero_shows_na(self):
        fd = {"is_finance": True, "負債比率(%)": 0}
        debt = self._get_debt(fd)
        self.assertEqual(debt["Status"], "N/A")
        self.assertIn("金融特許行業", debt["Value"])

    # ── is_finance=True, debt>0 → shows actual % with 金融業 label ────────
    def test_is_finance_debt_nonzero_shows_pct(self):
        fd = {"is_finance": True, "負債比率(%)": 85.0}
        debt = self._get_debt(fd)
        self.assertEqual(debt["Status"], "N/A")
        self.assertIn("85.0%", debt["Value"])
        self.assertIn("金融業", debt["Value"])

    # ── is_finance=False, debt provided → normal threshold logic ──────────
    def test_non_finance_debt_pass(self):
        fd = {"is_finance": False, "負債比率(%)": 45.0}
        debt = self._get_debt(fd)
        self.assertEqual(debt["Status"], "Pass")

    def test_non_finance_debt_warning(self):
        fd = {"is_finance": False, "負債比率(%)": 65.0}
        debt = self._get_debt(fd)
        self.assertEqual(debt["Status"], "Warning")

    def test_non_finance_debt_fail(self):
        fd = {"is_finance": False, "負債比率(%)": 75.0}
        debt = self._get_debt(fd)
        self.assertEqual(debt["Status"], "Fail")


class TestNoAiFinancialStructureDebtFallback(unittest.TestCase):
    """Debt ratio fallback from raw balance sheet fields when 負債比率(%)==0."""

    def _get_module(self, fd: dict) -> dict:
        return _no_ai_financial_structure(fd)["Financial_Structure_Module"]

    # ── Fallback via 總負債 + 總資產 ──────────────────────────────────────
    def test_fallback_via_total_liab_and_assets(self):
        fd = {
            "is_finance": False,
            "負債比率(%)": 0,
            "總負債(千)": 400,
            "總資產(千)": 1000,   # expected debt = 40.0%
        }
        module = self._get_module(fd)
        self.assertEqual(module["Debt_Ratio"]["Status"], "Pass")
        self.assertIn("40.0%", module["Debt_Ratio"]["Value"])

    # ── Fallback via 流動負債 only (總負債 absent) ─────────────────────────
    def test_fallback_via_current_liab_and_assets(self):
        fd = {
            "is_finance": False,
            "負債比率(%)": 0,
            "總負債(千)": 0,
            "流動負債(千)": 300,
            "總資產(千)": 1000,   # expected debt = 30.0%
        }
        module = self._get_module(fd)
        self.assertEqual(module["Debt_Ratio"]["Status"], "Pass")
        self.assertIn("30.0%", module["Debt_Ratio"]["Value"])

    # ── IFRS fallback: 總資產=0, use equity+liab ──────────────────────────
    def test_fallback_ifrs_equity_plus_liab(self):
        fd = {
            "is_finance": False,
            "負債比率(%)": 0,
            "總資產(千)": 0,
            "總負債(千)": 600,
            "股東權益(千)": 400,  # _eff_assets = 400+600 = 1000; debt = 60%
        }
        module = self._get_module(fd)
        # 60% is the boundary; debt<60 → Pass, debt==60 → Warning
        self.assertIn(module["Debt_Ratio"]["Status"], ("Pass", "Warning"))
        self.assertIn("60.0%", module["Debt_Ratio"]["Value"])

    # ── lt_liab derived from _tl - _cl when lt_liab==0 and _tl > _cl ─────
    def test_lt_liab_derived_from_tl_minus_cl(self):
        fd = {
            "is_finance": False,
            "負債比率(%)": 0,
            "總負債(千)": 500,
            "流動負債(千)": 200,  # lt_liab = 500-200 = 300
            "總資產(千)": 1000,
            "固定資產(千)": 400,
            "股東權益(千)": 500,  # lt_ratio = (500+300)/400 = 200% → Pass
        }
        module = self._get_module(fd)
        lt = module["Long_Term_Funding_Ratio"]
        self.assertEqual(lt["Status"], "Pass")

    # ── No usable data → debt stays 0 → "N/A (負債資料不足)" ─────────────
    def test_fallback_no_data_shows_na(self):
        fd = {"is_finance": False, "負債比率(%)": 0}
        module = self._get_module(fd)
        self.assertEqual(module["Debt_Ratio"]["Status"], "N/A")
        self.assertIn("負債資料不足", module["Debt_Ratio"]["Value"])

    # ── Fallback computes debt > 70 → Fail ────────────────────────────────
    def test_fallback_high_debt_shows_fail(self):
        fd = {
            "is_finance": False,
            "負債比率(%)": 0,
            "總負債(千)": 800,
            "總資產(千)": 1000,   # debt = 80% → Fail
        }
        module = self._get_module(fd)
        self.assertEqual(module["Debt_Ratio"]["Status"], "Fail")


if __name__ == "__main__":
    unittest.main()
