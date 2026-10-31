"use strict";

// Light characteristics as written on charts (e.g. "Oc(3)WRG.12s16-11M", "Gp Oc (2) 6s 11m 9M"):
// parse them and draw one period of the light as a timeline. Durations of each flash/occultation
// are not part of the characteristic, so the drawing uses typical proportions.

const LIGHT_RE = new RegExp(
  String.raw`(?:\bGp\.?\s*)?\b(LFl|Fl|Oc|Iso|VQ|Q|F)\.?\s*` + // rhythm
  String.raw`(?:\(\s*([\d+]+)\s*\))?\s*\.?\s*` + // group: (3) or (2+1)
  String.raw`((?:(?:W|R|G|Y|Bu)\.?\s*){0,4})` + // colours / sectors
  String.raw`(\d+(?:[.,]\d+)?)\s*s(?![a-zA-Z])` + // period ("12s16-11M" runs on into the range)
  String.raw`(?:\s*(\d+)\s*m(?![a-zA-Z]))?` + // elevation
  String.raw`(?:\s*(\d+(?:\s*-\s*\d+)*)\s*M(?![a-zA-Z]))?`, // nominal range(s)
  "g",
);

const COLOR = {
  W: { fill: "#fff3b0", es: "blanca", ca: "blanca" },
  R: { fill: "#e0352b", es: "roja", ca: "vermella" },
  G: { fill: "#1fa64a", es: "verde", ca: "verda" },
  Y: { fill: "#f2b705", es: "amarilla", ca: "groga" },
  Bu: { fill: "#2a6fdb", es: "azul", ca: "blava" },
};

const RHYTHM = {
  Fl: { es: ["destello", "destellos"], ca: ["llampada", "llampades"] },
  LFl: { es: ["destello largo", "destellos largos"], ca: ["llampada llarga", "llampades llargues"] },
  Oc: { es: ["ocultación", "ocultaciones"], ca: ["ocultació", "ocultacions"] },
  Iso: { es: ["isofase", "isofase"], ca: ["isofase", "isofase"] },
  Q: { es: ["centelleo", "centelleos"], ca: ["centelleig", "centellejos"] },
  VQ: { es: ["centelleo rápido", "centelleos rápidos"], ca: ["centelleig ràpid", "centellejos ràpids"] },
  F: { es: ["fija", "fija"], ca: ["fixa", "fixa"] },
};

function parseLights(text) {
  const out = [];
  for (const m of text.matchAll(LIGHT_RE)) {
    const colors = (m[3].match(/Bu|W|R|G|Y/g) || ["W"]);
    out.push({
      code: m[0].trim().replace(/[.)\s]+$/, ""),
      rhythm: m[1],
      groups: m[2] ? m[2].split("+").map(Number) : [1],
      colors,
      period: parseFloat(m[4].replace(",", ".")),
      height: m[5] ? +m[5] : null,
      ranges: m[6] ? m[6].split("-").map((r) => +r.trim()) : null,
    });
  }
  return out;
}

// [start, end] intervals (seconds) during which the light is ON within one period
function onIntervals(l) {
  const P = l.period;
  const seq = (unit, gap, groupGap) => {
    const marks = [];
    let t = 0;
    l.groups.forEach((n, gi) => {
      if (gi) t += groupGap - gap;
      for (let i = 0; i < n; i++) {
        marks.push([t, t + unit]);
        t += unit + gap;
      }
    });
    const used = t - gap;
    const scale = used > 0.6 * P ? (0.6 * P) / used : 1; // keep a visible pause at the end
    return marks.map(([a, b]) => [a * scale, b * scale]);
  };
  switch (l.rhythm) {
    case "F": return [[0, P]];
    case "Iso": return [[0, P / 2]];
    case "Fl": return seq(0.6, 1.2, 3);
    case "LFl": return seq(2, 1.5, 3.5);
    case "Q": return seq(0.4, 0.6, 2);
    case "VQ": return seq(0.25, 0.25, 1.5);
    case "Oc": {
      // light is on except for the occultations, which come after a lit lead-in
      const dark = seq(0.8, 1.0, 2.5).map(([a, b]) => [a + 1, b + 1]);
      const on = [];
      let t = 0;
      for (const [a, b] of dark) {
        on.push([t, a]);
        t = b;
      }
      on.push([t, P]);
      return on;
    }
  }
  return [];
}

function describeLight(l, lang) {
  const r = RHYTHM[l.rhythm][lang];
  const n = l.groups.reduce((a, b) => a + b, 0);
  const parts = [];
  if (l.rhythm === "F") parts.push(lang === "es" ? "luz fija" : "llum fixa");
  else if (l.rhythm === "Iso") parts.push(lang === "es" ? "isofase: luz y oscuridad iguales" : "isofase: llum i foscor iguals");
  else if (l.groups.length > 1) parts.push(`${lang === "es" ? "grupos compuestos de" : "grups compostos de"} ${l.groups.join("+")} ${r[1]}`);
  else if (n > 1) parts.push(`${lang === "es" ? "grupos de" : "grups de"} ${n} ${r[1]}`);
  else parts.push(r[0]);
  const names = l.colors.map((c) => COLOR[c][lang]);
  const list = names.length > 1
    ? `${names.slice(0, -1).join(", ")} ${lang === "es" ? "y" : "i"} ${names.at(-1)}`
    : names[0];
  if (l.colors.length > 1) parts.push(`${lang === "es" ? "sectores de luz" : "sectors de llum"} ${list}`);
  else parts.push(`${lang === "es" ? "luz" : "llum"} ${list}`);
  parts.push(`${lang === "es" ? "periodo" : "període"} ${String(l.period).replace(".", ",")} s`);
  if (l.height) parts.push(`${lang === "es" ? "elevación" : "elevació"} ${l.height} m`);
  if (l.ranges) {
    const unit = lang === "es" ? "millas" : "milles";
    parts.push(`${lang === "es" ? "alcance" : "abast"} ${l.ranges.join("–")} ${unit}` +
      (l.ranges.length > 1 && l.ranges.length === l.colors.length ? ` (${l.colors.join(", ")})` : ""));
  }
  return parts.join(" · ");
}

function lightSVG(l) {
  const W = 520, H = 74, x0 = 10, x1 = W - 10, bar = 22, y = 10;
  const sx = (t) => x0 + ((x1 - x0) * t) / l.period;
  const fill = l.colors.length === 1 ? COLOR[l.colors[0]].fill : "#fff3b0";
  const on = onIntervals(l)
    .filter(([a, b]) => b > a)
    .map(([a, b]) => `<rect x="${sx(a).toFixed(1)}" y="${y}" width="${Math.max(2, sx(b) - sx(a)).toFixed(1)}" height="${bar}" rx="3" fill="${fill}" stroke="#8a6d00" stroke-width="0.8"/>`)
    .join("");
  const step = l.period <= 6 ? 1 : l.period <= 15 ? 2 : 5;
  let ticks = "";
  for (let t = 0; t <= l.period + 1e-6; t += step) {
    ticks += `<line x1="${sx(t)}" y1="${y + bar + 4}" x2="${sx(t)}" y2="${y + bar + 9}" class="lt-axis"/>` +
      `<text x="${sx(t)}" y="${y + bar + 22}" class="lt-tick">${t}s</text>`;
  }
  const sectors = l.colors.length > 1
    ? l.colors.map((c, i) => `<rect x="${x1 - 18 * (l.colors.length - i)}" y="${H - 14}" width="14" height="10" rx="2" fill="${COLOR[c].fill}" stroke="#666" stroke-width="0.5"/>`).join("")
    : "";
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${l.code}">` +
    `<rect x="${x0}" y="${y}" width="${x1 - x0}" height="${bar}" rx="3" class="lt-dark"/>` +
    on + `<line x1="${x0}" y1="${y + bar + 4}" x2="${x1}" y2="${y + bar + 4}" class="lt-axis"/>` + ticks + sectors + `</svg>`;
}

// Diagrams for the light characteristics in the question and its correct answer(s).
function lightDiagrams(q, lang) {
  const texts = [q.q_es, ...q.answer.map((i) => q.options[i].es)];
  const seen = new Set();
  const lights = texts.flatMap(parseLights).filter((l) => !seen.has(l.code) && seen.add(l.code));
  if (!lights.length) return null;
  const box = document.createElement("div");
  box.className = "lights";
  for (const l of lights) {
    const fig = document.createElement("figure");
    fig.className = "light";
    fig.innerHTML = `<figcaption><code>${l.code}</code> <span>${describeLight(l, lang)}</span></figcaption>${lightSVG(l)}`;
    box.append(fig);
  }
  return box;
}
