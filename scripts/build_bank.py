"""Deduplicate parsed exam questions into a master question bank.

Usage: .venv/bin/python scripts/build_bank.py
Reads data/parsed/*.json, writes data/bank.json and copies figures to app/figures/.

Questions are the same when the Catalan stem and the set of Catalan options match after
normalisation (option order varies between exams), with a fuzzy pass for typo-level differences.
Figure questions that share wording but have different correct answers ("which knot is shown?")
are kept apart; for text-only questions disagreeing answer keys are resolved by majority.
"""
import difflib
import hashlib
import json
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARSED = ROOT / "data" / "parsed"
BANK = ROOT / "data" / "bank.json"
EXPLANATIONS = ROOT / "data" / "explanations.json"
OVERRIDES = ROOT / "data" / "review_overrides.json"
APP_FIGS = ROOT / "app" / "figures"

LETTERS = "abcd"
MONTHS = {m: i + 1 for i, m in enumerate("ENE FEB MAR ABR MAY JUN JUL AGO SEP OCT NOV DIC".split())}
FIGURE_WORDS = re.compile(r"dibuix|dibujo|figura|imatge|imagen|fotograf", re.I)

# Every exam follows the same structure (see the answer sheet), so the topic follows from the number.
TOPICS = [
    (4, 1, "Nomenclatura nàutica", "Nomenclatura náutica"),
    (6, 2, "Elements d’amarratge i fondeig", "Elementos de amarre y fondeo"),
    (10, 3, "Seguretat", "Seguridad"),
    (12, 4, "Legislació", "Legislación"),
    (17, 5, "Abalisament", "Balizamiento"),
    (27, 6, "Reglament (RIPA)", "Reglamento (RIPA)"),
    (29, 7, "Maniobra", "Maniobra"),
    (32, 8, "Emergències a la mar", "Emergencias en la mar"),
    (36, 9, "Meteorologia", "Meteorología"),
    (41, 10, "Teoria de navegació", "Teoría de navegación"),
    (45, 11, "Carta de navegació", "Carta de navegación"),
]


def topic_for(num):
    for last, code, ca, es in TOPICS:
        if num <= last:
            return {"code": code, "ca": ca, "es": es}
    raise ValueError(num)


def exam_date(name):
    """(year, month) from file names like PER_OCT26_2, PER-0421-3R, PER-2-0522, PER-11-18-1."""
    if m := re.search(r"(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)[_-]?(\d{2})", name):
        return 2000 + int(m.group(2)), MONTHS[m.group(1)]
    if m := re.search(r"(?<!\d)(\d{2})(\d{2})(?!\d)", name):
        return 2000 + int(m.group(2)), int(m.group(1))
    if m := re.search(r"-(\d{1,2})-(?:\d-)?(\d{2})(?:-\d)?$", name):
        return 2000 + int(m.group(2)), int(m.group(1))
    raise ValueError(f"no date in {name}")


def norm(t):
    t = unicodedata.normalize("NFC", t.lower()).replace("’", "'").replace("ŀl", "l·l").replace("l.l", "l·l")
    t = re.sub(r"[–−]", "-", t)
    t = re.sub(r"([+-])\s*(?=\d)", lambda m: " plus " if m.group(1) == "+" else " minus ", t)  # "Ct = –5º" vs "+5º"
    t = re.sub(r"[^\w\s·]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def correct_texts(q):
    """Normalised Catalan text of each accepted option."""
    return {norm(q["options"][LETTERS.index(a)]["ca"]) for a in (q["answer"] or "")}


def load():
    questions = []
    for f in sorted(PARSED.glob("*.json")):
        d = json.loads(f.read_text())
        for q in d["questions"]:
            if len(q["options"]) != 4:
                continue  # malformed in the source PDF
            q["exam"] = d["exam"]
            q["topic"] = topic_for(q["num"])
            q["date"] = exam_date(d["exam"])
            q["stem_n"] = norm(q["q_ca"])
            q["opts_n"] = tuple(sorted(norm(o["ca"]) for o in q["options"]))
            questions.append(q)
    return questions


def similar(a, b, threshold):
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def majority_answer(g):
    votes = Counter(t for q in g for t in correct_texts(q) if len(q["answer"] or "") == 1)
    return votes.most_common(1)[0][0] if votes else None


def group(questions):
    exact = defaultdict(list)
    for q in questions:
        exact[(q["stem_n"], q["opts_n"])].append(q)
    groups = list(exact.values())
    # fuzzy pass: merge groups whose stems and option sets are near-identical (typos, articles)
    by_opts = defaultdict(list)
    for i, g in enumerate(groups):
        by_opts[" | ".join(g[0]["opts_n"])[:40]].append(i)
    parent = list(range(len(groups)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for idxs in by_opts.values():
        for x, i in enumerate(idxs):
            for j in idxs[x + 1:]:
                a, b = groups[i][0], groups[j][0]
                # numbers must match exactly: chart exercises differ only in coordinates and times
                if re.findall(r"\d+", a["stem_n"] + " ".join(a["opts_n"])) != re.findall(r"\d+", b["stem_n"] + " ".join(b["opts_n"])):
                    continue
                # and so must the answer: "clockwise" vs "counter-clockwise" differ by one word
                if majority_answer(groups[i]) is None or majority_answer(groups[i]) != majority_answer(groups[j]):
                    continue
                if similar(a["stem_n"], b["stem_n"], 0.92) and similar(" | ".join(a["opts_n"]), " | ".join(b["opts_n"]), 0.92):
                    parent[find(j)] = find(i)
    merged = defaultdict(list)
    for i, g in enumerate(groups):
        merged[find(i)].extend(g)
    return list(merged.values())


def split_figure_variants(g):
    """Same wording, different picture: split figure questions by their correct answer."""
    has_fig = sum(bool(q["figure"]) for q in g) * 2 >= len(g)
    if not (has_fig or FIGURE_WORDS.search(g[0]["q_ca"] + g[0]["q_es"])):
        return [g]
    by_answer = defaultdict(list)
    for q in g:
        ans = correct_texts(q)
        by_answer[frozenset(ans) if len(ans) == 1 else None].append(q)
    unresolved = by_answer.pop(None, [])
    parts = list(by_answer.values()) or [unresolved]
    if by_answer and unresolved:
        parts[0].extend(unresolved)  # annulled/multi-answer occurrences can't be matched to a picture
    return parts


def build_entry(g):
    g.sort(key=lambda q: q["date"])
    # a figure belongs to the question if it refers to one or most exams print one next to it;
    # otherwise it is a neighbouring drawing caught by the crop in some exam
    wants_fig = FIGURE_WORDS.search(g[-1]["q_ca"] + g[-1]["q_es"]) or sum(bool(q["figure"]) for q in g) * 2 > len(g)
    rep = next((q for q in reversed(g) if q["figure"]), g[-1]) if wants_fig else g[-1]
    rep_opts = [norm(o["ca"]) for o in rep["options"]]
    votes = Counter()
    for q in g:
        ans = correct_texts(q)
        if len(ans) == 1:
            votes[next(iter(ans))] += 1
    multi = [q for q in g if q["answer"] and 1 < len(q["answer"]) < 4]
    if votes:
        best, n = votes.most_common(1)[0]
        answer = [rep_opts.index(best)] if best in rep_opts else []
        # no single-answer occurrence wins? keep every option some key accepted
    elif multi:
        answer = sorted({rep_opts.index(t) for q in multi for t in correct_texts(q) if t in rep_opts})
    else:
        answer = []
    if not answer and votes:
        # option wording drifted between exams: fall back to the closest option text
        best = votes.most_common(1)[0][0]
        answer = [max(range(4), key=lambda i: difflib.SequenceMatcher(None, rep_opts[i], best).ratio())]
    stable = "|".join([rep["stem_n"], *rep["opts_n"], *(rep_opts[i] for i in answer), rep["figure"] or ""])
    entry = {
        "key": hashlib.sha1(stable.encode()).hexdigest()[:12],
        "topic": rep["topic"],
        "q_ca": rep["q_ca"],
        "q_es": rep["q_es"],
        "options": rep["options"],
        "answer": answer,
        "figure": rep["figure"] if wants_fig else None,
        "seen": [f"{q['exam']}#{q['num']}" for q in g],
        "last_seen": "%d-%02d" % rep["date"],
        "count": len({q["exam"] for q in g}),
    }
    if len(votes) > 1:
        entry["key_conflict"] = dict(votes)
    if not answer:
        entry["annulled"] = True
    return entry


def apply_overrides(bank):
    """Hand review (data/review_overrides.json): each item names one exam occurrence ("EXAM#num")
    of the entry it fixes, and may replace its text, its answer (by Catalan option text),
    its explanation, or its note ("doubt": null removes the note)."""
    if not OVERRIDES.exists():
        return
    by_occ = {o: e for e in bank for o in e["seen"]}
    for item in json.loads(OVERRIDES.read_text()):
        e = by_occ.get(item["occ"])
        if e is None:
            raise SystemExit(f"override for {item['occ']}: no such question in the bank")
        for field in ("q_ca", "q_es", "options"):
            if field in item:
                e[field] = item[field]
        if "answer" in item:
            texts = [norm(o["ca"]) for o in e["options"]]
            if norm(item["answer"]) not in texts:
                raise SystemExit(f"override for {item['occ']}: no option {item['answer']!r}")
            e["answer"] = [texts.index(norm(item["answer"]))]
            e.pop("annulled", None)
        if "exp" in item:
            e["explanation"] = item["exp"]
        if "doubt" in item:
            if item["doubt"]:
                e["doubt"] = item["doubt"]
            else:
                e.pop("doubt", None)
        e["reviewed"] = True


def main():
    questions = load()
    groups = [part for g in group(questions) for part in split_figure_variants(g)]
    bank = [build_entry(g) for g in groups]
    bank.sort(key=lambda e: (e["topic"]["code"] or 99, -e["count"], e["q_ca"]))
    explanations = json.loads(EXPLANATIONS.read_text()) if EXPLANATIONS.exists() else {}
    by_occurrence = {occ: k for k, v in explanations.items() for occ in v["seen"]}
    for i, e in enumerate(bank, 1):
        e["id"] = i
        # match by key, else by shared exam occurrences (the key changes if the parsed text changes)
        votes = Counter(by_occurrence[o] for o in e["seen"] if o in by_occurrence)
        match = e["key"] if e["key"] in explanations else votes.most_common(1)[0][0] if votes else None
        if match:
            e["explanation"] = explanations[match]["exp"]
            if "duda" in explanations[match]:
                e["doubt"] = explanations[match]["duda"]
    # sync in place (never empty the folder) so an open app keeps loading pictures during a rebuild
    APP_FIGS.mkdir(parents=True, exist_ok=True)
    used = {e["figure"] for e in bank if e["figure"]}
    for name in used:
        shutil.copy(PARSED / "figures" / name, APP_FIGS / name)
    for stale in APP_FIGS.glob("*.png"):
        if stale.name not in used:
            stale.unlink()
    apply_overrides(bank)
    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=1))
    (ROOT / "app" / "bank.json").write_text(json.dumps(bank, ensure_ascii=False, separators=(",", ":")))
    topics = Counter((e["topic"]["code"], e["topic"]["ca"]) for e in bank)
    print(f"{len(questions)} parsed questions -> {len(bank)} unique "
          f"({sum('explanation' in e for e in bank)} with explanations)")
    print(f"  with figure: {sum(bool(e['figure']) for e in bank)}, annulled/no key: {sum(e.get('annulled', False) for e in bank)}, "
          f"key conflicts resolved by majority: {sum('key_conflict' in e for e in bank)}")
    for (code, name), n in sorted(topics.items(), key=lambda t: t[0][0] or 99):
        print(f"  UT{code} {name}: {n}")


if __name__ == "__main__":
    main()
