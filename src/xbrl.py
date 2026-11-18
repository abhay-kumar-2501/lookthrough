"""Parse an XBRL instance document into a flat table of facts.

The SEC's companyfacts API only returns "plain" facts. The detail this project
needs - gross PP&E *by asset class*, useful lives *by asset class* - is tagged
with dimensions (e.g. PropertyPlantAndEquipmentByTypeAxis = ServersMember), and
dimensional facts only exist in each filing's own instance document.
"""
from __future__ import annotations

import pandas as pd
from lxml import etree

import edgar

NS = {
    "xbrli": "http://www.xbrl.org/2003/instance",
    "xbrldi": "http://xbrl.org/2006/xbrldi",
}


def parse_instance(raw: bytes) -> pd.DataFrame:
    """Return one row per fact: concept, value, start, end, dims.

    `dims` is a sorted "axis=member|axis=member" string ("" for plain facts).
    Instant facts (balance sheet) have start = None.
    """
    root = etree.fromstring(raw, parser=etree.XMLParser(huge_tree=True, recover=True))
    contexts = {}
    for cx in root.findall("xbrli:context", NS):
        members = [
            f"{m.get('dimension').split(':')[-1]}={(m.text or '').strip().split(':')[-1]}"
            for m in cx.findall(".//xbrldi:explicitMember", NS)
        ]
        # Typed dimensions carry a free-form value instead of a named member. They must still
        # count as a dimension, or a part (e.g. the current portion) would look like a total.
        members += [
            f"{m.get('dimension').split(':')[-1]}={''.join(m.itertext()).strip() or 'typed'}"
            for m in cx.findall(".//xbrldi:typedMember", NS)
        ]
        members.sort()
        instant = cx.findtext(".//xbrli:instant", namespaces=NS)
        start = cx.findtext(".//xbrli:startDate", namespaces=NS)
        end = cx.findtext(".//xbrli:endDate", namespaces=NS)
        contexts[cx.get("id")] = ("|".join(members), start, (instant or end or "").strip())
    rows = []
    for el in root:
        if not isinstance(el.tag, str):
            continue
        ref = el.get("contextRef")
        if ref is None or ref not in contexts or el.text is None:
            continue
        q = etree.QName(el)
        dims, start, end = contexts[ref]
        rows.append(
            {
                "prefix": el.prefix,
                "concept": q.localname,
                "value": el.text.strip(),
                "start": start.strip() if start else None,
                "end": end,
                "dims": dims,
                "unit": el.get("unitRef"),
            }
        )
    return pd.DataFrame(rows)


def filing_facts(cik: int, filing: dict) -> pd.DataFrame:
    url = edgar.xbrl_instance_url(cik, filing)
    if url is None:
        return pd.DataFrame()
    df = parse_instance(edgar.get(url))
    df["accession"] = filing["accession"]
    df["filed"] = filing["filed"]
    df["form"] = filing["form"]
    return df


def numeric(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    return out.dropna(subset=["value"])
