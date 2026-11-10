"""Per-bank parsing and descriptor cleaning.

Each bank has:
  - a parser that turns its raw export rows into standard rows
    (Bank, TransactionID, Date, Amount), used by `txmap normalize`
  - a cleaner that strips bank-specific noise (type codes, store numbers,
    references) from the descriptor, used by the model

To add a bank: write a parser and a cleaner, register both in BANKS, and teach
detect() to recognise its export.
"""
import re

STANDARD_COLUMNS = ["Bank", "TransactionID", "Date", "Amount"]


# ---- parsers: raw export rows -> standard rows ---------------------------------

def _parse_td(rows):
    """TD Canada Trust chequing: no header; Date, Description, Out, In, Balance."""
    for r in rows:
        if not r:
            continue
        date, desc, out, into = r[0], r[1], r[2].strip(), r[3].strip()
        yield {"Bank": "td", "TransactionID": desc, "Date": date.strip(),
               "Amount": f"-{out}" if out else into}


def _parse_meridiancu(rows):
    """Meridian Credit Union: header row
    ID, Date, Account Name, Description1, Description2, Description3, Amount, Balance.
    The merchant is in Description1; the others hold locations and reference numbers."""
    header = [c.strip().lower() for c in rows[0]]
    date_i, desc_i, amt_i = header.index("date"), header.index("description1"), header.index("amount")
    for r in rows[1:]:
        if not r:
            continue
        yield {"Bank": "meridiancu", "TransactionID": r[desc_i].strip(),
               "Date": r[date_i].split()[0],  # "2026-11-06 12:00:00 AM" -> "2026-11-06"
               "Amount": r[amt_i].strip()}


def detect(rows):
    """Guess the bank from the shape of a raw export, or return None."""
    if not rows:
        return None
    first = [c.strip().lower() for c in rows[0]]
    if "description1" in first and "account name" in first:
        return "meridiancu"
    if len(first) == 5 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", first[0]):
        return "td"
    return None


# ---- cleaners: raw descriptor -> stable key -------------------------------------

# Payment-processor / web prefixes that precede the real merchant name.
_PREFIX = re.compile(r"^(?:WWW|SQ|TST|PAYPAL|VESTA)\s+(?=\S)")


def _generic(s: str) -> str:
    s = re.sub(r"\*{3}\w+", " ", s)                               # e-transfer refs (***vtg)
    s = re.sub(r"#\s*\d*", " ", s)                                # store numbers (#1348)
    s = re.sub(r"\b\d{1,2}/\d{2}\b", " ", s)                      # dates (09/28)
    s = re.sub(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?(?![A-Za-z0-9])", " ", s)  # standalone numbers/amounts
    s = re.sub(r"[^A-Za-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip().upper()
    return _PREFIX.sub("", s)


_TD_SUFFIX = re.compile(r"(?:_[A-Z]|\s(?:MSP|BPY|BUS|CCB))\s*$")


def _clean_td(raw: str) -> str:
    return _generic(_TD_SUFFIX.sub("", raw.strip()))


# Transaction-type prefixes and the trailing province/country code ("Onca" = Ontario, Canada).
_MERIDIAN_PREFIX = re.compile(r"^(?:POS Purchase|Pre-Authorized|Bill Payment)\s+", re.I)
_MERIDIAN_SUFFIX = re.compile(r"\s+Onca\s*$", re.I)


# Meridian appends the city after the merchant, often cut short ("Mississ", "Scarboroug").
_CITIES = [
    "TORONTO", "NORTH YORK", "YORK", "EAST YORK", "SCARBOROUGH", "ETOBICOKE", "MISSISSAUGA",
    "ERIN MILLS", "BRAMPTON", "MARKHAM", "MILTON", "RICHMOND HILL", "VAUGHAN", "THORNHILL",
    "WOODBRIDGE", "CONCORD", "OAKVILLE", "BURLINGTON", "HAMILTON", "AJAX", "PICKERING",
    "WHITBY", "OSHAWA", "NEWMARKET", "AURORA", "CALEDON", "BOLTON", "STOUFFVILLE",
]
_MIN_PARTIAL_CITY = 5  # shorter cut-offs ("Br", "Mar") are too ambiguous to strip


def _is_city(tail: str) -> bool:
    return any(tail == c or (len(tail) >= _MIN_PARTIAL_CITY and c.startswith(tail)) for c in _CITIES)


def _strip_city(key: str) -> str:
    """Drop a trailing city (full or cut off), keeping at least one word.
    'OF <city>' is kept so names like 'CITY OF TORONTO' survive."""
    words = key.split()
    for i in range(max(1, len(words) - 3), len(words)):  # longest tail first
        if _is_city(" ".join(words[i:])) and words[i - 1] != "OF":
            return " ".join(words[:i])
    return key


def _clean_meridiancu(raw: str) -> str:
    s = _MERIDIAN_SUFFIX.sub("", _MERIDIAN_PREFIX.sub("", raw.strip()))
    return _strip_city(_generic(s))


BANKS = {
    "td": {"parse": _parse_td, "clean": _clean_td},
    "meridiancu": {"parse": _parse_meridiancu, "clean": _clean_meridiancu},
}


def clean(bank: str, raw: str) -> str:
    """Normalize a raw descriptor into a stable key. Unknown banks use the generic cleaner."""
    b = BANKS.get(bank.lower())
    return b["clean"](raw) if b else _generic(raw)
