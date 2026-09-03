"""
Real PDF parsing for the Razorpay AI Finance Controller.

Strategy
--------
PRIMARY:  pdfplumber.extract_tables()  — best for structured financial tables.
FALLBACK: PyMuPDF via pymupdf4llm (markdown) + regex — for messy / scanned-like PDFs
          where the text layer is jumbled.

Public surface
--------------
- PDFParseResult dataclass  (df, source, pages, warnings)
- parse_pdf(file_path, kind)  -> PDFParseResult
- detect_kind(df)            -> 'razorpay_settlement' | 'bank_statement' | 'gst_invoice' | 'unknown'

`kind` may be one of:
    'razorpay_settlement', 'bank_statement', 'gst_invoice', 'auto'

Money is kept as ``decimal.Decimal`` (no float drift) when we can identify a
numeric column; unparseable text stays as string so the caller can decide.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

import pandas as pd

logger = logging.getLogger(__name__)

Kind = Literal["razorpay_settlement", "bank_statement", "gst_invoice", "auto", "unknown"]
Source = Literal["pdfplumber", "pymupdf", "none"]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PDFParseResult:
    """The result of parsing one PDF."""
    df: pd.DataFrame
    source: Source
    pages: int
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.df.empty and self.source != "none"


# ---------------------------------------------------------------------------
# Expected schemas
# ---------------------------------------------------------------------------

# Canonical column order for each kind. We do NOT insist on every column
# being present — we coerce / fill what we can and warn about the rest.
EXPECTED_COLUMNS: dict[str, list[str]] = {
    "razorpay_settlement": [
        "entity", "payment_id", "amount", "fee", "tax", "credit", "debit",
        "on_hold", "settlement_utr", "created_at", "settled_at", "method",
    ],
    "bank_statement": [
        "date", "narration", "utr", "debit", "credit", "balance",
    ],
    "gst_invoice": [
        "invoice_no", "invoice_date", "gstin", "taxable_value",
        "cgst", "sgst", "igst", "total",
    ],
}

# Subset of columns that should be parsed as Decimal money.
MONEY_COLUMNS: dict[str, set[str]] = {
    "razorpay_settlement": {"amount", "fee", "tax", "credit", "debit"},
    "bank_statement": {"debit", "credit", "balance"},
    "gst_invoice": {"taxable_value", "cgst", "sgst", "igst", "total"},
}

# Header keywords (lowercased) used by ``detect_kind``.
KIND_KEYWORDS: dict[str, set[str]] = {
    "razorpay_settlement": {
        "entity", "payment_id", "settlement_utr", "settled_at", "razorpay",
        "amount", "fee", "tax", "on_hold",
    },
    "bank_statement": {
        "narration", "utr", "balance", "debit", "credit", "statement",
        "txn", "transaction", "withdrawal", "deposit",
    },
    "gst_invoice": {
        "invoice", "gstin", "cgst", "sgst", "igst", "taxable", "gst",
    },
}


# ---------------------------------------------------------------------------
# Heuristics — is this likely a scanned / image PDF?
# ---------------------------------------------------------------------------

_SCANNED_TEXT_THRESHOLD = 40  # chars per page below this → probably scanned


def _looks_scanned(text_per_page: list[str]) -> bool:
    total = sum(len(t.strip()) for t in text_per_page)
    if not text_per_page:
        return True
    avg = total / len(text_per_page)
    return avg < _SCANNED_TEXT_THRESHOLD


# ---------------------------------------------------------------------------
# Decimal-safe money coercion
# ---------------------------------------------------------------------------

_NUM_CLEAN_RE = re.compile(r"[^0-9.\-]")


def _to_decimal(value: Any) -> Any:
    """Best-effort Decimal coercion. Returns the original value on failure."""
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return value
    s = str(value).strip()
    if not s:
        return None
    # Strip currency symbols, commas, spaces
    cleaned = _NUM_CLEAN_RE.sub("", s.replace(",", ""))
    if cleaned in ("", "-", ".", "-."):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return s  # leave as string for caller to inspect


def _coerce_money_columns(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    cols = MONEY_COLUMNS.get(kind, set())
    for c in cols:
        if c in df.columns:
            df[c] = df[c].apply(_to_decimal)
    return df


# ---------------------------------------------------------------------------
# Auto-detection from a DataFrame's columns
# ---------------------------------------------------------------------------

def detect_kind(df: pd.DataFrame) -> Kind:
    """Heuristically pick a kind by column overlap."""
    if df is None or len(df.columns) == 0:
        return "unknown"
    cols = {str(c).strip().lower() for c in df.columns}
    best_kind: Kind = "unknown"
    best_score = 0
    for kind, keywords in KIND_KEYWORDS.items():
        score = len(cols & keywords)
        if score > best_score:
            best_score = score
            best_kind = kind  # type: ignore[assignment]
    return best_kind if best_score >= 2 else "unknown"


# ---------------------------------------------------------------------------
# pdfplumber extraction
# ---------------------------------------------------------------------------

def _extract_with_pdfplumber(file_path: str | Path) -> tuple[pd.DataFrame, int, list[str]]:
    """Try to extract structured tables with pdfplumber."""
    warnings: list[str] = []
    try:
        import pdfplumber  # imported lazily so the module loads without it
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pdfplumber is required for the primary parser") from e

    tables: list[pd.DataFrame] = []
    pages = 0
    text_per_page: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        pages = len(pdf.pages)
        for page in pdf.pages:
            text_per_page.append(page.extract_text() or "")
            for tbl in page.extract_tables() or []:
                if not tbl or not any(any(c for c in row) for row in tbl):
                    continue
                # First non-empty row is the header
                header = [(c or "").strip() for c in tbl[0]]
                # If the header is empty / duplicated, skip
                if not any(header) or all(h == "" for h in header):
                    continue
                rows = [[(c or "").strip() for c in r] for r in tbl[1:]]
                df = pd.DataFrame(rows, columns=header)
                tables.append(df)

    if _looks_scanned(text_per_page):
        warnings.append("Scanned PDF, needs OCR")
        return pd.DataFrame(), pages, warnings

    if not tables:
        return pd.DataFrame(), pages, warnings

    # Concat all tables; pages may repeat the same header — drop dup rows
    df = pd.concat(tables, ignore_index=True, sort=False)
    if df.empty:
        return pd.DataFrame(), pages, warnings
    # De-duplicate exact rows (often the header repeats)
    df = df.drop_duplicates().reset_index(drop=True)
    return df, pages, warnings


# ---------------------------------------------------------------------------
# PyMuPDF (pymupdf4llm) fallback — markdown + regex
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(
    r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b"
)
_UTR_RE = re.compile(r"\b([A-Z0-9]{10,18})\b")
_AMOUNT_RE = re.compile(r"-?\(?₹?\s*\d[\d,]*\.?\d*\)?")
_GSTIN_RE = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z]{1}\d[Z]{1}[A-Z\d]{1})\b")
_INV_NO_RE = re.compile(r"\b([A-Z]{0,4}[-/]?\d{3,10}[-/]?\d{0,6})\b")


def _extract_with_pymupdf(file_path: str | Path) -> tuple[pd.DataFrame, int, list[str]]:
    """Fallback: markdown via pymupdf4llm, then per-line regex extraction."""
    warnings: list[str] = []
    try:
        import pymupdf4llm  # type: ignore
        import pymupdf  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("pymupdf4llm is required for the fallback parser") from e

    doc = pymupdf.open(file_path)
    pages = len(doc)
    text_per_page = [p.get_text() or "" for p in doc]
    if _looks_scanned(text_per_page):
        warnings.append("Scanned PDF, needs OCR")
        doc.close()
        return pd.DataFrame(), pages, warnings

    md = pymupdf4llm.to_markdown(str(file_path))
    doc.close()

    # Heuristic: split markdown table rows (lines containing '|')
    table_rows = [ln for ln in md.splitlines() if ln.count("|") >= 2 and "---" not in ln]
    df = _parse_markdown_table(table_rows)
    if df.empty:
        # Fall back to line-based regex extraction
        df = _parse_lines_with_regex(text_per_page)

    if df.empty and not warnings:
        warnings.append("PyMuPDF fallback could not extract tabular data")

    return df, pages, warnings


def _parse_markdown_table(rows: list[str]) -> pd.DataFrame:
    """Parse a list of markdown table rows into a DataFrame."""
    if not rows:
        return pd.DataFrame()
    # First row is header
    header = [c.strip() for c in rows[0].strip("|").split("|")]
    if len(header) < 2:
        return pd.DataFrame()
    body = rows[1:]
    data = []
    for r in body:
        cells = [c.strip() for c in r.strip("|").split("|")]
        if len(cells) != len(header):
            continue
        data.append(cells)
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data, columns=header).drop_duplicates().reset_index(drop=True)


def _parse_lines_with_regex(text_per_page: list[str]) -> pd.DataFrame:
    """Last-ditch per-line extraction — best-effort, schema is loose."""
    rows: list[dict[str, Any]] = []
    for page_text in text_per_page:
        for line in page_text.splitlines():
            line = line.strip()
            if not line:
                continue
            row: dict[str, Any] = {}
            m_date = _DATE_RE.search(line)
            if m_date:
                row["date"] = m_date.group(1)
            m_amt = _AMOUNT_RE.search(line)
            if m_amt:
                row["amount"] = m_amt.group(0)
            m_utr = _UTR_RE.search(line)
            if m_utr:
                row["utr"] = m_utr.group(1)
            m_gstin = _GSTIN_RE.search(line)
            if m_gstin:
                row["gstin"] = m_gstin.group(1)
            # The rest of the line is "narration"
            if row and len(line) > 4:
                row["narration"] = line
                rows.append(row)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)


# ---------------------------------------------------------------------------
# Kind-specific normalization
# ---------------------------------------------------------------------------

def _normalize_columns(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    """
    Normalize column names to the canonical schema for the given kind.
    - Case-insensitive
    - Common synonyms mapped
    """
    synonyms: dict[str, dict[str, str]] = {
        "razorpay_settlement": {
            "payment id": "payment_id",
            "txn id": "payment_id",
            "transaction id": "payment_id",
            "utr": "settlement_utr",
            "settlement utr": "settlement_utr",
            "created at": "created_at",
            "settled at": "settled_at",
            "on hold": "on_hold",
            "payment method": "method",
        },
        "bank_statement": {
            "txn date": "date",
            "transaction date": "date",
            "value date": "date",
            "description": "narration",
            "particulars": "narration",
            "details": "narration",
            "withdrawal": "debit",
            "deposit": "credit",
            "closing balance": "balance",
            "running balance": "balance",
        },
        "gst_invoice": {
            "invoice number": "invoice_no",
            "invoice no": "invoice_no",
            "inv no": "invoice_no",
            "bill no": "invoice_no",
            "date": "invoice_date",
            "bill date": "invoice_date",
            "taxable value": "taxable_value",
            "taxable amount": "taxable_value",
            "igst amount": "igst",
            "cgst amount": "cgst",
            "sgst amount": "sgst",
            "grand total": "total",
            "invoice total": "total",
            "amount": "total",
        },
    }
    mapping = synonyms.get(kind, {})
    canonical = {c.lower(): c for c in EXPECTED_COLUMNS.get(kind, [])}
    rename: dict[str, str] = {}
    for c in df.columns:
        key = str(c).strip().lower()
        if key in mapping:
            rename[c] = mapping[key]
        elif key in canonical:
            # Already canonical, just normalize the casing
            rename[c] = canonical[key]
    if rename:
        df = df.rename(columns=rename)
    return df


def _add_missing_columns(df: pd.DataFrame, kind: str, warnings: list[str]) -> pd.DataFrame:
    """Add any missing canonical columns as empty/None — keeps downstream stable."""
    for col in EXPECTED_COLUMNS.get(kind, []):
        if col not in df.columns:
            df[col] = None
            warnings.append(f"Missing column '{col}' for kind={kind}; left empty")
    # Reorder to canonical order
    df = df[EXPECTED_COLUMNS[kind]]
    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_pdf(file_path: str | Path, kind: Kind = "auto") -> PDFParseResult:
    """
    Parse a financial PDF into a typed DataFrame.

    Parameters
    ----------
    file_path : str | Path
        Path to the PDF on disk.
    kind : {'razorpay_settlement', 'bank_statement', 'gst_invoice', 'auto'}

    Returns
    -------
    PDFParseResult
        ``df`` is empty (and ``source == 'none'``) when the PDF could not be
        parsed — check ``warnings`` for the reason.
    """
    warnings: list[str] = []
    file_path = str(file_path)

    if not Path(file_path).exists():
        return PDFParseResult(
            df=pd.DataFrame(),
            source="none",
            pages=0,
            warnings=[f"File not found: {file_path}"],
        )

    # --- 1. PRIMARY: pdfplumber --------------------------------------------
    pages = 0
    source: Source = "none"
    df = pd.DataFrame()
    try:
        df, pages, w = _extract_with_pdfplumber(file_path)
        warnings.extend(w)
        scanned = "Scanned PDF, needs OCR" in warnings
        if not df.empty and not scanned:
            source = "pdfplumber"
    except Exception as e:  # pragma: no cover - defensive
        warnings.append(f"pdfplumber failed: {e!r}")

    # --- 2. FALLBACK: pymupdf4llm ------------------------------------------
    if df.empty and "Scanned PDF, needs OCR" not in warnings:
        try:
            df_fb, pages_fb, w = _extract_with_pymupdf(file_path)
            warnings.extend(w)
            if not df_fb.empty:
                df = df_fb
                source = "pymupdf"
                pages = pages or pages_fb
        except Exception as e:
            warnings.append(f"pymupdf fallback failed: {e!r}")

    # If we already flagged scanned, return early
    if "Scanned PDF, needs OCR" in warnings and df.empty:
        return PDFParseResult(df=pd.DataFrame(), source="none", pages=pages, warnings=warnings)

    if df.empty:
        return PDFParseResult(df=pd.DataFrame(), source="none", pages=pages, warnings=warnings)

    # --- 3. KIND resolution -------------------------------------------------
    if kind == "auto":
        kind = detect_kind(df)
        if kind == "unknown":
            warnings.append("Could not auto-detect kind; columns: "
                            + ", ".join(map(str, df.columns)))

    if kind not in EXPECTED_COLUMNS:
        # Unknown kind — return what we have, no normalization
        return PDFParseResult(df=df, source=source, pages=pages, warnings=warnings)

    df = _normalize_columns(df, kind)
    df = _add_missing_columns(df, kind, warnings)
    df = _coerce_money_columns(df, kind)
    return PDFParseResult(df=df, source=source, pages=pages, warnings=warnings)
