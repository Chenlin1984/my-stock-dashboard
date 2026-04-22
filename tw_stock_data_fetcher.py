"""
tw_stock_data_fetcher.py — 台股財報抓取模組（Proxy-aware）

強制走 NAS Proxy 路由，支援 Goodinfo / MOPS 備援。
與 data_loader.fetch_fin_data() 回傳格式相容。
"""

from __future__ import annotations

import random
import time
from typing import Any

import pandas as pd
import requests
import streamlit as st
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─────────────────────────────────────────────
# §1 Constants
# ─────────────────────────────────────────────
CACHE_TTL_SEC = 86400 * 3   # 3 days
_CONNECT_TIMEOUT = 10
_READ_TIMEOUT = 30
_RETRY_TOTAL = 3
_RETRY_BACKOFF = 1.5
_RETRY_STATUS = [429, 503, 504]

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

# ─────────────────────────────────────────────
# §2 Field Aliases
# ─────────────────────────────────────────────
FIELD_ALIASES: dict[str, list[str]] = {
    # Balance Sheet
    "現金及約當現金": ["現金及約當現金", "Cash and Cash Equivalents", "現金", "現金及銀行存款"],
    "應收帳款": [
        "應收帳款淨額", "應收帳款", "AccountsReceivable",
        "合約資產", "工程應收款", "應收帳款及合約資產", "應收票據及應收帳款",
    ],
    "存貨": ["存貨", "Inventory", "存貨淨額", "商品存貨"],
    "流動資產": ["流動資產", "流動資產合計", "CurrentAssets", "總流動資產"],
    "非流動資產": ["非流動資產", "非流動資產合計", "NonCurrentAssets"],
    "總資產": ["總資產", "資產合計", "TotalAssets", "資產總計"],
    "流動負債": ["流動負債", "流動負債合計", "CurrentLiabilities", "總流動負債"],
    "非流動負債": ["非流動負債", "非流動負債合計", "NonCurrentLiabilities"],
    "總負債": ["總負債", "負債合計", "TotalLiabilities", "負債總計"],
    "股東權益": ["股東權益合計", "權益合計", "TotalEquity", "股東權益總額"],
    "保留盈餘": ["保留盈餘", "RetainedEarnings", "累積盈虧", "未分配盈餘"],
    "合約負債": ["合約負債", "ContractLiabilities", "預收款項", "合約負債-流動"],
    # Income Statement
    "營業收入": ["營業收入", "Revenue", "營業收入淨額", "收入合計"],
    "營業成本": ["營業成本", "CostOfRevenue", "銷售成本", "製造成本"],
    "毛利": ["毛利", "GrossProfit", "毛利額"],
    "營業費用": ["營業費用", "OperatingExpenses", "銷管研費用"],
    "營業利益": ["營業利益", "OperatingIncome", "營業利潤"],
    "稅前淨利": ["稅前淨利", "IncomeBefore Tax", "稅前損益"],
    "淨利": ["淨利", "NetIncome", "本期淨利", "稅後淨利"],
    "EPS": ["EPS", "BasicEPS", "每股盈餘", "稀釋每股盈餘"],
    # Cash Flow Statement
    "營業現金流": ["營業活動現金流量", "OCF", "來自營業活動之現金流量", "OperatingCashFlow"],
    "投資現金流": ["投資活動現金流量", "InvestingCashFlow", "用於投資活動之現金流量"],
    "融資現金流": ["籌資活動現金流量", "FinancingCashFlow", "來自籌資活動之現金流量"],
    "資本支出": [
        "資本支出", "CapEx", "AcquisitionOfPropertyPlantAndEquipment",
        "取得不動產、廠房及設備", "購置不動產、廠房及設備",
    ],
    "股利支付": ["支付現金股利", "DividendsPaid", "支付股利"],
}

# ─────────────────────────────────────────────
# §3 Proxy Config
# ─────────────────────────────────────────────
def _load_proxy_config() -> dict[str, str] | None:
    """Read proxy settings from Streamlit Secrets; return None if absent."""
    try:
        secrets = st.secrets
        host = secrets.get("PROXY_HOST", "")
        port = secrets.get("PROXY_PORT", "")
        if not host or not port:
            return None
        user = secrets.get("PROXY_USER", "")
        passwd = secrets.get("PROXY_PASS", "")
        auth = f"{user}:{passwd}@" if user else ""
        url = f"http://{auth}{host}:{port}"
        return {"http": url, "https": url}
    except Exception:
        return None


# ─────────────────────────────────────────────
# §4 Session Builder
# ─────────────────────────────────────────────
def build_proxy_session() -> requests.Session:
    """Build a requests.Session with retry adapter and proxy (if configured)."""
    session = requests.Session()
    retry = Retry(
        total=_RETRY_TOTAL,
        backoff_factor=_RETRY_BACKOFF,
        status_forcelist=_RETRY_STATUS,
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    proxies = _load_proxy_config()
    if proxies:
        session.proxies.update(proxies)
    return session


def _random_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


# ─────────────────────────────────────────────
# §5 Proxy GET / POST with manual backoff
# ─────────────────────────────────────────────
def proxy_get(
    session: requests.Session,
    url: str,
    params: dict | None = None,
    **kwargs: Any,
) -> requests.Response | None:
    timeout = (_CONNECT_TIMEOUT, _READ_TIMEOUT)
    for attempt in range(_RETRY_TOTAL):
        try:
            resp = session.get(url, params=params, headers=_random_headers(),
                               timeout=timeout, **kwargs)
            if resp.status_code == 403:
                wait = _RETRY_BACKOFF ** attempt
                time.sleep(wait)
                continue
            return resp
        except requests.RequestException:
            if attempt < _RETRY_TOTAL - 1:
                time.sleep(_RETRY_BACKOFF ** attempt)
    return None


def proxy_post(
    session: requests.Session,
    url: str,
    data: dict | None = None,
    **kwargs: Any,
) -> requests.Response | None:
    timeout = (_CONNECT_TIMEOUT, _READ_TIMEOUT)
    for attempt in range(_RETRY_TOTAL):
        try:
            resp = session.post(url, data=data, headers=_random_headers(),
                                timeout=timeout, **kwargs)
            if resp.status_code in (403, 503):
                wait = _RETRY_BACKOFF ** attempt
                time.sleep(wait)
                continue
            return resp
        except requests.RequestException:
            if attempt < _RETRY_TOTAL - 1:
                time.sleep(_RETRY_BACKOFF ** attempt)
    return None


# ─────────────────────────────────────────────
# §6 Fuzzy Field Lookup
# ─────────────────────────────────────────────
def fuzzy_get(data: dict, field: str, default: float = 0.0) -> float:
    """Look up a financial field using FIELD_ALIASES; exact match first."""
    aliases = FIELD_ALIASES.get(field, [field])
    for alias in aliases:
        val = data.get(alias)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return default


def fuzzy_get_from_df(df: pd.DataFrame, field: str, default: float = 0.0) -> float:
    """Look up a field from a DataFrame column set using FIELD_ALIASES."""
    aliases = FIELD_ALIASES.get(field, [field])
    # Exact match
    for alias in aliases:
        if alias in df.columns:
            val = df[alias].dropna()
            if not val.empty:
                try:
                    return float(val.iloc[-1])
                except (TypeError, ValueError):
                    continue
    # Contains match (substring)
    for alias in aliases:
        matched = [c for c in df.columns if alias in c]
        for col in matched:
            val = df[col].dropna()
            if not val.empty:
                try:
                    return float(val.iloc[-1])
                except (TypeError, ValueError):
                    continue
    return default


# ─────────────────────────────────────────────
# §7 HTML Table Parser (Goodinfo)
# ─────────────────────────────────────────────
def _detect_quarter_cols(headers: list[str]) -> list[int]:
    """Return column indices that look like quarterly periods (e.g. '2024Q1')."""
    import re
    pattern = re.compile(r"\d{4}Q[1-4]")
    return [i for i, h in enumerate(headers) if pattern.search(h)]


def parse_goodinfo_table(html: str, table_id: str = "") -> pd.DataFrame:
    """
    Parse a Goodinfo financial table HTML into a DataFrame.
    Rows = fields; Columns = quarters.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"id": table_id}) if table_id else soup.find("table")
    if table is None:
        return pd.DataFrame()
    rows = table.find_all("tr")
    if len(rows) < 2:
        return pd.DataFrame()

    headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]
    quarter_idx = _detect_quarter_cols(headers)
    if not quarter_idx:
        return pd.DataFrame()

    records: dict[str, list] = {headers[i]: [] for i in quarter_idx}
    field_names: list[str] = []

    for row in rows[1:]:
        cells = [td.get_text(strip=True) for td in row.find_all(["th", "td"])]
        if not cells:
            continue
        field_name = cells[0]
        field_names.append(field_name)
        for i in quarter_idx:
            raw = cells[i] if i < len(cells) else ""
            raw = raw.replace(",", "").replace("(", "-").replace(")", "")
            try:
                records[headers[i]].append(float(raw))
            except ValueError:
                records[headers[i]].append(None)

    df = pd.DataFrame(records, index=field_names)
    return df


# ─────────────────────────────────────────────
# §8 Goodinfo Fetcher
# ─────────────────────────────────────────────
_GOODINFO_BASE = "https://goodinfo.tw/tw"

def _goodinfo_url(stock_id: str, report: str) -> str:
    report_map = {
        "BS": "BALANCE_SHEET",
        "IS": "INCOME_STATEMENT",
        "CF": "CASH_FLOW",
    }
    code = report_map.get(report, report)
    return f"{_GOODINFO_BASE}/StockFinDetail.asp?STOCK_ID={stock_id}&REPORT_TYPE={code}&RPT_TIME=QS"


def fetch_goodinfo_financials(
    stock_id: str,
    session: requests.Session | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Fetch BS/IS/CF quarterly DataFrames from Goodinfo.
    Returns dict with keys 'BS', 'IS', 'CF'; empty DataFrames on failure.
    """
    if session is None:
        session = build_proxy_session()

    result: dict[str, pd.DataFrame] = {"BS": pd.DataFrame(), "IS": pd.DataFrame(), "CF": pd.DataFrame()}
    for report_type in ("BS", "IS", "CF"):
        url = _goodinfo_url(stock_id, report_type)
        resp = proxy_get(session, url)
        if resp is None or resp.status_code != 200:
            continue
        try:
            df = parse_goodinfo_table(resp.text)
            if not df.empty:
                result[report_type] = df
        except Exception:
            continue
    return result


# ─────────────────────────────────────────────
# §9 MOPS Backup Fetcher
# ─────────────────────────────────────────────
_MOPS_URL = "https://mops.twse.com.tw/mops/web/ajax_t164sb03"

def fetch_mops_financials(
    stock_id: str,
    year: int,
    season: int,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """
    Fetch single-quarter financial statements from MOPS via POST.
    season: 1=Q1, 2=Q2, 3=Q3, 4=Q4.
    Returns raw DataFrame (all fields as rows); empty on failure.
    """
    if session is None:
        session = build_proxy_session()
    payload = {
        "encodeURIComponent": "1",
        "step": "1",
        "firstin": "1",
        "off": "1",
        "keyword4": "",
        "code1": "",
        "TYPEK2": "",
        "checkbtn": "",
        "queryName": "co_id",
        "inpuType": "co_id",
        "TYPEK": "all",
        "isnew": "false",
        "co_id": stock_id,
        "year": str(year - 1911),   # 民國年
        "season": f"{season:02d}",
    }
    resp = proxy_post(session, _MOPS_URL, data=payload)
    if resp is None or resp.status_code != 200:
        return pd.DataFrame()
    try:
        tables = pd.read_html(resp.text, flavor="lxml")
        return tables[0] if tables else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────
# §10 Metric Calculator
# ─────────────────────────────────────────────
def calc_financial_metrics(
    bs: pd.DataFrame,
    inc: pd.DataFrame,
    cf: pd.DataFrame,
    is_finance: bool = False,
) -> dict[str, Any]:
    """
    Compute standardised financial metrics compatible with
    data_loader.fetch_fin_data() return format.
    All monetary values are in thousands (千元).
    """
    def _g(df: pd.DataFrame, field: str) -> float:
        return fuzzy_get_from_df(df, field)

    rev = _g(inc, "營業收入")
    gross = _g(inc, "毛利")
    op_inc = _g(inc, "營業利益")
    net_inc = _g(inc, "淨利")
    eps = _g(inc, "EPS")

    total_assets = _g(bs, "總資產")
    cur_assets = _g(bs, "流動資產")
    non_cur_assets = _g(bs, "非流動資產")
    total_liab = _g(bs, "總負債")
    cur_liab = _g(bs, "流動負債")
    equity = _g(bs, "股東權益")
    cash = _g(bs, "現金及約當現金")
    inv = _g(bs, "存貨")
    ar = _g(bs, "應收帳款")
    retained = _g(bs, "保留盈餘")
    contract_liab = _g(bs, "合約負債")

    ocf = _g(cf, "營業現金流")
    capex = abs(_g(cf, "資本支出"))
    div = abs(_g(cf, "股利支付"))

    # Derived ratios
    gross_margin = round(gross / rev * 100, 2) if rev else 0.0
    op_margin = round(op_inc / rev * 100, 2) if rev else 0.0
    net_margin = round(net_inc / rev * 100, 2) if rev else 0.0
    debt_ratio = round(total_liab / total_assets * 100, 2) if total_assets else 0.0
    current_ratio = round(cur_assets / cur_liab, 2) if cur_liab else 0.0
    roe = round(net_inc / equity * 100, 2) if equity else 0.0

    return {
        # Revenue & Profit (千元)
        "營業收入(千)": rev,
        "毛利(千)": gross,
        "營業利益(千)": op_inc,
        "稅後淨利(千)": net_inc,
        "EPS": eps,
        # Balance Sheet (千元)
        "總資產(千)": total_assets,
        "流動資產(千)": cur_assets,
        "非流動資產(千)": non_cur_assets,
        "總負債(千)": total_liab,
        "流動負債(千)": cur_liab,
        "股東權益(千)": equity,
        "現金(千)": cash,
        "存貨(千)": inv,
        "應收帳款(千)": ar,
        "保留盈餘(千)": retained,
        "合約負債(千)": contract_liab,
        # Cash Flow (千元)
        "營業現金流(千)": ocf,
        "資本支出(千)": capex,
        "股利支付(千)": div,
        # Ratios (%)
        "毛利率(%)": gross_margin,
        "營益率(%)": op_margin,
        "淨利率(%)": net_margin,
        "負債比率(%)": debt_ratio,
        "流動比率": current_ratio,
        "ROE(%)": roe,
        # Flags
        "is_finance": is_finance,
        "source": "tw_stock_data_fetcher",
    }


# ─────────────────────────────────────────────
# §11 Cached Fetcher Factory
# ─────────────────────────────────────────────
def _make_cached_fetcher():
    @st.cache_data(ttl=CACHE_TTL_SEC, show_spinner=False)
    def _fetch(stock_id: str, is_finance: bool = False) -> dict[str, Any]:
        """
        Fetch Taiwan stock financials via Goodinfo (proxy-aware).
        Falls back to MOPS for the most recent quarter if Goodinfo fails.
        Compatible with data_loader.fetch_fin_data() return format.
        """
        session = build_proxy_session()

        # Primary: Goodinfo
        dfs = fetch_goodinfo_financials(stock_id, session)
        bs, inc, cf = dfs["BS"], dfs["IS"], dfs["CF"]

        # Fallback: MOPS for current quarter (rough estimate)
        if bs.empty and inc.empty:
            import datetime
            now = datetime.datetime.now()
            year = now.year
            season = (now.month - 1) // 3 + 1
            mops_df = fetch_mops_financials(stock_id, year, season, session)
            if not mops_df.empty:
                # MOPS returns raw rows; attempt minimal extraction
                inc = mops_df
        if bs.empty and inc.empty and cf.empty:
            return {"error": "all_sources_failed", "is_finance": is_finance}

        return calc_financial_metrics(bs, inc, cf, is_finance=is_finance)

    return _fetch


# ─────────────────────────────────────────────
# §12 Public API
# ─────────────────────────────────────────────
fetch_tw_financials = _make_cached_fetcher()


# ─────────────────────────────────────────────
# §12.5  5年期現金流量允當比率（B 項精確版）
# ─────────────────────────────────────────────
_CACHE_7D = 86400 * 7

@st.cache_data(ttl=_CACHE_7D, show_spinner=False)
def fetch_5_years_cash_flow(stock_code: str, token: str = "") -> dict:
    """
    抓取 5 年期現金流量允當比率（100/100/10 法則 B 項）
    資料源：FinMind TaiwanStockCashFlowsStatement 年度報表（12月）
    Proxy-aware；7 天快取。

    回傳 dict:
      ratio      : float  5年允當比率(%)；None 表示資料不足
      label      : str    顯示用文字
      status     : str    "ok" / "insufficient_data" / "error"
      years      : int    實際取得年份數
      ocf_5y     : float  5年 OCF 加總（千）
      capex_5y   : float  5年資本支出加總（千，絕對值）
      inv_inc_5y : float  5年存貨增加額加總（千，僅正值）
      div_5y     : float  5年現金股利加總（千，絕對值）
      denom_5y   : float  5年分母合計（千）
    """
    import datetime
    import os

    _tok = token or os.environ.get("FINMIND_TOKEN", "")
    _empty = {
        "status": "error", "ratio": None, "label": "資料不足",
        "years": 0, "ocf_5y": 0, "capex_5y": 0,
        "inv_inc_5y": 0, "div_5y": 0, "denom_5y": 0,
    }

    try:
        today  = datetime.date.today()
        start  = today.replace(year=today.year - 6).strftime("%Y-%m-%d")
        end    = today.strftime("%Y-%m-%d")
        params = {
            "dataset":    "TaiwanStockCashFlowsStatement",
            "data_id":    stock_code,
            "start_date": start,
            "end_date":   end,
        }
        if _tok:
            params["token"] = _tok

        session = build_proxy_session()
        r = session.get(
            "https://api.finmindtrade.com/api/v4/data",
            params=params,
            headers={"User-Agent": random.choice(_USER_AGENTS)},
            timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
        )
        j = r.json()
        if j.get("status") != 200 or not j.get("data"):
            return {**_empty, "label": f"FinMind status={j.get('status')}"}

        df = pd.DataFrame(j["data"])
        df["date"] = pd.to_datetime(df["date"])
        # 年度報表 = 每年 12 月（Q4 累計）
        df = df[df["date"].dt.month == 12].copy()
        df["year"] = df["date"].dt.year
        years_avail = sorted(df["year"].unique())[-5:]
        df = df[df["year"].isin(years_avail)]
        if len(years_avail) < 3:
            return {**_empty, "status": "insufficient_data",
                    "label": f"年份不足（僅{len(years_avail)}年）"}

        # ── 科目別名集合 ───────────────────────────────────────────
        _OCF   = {"CashFlowFromOperatingActivities", "OperatingActivities",
                  "來自營業活動之現金流量", "營業活動之淨現金流入",
                  "營業活動現金流量"}
        _CAPEX = {"AcquisitionOfPropertyPlantAndEquipment",
                  "取得不動產、廠房及設備", "購置不動產廠房及設備",
                  "取得不動產廠房及設備", "資本支出"}
        _INV   = {"IncreaseDecreaseInInventories", "存貨增加",
                  "存貨(增加)減少", "存貨(增加)、減少",
                  "IncreaseInInventories", "存貨之增加"}
        _DIV   = {"DividendsPaid", "CashDividendsPaid", "支付現金股利",
                  "發放現金股利", "支付股東現金股利",
                  "發放現金股利予非控制權益"}

        def _sum(aliases):
            mask = df["type"].isin(aliases)
            vals = pd.to_numeric(df.loc[mask, "value"], errors="coerce").dropna()
            return float(vals.sum()) if not vals.empty else 0.0

        ocf_5y     = _sum(_OCF)
        capex_5y   = abs(_sum(_CAPEX))          # CF 表通常為負值
        inv_inc_5y = max(_sum(_INV), 0.0)       # 只計存貨增加（分母意義）
        div_5y     = abs(_sum(_DIV))
        denom_5y   = capex_5y + inv_inc_5y + div_5y

        if denom_5y == 0:
            return {**_empty, "status": "insufficient_data",
                    "label": "分母為零（CapEx+存貨+股利均缺失）",
                    "ocf_5y": round(ocf_5y), "years": len(years_avail)}

        ratio = round(ocf_5y / denom_5y * 100, 1)
        return {
            "status":     "ok",
            "ratio":      ratio,
            "label":      f"{ratio:.1f}%（{len(years_avail)}年實際）",
            "years":      len(years_avail),
            "ocf_5y":     round(ocf_5y),
            "capex_5y":   round(capex_5y),
            "inv_inc_5y": round(inv_inc_5y),
            "div_5y":     round(div_5y),
            "denom_5y":   round(denom_5y),
        }

    except Exception as _e:
        return {**_empty, "label": f"例外:{type(_e).__name__}:{_e}"}


# ─────────────────────────────────────────────
# §13 CLI Test
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    stock_id = sys.argv[1] if len(sys.argv) > 1 else "2330"
    print(f"Fetching financials for {stock_id} …")

    session = build_proxy_session()
    dfs = fetch_goodinfo_financials(stock_id, session)
    for k, df in dfs.items():
        print(f"\n[{k}] shape={df.shape}")
        if not df.empty:
            print(df.head(5).to_string())

    print("\n--- calc_financial_metrics ---")
    metrics = calc_financial_metrics(dfs["BS"], dfs["IS"], dfs["CF"])
    for key, val in metrics.items():
        print(f"  {key}: {val}")
