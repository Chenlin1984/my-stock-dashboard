"""
financial_debug_helper.py

用途：
1. 診斷台股財報 / 月營收 / 合約負債 / 固定資產 / 資本支出抓不到的原因
2. 統一欄位別名管理
3. 區分：
   - 抓取失敗
   - 查無揭露
   - 產業不適用
4. 可直接整合到 Streamlit / Colab 專案

作者：OpenAI
版本：v1.0
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests


# =========================
# 1) 欄位別名字典
# =========================

FIELD_ALIASES: Dict[str, List[str]] = {
    "contract_liabilities": [
        "合約負債",
        "合約負債－流動",
        "合約負債－非流動",
        "預收款項",
        "遞延收入",
        "Contract liabilities",
    ],
    "fixed_assets": [
        "不動產、廠房及設備",
        "不動產、廠房及設備淨額",
        "固定資產",
        "固定資產淨額",
        "Property, plant and equipment",
        "PPE",
    ],
    "capex": [
        "資本支出",
        "取得不動產、廠房及設備",
        "購置固定資產",
        "Capital expenditures",
    ],
    "revenue": [
        "營業收入合計",
        "收入合計",
        "營收",
        "revenue",
    ],
    "gross_margin": [
        "毛利率",
        "營業毛利率",
        "gross margin",
    ],
}


# =========================
# 2) 狀態定義
# =========================

STATUS_OK = "ok"
STATUS_FETCH_ERROR = "fetch_error"
STATUS_MISSING = "missing"
STATUS_NOT_APPLICABLE = "not_applicable"


# =========================
# 3) 診斷資料結構
# =========================

@dataclass
class FieldResult:
    field_name: str
    status: str
    value: Optional[float] = None
    source: str = ""
    raw_label: str = ""
    message: str = ""
    unit: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DebugReport:
    stock_id: str
    industry: str = ""
    token_ok: Optional[bool] = None
    token_message: str = ""
    fields: Dict[str, FieldResult] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)

    def add_log(self, msg: str) -> None:
        self.logs.append(msg)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stock_id": self.stock_id,
            "industry": self.industry,
            "token_ok": self.token_ok,
            "token_message": self.token_message,
            "fields": {
                k: {
                    "field_name": v.field_name,
                    "status": v.status,
                    "value": v.value,
                    "source": v.source,
                    "raw_label": v.raw_label,
                    "message": v.message,
                    "unit": v.unit,
                    "extra": v.extra,
                }
                for k, v in self.fields.items()
            },
            "logs": self.logs,
        }

    def to_dataframe(self) -> pd.DataFrame:
        rows = []
        for key, fr in self.fields.items():
            rows.append(
                {
                    "key": key,
                    "field_name": fr.field_name,
                    "status": fr.status,
                    "value": fr.value,
                    "source": fr.source,
                    "raw_label": fr.raw_label,
                    "message": fr.message,
                    "unit": fr.unit,
                }
            )
        return pd.DataFrame(rows)


# =========================
# 4) 基礎工具函式
# =========================

def safe_float(value: Any) -> Optional[float]:
    """把字串安全轉成 float，支援逗號、空白、括號負數。"""
    if value is None:
        return None

    s = str(value).strip()
    if s == "" or s.lower() in {"nan", "none", "-", "--", "na", "n/a"}:
        return None

    s = s.replace(",", "").replace(" ", "")
    # 括號負數，例如 (1234)
    if re.match(r"^\(.*\)$", s):
        s = "-" + s[1:-1]

    try:
        return float(s)
    except Exception:
        return None


def normalize_text(x: Any) -> str:
    """把欄位名稱標準化，方便做模糊比對。"""
    return str(x).strip().replace(" ", "").replace("\u3000", "")


def is_financial_industry(industry: str) -> bool:
    """判斷是否為金融 / 保險 / 銀行 / 證券類。"""
    s = normalize_text(industry)
    keys = ["金融", "保險", "銀行", "證券", "金控"]
    return any(k in s for k in keys)


def classify_missing_data(industry: str, field_key: str, value: Optional[float]) -> str:
    """把抓不到資料分類成：正常 / 不適用 / 查無揭露。"""
    if value is not None:
        return STATUS_OK

    if is_financial_industry(industry) and field_key in {"gross_margin", "fixed_assets", "capex"}:
        return STATUS_NOT_APPLICABLE

    return STATUS_MISSING


def find_value_by_alias(
    df: pd.DataFrame,
    aliases: List[str],
    scan_all_columns: bool = True,
) -> Tuple[Optional[float], str]:
    """
    從任意表格中用別名找值。
    回傳：(值, 原始欄位名稱)
    預設會把每列第一欄當欄位名，再從後面欄位找第一個可轉數字的值。
    """
    if df is None or df.empty:
        return None, ""

    for _, row in df.iterrows():
        raw_label = normalize_text(row.iloc[0])
        if any(normalize_text(a) in raw_label for a in aliases):
            if scan_all_columns:
                for i in range(1, len(row)):
                    v = safe_float(row.iloc[i])
                    if v is not None:
                        return v, str(row.iloc[0])
            else:
                if len(row) > 1:
                    v = safe_float(row.iloc[1])
                    if v is not None:
                        return v, str(row.iloc[0])
    return None, ""


def estimate_capex_from_ppe(
    current_ppe: Optional[float],
    prev_ppe: Optional[float],
    depreciation: float = 0.0
) -> Optional[float]:
    """當現金流量表沒有直接 capex 欄位時，用 PPE 變動粗估。"""
    if current_ppe is None or prev_ppe is None:
        return None
    return max(0.0, current_ppe - prev_ppe + depreciation)


# =========================
# 5) FinMind 診斷
# =========================

def test_finmind_token(token: Optional[str] = None, stock_id: str = "2330") -> Tuple[bool, str]:
    """
    測試 FinMind token 是否可用。
    預設用月營收資料集測試。
    """
    token = (token or os.environ.get("FINMIND_TOKEN", "")).strip()
    if not token:
        return False, "FINMIND_TOKEN 未設定"

    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockMonthRevenue",
        "data_id": stock_id,
        "start_date": "2024-01-01",
    }
    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        j = r.json()

        if j.get("status") == 200 and j.get("data"):
            return True, f"FinMind token 正常，取得 {len(j['data'])} 筆月營收資料"
        return False, f"FinMind 回應異常：status={j.get('status')} msg={j.get('msg', '')}"
    except Exception as e:
        return False, f"FinMind 測試失敗：{e}"


def fetch_finmind_monthly_revenue(
    stock_id: str,
    token: Optional[str] = None,
    start_date: str = "2023-01-01"
) -> Tuple[Optional[pd.DataFrame], str]:
    """抓 FinMind 月營收。"""
    token = (token or os.environ.get("FINMIND_TOKEN", "")).strip()
    if not token:
        return None, "FINMIND_TOKEN 未設定"

    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockMonthRevenue",
        "data_id": stock_id,
        "start_date": start_date,
    }
    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=20)
        r.raise_for_status()
        j = r.json()
        if j.get("status") != 200 or not j.get("data"):
            return None, f"FinMind 月營收無資料：status={j.get('status')} msg={j.get('msg', '')}"

        df = pd.DataFrame(j["data"])
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date").reset_index(drop=True), ""
    except Exception as e:
        return None, f"FinMind 月營收抓取失敗：{e}"


# =========================
# 6) HTML / 表格診斷
# =========================

def read_html_tables(url: str, sleep_sec: float = 0.0) -> Tuple[List[pd.DataFrame], str]:
    """用 pandas.read_html 讀取表格並回傳錯誤訊息。"""
    try:
        if sleep_sec > 0:
            time.sleep(sleep_sec)
        tables = pd.read_html(url)
        return tables, ""
    except Exception as e:
        return [], str(e)


def debug_goodinfo_financial_tables(stock_id: str) -> Tuple[List[pd.DataFrame], str]:
    """
    嘗試抓 Goodinfo 常見財報頁面。
    注意：Goodinfo 可能因反爬限制失敗。
    """
    url = f"https://goodinfo.tw/tw/StockFinDetail.asp?RPT_CAT=BS_M_QUAR&STOCK_ID={stock_id}"
    return read_html_tables(url, sleep_sec=1.0)


# =========================
# 7) 單欄位診斷
# =========================

def diagnose_field_from_tables(
    field_key: str,
    tables: List[pd.DataFrame],
    industry: str = "",
    source_name: str = "html_table",
) -> FieldResult:
    """從多個表格中診斷單一欄位。"""
    aliases = FIELD_ALIASES.get(field_key, [])
    if not aliases:
        return FieldResult(
            field_name=field_key,
            status=STATUS_FETCH_ERROR,
            source=source_name,
            message=f"找不到欄位別名設定：{field_key}",
        )

    for idx, tb in enumerate(tables):
        value, raw_label = find_value_by_alias(tb, aliases)
        status = classify_missing_data(industry, field_key, value)
        if value is not None:
            return FieldResult(
                field_name=field_key,
                status=status,
                value=value,
                source=source_name,
                raw_label=raw_label,
                message=f"於第 {idx} 張表找到",
            )

    status = classify_missing_data(industry, field_key, None)
    msg = "欄位未出現在已解析表格中"
    if status == STATUS_NOT_APPLICABLE:
        msg = "產業不適用，可跳過"
    return FieldResult(
        field_name=field_key,
        status=status,
        source=source_name,
        message=msg,
    )


# =========================
# 8) 整體診斷主流程
# =========================

def build_financial_debug_report(
    stock_id: str,
    industry: str = "",
    finmind_token: Optional[str] = None,
    check_fields: Optional[List[str]] = None,
) -> DebugReport:
    """
    建立完整診斷報告。
    預設檢查：
    - contract_liabilities
    - fixed_assets
    - capex
    - revenue
    - gross_margin
    """
    if check_fields is None:
        check_fields = [
            "contract_liabilities",
            "fixed_assets",
            "capex",
            "revenue",
            "gross_margin",
        ]

    report = DebugReport(stock_id=stock_id, industry=industry)

    # 1) FinMind Token 健檢
    token_ok, token_msg = test_finmind_token(finmind_token, stock_id="2330")
    report.token_ok = token_ok
    report.token_message = token_msg
    report.add_log(f"[FinMind] {token_msg}")

    # 2) Goodinfo 財報表格測試
    tables, err = debug_goodinfo_financial_tables(stock_id)
    if err:
        report.add_log(f"[Goodinfo] 讀表失敗：{err}")
    else:
        report.add_log(f"[Goodinfo] 成功讀到 {len(tables)} 張表")

    # 3) 各欄位逐一診斷
    for field_key in check_fields:
        if tables:
            fr = diagnose_field_from_tables(
                field_key=field_key,
                tables=tables,
                industry=industry,
                source_name="Goodinfo",
            )
        else:
            status = classify_missing_data(industry, field_key, None)
            msg = "Goodinfo 表格抓取失敗"
            if status == STATUS_NOT_APPLICABLE:
                msg = "產業不適用，可跳過"
            fr = FieldResult(
                field_name=field_key,
                status=status,
                source="Goodinfo",
                message=msg,
            )

        report.fields[field_key] = fr

    # 4) 月營收用 FinMind 再獨立檢查一次
    rev_df, rev_err = fetch_finmind_monthly_revenue(stock_id, finmind_token)
    if rev_df is not None and not rev_df.empty:
        report.fields["monthly_revenue"] = FieldResult(
            field_name="monthly_revenue",
            status=STATUS_OK,
            value=float(len(rev_df)),
            source="FinMind",
            raw_label="TaiwanStockMonthRevenue",
            message=f"月營收資料正常，共 {len(rev_df)} 筆",
            extra={
                "latest_date": str(rev_df["date"].max()) if "date" in rev_df.columns else "",
                "columns": list(rev_df.columns),
            },
        )
    else:
        report.fields["monthly_revenue"] = FieldResult(
            field_name="monthly_revenue",
            status=STATUS_FETCH_ERROR if report.token_ok is False else STATUS_MISSING,
            source="FinMind",
            message=rev_err or "月營收無資料",
        )

    return report


# =========================
# 9) Streamlit 顯示輔助
# =========================

def status_to_ui_text(status: str) -> str:
    """把內部狀態轉成前端顯示文字。"""
    mapping = {
        STATUS_OK: "正常",
        STATUS_FETCH_ERROR: "抓取失敗",
        STATUS_MISSING: "查無揭露",
        STATUS_NOT_APPLICABLE: "產業不適用",
    }
    return mapping.get(status, status)


def status_to_color(status: str) -> str:
    """給前端簡易顏色提示。"""
    mapping = {
        STATUS_OK: "green",
        STATUS_FETCH_ERROR: "red",
        STATUS_MISSING: "orange",
        STATUS_NOT_APPLICABLE: "gray",
    }
    return mapping.get(status, "blue")


# =========================
# 10) 測試執行
# =========================

if __name__ == "__main__":
    # 範例：以 2330 測試
    rep = build_financial_debug_report(
        stock_id="2330",
        industry="半導體",
        finmind_token=os.environ.get("FINMIND_TOKEN", ""),
    )

    print("=== Debug Report ===")
    print(rep.to_dataframe())
    print("\n=== Logs ===")
    for log in rep.logs:
        print(log)
