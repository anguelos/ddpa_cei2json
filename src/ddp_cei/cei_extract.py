import calendar
import re
from urllib.parse import unquote

from lxml import etree

from .cei_dates import infer_date


# ---------------------------------------------------------------------------
# XML navigation helpers (namespace-agnostic: match on local name only, so both
# `cei:`-prefixed files and default-namespace files are handled identically).
# ---------------------------------------------------------------------------

def _local(tag):
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _child(node, name):
    if node is None:
        return None
    for candidate in node:
        if _local(candidate.tag) == name:
            return candidate
    return None


def _children(node, name):
    if node is None:
        return []
    return [c for c in node if _local(c.tag) == name]


def _descend(node, *names):
    for name in names:
        node = _child(node, name)
        if node is None:
            return None
    return node


def _find_descendant(node, name):
    if node is None:
        return None
    for candidate in node.iter():
        if _local(candidate.tag) == name:
            return candidate
    return None


def _text(node):
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


def _body(root):
    body = _descend(root, "content", "text", "body")
    if body is not None:
        return body
    return _find_descendant(root, "body")


def _chdesc(root):
    chdesc = _descend(root, "content", "text", "body", "chDesc")
    if chdesc is not None:
        return chdesc
    return _find_descendant(root, "chDesc")


# ---------------------------------------------------------------------------
# Date range helpers. Every path yields a widened [start, end] pair of ISO dates
# (a fully specified date collapses to start == end).
# ---------------------------------------------------------------------------

def _span_from_ymd(year, month, day):
    if not 1 <= month <= 12:
        return (f"{year:04d}-01-01", f"{year:04d}-12-31")
    last = calendar.monthrange(year, month)[1]
    if not 1 <= day <= last:
        return (f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last:02d}")
    return (f"{year:04d}-{month:02d}-{day:02d}", f"{year:04d}-{month:02d}-{day:02d}")


def _numeric_span(value):
    if value is None:
        return None
    value = value.strip()
    if not (value.isdigit() and len(value) == 8):
        return None
    year, month, day = int(value[:4]), int(value[4:6]), int(value[6:8])
    if year == 0 or year == 9999:
        return None
    return _span_from_ymd(year, month, day)


def _text_span(text):
    if not text:
        return None
    parsed = infer_date(text, fail_quietly=True)
    if not isinstance(parsed, tuple):
        return None
    year, month, day = parsed
    if year == 0:
        return None
    return _span_from_ymd(year, month, day)


def _loose_text_span(text):
    # Last resort when numeric attributes are missing/sentinels. Scoped to the
    # authoritative issued date element, so bare years here are the date itself.
    if not text:
        return None
    single = _text_span(text)
    if single is not None:
        return single
    years = [int(y) for y in re.findall(r"(?<!\d)\d{4}(?!\d)", text) if 1000 <= int(y) <= 1999]
    if len(years) >= 2:
        return (f"{min(years):04d}-01-01", f"{max(years):04d}-12-31")
    if len(years) == 1:
        return (f"{years[0]:04d}-01-01", f"{years[0]:04d}-12-31")
    return None


def _range_span(frm, to):
    # Bogus whole-year-2000 placeholder used by some archives for "unknown date".
    if frm == "20000101" and to == "20001231":
        return None
    start = _numeric_span(frm)
    end = _numeric_span(to)
    if start is None and end is None:
        return None
    if start is None:
        return (end[0], end[1])
    if end is None:
        return (start[0], start[1])
    return (start[0], end[1])


def _value_span(value, text):
    span = _numeric_span(value)
    if span is None:
        return None
    # `MM=01, DD=01` is ambiguous: a real 1 January vs. a year-only date padded to
    # look like it. Trust the element text when it is year-only and widen.
    if span[0] == span[1] and value.endswith("0101") and _is_year_only(text):
        year = int(value[:4])
        return (f"{year:04d}-01-01", f"{year:04d}-12-31")
    return span


def _is_year_only(text):
    parsed = infer_date(text, fail_quietly=True)
    return isinstance(parsed, tuple) and parsed[0] != 0 and parsed[1] == 0 and parsed[2] == 0


# ---------------------------------------------------------------------------
# Content classifiers (degenerate abstracts and placeholder place names).
# ---------------------------------------------------------------------------

_ABSTRACT_PLACEHOLDERS = {"", "-", "--", "noch kein regest vorhanden", "kein regest vorhanden"}
_LOCATION_PLACEHOLDERS = {"", "-", "--", "nicht angegeben", "ohne herkunftsangabe", "o o", "oo", "unbekannt"}


def _norm(text):
    return " ".join(text.lower().replace(".", " ").split())


def _is_placeholder_abstract(text):
    return _norm(text) in _ABSTRACT_PLACEHOLDERS


def _is_issuer_only(abstract):
    issuers = _children(abstract, "issuer")
    if not issuers:
        return False
    issuer_text = " ".join(_text(issuer) for issuer in issuers)
    return _text(abstract) == " ".join(issuer_text.split())


def _is_placeholder_location(name):
    return _norm(name) in _LOCATION_PLACEHOLDERS


# ---------------------------------------------------------------------------
# Field extractors. All share the signature `extract_<field>(root) -> value|None`
# (except the date, which returns an ISO [start, end] pair) and use an if/else
# ladder internally.
# ---------------------------------------------------------------------------

def extract_atom_id(root):
    node = _child(root, "id")
    if node is None:
        return None
    text = _text(node)
    if not text:
        return None
    return unquote(text)


def extract_tenor(root):
    tenor = _child(_body(root), "tenor")
    if tenor is None:
        return None
    text = _text(tenor)
    if not text:
        return None
    return text


def extract_abstract(root):
    abstract = _child(_chdesc(root), "abstract")
    if abstract is None:
        return None
    text = _text(abstract)
    if _is_placeholder_abstract(text):
        return None
    if _is_issuer_only(abstract):
        return None
    return text


def extract_date(root):
    issued = _child(_chdesc(root), "issued")
    if issued is None:
        return None
    daterange = _child(issued, "dateRange")
    if daterange is not None:
        span = _range_span(daterange.get("from"), daterange.get("to"))
        if span is not None:
            return span
        span = _loose_text_span(_text(daterange))
        if span is not None:
            return span
    date = _child(issued, "date")
    if date is not None:
        span = _value_span(date.get("value"), _text(date))
        if span is not None:
            return span
        span = _range_span(date.get("notBefore"), date.get("notAfter"))
        if span is not None:
            return span
        span = _loose_text_span(_text(date))
        if span is not None:
            return span
    return None


def extract_location(root):
    issued = _child(_chdesc(root), "issued")
    place = _child(issued, "placeName")
    if place is None:
        return None
    reg = place.get("reg")
    if reg and reg.strip():
        name = reg.strip()
    else:
        name = _text(place)
    if _is_placeholder_location(name):
        return None
    return name


def extract_geo_key(root):
    issued = _child(_chdesc(root), "issued")
    place = _child(issued, "placeName")
    if place is None:
        return None
    key = place.get("key")
    if key and key.strip():
        return key.strip()
    return None


# ---------------------------------------------------------------------------
# Orchestrator.
# ---------------------------------------------------------------------------

def cei_to_dict(cei_path):
    root = etree.parse(cei_path).getroot()
    date = extract_date(root)
    return {
        "atom_id": extract_atom_id(root),
        "tenor": extract_tenor(root),
        "abstract": extract_abstract(root),
        "date": {"start": date[0], "end": date[1]} if date is not None else None,
        "location": extract_location(root),
        "geo_key": extract_geo_key(root),
    }
