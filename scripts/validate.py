"""Report parse-quality problems across data/parsed/*.json."""
import json
import re
from pathlib import Path

PARSED = Path(__file__).resolve().parent.parent / "data" / "parsed"

SUSPECT = re.compile(r"(^|\s)[a-d]\)\s|\s\d{1,2}\s*\.-")


def issues(d):
    out = []
    nums = [q["num"] for q in d["questions"]]
    missing = sorted(set(range(1, 46)) - set(nums))
    if missing:
        out.append(f"missing questions {missing}")
    for q in d["questions"]:
        tag = f"Q{q['num']}"
        if len(q["options"]) != 4:
            out.append(f"{tag}: {len(q['options'])} options")
        if not q["answer"]:
            out.append(f"{tag}: no answer")
        elif len(q["answer"]) > 1:
            out.append(f"{tag}: multiple accepted answers {q['answer']}")
        if len(q["q_ca"]) < 10 or len(q["q_es"]) < 10:
            out.append(f"{tag}: short stem ca={q['q_ca'][:40]!r} es={q['q_es'][:40]!r}")
        if len(q["q_ca"]) > 500 or len(q["q_es"]) > 500:
            out.append(f"{tag}: long stem ({len(q['q_ca'])}/{len(q['q_es'])})")
        for i, o in enumerate(q["options"]):
            for lang in ("ca", "es"):
                t = o[lang]
                if not t:
                    out.append(f"{tag}{'abcd'[i]}: empty {lang}")
                elif len(t) > 250 or SUSPECT.search(t):
                    out.append(f"{tag}{'abcd'[i]}: suspicious {lang}: {t[:90]!r}")
    return out


def main():
    total = clean = 0
    for f in sorted(PARSED.glob("*.json")):
        d = json.loads(f.read_text())
        total += len(d["questions"])
        probs = issues(d)
        clean += len(d["questions"]) - len({p.split(":")[0].rstrip("abcd") for p in probs if p.startswith("Q")})
        if probs:
            print(f"== {d['exam']} ({d['key_mode']}, key {d['key_size']})")
            for p in probs:
                print("   ", p)
    print(f"\n{total} questions parsed, ~{clean} without flagged issues")


if __name__ == "__main__":
    main()
