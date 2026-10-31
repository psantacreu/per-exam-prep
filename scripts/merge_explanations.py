"""Collect generated explanations into data/explanations.json.

Usage: .venv/bin/python scripts/merge_explanations.py
Reads data/explain/out/batch_*.json (written per data/explain/INSTRUCTIONS.md) and the bank snapshot
the batches were made from, and stores each explanation with the exam occurrences it belongs to,
so build_bank.py can re-attach it even if a later re-parse changes the entry's key.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "explain" / "out"
SNAPSHOT = ROOT / "data" / "explain" / "bank_at_batching.json"
EXPLANATIONS = ROOT / "data" / "explanations.json"


def main():
    seen = {e["key"]: e["seen"] for e in json.loads(SNAPSHOT.read_text())}
    merged = json.loads(EXPLANATIONS.read_text()) if EXPLANATIONS.exists() else {}
    for f in sorted(OUT.glob("batch_*.json")):
        for key, v in json.loads(f.read_text()).items():
            if isinstance(v, str):
                v = {"exp": v}  # some batches wrote the bare text
            if key in seen and v.get("exp"):
                merged[key] = {**v, "seen": seen[key]}
    EXPLANATIONS.write_text(json.dumps(merged, ensure_ascii=False, indent=1))
    print(f"{len(merged)} explanations ({sum('duda' in v for v in merged.values())} flagged with duda)")


if __name__ == "__main__":
    main()
