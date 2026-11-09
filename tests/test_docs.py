"""Docs must not drift from the code."""
from dataclasses import fields
from pathlib import Path

from tsunagu.config import Scenario
from tsunagu.contract import load_contract

ROOT = Path(__file__).resolve().parents[1]


def test_every_parameter_is_documented():
    text = (ROOT / "docs" / "ASSUMPTIONS.md").read_text(encoding="utf-8")
    missing = [f.name for f in fields(Scenario) if f"`{f.name}`" not in text]
    assert missing == []


def test_every_contract_table_is_documented():
    text = (ROOT / "docs" / "DATA_MODEL.md").read_text(encoding="utf-8") + \
        (ROOT / "README.md").read_text(encoding="utf-8")
    missing = [t for t in load_contract()["tables"] if t.split(".")[0] not in text]
    assert missing == []
