"use strict";

// Official PER structure: questions per topic (UT1..UT11) in every exam, 45 in total.
const EXAM_PLAN = { 1: 4, 2: 2, 3: 4, 4: 2, 5: 5, 6: 10, 7: 2, 8: 3, 9: 4, 10: 5, 11: 4 };
// Pass rules (Escola Port PER study guide 2024): at least 32 correct (max 13 mistakes) and
// no more than this many mistakes in these units. An unanswered question counts as a mistake.
const PASS_MARK = 32;
const MAX_ERRORS = 45 - PASS_MARK;
const UNIT_MAX_ERRORS = { 5: 2, 6: 5, 11: 2 };
// Failing the PER can still pass the PNB part: UT1–6 with at most 10 mistakes (UT5/UT6 limits apply).
const PNB_UNITS = [1, 2, 3, 4, 5, 6];
const PNB_MAX_ERRORS = 10;
const EXAM_SECONDS = 90 * 60;
const LETTERS = "abcd";

const state = {
  bank: [],
  lang: load("per.lang", "es"),
  stats: load("per.stats", {}),
  session: null, // {mode, items, i, answers, startedAt, timer}
};

function load(k, fallback) {
  try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : fallback; } catch { return fallback; }
}
function save(k, v) {
  try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable: progress just isn't kept */ }
}

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, props = {}, ...kids) => {
  const n = Object.assign(document.createElement(tag), props);
  n.append(...kids.filter((k) => k != null));
  return n;
};
const topicName = (t) => `UT${t.code} · ${t[state.lang]}`;
const stem = (q) => q["q_" + state.lang] || q.q_es;
const optText = (q, i) => q.options[i][state.lang] || q.options[i].es;

function shuffle(a) {
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// ------------------------------------------------------------------ selection

function priority(q) {
  const s = state.stats[q.key];
  const freq = Math.sqrt(q.count);
  if (!s) return 2 * freq;
  if (!s.last) return 3 * freq;
  return freq / (1 + s.ok);
}

function pickWeighted(pool, n, weight) {
  // weighted sampling without replacement (Efraimidis–Spirakis keys)
  return pool
    .map((q) => ({ q, k: Math.pow(Math.random(), 1 / Math.max(weight(q), 1e-6)) }))
    .sort((a, b) => b.k - a.k)
    .slice(0, n)
    .map((x) => x.q);
}

function buildExam(recent) {
  const items = [];
  for (const [code, n] of Object.entries(EXAM_PLAN)) {
    const pool = state.bank.filter((q) => q.topic.code === +code);
    const year = (q) => +q.last_seen.slice(0, 4);
    items.push(...pickWeighted(pool, n, (q) => Math.sqrt(q.count) * (recent ? Math.pow(2, year(q) - 2020) : 1)));
  }
  return items;
}

function buildPractice(codes, n) {
  const pool = state.bank.filter((q) => codes.includes(q.topic.code));
  const picked = pickWeighted(pool, n || pool.length, priority);
  return picked;
}

function buildReview() {
  return shuffle(state.bank.filter((q) => state.stats[q.key] && !state.stats[q.key].last));
}

// ------------------------------------------------------------------ views

function go(where) {
  stopTimer();
  if (where === "home") return renderHome();
  let items, mode = where;
  if (where === "exam") {
    items = buildExam($("#exam-recent").checked);
    state.session = { mode, items, i: 0, answers: [], timed: $("#exam-timer").checked, startedAt: Date.now() };
  } else if (where === "practice") {
    const codes = [...document.querySelectorAll("#topic-picks input:checked")].map((i) => +i.value);
    if (!codes.length) return alert("Elige al menos un tema.");
    items = buildPractice(codes, +$("#practice-n").value);
    state.session = { mode, items, i: 0, answers: [] };
  } else if (where === "review") {
    items = buildReview();
    if (!items.length) return;
    state.session = { mode, items, i: 0, answers: [] };
  }
  renderQuestion();
}

function renderHome() {
  state.session = null;
  const view = $("#view");
  view.replaceChildren($("#tpl-home").content.cloneNode(true));

  const withExp = state.bank.filter((q) => q.explanation).length;
  $("#bank-summary").textContent =
    `${state.bank.length} preguntas únicas de 141 exámenes oficiales (2017–2026), ${withExp} con explicación.`;

  const topics = topicsInBank();
  const picks = $("#topic-picks");
  const chosen = load("per.topics", topics.map((t) => t.code));
  for (const t of topics) {
    const input = el("input", { type: "checkbox", value: t.code, checked: chosen.includes(t.code) });
    input.addEventListener("change", () =>
      save("per.topics", [...picks.querySelectorAll("input:checked")].map((i) => +i.value)));
    picks.append(el("label", { title: t[state.lang] }, input, `UT${t.code}`));
  }

  const wrong = buildReview().length;
  $("#review-count").textContent = wrong
    ? `${wrong} preguntas cuya última respuesta fue incorrecta.`
    : "Aún no tienes fallos pendientes. Aparecerán aquí al practicar.";
  $('[data-go="review"]').disabled = !wrong;

  const prog = $("#progress");
  for (const t of topics) {
    const qs = state.bank.filter((q) => q.topic.code === t.code);
    let ok = 0, bad = 0;
    for (const q of qs) {
      const s = state.stats[q.key];
      if (s) s.last ? ok++ : bad++;
    }
    const pct = (x) => `${(100 * x) / qs.length}%`;
    prog.append(el("div", { className: "prog-row" },
      el("span", {}, topicName(t)),
      el("div", { className: "prog-bar", title: `${ok} bien · ${bad} mal · ${qs.length - ok - bad} sin ver` },
        el("div", { className: "ok", style: `width:${pct(ok)}` }),
        el("div", { className: "bad", style: `width:${pct(bad)}` })),
      el("span", { className: "num" }, `${ok + bad}/${qs.length}`)));
  }

  $("#reset").addEventListener("click", () => {
    if (!confirm("¿Borrar todo tu progreso?")) return;
    state.stats = {};
    save("per.stats", state.stats);
    renderHome();
  });
}

function topicsInBank() {
  const seen = new Map();
  for (const q of state.bank) seen.set(q.topic.code, q.topic);
  return [...seen.values()].sort((a, b) => a.code - b.code);
}

function renderQuestion() {
  const s = state.session;
  const q = s.items[s.i];
  const view = $("#view");
  view.replaceChildren($("#tpl-question").content.cloneNode(true));
  const exam = s.mode === "exam";

  $(".counter").textContent = `${s.i + 1} / ${s.items.length}`;
  $(".bar-fill").style.width = `${(100 * s.i) / s.items.length}%`;
  $(".quit").addEventListener("click", () => (exam && !confirm("¿Abandonar el examen?") ? null : go("home")));
  $(".meta").textContent = `${topicName(q.topic)} · en ${q.count} examen${q.count > 1 ? "es" : ""}, último ${q.last_seen}`;
  $(".stem").textContent = stem(q);
  if (q.figure) {
    $(".fig").hidden = false;
    const img = $(".fig img");
    img.addEventListener("error", () => {
      img.replaceWith(el("p", { className: "fig-error" },
        `No se pudo cargar el dibujo (figures/${q.figure}). Recarga la página; si sigue fallando, abre app/index.html de nuevo.`));
    }, { once: true });
    img.src = "figures/" + q.figure;
  }

  const list = $(".options");
  q.options.forEach((_, i) => {
    const b = el("button", { type: "button" }, el("span", { className: "letter" }, LETTERS[i]), el("span", {}, optText(q, i)));
    b.addEventListener("click", () => answer(i));
    list.append(el("li", {}, b));
  });

  const next = $(".next");
  next.textContent = s.i === s.items.length - 1 ? (exam ? "Corregir examen" : "Terminar") : "Siguiente";
  next.addEventListener("click", advance);
  if (exam) {
    const prev = $(".prev");
    prev.hidden = s.i === 0;
    prev.addEventListener("click", () => { s.i--; renderQuestion(); });
    if (s.timed) startTimer();
  }

  if (s.answers[s.i] != null) paintAnswer(s.answers[s.i]);
  else if (!exam) {
    // in practice the answer is required to move on, unless the question is skipped
    next.disabled = true;
    const skip = $(".skip");
    skip.hidden = false;
    skip.addEventListener("click", advance);
  }
}

function answer(i) {
  const s = state.session;
  const exam = s.mode === "exam";
  if (!exam && s.answers[s.i] != null) return; // practice answers are final
  s.answers[s.i] = i;
  if (!exam) record(s.items[s.i], i);
  paintAnswer(i);
}

function paintAnswer(i) {
  const s = state.session;
  const q = s.items[s.i];
  const buttons = [...document.querySelectorAll(".options button")];
  if (s.mode === "exam") {
    buttons.forEach((b, j) => b.classList.toggle("chosen", j === i));
    return;
  }
  const right = q.answer.includes(i);
  buttons.forEach((b, j) => {
    b.disabled = true;
    if (q.answer.includes(j)) b.classList.add("correct");
    else if (j === i) b.classList.add("wrong");
  });
  showFeedback(q, right);
  $(".skip").hidden = true;
  $(".next").disabled = false;
  $(".next").focus();
}

function showFeedback(q, right) {
  $(".feedback").hidden = false;
  const v = $(".verdict");
  v.textContent = right ? "¡Correcto!" : `Incorrecto. La respuesta es la ${q.answer.map((a) => LETTERS[a]).join(" / ")}.`;
  v.className = "verdict " + (right ? "ok" : "bad");
  $(".explanation").textContent = q.explanation || "Sin explicación disponible para esta pregunta.";
  const lights = lightDiagrams(q, state.lang);
  if (lights) $(".explanation").after(lights);
  if (q.doubt) {
    $(".doubt").hidden = false;
    $(".doubt").textContent = "Ojo: " + q.doubt;
  }
}

function record(q, i) {
  const s = state.stats[q.key] || { n: 0, ok: 0 };
  const right = q.answer.includes(i);
  s.n++;
  if (right) s.ok++;
  s.last = right ? 1 : 0;
  s.t = Date.now();
  state.stats[q.key] = s;
  save("per.stats", state.stats);
}

function advance() {
  const s = state.session;
  if (s.i < s.items.length - 1) {
    s.i++;
    renderQuestion();
  } else if (s.mode === "exam") {
    finishExam();
  } else {
    renderPracticeSummary();
  }
}

// ------------------------------------------------------------------ exam timer

function startTimer() {
  const s = state.session;
  const t = $(".timer");
  t.hidden = false;
  const tick = () => {
    const left = Math.max(0, EXAM_SECONDS - Math.floor((Date.now() - s.startedAt) / 1000));
    t.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
    t.classList.toggle("low", left < 300);
    if (!left) finishExam();
  };
  tick();
  s.timer = setInterval(tick, 1000);
}

function stopTimer() {
  if (state.session?.timer) clearInterval(state.session.timer);
}

// ------------------------------------------------------------------ results

function finishExam() {
  stopTimer();
  const s = state.session;
  s.items.forEach((q, i) => { if (s.answers[i] != null) record(q, s.answers[i]); });
  renderResults(s.items, s.answers, true);
}

function gradeExam(byTopic, errors) {
  const errs = (code) => { const r = byTopic.get(code); return r ? r.n - r.ok : 0; };
  const reasons = [];
  if (errors > MAX_ERRORS) reasons.push(`${errors} fallos en total (máximo ${MAX_ERRORS}).`);
  for (const [code, max] of Object.entries(UNIT_MAX_ERRORS)) {
    const e = errs(+code);
    if (e > max) reasons.push(`${e} fallos en ${topicName(byTopic.get(+code).t)} (máximo ${max}).`);
  }
  const pnbErrors = PNB_UNITS.reduce((s, c) => s + errs(c), 0);
  const pnbPass = pnbErrors <= PNB_MAX_ERRORS && errs(5) <= UNIT_MAX_ERRORS[5] && errs(6) <= UNIT_MAX_ERRORS[6];
  return { pass: !reasons.length, reasons, pnbPass };
}

function renderPracticeSummary() {
  const s = state.session;
  renderResults(s.items, s.answers, false);
}

function renderResults(items, answers, exam) {
  const view = $("#view");
  view.replaceChildren($("#tpl-results").content.cloneNode(true));
  const right = items.filter((q, i) => q.answer.includes(answers[i])).length;
  $(".score").textContent = `${right} / ${items.length}`;
  const v = $(".verdict-big");

  const byTopic = new Map();
  items.forEach((q, i) => {
    const r = byTopic.get(q.topic.code) || { t: q.topic, n: 0, ok: 0 };
    r.n++;
    if (q.answer.includes(answers[i])) r.ok++;
    byTopic.set(q.topic.code, r);
  });

  if (exam) {
    const g = gradeExam(byTopic, items.length - right);
    v.textContent = g.pass ? `Aprobado (${items.length - right} fallos)` : "Suspenso";
    v.className = "verdict-big " + (g.pass ? "ok" : "bad");
    if (!g.pass) {
      v.after(el("ul", { className: "fail-reasons" }, ...g.reasons.map((r) => el("li", {}, r))));
      if (g.pnbPass) {
        $(".fail-reasons").after(el("p", { className: "pnb-note" },
          "Has aprobado el parcial PNB (UT1–6). Puedes tramitar el título de PNB o conservar esta parte " +
          "para las dos convocatorias siguientes haciendo la prueba complementaria (UT7–11, máx. 3 fallos)."));
      }
    }
  } else {
    const answered = answers.filter((a) => a != null).length;
    const skipped = items.length - answered;
    v.textContent = answered
      ? `${Math.round((100 * right) / answered)}% de aciertos en ${answered} respondida${answered > 1 ? "s" : ""}`
      : "No has respondido ninguna pregunta";
    if (skipped) v.textContent += ` · ${skipped} saltada${skipped > 1 ? "s" : ""}`;
  }

  const rows = [...byTopic.values()].sort((a, b) => a.t.code - b.t.code).map((r) => {
    const max = exam ? UNIT_MAX_ERRORS[r.t.code] : undefined;
    const over = max != null && r.n - r.ok > max;
    return el("tr", { className: over ? "over" : "" },
      el("td", {}, topicName(r.t)),
      el("td", { className: "n" }, `${r.ok} / ${r.n}`),
      exam ? el("td", { className: "n" }, max != null ? `${r.n - r.ok} / ${max}` : `${r.n - r.ok}`) : null);
  });
  const head = el("tr", {}, el("th", {}, "Tema"), el("th", { className: "n" }, "Aciertos"),
    exam ? el("th", { className: "n" }, "Fallos / máx.") : null);
  $(".topic-table").append(el("table", {}, el("thead", {}, head), el("tbody", {}, ...rows)));

  const list = $(".review-list");
  items.forEach((q, i) => {
    const ok = q.answer.includes(answers[i]);
    const yours = answers[i] == null ? "sin responder" : `${LETTERS[answers[i]]}) ${optText(q, answers[i])}`;
    list.append(el("div", { className: "review-item" + (ok ? "" : " bad") },
      el("p", { className: "stem" }, `${i + 1}. ${stem(q)}`),
      q.figure ? el("img", { src: "figures/" + q.figure, alt: "" }) : null,
      ok ? null : el("p", {}, `Tu respuesta: ${yours}`),
      el("p", {}, el("strong", {}, "Correcta: "), q.answer.map((a) => `${LETTERS[a]}) ${optText(q, a)}`).join(" / ")),
      q.explanation ? el("p", { className: "fine" }, q.explanation) : null,
      lightDiagrams(q, state.lang)));
  });
  $('[data-go="home"]', view).addEventListener("click", () => go("home"));
  window.scrollTo(0, 0);
}

// ------------------------------------------------------------------ wiring

function setLang(lang) {
  state.lang = lang;
  save("per.lang", lang);
  document.querySelectorAll("[data-lang]").forEach((b) => b.classList.toggle("on", b.dataset.lang === lang));
  if (state.session && $(".q")) renderQuestion();
  else if (!state.session) renderHome();
}

document.addEventListener("click", (e) => {
  const g = e.target.closest("[data-go]");
  if (g && !g.closest(".results")) go(g.dataset.go);
  const l = e.target.closest("[data-lang]");
  if (l) setLang(l.dataset.lang);
});

document.addEventListener("keydown", (e) => {
  if (!state.session || !$(".q") || e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key.toLowerCase();
  const idx = "1234".indexOf(k) >= 0 ? "1234".indexOf(k) : LETTERS.indexOf(k);
  if (idx >= 0 && k.length === 1) {
    e.preventDefault();
    answer(idx);
  } else if (e.key === "Enter" && !$(".next").disabled) {
    e.preventDefault();
    advance();
  } else if (k === "s" && (!$(".skip").hidden || state.session.mode === "exam")) {
    e.preventDefault();
    advance(); // skip; in the exam an unanswered question can be revisited with "Anterior"
  }
});

if (window.BANK) {
  state.bank = window.BANK.filter((q) => q.answer.length && q.options.length === 4);
  setLang(state.lang);
} else {
  $("#view").textContent = "No se pudo cargar bank.js. Regenera el banco con scripts/build_bank.py (ver README).";
}
