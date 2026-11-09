"""Check a generated warehouse against the data contract (src/tsunagu/contract.yml)."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import duckdb
import yaml

TYPES = {
    "integer": ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT"),
    "number": ("DOUBLE", "FLOAT", "DECIMAL", "INTEGER", "BIGINT", "SMALLINT"),
    "string": ("VARCHAR",),
    "boolean": ("BOOLEAN",),
    "date": ("DATE",),
    "timestamp": ("TIMESTAMP", "TIMESTAMP_NS", "TIMESTAMP_US", "TIMESTAMP_MS"),
}


@dataclass
class Breach:
    table: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.table}: {self.rule} -> {self.detail}"


def load_contract(path: str | Path | None = None) -> dict:
    text = Path(path).read_text(encoding="utf-8") if path else \
        resources.files("tsunagu").joinpath("contract.yml").read_text(encoding="utf-8")
    return yaml.safe_load(text)


def _q(con, sql: str):
    return con.execute(sql).fetchone()[0]


def validate(db_path: str | Path, contract: dict | None = None) -> list[Breach]:
    contract = contract or load_contract()
    out: list[Breach] = []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        for table, spec in contract["tables"].items():
            schema, name = table.split(".")
            cols = dict(con.execute(
                "select column_name, data_type from information_schema.columns where table_schema=? and table_name=?",
                [schema, name]).fetchall())
            if not cols:
                out.append(Breach(table, "exists", "table missing"))
                continue
            pk = spec.get("primary_key")
            if pk:
                keys = ", ".join(pk)
                dup = _q(con, f"select count(*) from (select {keys} from {table} group by {keys} having count(*) > 1)")
                nulls = _q(con, f"select count(*) from {table} where " + " or ".join(f"{k} is null" for k in pk))
                if dup or nulls:
                    out.append(Breach(table, f"primary key ({keys})", f"{dup} duplicates, {nulls} nulls"))
            for col, rule in (spec.get("columns") or {}).items():
                if col not in cols:
                    out.append(Breach(table, f"column {col}", "missing"))
                    continue
                want = rule.get("type")
                if want and not cols[col].upper().startswith(TYPES[want]):
                    out.append(Breach(table, f"{col} type", f"expected {want}, found {cols[col]}"))
                checks = []
                if rule.get("not_null"):
                    checks.append((f"{col} is null", "not null"))
                if "min" in rule:
                    checks.append((f"{col} < {rule['min']}", f">= {rule['min']}"))
                if "max" in rule:
                    checks.append((f"{col} > {rule['max']}", f"<= {rule['max']}"))
                if "accepted" in rule:
                    vals = ", ".join("'" + str(v).replace("'", "''") + "'" for v in rule["accepted"])
                    checks.append((f"{col} is not null and {col}::varchar not in ({vals})", "accepted values"))
                if "pattern" in rule:
                    checks.append((f"{col} is not null and not regexp_full_match({col}, '{rule['pattern']}')", "pattern"))
                for where, label in checks:
                    bad = _q(con, f"select count(*) from {table} where {where}")
                    if bad:
                        out.append(Breach(table, f"{col} {label}", f"{bad} rows"))
                if rule.get("unique"):
                    dup = _q(con, f"select count(*) - count(distinct {col}) from {table} where {col} is not null")
                    if dup:
                        out.append(Breach(table, f"{col} unique", f"{dup} duplicates"))
            for col, target in (spec.get("references") or {}).items():
                ref_table, ref_col = target.rsplit(".", 1)
                orphans = _q(con, f"select count(*) from {table} c where c.{col} is not null and not exists "
                                  f"(select 1 from {ref_table} p where p.{ref_col} = c.{col})")
                if orphans:
                    out.append(Breach(table, f"{col} -> {target}", f"{orphans} orphan rows"))
            for check in spec.get("checks") or []:
                bad = _q(con, f"select count(*) from {table} where not coalesce(({check}), false)")
                if bad:
                    out.append(Breach(table, f"check {check}", f"{bad} rows"))
    finally:
        con.close()
    return out
