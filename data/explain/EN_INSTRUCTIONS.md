# Translating explanations to English

Each `en_batches/batch_NN.json` maps a key to `{"exp": "...", "duda": "..."}` (`duda` is optional).
These are Spanish explanations for questions in the Spanish PER (recreational skipper) exam.

Write `en_out/batch_NN.json` with the same keys and the same fields, in English:

- Translate faithfully and completely. Don't add, drop or "correct" content, and keep every number,
  unit, sign (+/−), light characteristic (e.g. `Oc(3)WRG.12s16-11M`) and rule number unchanged.
- Use standard English nautical terms: babor = port, estribor = starboard, RIPA = COLREGs,
  balizamiento = buoyage (IALA), desvío = deviation, declinación magnética = variation,
  corrección total = total correction, rumbo = course, demora = bearing, abatimiento = leeway,
  escora = heel, asiento = trim, and so on.
- The learner sits the exam in Spanish, so after a key exam term put the Spanish word in
  parentheses the first time it appears, e.g. "trim (asiento)", "down by the head (aproante)".
  Do this sparingly, only for terms the question is about.
- Keep it plain and concise, in the same tone as the original. Output valid JSON only (UTF-8, no
  comments), and make sure every input key is present.
