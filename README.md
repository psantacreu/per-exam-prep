# PER exam prep

Question bank and local quiz app built from the 141 official PER exams in `data/pdfs/`.

## Run the app

Open `app/index.html` directly in a browser: no server is needed. Or serve it, with caching disabled
so a rebuilt bank is always picked up:

```bash
python3 scripts/serve.py
```

Then open http://localhost:8765. Progress is kept in the browser's localStorage. Opening the file
and opening the server URL are different origins, so each keeps its own progress.

## Rebuild the data

Needs Python 3.13 with the packages in `requirements.txt`:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/python scripts/parse_exams.py      # PDFs -> data/parsed/*.json + figures
.venv/bin/python scripts/validate.py         # parse-quality report
.venv/bin/python scripts/merge_explanations.py
.venv/bin/python scripts/build_bank.py       # dedupe -> data/bank.json, app/bank.json, app/figures/
```

- **Answer keys** come from page 1 of each PDF: vector sheets are read by sampling the cell behind
  each letter; four scanned sheets (OCT26, JUN23) by blob detection. A cell counts as marked when
  it is filled, so a question can have several accepted answers; all four filled means annulled.
  `KEY_OVERRIDES` in `parse_exams.py` holds hand corrections (PER-JUN23-2 Q5).
- **Text**: bold is Catalan, regular is Spanish. Each exam is parsed in content-stream order and in
  top-to-bottom order, and the cleaner result is kept.
- **Dedupe** matches the Catalan stem and option set. Fuzzy merges are allowed only when the numbers
  and the correct answer match too. Figure questions with the same wording but different answers
  stay separate.
- **Explanations** (Spanish) were generated per batch following `data/explain/INSTRUCTIONS.md`.
  They are stored in `data/explanations.json`, and the app shows the `duda` notes, where the
  generator questioned the official key, as "Ojo".

- **Cache stamps**: `build_bank.py` also writes `app/bank.js` and adds a content hash to every script
  and stylesheet URL in `app/index.html`. Re-run it after editing the app's JS or CSS.
- **Hand review** lives in `data/review_overrides.json` and is applied last by `build_bank.py`.
  Each item points at one exam occurrence (`"EXAM#num"`) and can fix the answer (by Catalan option
  text), the question or option text, the explanation, or the note (`"doubt": null` removes it).

Eight questions are missing from the source PDFs themselves (e.g. PER_ABR24_2 Q6).
