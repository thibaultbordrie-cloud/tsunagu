"""Command line: python -m tsunagu generate | validate | describe."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from dataclasses import fields

from .config import SCENARIOS, Scenario

TUNABLE = {f.name for f in fields(Scenario)} - {"name", "seed", "start", "end"}


def parse_overrides(pairs: list[str], base: Scenario) -> dict:
    """--set holdout_rate=0.2 --set 'email_open={"FR":0.3,"JP":0.2,"TW":0.2}'"""
    out = {}
    for pair in pairs or []:
        key, sep, raw = pair.partition("=")
        key = key.strip()
        if not sep or key not in TUNABLE:
            raise SystemExit(f"--set {pair!r}: unknown parameter. Choose from: {', '.join(sorted(TUNABLE))}")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"--set {pair!r}: the value must be JSON "
                             "(a number, or an object for per-market values)") from exc
        current = getattr(base, key)
        if isinstance(current, dict):
            if not isinstance(value, dict) or set(value) - set(current):
                raise SystemExit(f"--set {key}: expected an object with keys among {sorted(current)}")
            value = {**current, **value}
        elif isinstance(current, (int, float)) and not isinstance(value, (int, float)):
            raise SystemExit(f"--set {key}: expected a number")
        out[key] = value
    return out


def _generate(args) -> int:
    from .contract import validate
    from .exporters import api_json, duckdb_out, salesforce
    from .simulate import run

    sc = SCENARIOS[args.scenario]
    changes = {}
    if args.seed is not None:
        changes["seed"] = args.seed
    if args.start:
        changes["start"] = dt.date.fromisoformat(args.start)
    if args.end:
        changes["end"] = dt.date.fromisoformat(args.end)
    changes.update(parse_overrides(args.set, sc))
    sc = sc.with_(**changes) if changes else sc
    t0 = time.time()
    print(f"Simulating '{sc.name}' (seed {sc.seed}, {sc.start} -> {sc.end}) ...")
    for key in sorted(set(changes) & TUNABLE):
        print(f"  override {key} = {getattr(sc, key)}")
    res = run(sc)
    counts = duckdb_out.write(res, args.out)
    print(f"Wrote {args.out} in {time.time() - t0:.1f} s")
    for name, n in counts.items():
        print(f"  {name:<30} {n:>10,}")
    if args.api:
        for name, n in api_json.write(res, args.api).items():
            print(f"  api/{name:<26} {n:>10,}")
    if args.salesforce:
        for name, n in salesforce.write(res, args.salesforce).items():
            print(f"  salesforce/{name:<19} {n:>10,}")
    breaches = validate(args.out)
    print("Contract: OK" if not breaches else "Contract: BROKEN")
    for b in breaches:
        print("  ", b)
    return 0 if not breaches else 1


def _validate(args) -> int:
    from .contract import validate

    breaches = validate(args.path)
    for b in breaches:
        print(b)
    print("Contract: OK" if not breaches else f"Contract: {len(breaches)} breach(es)")
    return 0 if not breaches else 1


def _describe(args) -> int:
    from .describe import describe

    print(describe(args.path))
    return 0


def _query(args) -> int:
    import duckdb

    from .describe import _table

    sql = open(args.sql, encoding="utf-8").read() if args.sql.endswith(".sql") else args.sql
    con = duckdb.connect(args.path, read_only=True)
    try:
        cur = con.execute(sql)
        headers = [d[0] for d in cur.description]
        rows = cur.fetchmany(args.limit)
    finally:
        con.close()
    print(_table(rows, headers))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="tsunagu", description="Fictional cross-border CRM data for FR / JP / TW.")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="simulate and write the DuckDB warehouse")
    g.add_argument("--scenario", default="standard", choices=sorted(SCENARIOS))
    g.add_argument("--seed", type=int)
    g.add_argument("--start", help="YYYY-MM-DD")
    g.add_argument("--end", help="YYYY-MM-DD")
    g.add_argument("--out", default="data/tsunagu.duckdb")
    g.add_argument("--api", help="also write API-shaped JSON samples to this folder")
    g.add_argument("--salesforce", help="also write a small Sales Cloud load (CSV per object) to this folder")
    g.add_argument("--set", action="append", metavar="PARAM=VALUE",
                   help="change one parameter of config.py, e.g. --set holdout_rate=0.5 (repeatable)")
    g.set_defaults(func=_generate)
    v = sub.add_parser("validate", help="check a warehouse against the data contract")
    v.add_argument("path")
    v.set_defaults(func=_validate)
    d = sub.add_parser("describe", help="key numbers by market and channel, and what last-click gets wrong")
    d.add_argument("path")
    d.set_defaults(func=_describe)
    q = sub.add_parser("query", help="run a read-only SQL query (text or a .sql file) and print the result")
    q.add_argument("path")
    q.add_argument("sql")
    q.add_argument("--limit", type=int, default=50)
    q.set_defaults(func=_query)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
