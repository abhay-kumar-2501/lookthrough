"""xbrl.parse_instance on a tiny hand-written XBRL instance document."""
from __future__ import annotations

import pandas as pd
import pytest

import xbrl

ENTITY = '<xbrli:identifier scheme="http://www.sec.gov/CIK">0000000001</xbrli:identifier>'

DOC = f"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
            xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xmlns:us-gaap="http://fasb.org/us-gaap/2025"
            xmlns:abc="http://www.example.com/20251231">
  <!-- plain instant -->
  <xbrli:context id="now">
    <xbrli:entity>{ENTITY}</xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <!-- one dimension -->
  <xbrli:context id="now_servers">
    <xbrli:entity>{ENTITY}
      <xbrli:segment>
        <xbrldi:explicitMember dimension="us-gaap:PropertyPlantAndEquipmentByTypeAxis">abc:ServersAndNetworkAssetsMember</xbrldi:explicitMember>
      </xbrli:segment>
    </xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <!-- two dimensions, written in non-alphabetical order -->
  <xbrli:context id="now_two">
    <xbrli:entity>{ENTITY}
      <xbrli:segment>
        <xbrldi:explicitMember dimension="srt:RangeAxis">srt:MaximumMember</xbrldi:explicitMember>
        <xbrldi:explicitMember dimension="us-gaap:PropertyPlantAndEquipmentByTypeAxis">us-gaap:BuildingMember</xbrldi:explicitMember>
      </xbrli:segment>
    </xbrli:entity>
    <xbrli:period><xbrli:instant>2025-12-31</xbrli:instant></xbrli:period>
  </xbrli:context>
  <!-- plain duration -->
  <xbrli:context id="year">
    <xbrli:entity>{ENTITY}</xbrli:entity>
    <xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period>
  </xbrli:context>
  <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>

  <us-gaap:PropertyPlantAndEquipmentGross contextRef="now" unitRef="usd" decimals="-6">250000000000</us-gaap:PropertyPlantAndEquipmentGross>
  <us-gaap:PropertyPlantAndEquipmentGross contextRef="now_servers" unitRef="usd" decimals="-6">98040000000</us-gaap:PropertyPlantAndEquipmentGross>
  <us-gaap:PropertyPlantAndEquipmentUsefulLife contextRef="now_two">P30Y</us-gaap:PropertyPlantAndEquipmentUsefulLife>
  <us-gaap:NetIncomeLoss contextRef="year" unitRef="usd" decimals="-6">
      60458000000
  </us-gaap:NetIncomeLoss>
  <abc:ServerDepreciationPolicyTextBlock contextRef="year">Servers are depreciated over 5.5 years.</abc:ServerDepreciationPolicyTextBlock>
  <us-gaap:Goodwill contextRef="now" unitRef="usd" xsi:nil="true"/>
  <us-gaap:Assets contextRef="missing_context" unitRef="usd">1</us-gaap:Assets>
</xbrli:xbrl>
""".encode()


@pytest.fixture(scope="module")
def facts() -> pd.DataFrame:
    return xbrl.parse_instance(DOC)


def one(facts: pd.DataFrame, concept: str, dims: str | None = None) -> pd.Series:
    sel = facts[facts.concept == concept]
    if dims is not None:
        sel = sel[sel.dims == dims]
    assert len(sel) == 1, f"expected one {concept} fact, got {len(sel)}"
    return sel.iloc[0]


def test_columns(facts):
    assert list(facts.columns) == ["prefix", "concept", "value", "start", "end", "dims", "unit"]


def test_plain_instant_fact(facts):
    f = one(facts, "PropertyPlantAndEquipmentGross", "")
    assert f.value == "250000000000"
    assert f.start is None
    assert f.end == "2025-12-31"
    assert f.prefix == "us-gaap"
    assert f.unit == "usd"


def test_dimensional_fact(facts):
    f = one(facts, "PropertyPlantAndEquipmentGross", "PropertyPlantAndEquipmentByTypeAxis=ServersAndNetworkAssetsMember")
    assert f.value == "98040000000"
    assert f.start is None
    assert f.end == "2025-12-31"


def test_two_dimensions_are_sorted_and_joined(facts):
    f = one(facts, "PropertyPlantAndEquipmentUsefulLife")
    assert f.dims == "PropertyPlantAndEquipmentByTypeAxis=BuildingMember|RangeAxis=MaximumMember"
    assert f.value == "P30Y"
    assert f.unit is None


def test_duration_fact_and_whitespace(facts):
    f = one(facts, "NetIncomeLoss")
    assert (f.start, f.end, f.dims) == ("2025-01-01", "2025-12-31", "")
    assert f.value == "60458000000"


def test_company_extension_prefix(facts):
    assert one(facts, "ServerDepreciationPolicyTextBlock").prefix == "abc"


def test_nil_facts_contexts_and_units_are_not_facts(facts):
    assert "Goodwill" not in set(facts.concept)  # xsi:nil, no value
    assert "Assets" not in set(facts.concept)  # points at a context that does not exist
    assert not set(facts.concept) & {"context", "unit", "identifier"}
    assert len(facts) == 5


def test_numeric_keeps_only_numbers(facts):
    num = xbrl.numeric(facts)
    assert set(num.concept) == {"PropertyPlantAndEquipmentGross", "NetIncomeLoss"}
    assert num.value.dtype.kind == "f"
    assert num[num.concept == "NetIncomeLoss"].value.iloc[0] == 60_458_000_000
    assert facts.value.map(type).eq(str).all()  # the input frame is left alone


def test_the_selection_used_for_server_assets(facts):
    # build_dataset picks "exactly one dimension whose member is the one we want".
    num = xbrl.numeric(facts)
    sel = num[num.start.isna() & num.dims.str.fullmatch(r"[A-Za-z]+Axis=ServersAndNetworkAssetsMember")]
    assert sel.value.tolist() == [98_040_000_000]


TYPED_DOC = f"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
            xmlns:us-gaap="http://fasb.org/us-gaap/2026">
  <xbrli:context id="total">
    <xbrli:entity>{ENTITY}</xbrli:entity>
    <xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period>
  </xbrli:context>
  <xbrli:context id="part">
    <xbrli:entity>{ENTITY}
      <xbrli:segment>
        <xbrldi:typedMember dimension="us-gaap:StatementOfFinancialPositionLocationBalanceAxis">
          <us-gaap:QName.domain>us-gaap:OtherLiabilitiesCurrent</us-gaap:QName.domain>
        </xbrldi:typedMember>
      </xbrli:segment>
    </xbrli:entity>
    <xbrli:period><xbrli:instant>2026-09-30</xbrli:instant></xbrli:period>
  </xbrli:context>
  <us-gaap:OperatingLeaseLiability contextRef="total" unitRef="usd">27477000000</us-gaap:OperatingLeaseLiability>
  <us-gaap:OperatingLeaseLiability contextRef="part" unitRef="usd">5758000000</us-gaap:OperatingLeaseLiability>
</xbrli:xbrl>
""".encode()


def test_typed_dimension_facts_are_not_reported_as_plain():
    # This is how Microsoft's 10-Q tags the current part of its operating lease liability.
    facts = xbrl.parse_instance(TYPED_DOC)
    plain = facts[(facts.concept == "OperatingLeaseLiability") & (facts.dims == "")]
    assert plain.value.tolist() == ["27477000000"]
