"""Unit coverage for ddp_cei.cei_extract.cei_to_dict (the offline extractor)."""
import json

import pytest

from ddp_cei.cei_extract import cei_to_dict


def _write(tmp_path, xml):
    p = tmp_path / "CH.cei.xml"
    p.write_text(xml, encoding="utf-8")
    return str(p)


# A default-namespace CEI (no cei: prefix). The extractor is namespace-agnostic.
FULL = """<entry xmlns="http://www.monasterium.net/NS/cei">
  <id>tag:www.monasterium.net,2011:/charter/DE-Test/fond/sig1</id>
  <content><text><body>
    <chDesc>
      <abstract>Verkauf eines Weinbergs bei Trier.</abstract>
      <issued>
        <placeName reg="Trier" key="geo:49.75,6.63">Treveris</placeName>
        <date value="12550714">14. Juli 1255</date>
      </issued>
    </chDesc>
    <tenor>In nomine domini amen.</tenor>
  </body></text></content>
</entry>"""


def test_full_record(tmp_path):
    rec = cei_to_dict(_write(tmp_path, FULL))
    assert rec["date"] == {"start": "1255-07-14", "end": "1255-07-14"}
    assert rec["location"] == "Trier"
    assert rec["geo_key"] == "geo:49.75,6.63"
    assert rec["abstract"] == "Verkauf eines Weinbergs bei Trier."
    assert rec["tenor"] == "In nomine domini amen."
    assert rec["atom_id"].endswith("/charter/DE-Test/fond/sig1")


def test_cei_prefixed_namespace_is_equivalent(tmp_path):
    xml = FULL.replace("<entry xmlns=", '<cei:entry xmlns:cei=').replace("</entry>", "</cei:entry>")
    # prefix every element so it is genuinely the cei:-prefixed shape
    for tag in ("id", "content", "text", "body", "chDesc", "abstract", "issued",
                "placeName", "date", "tenor"):
        xml = xml.replace(f"<{tag}", f"<cei:{tag}").replace(f"</{tag}>", f"</cei:{tag}>")
    rec = cei_to_dict(_write(tmp_path, xml))
    assert rec["location"] == "Trier"
    assert rec["date"] == {"start": "1255-07-14", "end": "1255-07-14"}


def test_daterange_widens(tmp_path):
    xml = """<entry xmlns="http://www.monasterium.net/NS/cei"><id>x</id><content><text><body>
      <chDesc><issued><dateRange from="12000101" to="12091231">13th c.</dateRange></issued></chDesc>
    </body></text></content></entry>"""
    rec = cei_to_dict(_write(tmp_path, xml))
    assert rec["date"] == {"start": "1200-01-01", "end": "1209-12-31"}


def test_placeholders_become_none(tmp_path):
    xml = """<entry xmlns="http://www.monasterium.net/NS/cei"><id>x</id><content><text><body>
      <chDesc><abstract>Kein Regest vorhanden</abstract>
      <issued><placeName>ohne Herkunftsangabe</placeName><date value="00000000"></date></issued></chDesc>
    </body></text></content></entry>"""
    rec = cei_to_dict(_write(tmp_path, xml))
    assert rec["abstract"] is None
    assert rec["location"] is None
    assert rec["date"] is None


def test_year_only_value_widens(tmp_path):
    # value padded to 0101 but the text is year-only -> widen to the whole year.
    xml = """<entry xmlns="http://www.monasterium.net/NS/cei"><id>x</id><content><text><body>
      <chDesc><issued><date value="13000101">1300</date></issued></chDesc>
    </body></text></content></entry>"""
    rec = cei_to_dict(_write(tmp_path, xml))
    assert rec["date"] == {"start": "1300-01-01", "end": "1300-12-31"}


def test_missing_issued_yields_none_date_and_location(tmp_path):
    xml = """<entry xmlns="http://www.monasterium.net/NS/cei"><id>x</id><content><text><body>
      <chDesc><abstract>Something happened.</abstract></chDesc></body></text></content></entry>"""
    rec = cei_to_dict(_write(tmp_path, xml))
    assert rec["date"] is None
    assert rec["location"] is None
    assert rec["abstract"] == "Something happened."


def test_output_is_json_serialisable(tmp_path):
    rec = cei_to_dict(_write(tmp_path, FULL))
    json.dumps(rec)  # must not raise
