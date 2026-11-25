import datetime as dt

import pandas as pd

from gridkeepup.fetch import eia860m

HEADERS = ["Entity ID", "Entity Name", "Plant ID", "Plant State", "Balancing Authority Code",
           "Generator ID", "Nameplate Capacity (MW)", "Technology"]


def _write_workbook(path):
    rows = [
        ["U.S. Energy Information Administration"] + [None] * 7,
        ["Preliminary data, subject to revision"] + [None] * 7,
        HEADERS,
        [1, "A", 10, "TX", "ERCO", "G1", 500.0, "Solar Photovoltaic"],
        [2, "B", 11, "TX", "SWPP", "G1", 200.0, "Onshore Wind Turbine"],
        [3, "C", 12, "TX", "ERCO", "B1", 100.0, "Batteries"],
        ["NOTE: footnote row", None, None, None, None, None, None, None],
    ]
    with pd.ExcelWriter(path) as xl:
        for sheet in eia860m.SHEETS.values():
            pd.DataFrame(rows).to_excel(xl, sheet_name=sheet, header=False, index=False)


def test_read_sheet_finds_header_and_drops_footnotes(tmp_path):
    path = tmp_path / "october_generator2026.xlsx"
    _write_workbook(path)
    df = eia860m.read_sheet(path, "Operating")
    assert "nameplate_capacity_mw" in df.columns
    assert "balancing_authority_code" in df.columns
    assert len(df) == 3


def test_load_latest_keeps_only_ercot(tmp_path):
    _write_workbook(tmp_path / "october_generator2026.xlsx")
    out = eia860m.load_latest("ERCO", raw_dir=tmp_path)
    assert set(out) == {"operating", "planned", "retired"}
    assert out["operating"]["nameplate_capacity_mw"].sum() == 600.0


def test_candidate_urls_walk_back_across_year_end():
    names = [n for n, _ in eia860m.candidate_urls(dt.date(2026, 2, 10), months_back=3)]
    assert names[0] == "february_generator2026.xlsx"
    assert "december_generator2025.xlsx" in names
