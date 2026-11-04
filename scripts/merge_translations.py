"""Add the English translations (data/explain/en_out/batch_*.json, made per
data/explain/EN_INSTRUCTIONS.md) to data/explanations.json as exp_en/duda_en, and to the hand-review
items in data/review_overrides.json (keys "ov:<occ>") as exp_en/doubt_en.

Usage: .venv/bin/python scripts/merge_translations.py, then build_bank.py.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "explain" / "en_out"
EXPLANATIONS = ROOT / "data" / "explanations.json"
OVERRIDES = ROOT / "data" / "review_overrides.json"


def main():
    explanations = json.loads(EXPLANATIONS.read_text())
    overrides = json.loads(OVERRIDES.read_text())
    by_occ = {o["occ"]: o for o in overrides}
    done = missing = 0
    for f in sorted(OUT.glob("batch_*.json")):
        for key, v in json.loads(f.read_text()).items():
            if key.startswith("ov:"):
                item = by_occ.get(key[3:])
                if item is None:
                    missing += 1
                    continue
                if v.get("exp") and "exp" in item:
                    item["exp_en"] = v["exp"]
                if v.get("duda") and item.get("doubt"):
                    item["doubt_en"] = v["duda"]
            elif key in explanations:
                x = explanations[key]
                if v.get("exp"):
                    x["exp_en"] = v["exp"]
                if v.get("duda") and "duda" in x:
                    x["duda_en"] = v["duda"]
            else:
                missing += 1
                continue
            done += 1
    EXPLANATIONS.write_text(json.dumps(explanations, ensure_ascii=False, indent=1))
    OVERRIDES.write_text(json.dumps(overrides, ensure_ascii=False, indent=1))
    untranslated = sum("exp_en" not in x for x in explanations.values())
    print(f"{done} translations merged, {missing} unknown keys, {untranslated} explanations still Spanish-only")


if __name__ == "__main__":
    main()
