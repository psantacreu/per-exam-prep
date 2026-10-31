"""Parse PER exam PDFs into JSON: bilingual questions, options, answer key and figures.

Usage: .venv/bin/python scripts/parse_exams.py [pdf ...]
Writes data/parsed/<exam>.json and data/parsed/figures/<exam>_<n>.png
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pymupdf
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "pdfs"
OUT_DIR = ROOT / "data" / "parsed"
FIG_DIR = OUT_DIR / "figures"

LETTERS = "abcd"

# Corrections hand-marked on scanned sheets that pixel detection cannot read.
KEY_OVERRIDES = {
    # Q5: bubble d filled then annulled (ANUL·LAR bar), option a circled in red.
    ("PER-JUN23-2", 5): "a",
}


# ---------------------------------------------------------------- answer key

def render(page, zoom):
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    return np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]


MARK_THRESHOLD = 150  # mean darkest-channel value of a cell; blank cells ~200+, filled ones far lower


def key_from_vector(page):
    """Answer sheet with text-layer numbers/letters: sample the cell behind each letter.

    Returns {num: marked letters} (several letters = all accepted) and {num: per-letter scores}."""
    zoom = 4
    arr = render(page, zoom).astype(float)
    minchan = arr.min(axis=2)
    # word boxes are in unrotated page space; the render is rotated
    words = [tuple(pymupdf.Rect(w[:4]) * page.rotation_matrix) + (w[4],) for w in page.get_text("words")]
    letters = [w for w in words if w[4] in LETTERS]
    rows = {}
    for w in words:
        if not w[4].isdigit() or not 1 <= int(w[4]) <= 60:
            continue
        cy = (w[1] + w[3]) / 2
        row = sorted(
            (l for l in letters if abs((l[1] + l[3]) / 2 - cy) < 4 and 0 < l[0] - w[2] < 90),
            key=lambda l: l[0],
        )
        # the same number also appears in labels ("BLOC 1"): keep the occurrence with answer cells
        if len(row) > len(rows.get(int(w[4]), (None, []))[1]):
            rows[int(w[4])] = (w, row)
    # cell pitch from complete rows, used to place letters hidden under a fill
    pitches = [b[0] - a[0] for _, row in rows.values() if "".join(l[4] for l in row[:4]) == LETTERS
               for a, b in zip(row, row[1:4])]
    if not pitches:
        return {}, {}
    pitch = float(np.median(pitches))
    key, scores = {}, {}
    for n, (w, row) in rows.items():
        row = [l for l in row if l[0] - w[2] < 4.6 * pitch]
        deduped = []  # some sheets draw the same glyph twice, a fraction of a point apart
        for l in row:
            if not any(d[4] == l[4] and abs(d[0] - l[0]) < 3 for d in deduped):
                deduped.append(l)
        seen = {l[4]: ((l[0] + l[2]) / 2, (l[1] + l[3]) / 2) for l in deduped}
        if not seen or len(seen) != len(deduped):
            continue
        ref_letter, (rx, ry) = next(iter(seen.items()))
        cells = {c: seen.get(c, (rx + (LETTERS.index(c) - LETTERS.index(ref_letter)) * pitch, ry)) for c in LETTERS}
        sc = {}
        for c, (lx, ly) in cells.items():
            region = minchan[int((ly - 5) * zoom):int((ly + 5) * zoom), int((lx - 4.5) * zoom):int((lx + 4.5) * zoom)]
            sc[c] = round(float(region.mean()), 1)
        key[n] = "".join(c for c in LETTERS if sc[c] < MARK_THRESHOLD)
        scores[n] = sc
    return key, scores


def blobs(mask, min_area, max_area=10**9, max_aspect=10.0):
    """Centers of connected components within an area range and roughly compact shape."""
    lab, n = ndimage.label(mask)
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab)):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        area = int((lab[sl] == i + 1).sum())
        if min_area <= area <= max_area and max(w / h, h / w) <= max_aspect:
            out.append(((sl[1].start + sl[1].stop) / 2, (sl[0].start + sl[0].stop) / 2))
    # merge fragments of the same mark
    merged = []
    for x, y in sorted(out):
        if not any(abs(mx - x) < 25 and abs(my - y) < 25 for mx, my in merged):
            merged.append((x, y))
    return merged


def cluster_1d(values, tol):
    """Group sorted values into clusters whose consecutive members are within tol; return centers."""
    vals = sorted(values)
    groups = [[vals[0]]]
    for v in vals[1:]:
        if v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def nearest(centers, v):
    return min(range(len(centers)), key=lambda i: abs(centers[i] - v))


def grid_slots(xs, n_cols, tol):
    """Map mark x positions to (column, option) on a sheet of n_cols columns of 4 equally spaced options.

    Option positions with no mark are inferred from the pitch and the column spacing."""
    centers = cluster_1d(xs, tol)
    gaps = [b - a for a, b in zip(centers, centers[1:])]
    pitch = float(np.median([g for g in gaps if g < 2.5 * min(gaps)]))
    groups = [[centers[0]]]
    for c in centers[1:]:
        if c - groups[-1][-1] > 2.4 * pitch:
            groups.append([c])
        else:
            groups[-1].append(c)
    if len(groups) != n_cols:
        return None
    full = [(i, g[0]) for i, g in enumerate(groups) if len(g) == 4]
    if not full:
        return None
    if len(full) > 1:
        spacing = float(np.median([(b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(full, full[1:])]))
    else:
        spacing = None
    starts = []
    for i, g in enumerate(groups):
        if len(g) == 4:
            starts.append(g[0])
        else:
            ref = min(full, key=lambda f: abs(f[0] - i))
            starts.append(ref[1] + (i - ref[0]) * spacing)
    result = []
    for x in xs:
        col = min(range(n_cols), key=lambda i: abs(x - (starts[i] + 1.5 * pitch)))
        opt = int(round((x - starts[col]) / pitch))
        if not 0 <= opt <= 3:
            return None
        result.append((col, opt))
    return result


def key_from_red_grid_image(page):
    """Scanned copy of the usual 2-block grid sheet: one red cell per question."""
    zoom = 3
    arr = render(page, zoom).astype(int)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    marks = blobs((r > 170) & (g < 110) & (b < 110), min_area=400)
    if len(marks) < 40:
        return None
    slots = grid_slots([x for x, _ in marks], 4, tol=6 * zoom)
    if not slots:
        return None
    ys = sorted(y for _, y in marks)
    gaps = [(ys[i + 1] - ys[i], i) for i in range(len(ys) - 1)]
    bloc_split = ys[max(gaps)[1]] + 1
    placed = sorted((y >= bloc_split, col, y, opt) for (x, y), (col, opt) in zip(marks, slots))
    # marks on the same row of a column belong to one question (several accepted answers)
    questions = []
    for bloc, col, y, opt in placed:
        last = questions[-1] if questions else None
        if last and last[0] == (bloc, col) and abs(last[1] - y) < 8 * zoom:
            last[2].add(opt)
        else:
            questions.append([(bloc, col), y, {opt}])
    return {i + 1: "".join(LETTERS[o] for o in sorted(q[2])) for i, q in enumerate(questions)}


def key_from_bubble_image(page):
    """Scanned optical bubble sheet: 5 columns x 10 rows, numbered column-major."""
    zoom = 3
    arr = render(page, zoom).astype(int)
    marks = blobs(arr.max(axis=2) < 110, min_area=150, max_area=700, max_aspect=1.8)
    marks = [m for m in marks if m[0] < arr.shape[1] * 0.93]  # drop scanner timing marks
    if len(marks) < 40:
        return None
    slots = grid_slots([x for x, _ in marks], 5, tol=5 * zoom)
    rows = cluster_1d([y for _, y in marks], tol=6 * zoom)
    if not slots or len(rows) != 10:
        return None
    key = {}
    for (x, y), (col, opt) in zip(marks, slots):
        key[col * 10 + nearest(rows, y) + 1] = LETTERS[opt]
    return key


def answer_key(doc):
    page = doc[0]
    words = page.get_text("words")
    if sum(w[4].isdigit() for w in words) >= 30:
        key, scores = key_from_vector(page)
        if len(key) >= 40:
            return key, scores, "vector"
    for fn, name in ((key_from_red_grid_image, "red-grid-image"), (key_from_bubble_image, "bubble-image")):
        key = fn(page)
        if key:
            return key, {}, name
    return {}, {}, "failed"


# ---------------------------------------------------------------- questions

Q_START = re.compile(r"^\s*(\d{1,2})\s*(?:[.,]\s*[-–—]+|\.\d{1,2}\.|\.(?!\d)|[-–—]+|(?=\s*[A-ZÀ-Ý¿]))\s*")
OPT_START = re.compile(r"^\s*([a-dA-D])\s*\)\s*")
SECTION = re.compile(r"^\s*(?:[^\w\s]|x(?=\s))?\s*UT\s*(\d+)\s*(.*)$")  # optional bullet glyph
HEADER = re.compile(r"Examen te[òo]ric|Patr[óo]n?/ona de Embarcaciones|Patró/ona d|Generalitat de Catalunya|Departament d.Agricultura|Ramaderia, Pesca|^\s*\d{1,2}\s*/\s*\d{1,2}\s*$", re.I)
HAS_LETTER = re.compile(r"[A-Za-zÀ-ÿ]")


def page_lines(page, order="native"):
    """Visual text lines of a page, each with spans tagged bold/regular.

    order="native" keeps the PDF's content-stream order (right when lines overlap on the page);
    order="y" sorts top to bottom (right when the stream is scrambled). Same-height fragments
    that don't overlap horizontally are merged into one line."""
    natives = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [
                {"text": s["text"], "bbox": s["bbox"],
                 "bold": bool(s["flags"] & 16) or "bold" in s["font"].lower()}
                for s in line["spans"] if s["text"].strip()
            ]
            # in "y" mode treat every span on its own: scrambled PDFs also mix lines within a line object
            for group in ([[sp] for sp in spans] if order == "y" else [spans] if spans else []):
                natives.append({
                    "spans": group,
                    "cy": sum((s["bbox"][1] + s["bbox"][3]) / 2 for s in group) / len(group),
                    "x0": min(s["bbox"][0] for s in group),
                    "x1": max(s["bbox"][2] for s in group),
                })
    if order == "y":
        natives.sort(key=lambda n: n["cy"])
    lines = []
    for n in natives:
        # merge into a recent line at the same height that it does not overlap horizontally
        for l in lines[-6:]:
            if abs(l["cy"] - n["cy"]) < 3 and (order == "y" or all(
                    n["x1"] <= s["bbox"][0] + 1 or n["x0"] >= s["bbox"][2] - 1 for s in l["spans"])):
                l["spans"].extend(n["spans"])
                break
        else:
            lines.append({"cy": n["cy"], "spans": list(n["spans"])})
    for l in lines:
        l["spans"].sort(key=lambda s: s["bbox"][0])
        l["text"] = "".join(s["text"] for s in l["spans"])
        l["y0"] = min(s["bbox"][1] for s in l["spans"])
        l["y1"] = max(s["bbox"][3] for s in l["spans"])
        l["x0"] = l["spans"][0]["bbox"][0]
    return lines


def clean(t):
    t = re.sub(r"[\x00-\x1f]", " ", t.replace("\u00a0", " ").replace("\u00ad", ""))
    t = re.sub(r"\s+\d{1,2}/\d{1,2}\s*$", "", t)  # page footer "9/19" on the same line
    t = re.sub(r"\s+PER\s*-\s*[A-Za-zé]+\s+\d{4}\s*-\s*\d+\s*$", "", t)  # page footer "PER - Mayo 2023 - 2"
    t = re.sub(r"(^|\s)(?:x\s+|[^\w\s]\s*)?UT\s?\d{1,2}[\s·]+[A-ZÀ-Ý].*$", "", t)  # next section header
    t = re.sub(r"\s+", " ", t).strip()
    return t.strip(" /").strip()


class Target:
    """Accumulates Catalan (bold) and Spanish (regular) text for a stem or an option."""

    def __init__(self):
        self.ca, self.es, self.in_es = [], [], False

    def add(self, text, bold, glue=False):
        """glue: the span touches the previous one on the same line (a word split across spans)."""
        if HAS_LETTER.search(text) and not bold:
            self.in_es = True
        parts = self.es if self.in_es else self.ca
        if glue and parts:
            parts[-1] += text
        else:
            parts.append(text)

    def result(self):
        ca = clean(" ".join(self.ca))
        es = clean(" ".join(self.es))
        # punctuation/symbols that closed the Catalan text before the "/" separator
        es = clean(re.sub(r"^[^\w¿¡]*?/\s*", "", es))
        if not es and " / " in ca:
            ca, es = (clean(x) for x in ca.split(" / ", 1))
        if not ca and es:
            # no bold text at all: fall back to the separators between the two languages
            m = re.search(r"\s/\s*|/\s*(?=¿)|\s(?=¿)", es[5:])
            if m:
                ca, es = clean(es[:m.start() + 5]), clean(es[m.end() + 5:])
        return ca or es, es or ca


def close_region(segments, pno, y):
    """End a question's last page segment where the next element starts (if on the same page)."""
    if segments[-1][0] == pno:
        segments[-1][2] = y


def find_starts(pages):
    """Question-start lines as {(page, line index): number}.

    Numbers may appear slightly out of order (swapped on the page) or be missing in the source,
    so accept any unused number close to the highest seen so far, written at the left margin."""
    starts, used, top = {}, set(), 0
    for pno, lines in pages.items():
        margin = min((l["x0"] for l in lines if Q_START.match(l["text"])), default=0)
        for i, line in enumerate(lines):
            m = Q_START.match(line["text"])
            # "12.-" is unambiguous; weaker forms ("12. ", "12 Quin") must sit at the left margin
            if not m or (line["x0"] > margin + 25 and not re.match(r"\s*\d+\s*[.,]\s*[-–—]", line["text"])):
                continue
            n = int(m.group(1))
            if n in used or not 1 <= n <= 60 or not top - 3 <= n <= top + 6:
                continue
            starts[(pno, i)] = (n, m.end())
            used.add(n)
            top = max(top, n)
    return starts


def parse_questions(doc, order):
    questions, regions = [], {}
    topic = {"code": None, "ca": None, "es": None}
    cur, target = None, None
    pages = {pno: page_lines(doc[pno], order) for pno in range(1, doc.page_count)}
    starts = find_starts(pages)
    for pno, lines in pages.items():
        page = doc[pno]
        img_rects = [pymupdf.Rect(i["bbox"]) + (-2, -2, 2, 2) for i in page.get_image_info()]
        prev_y1 = None
        for idx, line in enumerate(lines):
            text = line["text"]
            if HEADER.search(text) and len(text) < 150:
                continue
            m = SECTION.match(text)
            if m and len(text) < 140:
                rest = re.sub(r"\(\s*\d+\s*-\s*\d+\s*\)\s*$", "", m.group(2)).strip()
                ca, _, es = rest.partition("/")
                es = re.sub(r"^\s*UT\s*\d+\s*", "", es)
                topic = {"code": int(m.group(1)), "ca": clean(ca), "es": clean(es) or clean(ca)}
                if cur is not None:
                    close_region(regions[cur["num"]], pno, line["y0"])
                    cur, target = None, None
                continue
            if re.fullmatch(r"\s*\(\s*\d+\s*-\s*\d+\s*\)\s*", text):
                continue
            if (pno, idx) in starts:
                num, prefix = starts[(pno, idx)]
                if cur is not None:
                    close_region(regions[cur["num"]], pno, line["y0"])
                cur = {"num": num, "topic": dict(topic), "stem": Target(), "options": []}
                questions.append(cur)
                regions[num] = [[pno, line["y0"], None]]
                target = cur["stem"]
                prev_y1 = None
                spans = strip_prefix(line["spans"], prefix)
            elif cur is not None and (m := OPT_START.match(text)) and len(cur["options"]) < 4 \
                    and m.group(1).lower() == LETTERS[len(cur["options"])]:
                target = Target()
                cur["options"].append(target)
                spans = strip_prefix(line["spans"], m.end())
            elif cur is not None:
                center = pymupdf.Point(line["spans"][0]["bbox"][0] + 1, line["cy"])
                if any(center in r for r in img_rects):
                    continue  # text drawn over a figure
                height = line["y1"] - line["y0"]
                if prev_y1 is not None and line["y0"] - prev_y1 > 0.9 * height and len(text.strip()) < 40:
                    continue  # detached short label (figure caption / legend)
                spans = line["spans"]
            else:
                continue
            if regions[cur["num"]][-1][0] != pno:
                regions[cur["num"]][-1][2] = None
                regions[cur["num"]].append([pno, line["y0"], None])
            for i, s in enumerate(spans):
                text, gap = s["text"], s["bbox"][0] - spans[i - 1]["bbox"][2] if i else 99
                if gap < -1 and text[:1] == spans[i - 1]["text"][-1:]:
                    text = text[1:]  # fragments that overlap repeat the boundary glyph
                target.add(text, s["bold"], glue=gap < 1)
            prev_y1 = line["y1"]
    out = []
    for q in sorted(questions, key=lambda q: q["num"]):
        ca, es = q["stem"].result()
        out.append({
            "num": q["num"],
            "topic": q["topic"],
            "q_ca": ca,
            "q_es": es,
            "options": [dict(zip(("ca", "es"), o.result())) for o in q["options"]],
        })
    return out, regions


def strip_prefix(spans, n):
    """Drop the first n characters (question/option marker) from a list of spans."""
    out = []
    for s in spans:
        if n <= 0:
            out.append(s)
        elif len(s["text"]) <= n:
            n -= len(s["text"])
        else:
            out.append({**s, "text": s["text"][n:]})
            n = 0
    return out


SUSPECT = re.compile(r"(^|\s)[a-d]\)\s|\s\d{1,2}\s*\.-")


SHORT_WORDS = set("a o i y e l d s m h de la el en al es un lo le se si no ja hi ha he va ni te ho me "
                  "ya és sí ús fa li km mb".split())


def problem_count(questions):
    n = 3 * (45 - len(questions))
    for q in questions:
        # word fragments betray a scrambled reading order
        text = " ".join([q["q_ca"], q["q_es"]] + [o[l] for o in q["options"] for l in ("ca", "es")])
        n += sum(1 for t in text.split() if re.fullmatch(r"[a-zà-ú]{1,2}", t) and t not in SHORT_WORDS) / 2
        n += 2 * abs(4 - len(q["options"])) + (len(q["q_ca"]) < 10) + (len(q["q_es"]) < 10)
        n += (len(q["q_ca"]) > 500) + (len(q["q_es"]) > 500)
        for o in q["options"]:
            n += sum(not t or len(t) > 250 or bool(SUSPECT.search(t)) for t in (o["ca"], o["es"]))
    return n


# ---------------------------------------------------------------- figures

def figure_clip(page, y0, y1):
    """Union of images and non-trivial drawings between y0 and y1 on the page."""
    prect = page.rect
    rects = []
    for info in page.get_image_info():
        r = pymupdf.Rect(info["bbox"]) & prect
        if r.is_empty or r.width < 15 or r.height < 15:
            continue
        if r.y1 > y0 and r.y0 < y1:
            rects.append(r)
    for d in page.get_drawings():
        r = d["rect"] & prect
        if r.is_empty or (r.width < 3 and r.height < 3):
            continue
        if r.width > prect.width * 0.8 and r.height < 3:
            continue  # rules / underlines
        if d.get("fill") and min(d["fill"]) > 0.88 and not d.get("color"):
            continue  # near-white background panels
        if r.y1 > y0 and r.y0 < y1 and r.y0 > y0 - 20:
            rects.append(r)
    rects = [r for r in rects if r.width * r.height > 40 or r.width > 20 or r.height > 20]
    # boxes behind text (highlights, framed answers, pasted text) are not figures
    text = [pymupdf.Rect(s["bbox"]) for b in page.get_text("dict", clip=pymupdf.Rect(0, y0 - 20, prect.x1, y1))["blocks"]
            for l in b.get("lines", []) for s in l["spans"] if len(s["text"].strip()) > 3]
    rects = [r for r in rects if sum((r & t).get_area() for t in text) < 0.3 * r.get_area()]
    if not rects:
        return None
    u = pymupdf.Rect(rects[0])
    for r in rects[1:]:
        u |= r
    if u.width < 25 or u.height < 25:
        return None
    return (u + (-4, -4, 4, 4)) & prect


def extract_figures(doc, exam, regions):
    figs = {}
    for num, segs in regions.items():
        best = None
        for seg in segs:
            pno, y0, y_end = seg[0], seg[1], seg[2]
            page = doc[pno]
            y1 = y_end if y_end is not None else page.rect.y1 - 30
            clip = figure_clip(page, y0, y1)
            if clip and (best is None or clip.get_area() > best[1].get_area()):
                best = (pno, clip)
        if best:
            pno, clip = best
            name = f"{exam}_{num:02d}.png"
            doc[pno].get_pixmap(matrix=pymupdf.Matrix(2.5, 2.5), clip=clip, alpha=False).save(FIG_DIR / name)
            figs[num] = name
    return figs


# ---------------------------------------------------------------- main

def parse(pdf):
    exam = pdf.stem
    doc = pymupdf.open(pdf)
    key, conf, key_mode = answer_key(doc)
    # each reading order fails on different source quirks; keep the cleaner result
    questions, regions = min((parse_questions(doc, order) for order in ("native", "y")),
                             key=lambda r: problem_count(r[0]))
    figs = extract_figures(doc, exam, regions)
    for q in questions:
        q["answer"] = KEY_OVERRIDES.get((exam, q["num"]), key.get(q["num"]))
        q["key_scores"] = conf.get(q["num"])
        q["figure"] = figs.get(q["num"])
    return {"exam": exam, "key_mode": key_mode, "key_size": len(key), "questions": questions}


def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = [Path(p) for p in sys.argv[1:]] or sorted(PDF_DIR.glob("*.pdf"))
    for pdf in pdfs:
        data = parse(pdf)
        (OUT_DIR / f"{data['exam']}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
        qs = data["questions"]
        n_opts = sum(len(q["options"]) == 4 for q in qs)
        n_ans = sum(len(q["answer"] or "") == 1 for q in qs)
        print(f"{data['exam']:20s} key={data['key_mode']:14s}/{data['key_size']:2d} "
              f"qs={len(qs):2d} 4opts={n_opts:2d} ans={n_ans:2d} figs={sum(bool(q['figure']) for q in qs)}")


if __name__ == "__main__":
    main()
