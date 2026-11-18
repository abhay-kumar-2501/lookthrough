/* Shared helpers and charts. Every page loads this file; each chart is a function that takes the
   element to draw into and the data to draw, so the same chart can appear on more than one page. */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const svgEl = (tag, attrs = {}, text) => { const e = document.createElementNS("http://www.w3.org/2000/svg", tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (text != null) e.textContent = text; return e; };
const bn = (v, d = 1) => (v / 1e9).toLocaleString("en-US", {minimumFractionDigits: d, maximumFractionDigits: d});
const B = (v, d = 0) => v == null ? "n/a" : (v < 0 ? "-" : "") + "$" + bn(Math.abs(v), d) + "bn";
const pct = (v, d = 0) => v == null ? "n/a" : (v * 100).toFixed(d) + "%";
const money = v => "$" + Math.round(v).toLocaleString("en-US");
const mon = iso => new Date(iso + "T00:00:00").toLocaleDateString("en-US", {month: "short", year: "numeric"});
const full = iso => new Date(iso + "T00:00:00").toLocaleDateString("en-US", {month: "long", day: "numeric", year: "numeric"});
const qLabel = q => `Q${q.slice(5)} '${q.slice(2, 4)}`;
const sum = (rows, f) => rows.reduce((s, r) => s + (f(r) || 0), 0);

const TICKERS = ["MSFT", "GOOGL", "AMZN", "META", "ORCL", "CRWV"];
const COLOR = Object.fromEntries(TICKERS.map((t, i) => [t, `var(--s${i + 1})`]));
const dot = t => `<i class="dot" style="display:inline-block;width:9px;height:9px;margin-right:7px;background:${COLOR[t]}"></i>`;

function tipOf(chart) { let t = chart.querySelector(".tip"); if (!t) { t = document.createElement("div"); t.className = "tip"; chart.prepend(t); } return t; }
function showTip(chart, html, x, y) {
  const tip = tipOf(chart); tip.innerHTML = html; tip.style.opacity = 1;
  tip.style.left = Math.max(0, Math.min(chart.clientWidth - tip.offsetWidth, x + 12)) + "px"; tip.style.top = Math.max(0, y - 10) + "px";
}
const hideTip = chart => { tipOf(chart).style.opacity = 0; };
function hover(el, chart, html, pos) {
  const show = () => { const [x, y] = pos(); showTip(chart, html, x, y); };
  el.addEventListener("pointermove", show); el.addEventListener("focus", show);
  el.addEventListener("pointerleave", () => hideTip(chart)); el.addEventListener("blur", () => hideTip(chart));
}
const legend = items => items.map(([c, l, o]) => `<span><i style="background:${c}${o ? ";opacity:" + o : ""}"></i>${l}</span>`).join("");
function fresh(chart) { chart.querySelector("svg")?.remove(); tipOf(chart); return chart; }

const Charts = {
  /* The same balance in every fund: stacked horizontal bars, one row per fund. */
  funds(chart, funds, groups, selected, bal, onPick) {
    fresh(chart);
    const total = f => groups.reduce((s, g) => s + f[g.key], 0);
    const rows = funds.slice().sort((a, b) => total(b) - total(a));
    const W = 720, row = 36, m = {t: 6, r: 74, b: 22, l: 212}, H = m.t + row * rows.length + m.b, max = 60;
    const x = v => m.l + (W - m.l - m.r) * v / max;
    const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Share of each fund in AI-linked companies"});
    for (let v = 0; v <= max; v += 10) { svg.append(svgEl("line", {class: "grid", x1: x(v), x2: x(v), y1: m.t, y2: H - m.b})); svg.append(svgEl("text", {x: x(v), y: H - 6, "text-anchor": "middle"}, v + "%")); }
    rows.forEach((f, i) => {
      const cy = m.t + row * i + row / 2; let acc = 0;
      svg.append(svgEl("text", {x: m.l - 10, y: cy + 4, "text-anchor": "end", class: f.key === selected ? "val" : "", style: "font-family:var(--sans)"}, f.name.replace(/ \(.*\)/, "")));
      groups.forEach(g => { const w = x(acc + f[g.key]) - x(acc); if (w > 1.5) svg.append(svgEl("rect", {x: x(acc) + 1, y: cy - 8, width: Math.max(0, w - 2), height: 16, fill: g.color, opacity: f.key === selected ? 1 : .5})); acc += f[g.key]; });
      svg.append(svgEl("text", {x: x(acc) + 8, y: cy + 4, class: "val"}, bal ? money(bal * acc / 100) : acc.toFixed(0) + "%"));
      const hit = svgEl("rect", {x: 0, y: cy - row / 2, width: W, height: row, fill: "transparent", tabindex: 0, style: onPick ? "cursor:pointer" : "", role: onPick ? "button" : "img", "aria-label": `${f.name}: ${acc.toFixed(0)} percent`});
      hover(hit, chart, `<b>${esc(f.name)}</b>` + groups.map(g => `<div><span><i style="background:${g.color}"></i>${g.label}</span><span>${f[g.key].toFixed(1)}%</span></div>`).join("") + `<div><span>As of</span><span>${mon(f.as_of)}</span></div>`,
        () => [x(acc) / W * chart.clientWidth, (cy - row / 2) / H * chart.clientHeight]);
      if (onPick) { hit.addEventListener("click", () => onPick(f.key)); hit.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(f.key); } }); }
      svg.append(hit);
    });
    chart.append(svg);
  },

  /* Leases signed but not yet started, by quarter and company. */
  leases(chart, series, names) {
    fresh(chart);
    const W = 720, H = 330, m = {t: 24, r: 8, b: 28, l: 52}, n = series.length;
    const totals = series.map(q => TICKERS.reduce((s, t) => s + (q.values[t] || 0), 0));
    const max = Math.ceil(Math.max(...totals) / 2.5e11) * 2.5e11;
    const y = v => m.t + (H - m.t - m.b) * (1 - v / max), band = (W - m.l - m.r) / n, bw = Math.min(34, band - 6);
    const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Leases signed but not yet started, by quarter and company"});
    for (let v = 0; v <= max; v += 2.5e11) { svg.append(svgEl("line", {class: "grid", x1: m.l, x2: W - m.r, y1: y(v), y2: y(v)})); svg.append(svgEl("text", {x: m.l - 8, y: y(v) + 4, "text-anchor": "end"}, v === 0 ? "0" : "$" + (v / 1e9) + "bn")); }
    series.forEach((q, i) => {
      const x = m.l + band * i + (band - bw) / 2; let acc = 0;
      TICKERS.forEach(t => { const v = q.values[t]; if (!v) return; const y1 = y(acc + v), h = y(acc) - y1; if (h > 2.5) svg.append(svgEl("rect", {x, y: y1 + 1, width: bw, height: h - 2, fill: COLOR[t]})); acc += v; });
      if (i === n - 1 || i === 0) svg.append(svgEl("text", {class: "val", x: x + bw / 2, y: y(acc) - 6, "text-anchor": i === n - 1 ? "end" : "middle"}, "$" + bn(acc, 0) + "bn"));
      if (i % 2 === (n - 1) % 2) svg.append(svgEl("text", {x: x + bw / 2, y: H - 8, "text-anchor": "middle"}, qLabel(q.quarter)));
      const hit = svgEl("rect", {x: m.l + band * i, y: m.t, width: band, height: H - m.t - m.b, fill: "transparent", tabindex: 0, "aria-label": `${qLabel(q.quarter)} total $${bn(acc, 0)} billion`});
      hover(hit, chart, `<b>${qLabel(q.quarter)} · $${bn(acc, 0)}bn</b>` + TICKERS.slice().reverse().filter(t => q.values[t]).map(t => `<div><span><i style="background:${COLOR[t]}"></i>${names[t]}</span><span>$${bn(q.values[t])}bn</span></div>`).join(""),
        () => [(x + bw) / W * chart.clientWidth, y(acc) / H * chart.clientHeight]);
      svg.append(hit);
    });
    chart.append(svg);
  },

  /* Present value of those leases: pale bar is total payments, solid bar is today's value, line is the range. */
  presentValue(chart, pvRows, names) {
    fresh(chart);
    const rows = pvRows.slice().sort((a, b) => b.base - a.base);
    const W = 720, row = 44, m = {t: 6, r: 150, b: 22, l: 92}, H = m.t + row * rows.length + m.b, max = Math.ceil(Math.max(...rows.map(r => r.undiscounted)) / 1e11) * 1e11;
    const x = v => m.l + (W - m.l - m.r) * v / max;
    const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Present value of leases not yet started, by company"});
    for (let v = 0; v <= max; v += 1e11) { svg.append(svgEl("line", {class: "grid", x1: x(v), x2: x(v), y1: m.t, y2: H - m.b})); svg.append(svgEl("text", {x: x(v), y: H - 6, "text-anchor": "middle"}, v === 0 ? "0" : "$" + v / 1e9 + "bn")); }
    rows.forEach((r, i) => {
      const cy = m.t + row * i + row / 2;
      svg.append(svgEl("text", {x: m.l - 10, y: cy + 4, "text-anchor": "end", class: "val", style: "font-family:var(--sans)"}, names[r.ticker]));
      svg.append(svgEl("rect", {x: x(0), y: cy - 9, width: x(r.undiscounted) - x(0), height: 18, fill: COLOR[r.ticker], opacity: .22}));
      svg.append(svgEl("rect", {x: x(0), y: cy - 9, width: x(r.base) - x(0), height: 18, fill: COLOR[r.ticker]}));
      svg.append(svgEl("line", {x1: x(r.low), x2: x(r.high), y1: cy, y2: cy, stroke: "var(--text)", "stroke-width": 1.5}));
      [r.low, r.high].forEach(v => svg.append(svgEl("line", {x1: x(v), x2: x(v), y1: cy - 5, y2: cy + 5, stroke: "var(--text)", "stroke-width": 1.5})));
      svg.append(svgEl("text", {x: x(r.undiscounted) + 8, y: cy + 4, class: "val"}, `${B(r.base)} of ${B(r.undiscounted)}`));
      const hit = svgEl("rect", {x: m.l, y: cy - row / 2, width: W - m.l, height: row, fill: "transparent", tabindex: 0, "aria-label": `${names[r.ticker]} present value ${B(r.base)}`});
      hover(hit, chart, `<b>${names[r.ticker]}</b><div><span>Total payments</span><span>${B(r.undiscounted, 1)}</span></div><div><span>Worth today</span><span>${B(r.base, 1)}</span></div><div><span>Low to high</span><span>${B(r.low)} – ${B(r.high)}</span></div><div><span>Discount rate</span><span>${(r.rate * 100).toFixed(1)}%</span></div><div><span>Lease term used</span><span>${r.term.toFixed(0)} yrs</span></div>`,
        () => [x(r.base) / W * chart.clientWidth, (cy - row / 2) / H * chart.clientHeight]);
      svg.append(hit);
    });
    chart.append(svg);
  },

  /* Capital spending as a share of the cash each business brings in. */
  capexShare(chart, funding, names) {
    fresh(chart);
    const shown = TICKERS.filter(t => t !== "CRWV");
    const labels = ["FY2019", "FY2020", "FY2021", "FY2022", "FY2023", "FY2024", "FY2025", "Latest 12m"];
    const series = shown.map(t => { const h = funding.history[t], fy = h.filter(p => p.period !== "TTM"), ttm = h.find(p => p.period === "TTM");
      const pts = labels.slice(0, -1).map(l => (fy.find(p => p.period === l) || {}).share ?? null); pts.push(ttm ? ttm.share : null); return {t, pts}; });
    const W = 720, H = 310, m = {t: 16, r: 14, b: 28, l: 48}, max = 2;
    const x = i => m.l + (W - m.l - m.r) * i / (labels.length - 1), y = v => m.t + (H - m.t - m.b) * (1 - Math.min(v, max) / max);
    const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Capital expenditure as a share of operating cash flow"});
    for (let v = 0; v <= max + 1e-9; v += .5) { svg.append(svgEl("line", {class: "grid", x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), style: Math.abs(v - 1) < 1e-9 ? "stroke:var(--muted);stroke-dasharray:4 3" : ""})); svg.append(svgEl("text", {x: m.l - 8, y: y(v) + 4, "text-anchor": "end"}, (v * 100) + "%")); }
    svg.append(svgEl("text", {x: m.l + 6, y: y(1) - 6}, "spends everything its operations bring in"));
    labels.forEach((l, i) => svg.append(svgEl("text", {x: x(i), y: H - 8, "text-anchor": i === labels.length - 1 ? "end" : "middle"}, l.replace("FY20", "FY"))));
    series.forEach(s => {
      svg.append(svgEl("polyline", {points: s.pts.map((v, i) => v == null ? null : `${x(i)},${y(v)}`).filter(Boolean).join(" "), fill: "none", stroke: COLOR[s.t], "stroke-width": 2, "stroke-linejoin": "round"}));
      const last = s.pts.length - 1; if (s.pts[last] != null) svg.append(svgEl("circle", {cx: x(last), cy: y(s.pts[last]), r: 4, fill: COLOR[s.t], stroke: "var(--raised)", "stroke-width": 2}));
    });
    labels.forEach((l, i) => {
      const w = (W - m.l - m.r) / (labels.length - 1);
      const hit = svgEl("rect", {x: x(i) - w / 2, y: m.t, width: w, height: H - m.t - m.b, fill: "transparent", tabindex: 0, "aria-label": l});
      hover(hit, chart, `<b>${l}</b>` + series.filter(s => s.pts[i] != null).sort((a, b) => b.pts[i] - a.pts[i]).map(s => `<div><span><i style="background:${COLOR[s.t]}"></i>${names[s.t]}</span><span>${pct(s.pts[i])}</span></div>`).join(""),
        () => [x(i) / W * chart.clientWidth, m.t / H * chart.clientHeight]);
      svg.append(hit);
    });
    chart.append(svg);
    return shown;
  },

  /* Debt against yearly cash earnings: hollow dot is today, solid dot counts the signed leases as debt. */
  leverage(chart, levRows, names) {
    fresh(chart);
    const rows = levRows.filter(r => r.today != null && r.pro_forma != null).sort((a, b) => b.pro_forma - a.pro_forma);
    const W = 720, row = 42, m = {t: 22, r: 60, b: 8, l: 100}, H = m.t + row * rows.length + m.b, max = Math.ceil(Math.max(...rows.map(r => r.pro_forma_high || r.pro_forma)) / 5) * 5;
    const x = v => m.l + (W - m.l - m.r) * v / max;
    const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Debt and leases as a multiple of yearly cash earnings, today and with signed leases counted"});
    for (let v = 0; v <= max; v += 5) { svg.append(svgEl("line", {class: "grid", x1: x(v), x2: x(v), y1: m.t - 4, y2: H - m.b})); svg.append(svgEl("text", {x: x(v), y: 12, "text-anchor": "middle"}, v + "×")); }
    rows.forEach((r, i) => {
      const cy = m.t + row * i + row / 2, hot = r.pro_forma >= 4, col = hot ? "var(--accent)" : "var(--text-2)";
      svg.append(svgEl("text", {x: m.l - 12, y: cy + 4, "text-anchor": "end", class: "val", style: "font-family:var(--sans)"}, names[r.ticker]));
      svg.append(svgEl("line", {x1: x(r.today), x2: x(r.pro_forma), y1: cy, y2: cy, stroke: col, "stroke-width": 3, opacity: .35}));
      if (r.pro_forma_low != null) svg.append(svgEl("line", {x1: x(r.pro_forma_low), x2: x(r.pro_forma_high), y1: cy, y2: cy, stroke: col, "stroke-width": 1.5}));
      svg.append(svgEl("circle", {cx: x(r.today), cy, r: 5, fill: "var(--raised)", stroke: col, "stroke-width": 2}));
      svg.append(svgEl("circle", {cx: x(r.pro_forma), cy, r: 6, fill: col, stroke: "var(--raised)", "stroke-width": 2}));
      svg.append(svgEl("text", {x: x(r.pro_forma_high || r.pro_forma) + 10, y: cy + 4, class: "val"}, r.pro_forma.toFixed(1) + "×"));
      const hit = svgEl("rect", {x: 0, y: cy - row / 2, width: W, height: row, fill: "transparent", tabindex: 0, "aria-label": `${names[r.ticker]}: ${r.today.toFixed(1)} times today, ${r.pro_forma.toFixed(1)} times with signed leases`});
      hover(hit, chart, `<b>${names[r.ticker]}</b><div><span>Today</span><span>${r.today.toFixed(1)}×</span></div><div><span>With signed leases</span><span>${r.pro_forma.toFixed(1)}×</span></div><div><span>Range</span><span>${r.pro_forma_low.toFixed(1)}× – ${r.pro_forma_high.toFixed(1)}×</span></div><div><span>Borrowings</span><span>${B(r.debt)}</span></div><div><span>Leases on the books</span><span>${B(r.leases)}</span></div><div><span>Signed leases, worth today</span><span>${B(r.signed)}</span></div><div><span>Yearly cash earnings</span><span>${B(r.ebitda)}</span></div>`,
        () => [x(r.pro_forma) / W * chart.clientWidth, (cy - row / 2) / H * chart.clientHeight]);
      svg.append(hit);
    });
    chart.append(svg);
  },

  /* The telecom makers after the peak: money actually lent or guaranteed, as a share of sales, year by year. */
  paths(chart, companies, nvidiaInForce, nvidiaPromised) {
    fresh(chart);
    const short = c => c.replace(" Technologies", "").replace(" Networks", "").replace(" Systems", "");
    const series = companies.map((c, i) => ({name: short(c.company), color: `var(--s${i + 1})`, pts: c.path.filter(p => p.in_force != null)})).filter(s => s.pts.length > 1);
    const W = 720, H = 300, m = {t: 16, r: 86, b: 28, l: 44}, t0 = +new Date("1997-06-30"), t1 = +new Date("2003-12-31"), max = .16;
    const x = d => m.l + (W - m.l - m.r) * (+new Date(d) - t0) / (t1 - t0), y = v => m.t + (H - m.t - m.b) * (1 - v / max);
    const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Customer financing lent or guaranteed as a share of sales, 1997 to 2003"});
    for (let v = 0; v <= max + 1e-9; v += .04) { svg.append(svgEl("line", {class: "grid", x1: m.l, x2: W - m.r, y1: y(v), y2: y(v)})); svg.append(svgEl("text", {x: m.l - 8, y: y(v) + 4, "text-anchor": "end"}, Math.round(v * 100) + "%")); }
    for (let yr = 1998; yr <= 2003; yr++) svg.append(svgEl("text", {x: x(`${yr}-06-30`), y: H - 8, "text-anchor": "middle"}, yr));
    svg.append(svgEl("line", {x1: m.l, x2: W - m.r, y1: y(nvidiaInForce), y2: y(nvidiaInForce), stroke: "var(--accent)", "stroke-width": 1.5, "stroke-dasharray": "5 4"}));
    svg.append(svgEl("text", {x: m.l + 6, y: y(nvidiaInForce) - 6, style: "fill:var(--accent)"}, `NVIDIA today: ${pct(nvidiaInForce, 1)} in force (${pct(nvidiaPromised)} promised)`));
    series.forEach(s => {
      svg.append(svgEl("polyline", {points: s.pts.map(p => `${x(p.date)},${y(p.in_force)}`).join(" "), fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round"}));
      const last = s.pts[s.pts.length - 1];
      svg.append(svgEl("circle", {cx: x(last.date), cy: y(last.in_force), r: 3.5, fill: s.color, stroke: "var(--raised)", "stroke-width": 2}));
      s.labelY = y(last.in_force) + 4; s.labelX = x(last.date) + 8;
    });
    series.slice().sort((a, b) => a.labelY - b.labelY).forEach((s, i, arr) => { if (i && s.labelY - arr[i - 1].labelY < 12) s.labelY = arr[i - 1].labelY + 12; svg.append(svgEl("text", {x: s.labelX, y: s.labelY, style: "font-family:var(--sans)"}, s.name)); });
    series.forEach(s => s.pts.forEach(p => {
      const hit = svgEl("circle", {cx: x(p.date), cy: y(p.in_force), r: 9, fill: "transparent", tabindex: 0, "aria-label": `${s.name} ${mon(p.date)}: ${pct(p.in_force, 1)}`});
      hover(hit, chart, `<b>${s.name} · ${mon(p.date)}</b><div><span>Lent or guaranteed ÷ sales</span><span>${pct(p.in_force, 1)}</span></div>${p.promised != null ? `<div><span>Promised ÷ sales</span><span>${pct(p.promised, 1)}</span></div>` : ""}${p.dso != null ? `<div><span>Days to get paid</span><span>${Math.round(p.dso)}</span></div>` : ""}${p.reserved != null ? `<div><span>Set aside for losses ÷ lent</span><span>${pct(p.reserved)}</span></div>` : ""}`,
        () => [x(p.date) / W * chart.clientWidth, y(p.in_force) / H * chart.clientHeight]);
      svg.append(hit);
    }));
    chart.append(svg);
    return series.map(s => [s.color, s.name]);
  },

  /* NVIDIA's orders from its own suppliers, in years of what it spent making products over the previous year. */
  supply(chart, allPts) {
    fresh(chart);
    // Measured at the current pace of production (the latest quarter's cost times four), so a fast-growing company is not flattered or penalised by last year's smaller size.
    const pts = allPts.filter(p => p.years_run_rate != null).map(p => ({...p, y: p.years_run_rate, n: p.near_years_run_rate}));
    const W = 720, H = 310, m = {t: 18, r: 60, b: 28, l: 44}, max = Math.ceil(Math.max(...pts.map(p => p.y)));
    const t0 = +new Date(pts[0].period_end), t1 = +new Date(pts[pts.length - 1].period_end);
    const x = d => m.l + (W - m.l - m.r) * (+new Date(d) - t0) / (t1 - t0), y = v => m.t + (H - m.t - m.b) * (1 - v / max);
    const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "NVIDIA supply commitments in years of production cost at the current pace"});
    for (let v = 0; v <= max; v++) { svg.append(svgEl("line", {class: "grid", x1: m.l, x2: W - m.r, y1: y(v), y2: y(v)})); svg.append(svgEl("text", {x: m.l - 8, y: y(v) + 4, "text-anchor": "end"}, v === 0 ? "0" : v + " yr")); }
    for (let yr = 2019; yr <= 2026; yr++) { const d = `${yr}-01-31`; if (+new Date(d) >= t0) svg.append(svgEl("text", {x: x(d), y: H - 8, "text-anchor": "middle"}, yr)); }
    svg.append(svgEl("polyline", {points: pts.map(p => `${x(p.period_end)},${y(p.y)}`).join(" "), fill: "none", stroke: "var(--s1)", "stroke-width": 2, "stroke-linejoin": "round"}));
    const last = pts[pts.length - 1], peak22 = pts.filter(p => p.period_end < "2023-01-01").reduce((a, b) => b.y > a.y ? b : a);
    [[peak22, "2022 peak: " + peak22.y.toFixed(2) + " yr", "middle", -12], [last, last.y.toFixed(1) + " yr", "start", 4]].forEach(([p, label, anchor, dy]) => {
      svg.append(svgEl("circle", {cx: x(p.period_end), cy: y(p.y), r: 4, fill: "var(--s1)", stroke: "var(--raised)", "stroke-width": 2}));
      svg.append(svgEl("text", {class: "val", x: x(p.period_end) + (anchor === "start" ? 8 : 0), y: y(p.y) + dy, "text-anchor": anchor}, label));
    });
    if (last.n != null) {
      svg.append(svgEl("circle", {cx: x(last.period_end), cy: y(last.n), r: 4, fill: "var(--raised)", stroke: "var(--s1)", "stroke-width": 2}));
      svg.append(svgEl("text", {x: x(last.period_end) - 10, y: y(last.n) + 4, "text-anchor": "end"}, "due within a year: " + last.n.toFixed(1) + " yr"));
    }
    pts.forEach(p => {
      const w = (W - m.l - m.r) / pts.length;
      const hit = svgEl("rect", {x: x(p.period_end) - w / 2, y: m.t, width: w, height: H - m.t - m.b, fill: "transparent", tabindex: 0, "aria-label": `${mon(p.period_end)}: ${p.y.toFixed(2)} years`});
      hover(hit, chart, `<b>Quarter to ${mon(p.period_end)}</b><div><span>Ordered from suppliers</span><span>${B(p.commitments, 1)}</span></div><div><span>Years at the current pace</span><span>${p.y.toFixed(2)}</span></div>${p.n != null ? `<div><span>Due within about a year</span><span>${p.n.toFixed(2)} yr</span></div>` : ""}<div><span>Gross margin</span><span>${pct(p.gross_margin, 1)}</span></div>${p.provisions_share != null ? `<div><span>Inventory charges ÷ sales</span><span>${pct(p.provisions_share, 1)}</span></div>` : ""}`,
        () => [x(p.period_end) / W * chart.clientWidth, y(p.y) / H * chart.clientHeight]);
      svg.append(hit);
    });
    chart.append(svg);
    return {last, peak22, pts};
  },

  FINANCING_GROUPS: [
    {k: "guarantee_2029", c: "var(--rest)", l: "Guarantee not yet in effect"},
    {k: "guarantees_other", c: "var(--s1)", l: "Guarantees in effect"},
    {k: "unfunded_equity", c: "var(--s2)", l: "Investments promised, not yet paid"},
    {k: "equity_stakes", c: "var(--s3)", l: "Shares it holds in other companies"},
    {k: "capacity", c: "var(--s4)", l: "Capacity it has agreed to rent or lease"},
  ],
  /* NVIDIA's support for customers and partners, as a share of its annual rate of sales. */
  financing(chart, pts) {
    fresh(chart);
    const G = Charts.FINANCING_GROUPS, n = pts.length;
    const tot = p => (G.reduce((s, g) => s + p[g.k], 0) + (p.capacity_carried || 0)) / p.revenue_annualized;
    const W = 720, H = 310, m = {t: 22, r: 8, b: 28, l: 48}, max = Math.ceil(Math.max(...pts.map(tot)) * 5) / 5;
    const y = v => m.t + (H - m.t - m.b) * (1 - v / max), band = (W - m.l - m.r) / n, bw = Math.min(30, band - 6);
    const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "NVIDIA support for customers and partners as a share of annualised sales"});
    for (let v = 0; v <= max + 1e-9; v += .2) { svg.append(svgEl("line", {class: "grid", x1: m.l, x2: W - m.r, y1: y(v), y2: y(v)})); svg.append(svgEl("text", {x: m.l - 8, y: y(v) + 4, "text-anchor": "end"}, Math.round(v * 100) + "%")); }
    pts.forEach((p, i) => {
      const x = m.l + band * i + (band - bw) / 2; let acc = 0;
      if (p.capacity_carried) { const v = p.capacity_carried / p.revenue_annualized, y1 = y(acc + v), h = y(acc) - y1; svg.append(svgEl("rect", {x, y: y1 + 1, width: bw, height: h - 2, fill: "var(--s4)", opacity: .4})); acc += v; }
      G.slice().reverse().forEach(g => { const v = p[g.k] / p.revenue_annualized; if (v <= 0) return; const y1 = y(acc + v), h = y(acc) - y1; if (h > 2.2) svg.append(svgEl("rect", {x, y: y1 + 1, width: bw, height: h - 2, fill: g.c})); acc += v; });
      const narrow = p.narrow / p.revenue_annualized;
      if (narrow > 0.005 && i >= n - 4) svg.append(svgEl("text", {class: "val", x: x + bw / 2, y: y(acc) - 6, "text-anchor": "middle"}, pct(narrow)));
      if (i % 2 === (n - 1) % 2) svg.append(svgEl("text", {x: x + bw / 2, y: H - 8, "text-anchor": "middle"}, mon(p.period_end).replace(" 20", " '")));
      const hit = svgEl("rect", {x: m.l + band * i, y: m.t, width: band, height: H - m.t - m.b, fill: "transparent", tabindex: 0, "aria-label": `${mon(p.period_end)}: guarantees and promises ${pct(narrow)} of annualised sales`});
      hover(hit, chart, `<b>${mon(p.period_end)}</b><div><span>Guarantees and promises</span><span>${pct(narrow)} of sales</span></div><div><span>Everything shown</span><span>${pct(acc)} of sales</span></div>` + G.filter(g => p[g.k] > 0).map(g => `<div><span><i style="background:${g.c}"></i>${g.l}</span><span>${B(p[g.k], 1)}</span></div>`).join("") + (p.capacity_carried ? `<div><span>Capacity (carried forward)</span><span>${B(p.capacity_carried, 1)}</span></div>` : "") + `<div><span>Sales, quarter × 4</span><span>${B(p.revenue_annualized)}</span></div>`,
        () => [(x + bw) / W * chart.clientWidth, y(acc) / H * chart.clientHeight]);
      svg.append(hit);
    });
    chart.append(svg);
  },

  /* Then and now: what each supplier had promised its customers, against what was actually lent or in force. */
  thenAndNow(chart, companies, latest) {
    fresh(chart);
    const rev = latest.revenue_annualized, short = c => c.replace(" Technologies", "").replace(" Networks", "").replace(" Systems", "");
    const rows = [
      {name: "NVIDIA", sub: mon(latest.period_end), promised: latest.narrow / rev, force: latest.guarantees_other / rev, now: true, promised_usd: latest.narrow, force_usd: latest.guarantees_other},
      ...companies.map(c => ({name: short(c.company), sub: "highest, 1997–2003", promised: c.high_promised, force: c.peak_in_force_ratio, c, when_p: c.high_promised_date, when_f: c.peak_in_force_date, min: !c.high_promised_complete})),
    ].sort((a, b) => b.promised - a.promised);
    const W = 720, row = 50, m = {t: 6, r: 96, b: 22, l: 120}, H = m.t + row * rows.length + m.b, max = Math.ceil(Math.max(...rows.map(r => r.promised)) * 10) / 10;
    const x = v => m.l + (W - m.l - m.r) * v / max;
    const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Financing promised and in force, as a share of annual sales"});
    for (let v = 0; v <= max + 1e-9; v += .1) { svg.append(svgEl("line", {class: "grid", x1: x(v), x2: x(v), y1: m.t, y2: H - m.b})); svg.append(svgEl("text", {x: x(v), y: H - 6, "text-anchor": "middle"}, Math.round(v * 100) + "%")); }
    rows.forEach((r, i) => {
      const cy = m.t + row * i + row / 2, col = r.now ? "var(--accent)" : "var(--text-2)";
      svg.append(svgEl("text", {x: m.l - 10, y: cy - 1, "text-anchor": "end", class: "val", style: "font-family:var(--sans)"}, r.name));
      svg.append(svgEl("text", {x: m.l - 10, y: cy + 12, "text-anchor": "end", style: "font-size:10px"}, r.sub));
      svg.append(svgEl("rect", {x: x(0), y: cy - 15, width: Math.max(1, x(r.promised) - x(0)), height: 13, fill: col, opacity: .32}));
      svg.append(svgEl("text", {x: x(r.promised) + 8, y: cy - 4, class: "val"}, (r.min ? "at least " : "") + pct(r.promised)));
      svg.append(svgEl("rect", {x: x(0), y: cy + 2, width: Math.max(1, x(r.force) - x(0)), height: 13, fill: col}));
      svg.append(svgEl("text", {x: x(r.force) + 8, y: cy + 13, class: "val"}, pct(r.force)));
      const hit = svgEl("rect", {x: 0, y: cy - row / 2, width: W, height: row, fill: "transparent", tabindex: 0, "aria-label": `${r.name}: promised ${pct(r.promised)}, in force ${pct(r.force)}`});
      hover(hit, chart, `<b>${esc(r.c ? r.c.company : "NVIDIA")}</b><div><span>Promised ÷ sales</span><span>${pct(r.promised, 1)}${r.when_p ? " · " + mon(r.when_p) : ""}</span></div><div><span>Lent or in force ÷ sales</span><span>${pct(r.force, 1)}${r.when_f ? " · " + mon(r.when_f) : ""}</span></div>${r.now ? `<div><span>Promised</span><span>${B(r.promised_usd, 1)}</span></div><div><span>In force</span><span>${B(r.force_usd, 1)}</span></div>` : ""}`,
        () => [x(r.promised) / W * chart.clientWidth, (cy - row / 2) / H * chart.clientHeight]);
      svg.append(hit);
    });
    chart.append(svg);
  },
};

/* Evidence panels draw their chart the first time they are opened, so nothing is drawn until someone asks for it. */
function onOpen(id, draw) {
  const d = document.getElementById(id); if (!d) return;
  let done = false; const run = () => { if (d.open && !done) { done = true; draw(); } };
  d.addEventListener("toggle", run); run();
}
