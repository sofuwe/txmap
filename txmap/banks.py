"""Per-bank input layouts and descriptor cleaning.

Each bank gets (a) a layout for headerless exports and (b) a cleaner that strips
bank-specific noise (type codes, store numbers, references) from the descriptor.
Add a Malaysian or other Canadian bank by registering a cleaner + layout here.
"""
import re

# TD Canada Trust chequing export: no header; Date, Description, Out, In, Balance.
TD_LAYOUT = {"date": 0, "descriptor": 1}

LAYOUTS = {"td": TD_LAYOUT}

_TD_SUFFIX = re.compile(r"(?:_[A-Z]|\s(?:MSP|BPY|BUS|CCB))\s*$")


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


def _td(raw: str) -> str:
    return _generic(_TD_SUFFIX.sub("", raw.strip()))


CLEANERS = {"td": _td}


def clean(bank: str, raw: str) -> str:
    """Normalize a raw descriptor into a stable key. Unknown banks use the generic cleaner."""
    return CLEANERS.get(bank.lower(), _generic)(raw)
