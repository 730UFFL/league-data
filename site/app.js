/* 730UFFL - static site. No build step, no dependencies.
   Reads site/data/{season}.json; every metric is precomputed by pipeline/.

   Twelve teams is well past the eight-slot categorical ceiling, so no chart
   here assigns a hue per team. Multi-team charts use emphasis: the selected
   team in the accent, everyone else in context gray. */

'use strict';

const NS = 'http://www.w3.org/2000/svg';
const $ = (sel, root = document) => root.querySelector(sel);

const state = { data: null, seasons: [], season: null, view: 'standings', teamId: null, quadWeek: null, forecastOrigin: null };

/* ---------------------------------------------------------------- utils */

const fmt = (n, dp = 1) =>
  n === null || n === undefined || Number.isNaN(n) ? '–' : Number(n).toFixed(dp);
const signed = (n, dp = 2) => (n > 0 ? '+' : '') + fmt(n, dp);
const pct = (n, dp = 0) => fmt(n * 100, dp) + '%';
const rec = (w, l) => w + '‑' + l;

function el(name, attrs, ...kids) {
  const node = document.createElementNS(NS, name);
  for (const k in attrs || {}) {
    if (attrs[k] !== null && attrs[k] !== undefined) node.setAttribute(k, attrs[k]);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined) continue;
    node.appendChild(typeof kid === 'string' ? document.createTextNode(kid) : kid);
  }
  return node;
}

function h(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  for (const k in attrs || {}) {
    const v = attrs[k];
    if (v === null || v === undefined) continue;
    if (k === 'class') node.className = v;
    else if (k === 'text') node.textContent = v;
    else if (k.slice(0, 2) === 'on') node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined) continue;
    node.appendChild(typeof kid === 'string' ? document.createTextNode(kid) : kid);
  }
  return node;
}

const teamName = (id) => {
  const t = state.data.teams.find((x) => x.team_id === id);
  return t ? t.name : String(id);
};
const shortName = (id, max) => {
  const n = teamName(id);
  const cap = max || 16;
  return n.length > cap ? n.slice(0, cap - 1).trimEnd() + '…' : n;
};
const isSel = (id) => id === state.teamId;
const markColor = (id) => (isSel(id) ? 'var(--accent)' : 'var(--context)');

/* ---------------------------------------------------------------- tooltip */

const tip = {
  node: null,
  show(x, y, title, rows) {
    if (!this.node) this.node = $('#tooltip');
    this.node.innerHTML = '';
    this.node.appendChild(h('div', { class: 't-title', text: title }));
    for (const r of rows) {
      const row = h('div', { class: 't-row' });
      row.innerHTML = r;
      this.node.appendChild(row);
    }
    this.node.classList.add('on');
    const box = this.node.getBoundingClientRect();
    this.node.style.left =
      Math.min(Math.max(8, x + 14), window.innerWidth - box.width - 8) + 'px';
    this.node.style.top =
      Math.min(Math.max(8, y - box.height - 12), window.innerHeight - box.height - 8) + 'px';
  },
  hide() {
    if (this.node) this.node.classList.remove('on');
  },
};

/* Hover, and the same content on keyboard focus. */
function hoverable(node, title, rows) {
  const show = (ev) => {
    const r = node.getBoundingClientRect();
    tip.show(
      ev.clientX === undefined ? r.left + r.width / 2 : ev.clientX,
      ev.clientY === undefined ? r.top : ev.clientY,
      title,
      rows
    );
  };
  node.addEventListener('mousemove', show);
  node.addEventListener('mouseenter', show);
  node.addEventListener('mouseleave', () => tip.hide());
  node.addEventListener('focus', show);
  node.addEventListener('blur', () => tip.hide());
  node.setAttribute('tabindex', '0');
  node.setAttribute('role', 'img');
  node.setAttribute('aria-label', title + '. ' + rows.join('. ').replace(/<[^>]+>/g, ''));
  return node;
}

/* Selecting a team from a mark. Clicking the highlighted team clears it, so
   the same gesture toggles rather than stranding the reader with no way back
   except the dropdown. */
function selectTeam(id) {
  state.teamId = state.teamId === id ? null : id;
  const sel = $('#team-select');
  if (sel) sel.value = state.teamId === null ? '' : String(state.teamId);
  tip.hide();
  render();
}

/* Marks already carry a hover tooltip and keyboard focus; this makes them
   activate. Call after hoverable() so the button role wins. */
function selectable(node, teamId) {
  /* Marks carry tabindex so they are keyboard reachable, which means a tap
     also focuses them - and the browser scrolls a newly focused element into
     view, landing the reader at the top of the chart. Cancelling the default
     on mousedown suppresses focus-on-pointer without touching Tab focus. */
  node.addEventListener('mousedown', (ev) => ev.preventDefault());
  node.addEventListener('click', (ev) => {
    ev.preventDefault();
    selectTeam(teamId);
  });
  node.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'Spacebar') {
      ev.preventDefault();
      selectTeam(teamId);
    }
  });
  node.setAttribute('role', 'button');
  const label = node.getAttribute('aria-label') || teamName(teamId);
  node.setAttribute('aria-label', label + '. ' +
    (isSel(teamId) ? 'Highlighted; activate to clear.' : 'Activate to highlight.'));
  node.setAttribute('aria-pressed', isSel(teamId) ? 'true' : 'false');
  return node;
}

/* ---------------------------------------------------------------- scales */

function linear(domain, range) {
  const d0 = domain[0], d1 = domain[1], r0 = range[0], r1 = range[1];
  const span = d1 - d0 || 1;
  const f = (v) => r0 + ((v - d0) / span) * (r1 - r0);
  f.domain = domain;
  return f;
}

function niceTicks(min, max, count) {
  const span = max - min || 1;
  const raw = span / (count || 5);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm >= 7.5 ? 10 : norm >= 3 ? 5 : norm >= 1.5 ? 2 : 1) * mag;
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) {
    out.push(Math.abs(v) < 1e-9 ? 0 : +v.toFixed(10));
  }
  return out;
}

/* ------------------------------------------------------- responsive layout */

/* Charts used to carry a fixed 720-unit viewBox, so on a phone the whole
   drawing scaled to 38% and 11px labels rendered at 4px. They are now built at
   the width they will actually occupy, which keeps text at its real size.
   Measured once per render and passed down. */
function layout() {
  const view = $('#view');
  const padX = parseFloat(
    getComputedStyle(document.documentElement).getPropertyValue('--card-pad-x')
  ) || 20;
  /* clientWidth includes the element's own padding, so take it off before
     subtracting the card's - otherwise the chart is built wider than the box
     it lands in and the browser scales it back down, which is the bug this
     whole change exists to remove. */
  let avail = 720;
  if (view) {
    const cs = getComputedStyle(view);
    avail = view.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  }
  /* No upper clamp. Building narrower than the box and letting the browser
     stretch it is the same scaling bug in the other direction: text ends up
     larger than its declared size rather than smaller. */
  const width = Math.max(260, avail - padX * 2 - 2);
  const narrow = width < 460;
  return {
    width,
    narrow,
    /* Taller rows on a phone so a tap target clears ~24px. */
    rowH: narrow ? 34 : 26,
    /* The name gutter is 21% of a desktop chart but would be 45% of a phone
       one, so it shrinks and the names truncate harder. It cannot go away
       entirely on bar charts - it is the y axis. */
    labelW: narrow ? 94 : 150,
    nameChars: narrow ? 11 : 20,
    /* Per-mark labels on scatter and line ends do collide on a phone, and
       tap-to-select covers identifying a team there. */
    markLabels: !narrow,
    weekTickEvery: narrow ? 2 : 1,
    valueLabels: !narrow,
  };
}

/* ---------------------------------------------------------------- frame */

function frame(width, height, m) {
  const margin = Object.assign({ top: 12, right: 20, bottom: 34, left: 48 }, m || {});
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const svg = el('svg', {
    class: 'chart',
    viewBox: '0 0 ' + width + ' ' + height,
    preserveAspectRatio: 'xMidYMid meet',
    role: 'group',
  });
  const g = el('g', { transform: 'translate(' + margin.left + ',' + margin.top + ')' });
  svg.appendChild(g);
  return { svg, g, margin, plotW, plotH };
}

function gridX(g, x, ticks, plotH, format) {
  const f = format || String;
  for (const t of ticks) {
    g.appendChild(el('line', { class: 'tick-line', x1: x(t), x2: x(t), y1: 0, y2: plotH }));
    g.appendChild(
      el('text', { class: 'axis-label', x: x(t), y: plotH + 16, 'text-anchor': 'middle' }, f(t))
    );
  }
}

function gridY(g, y, ticks, plotW, format) {
  const f = format || String;
  for (const t of ticks) {
    g.appendChild(el('line', { class: 'tick-line', x1: 0, x2: plotW, y1: y(t), y2: y(t) }));
    g.appendChild(
      el('text', { class: 'axis-label', x: -8, y: y(t) + 4, 'text-anchor': 'end' }, f(t))
    );
  }
}

/* Text can only be measured once it is in the document, so charts register a
   fixup that render() runs after mounting. */
function onMount(svg, fn) {
  svg.__fixup = fn;
  return svg;
}

/* Push apart labels that collide, alternating down then up, clamped to the
   plot. Twelve teams in a scatter will always crowd somewhere. */
function decollide(nodes, bounds) {
  const items = nodes.map((n) => ({ n, y0: parseFloat(n.getAttribute('y')), dy: 0 }));
  const boxOf = (it) => {
    const b = it.n.getBBox();
    return { x1: b.x, x2: b.x + b.width, y1: b.y, y2: b.y + b.height };
  };
  items.sort((a, b) => boxOf(a).y1 - boxOf(b).y1);
  for (let pass = 0; pass < 12; pass++) {
    let moved = false;
    for (let i = 0; i < items.length; i++) {
      for (let j = i + 1; j < items.length; j++) {
        const A = boxOf(items[i]), B = boxOf(items[j]);
        const hit = A.x1 < B.x2 && B.x1 < A.x2 && A.y1 < B.y2 && B.y1 < A.y2;
        if (!hit) continue;
        const push = A.y2 - B.y1 + 2;
        const target = items[j];
        const down = target.y0 + target.dy + push;
        if (down + 4 < bounds.height) target.dy += push;
        else items[i].dy -= push;
        for (const t of [items[i], items[j]]) {
          const y = Math.max(10, Math.min(bounds.height - 2, t.y0 + t.dy));
          t.n.setAttribute('y', y);
        }
        moved = true;
      }
    }
    if (!moved) break;
  }
}

function legend(items) {
  const box = h('div', { class: 'legend' });
  for (const it of items) {
    box.appendChild(
      h('span', { class: 'key' }, h('span', { class: 'swatch', style: 'background:' + it[1] }), it[0])
    );
  }
  return box;
}

function card(title, note, ...body) {
  return h(
    'section',
    { class: 'card' },
    h('h2', { text: title }),
    note ? h('p', { class: 'note', text: note }) : null,
    ...body
  );
}

function caption(text) {
  return h('p', { class: 'caption', text: text });
}

function tableEl(headers, rows) {
  const table = h('table');
  table.appendChild(
    h('thead', {}, h('tr', {}, headers.map((x, i) => h('th', { class: i ? '' : 'left', text: x }))))
  );
  const tbody = h('tbody');
  for (const r of rows) {
    const tr = h('tr', r.selected ? { class: 'is-selected' } : {});
    if (r.team_id !== undefined && r.team_id !== null) {
      tr.className = (tr.className + ' clickable').trim();
      tr.setAttribute('tabindex', '0');
      tr.setAttribute('title', (r.selected ? 'Clear highlight on ' : 'Highlight ') + teamName(r.team_id));
      tr.addEventListener('mousedown', (ev) => ev.preventDefault());
      tr.addEventListener('click', () => selectTeam(r.team_id));
      tr.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'Spacebar') {
          ev.preventDefault();
          selectTeam(r.team_id);
        }
      });
    }
    r.cells.forEach((c, i) => {
      const cell = c !== null && typeof c === 'object' ? c : { text: String(c) };
      const cls = [i ? '' : 'left', cell.cls || ''].join(' ').trim();
      tr.appendChild(h('td', { class: cls, text: cell.text }));
    });
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  return h('div', { class: 'table-wrap' }, table);
}

function detailsTable(summary, headers, rows) {
  return h('details', { class: 'table-view' }, h('summary', { text: summary }), tableEl(headers, rows));
}

function tile(label, value, detail) {
  return h(
    'div',
    { class: 'tile' },
    h('div', { class: 'label', text: label }),
    h('div', { class: 'value', text: value }),
    detail ? h('div', { class: 'detail', text: detail }) : null
  );
}

/* ---------------------------------------------------------------- charts */

/* Horizontal diverging bars around a zero baseline. */
function divergingBars(rows, opts) {
  const L = layout();
  const o = Object.assign({ dp: 2, unit: '', rowH: L.rowH, labelW: L.labelW }, opts || {});
  const height = rows.length * o.rowH + 46;
  const f = frame(L.width, height, { left: o.labelW, right: L.narrow ? 42 : 56, bottom: 26, top: 8 });
  const max = Math.max(...rows.map((r) => Math.abs(r.value)), 0.001) * 1.15;
  const x = linear([-max, max], [0, f.plotW]);
  const valueLabels = [];
  gridX(f.g, x, niceTicks(-max, max, 5), rows.length * o.rowH, (t) => fmt(t, 0));

  rows.forEach((r, i) => {
    const y = i * o.rowH + 4;
    const bh = o.rowH - 12;
    const zero = x(0);
    const end = x(r.value);
    const left = Math.min(zero, end);
    const w = Math.max(Math.abs(end - zero), 1.5);
    const positive = r.value >= 0;

    f.g.appendChild(
      el('text', {
        class: 'mark-label' + (isSel(r.team_id) ? ' strong' : ''),
        x: -10,
        y: y + bh / 2 + 4,
        'text-anchor': 'end',
      }, shortName(r.team_id, o.nameChars || L.nameChars))
    );

    const bar = el('rect', {
      x: left, y, width: w, height: bh, rx: 4,
      fill: positive ? 'var(--pole-pos)' : 'var(--pole-neg)',
      opacity: isSel(r.team_id) || !state.teamId ? 1 : 0.45,
    });
    f.g.appendChild(bar);

    const valLabel = el('text', {
      class: 'mark-label',
      x: positive ? end + 8 : end - 8,
      y: y + bh / 2 + 4,
      'text-anchor': positive ? 'start' : 'end',
    }, signed(r.value, o.dp) + o.unit);
    f.g.appendChild(valLabel);
    valueLabels.push({ node: valLabel, end, positive });

    const hit = el('rect', { class: 'hit', x: -o.labelW, y: y - 4, width: f.plotW + o.labelW, height: o.rowH });
    selectable(hoverable(hit, teamName(r.team_id), r.rows), r.team_id);
    f.g.appendChild(hit);
  });

  f.g.appendChild(el('line', { class: 'baseline', x1: x(0), x2: x(0), y1: 0, y2: rows.length * o.rowH }));

  /* The longest bar reaches the plot edge, so its value would sit in the team
     name gutter. Flip those labels inside the bar end. */
  return onMount(f.svg, () => {
    for (const L of valueLabels) {
      const w = L.node.getComputedTextLength();
      if (L.positive && L.end + 8 + w > f.plotW) {
        L.node.setAttribute('x', L.end - 8);
        L.node.setAttribute('text-anchor', 'end');
      } else if (!L.positive && L.end - 8 - w < 0) {
        L.node.setAttribute('x', L.end + 8);
        L.node.setAttribute('text-anchor', 'start');
      }
    }
  });
}

/* Two values per row joined by a rule - one hue, two shades. */
function dumbbell(rows, opts) {
  const L = layout();
  const o = Object.assign({ rowH: L.rowH, labelW: L.labelW, format: (v) => fmt(v, 0) }, opts || {});
  const height = rows.length * o.rowH + 46;
  const f = frame(L.width, height, { left: o.labelW, right: L.narrow ? 24 : 60, bottom: 26, top: 8 });
  const all = rows.flatMap((r) => [r.a, r.b]);
  const lo = Math.min(...all), hi = Math.max(...all);
  const pad = (hi - lo) * 0.12 || 1;
  const x = linear([lo - pad, hi + pad], [0, f.plotW]);
  gridX(f.g, x, niceTicks(lo - pad, hi + pad, 5), rows.length * o.rowH, o.format);

  rows.forEach((r, i) => {
    const y = i * o.rowH + o.rowH / 2 - 4;
    const dim = state.teamId && !isSel(r.team_id) ? 0.5 : 1;
    f.g.appendChild(
      el('text', {
        class: 'mark-label' + (isSel(r.team_id) ? ' strong' : ''),
        x: -10, y: y + 4, 'text-anchor': 'end',
      }, shortName(r.team_id, L.nameChars))
    );
    f.g.appendChild(
      el('line', { x1: x(r.a), x2: x(r.b), y1: y, y2: y, stroke: 'var(--axis)', 'stroke-width': 2, opacity: dim })
    );
    f.g.appendChild(el('circle', { cx: x(r.a), cy: y, r: 5, fill: 'var(--seq-250)', stroke: 'var(--surface-1)', 'stroke-width': 2, opacity: dim }));
    f.g.appendChild(el('circle', { cx: x(r.b), cy: y, r: 5, fill: 'var(--seq-550)', stroke: 'var(--surface-1)', 'stroke-width': 2, opacity: dim }));
    const hit = el('rect', { class: 'hit', x: -o.labelW, y: i * o.rowH, width: f.plotW + o.labelW, height: o.rowH });
    selectable(hoverable(hit, teamName(r.team_id), r.rows), r.team_id);
    f.g.appendChild(hit);
  });
  return f.svg;
}

/* worst .. best range with the actual result marked inside it. */
function rangeBars(rows) {
  const L = layout();
  const rowH = L.narrow ? 34 : 30, labelW = L.labelW;
  const f = frame(L.width, rows.length * rowH + 48, { left: labelW, right: L.narrow ? 22 : 40, bottom: 28, top: 8 });
  const lo = Math.min(...rows.map((r) => r.lo));
  const hi = Math.max(...rows.map((r) => r.hi));
  const x = linear([lo - 0.5, hi + 0.5], [0, f.plotW]);
  gridX(f.g, x, niceTicks(lo, hi, 6), rows.length * rowH, (t) => fmt(t, 0));

  rows.forEach((r, i) => {
    const y = i * rowH + rowH / 2 - 4;
    const dim = state.teamId && !isSel(r.team_id) ? 0.45 : 1;
    f.g.appendChild(
      el('text', { class: 'mark-label' + (isSel(r.team_id) ? ' strong' : ''), x: -10, y: y + 4, 'text-anchor': 'end' },
        shortName(r.team_id, L.nameChars))
    );
    f.g.appendChild(
      el('rect', {
        x: x(r.lo), y: y - 6, width: Math.max(x(r.hi) - x(r.lo), 2), height: 12, rx: 4,
        fill: 'var(--seq-100)', opacity: dim,
      })
    );
    f.g.appendChild(
      el('circle', { cx: x(r.actual), cy: y, r: 6, fill: markColor(r.team_id), stroke: 'var(--surface-1)', 'stroke-width': 2, opacity: dim })
    );
    const hit = el('rect', { class: 'hit', x: -labelW, y: i * rowH, width: f.plotW + labelW, height: rowH });
    selectable(hoverable(hit, teamName(r.team_id), r.rows), r.team_id);
    f.g.appendChild(hit);
  });
  return f.svg;
}

/* Multi-line over weeks - one team emphasised, the rest context gray. */
function emphasisLines(series, opts) {
  const L = layout();
  const o = Object.assign({ invertY: false, height: 380, yLabel: '', solidUntil: null, format: (v) => fmt(v, 0) }, opts || {});
  const f = frame(L.width, L.narrow ? Math.min(o.height, 300) : o.height,
                  { left: 40, right: L.markLabels ? 108 : 14, bottom: 34, top: 10 });
  const weeks = series[0].points.map((p) => p.x);
  const vals = series.flatMap((s) => s.points.map((p) => p.y));
  let lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = (hi - lo) * 0.08 || 1;
  lo -= pad; hi += pad;
  const x = linear([Math.min(...weeks), Math.max(...weeks)], [0, f.plotW]);
  const y = o.invertY ? linear([lo, hi], [0, f.plotH]) : linear([lo, hi], [f.plotH, 0]);

  gridY(f.g, y, niceTicks(lo, hi, 5), f.plotW, o.format);
  for (const w of weeks) {
    if (L.weekTickEvery > 1 && w % L.weekTickEvery !== 0
        && w !== weeks[0] && w !== weeks[weeks.length - 1]) continue;
    f.g.appendChild(el('text', { class: 'axis-label', x: x(w), y: f.plotH + 18, 'text-anchor': 'middle' }, String(w)));
  }
  f.g.appendChild(el('line', { class: 'baseline', x1: 0, x2: f.plotW, y1: f.plotH, y2: f.plotH }));

  const pathOf = (pts) => pts.map((p, i) => (i ? 'L' : 'M') + x(p.x) + ' ' + y(p.y)).join(' ');
  /* Everything up to solidUntil already happened; everything after it is
     simulated. Drawing them as one line implies the whole thing is measured.
     The segments share the boundary point so they meet without a gap. */
  const segments = (s) => {
    if (o.solidUntil === null || o.solidUntil === undefined) {
      return [{ pts: s.points, dash: null }];
    }
    const played = s.points.filter((p) => p.x <= o.solidUntil);
    const ahead = s.points.filter((p) => p.x >= o.solidUntil);
    const out = [];
    if (played.length > 1) out.push({ pts: played, dash: null });
    if (ahead.length > 1) out.push({ pts: ahead, dash: '5 4' });
    if (!out.length) out.push({ pts: s.points, dash: null });
    return out;
  };
  const context = series.filter((s) => !isSel(s.team_id));
  const focus = series.filter((s) => isSel(s.team_id));

  for (const s of context) {
    for (const seg of segments(s)) {
      f.g.appendChild(el('path', {
        d: pathOf(seg.pts), fill: 'none', stroke: 'var(--context)',
        'stroke-width': 1.5, 'stroke-dasharray': seg.dash,
        opacity: state.teamId ? 0.5 : 0.8,
      }));
    }
  }
  for (const s of focus) {
    for (const seg of segments(s)) {
      f.g.appendChild(el('path', {
        d: pathOf(seg.pts), fill: 'none', stroke: 'var(--accent)',
        'stroke-width': 2.5, 'stroke-dasharray': seg.dash,
      }));
    }
    for (const p of s.points) {
      const projected = o.solidUntil !== null && o.solidUntil !== undefined && p.x > o.solidUntil;
      f.g.appendChild(el('circle', {
        cx: x(p.x), cy: y(p.y), r: 4,
        fill: projected ? 'var(--surface-1)' : 'var(--accent)',
        stroke: 'var(--accent)', 'stroke-width': 2,
      }));
    }
  }

  /* Direct-label the emphasised line plus the two extremes; never every line. */
  const labelled = new Set();
  const last = (s) => s.points[s.points.length - 1];
  const ranked = series.slice().sort((a, b) => last(a).y - last(b).y);
  const picks = (L.markLabels
    ? [focus[0], ranked[0], ranked[ranked.length - 1]]
    : [focus[0]]).filter(Boolean);
  for (const s of picks) {
    if (labelled.has(s.team_id)) continue;
    labelled.add(s.team_id);
    const p = last(s);
    f.g.appendChild(
      el('text', Object.assign(
        { class: 'mark-label' + (isSel(s.team_id) ? ' strong' : '') },
        L.markLabels
          ? { x: x(p.x) + 8, y: y(p.y) + 4 }
          : { x: f.plotW - 2, y: y(p.y) - 9, 'text-anchor': 'end' }
      ), shortName(s.team_id, L.markLabels ? 14 : 18))
    );
  }

  /* Crosshair: nearest week, all teams in the tooltip. */
  const crosshair = el('line', { class: 'baseline', x1: 0, x2: 0, y1: 0, y2: f.plotH, opacity: 0 });
  f.g.appendChild(crosshair);
  const overlay = el('rect', { class: 'hit', x: 0, y: 0, width: f.plotW, height: f.plotH });
  overlay.addEventListener('mousemove', (ev) => {
    const box = overlay.getBoundingClientRect();
    const rel = ((ev.clientX - box.left) / box.width) * f.plotW;
    let best = weeks[0], bestD = Infinity;
    for (const w of weeks) {
      const d = Math.abs(x(w) - rel);
      if (d < bestD) { bestD = d; best = w; }
    }
    crosshair.setAttribute('x1', x(best));
    crosshair.setAttribute('x2', x(best));
    crosshair.setAttribute('opacity', 1);
    const at = series
      .map((s) => ({ s, p: s.points.find((p) => p.x === best) }))
      .filter((r) => r.p)
      .sort((a, b) => (o.invertY ? a.p.y - b.p.y : b.p.y - a.p.y))
      .slice(0, 6)
      .map((r) => (isSel(r.s.team_id) ? '<b>' : '') + shortName(r.s.team_id, 18) + ' ' + o.format(r.p.y) + (isSel(r.s.team_id) ? '</b>' : ''));
    tip.show(ev.clientX, ev.clientY, 'Week ' + best, at);
  });
  overlay.addEventListener('mouseleave', () => { crosshair.setAttribute('opacity', 0); tip.hide(); });

  /* The overlay covers every line, so a click has to work out which one was
     meant: nearest week first, then the closest series at that week. */
  overlay.addEventListener('click', (ev) => {
    const box = overlay.getBoundingClientRect();
    const relX = ((ev.clientX - box.left) / box.width) * f.plotW;
    const relY = ((ev.clientY - box.top) / box.height) * f.plotH;
    let week = weeks[0], weekD = Infinity;
    for (const w of weeks) {
      const d = Math.abs(x(w) - relX);
      if (d < weekD) { weekD = d; week = w; }
    }
    let pick = null, pickD = Infinity;
    for (const sr of series) {
      const pt = sr.points.find((q) => q.x === week);
      if (!pt) continue;
      const d = Math.abs(y(pt.y) - relY);
      if (d < pickD) { pickD = d; pick = sr; }
    }
    if (pick) selectTeam(pick.team_id);
  });
  overlay.style.cursor = 'pointer';
  f.g.appendChild(overlay);
  return f.svg;
}

/* ---------------------------------------------------------------- views */

const views = {};

views.standings = () => {
  const st = state.data.standings;
  const wrap = document.createDocumentFragment();

  const lucky = st.slice().sort((a, b) => b.wins_above_expected - a.wins_above_expected)[0];
  const unlucky = st.slice().sort((a, b) => a.wins_above_expected - b.wins_above_expected)[0];
  const top = st[0];

  wrap.appendChild(
    h('div', { class: 'tiles' },
      tile('League leader', rec(top.wins, top.losses), teamName(top.team_id)),
      tile('Luckiest', signed(lucky.wins_above_expected) + ' wins', teamName(lucky.team_id) + ' · ' + rec(lucky.wins, lucky.losses)),
      tile('Unluckiest', signed(unlucky.wins_above_expected) + ' wins', teamName(unlucky.team_id) + ' · ' + rec(unlucky.wins, unlucky.losses))
    )
  );

  const rows = st.map((r) => ({
    team_id: r.team_id,
    selected: isSel(r.team_id),
    cells: [
      r.rank + '. ' + teamName(r.team_id),
      rec(r.wins, r.losses),
      fmt(r.points_for, 1),
      fmt(r.points_against, 1),
      rec(r.ap_wins, r.ap_losses),
      rec(r.median_wins, r.median_losses),
      fmt(r.avg_score, 1),
      fmt(r.score_sd, 1),
    ],
  }));

  wrap.appendChild(
    card('Standings', 'Record vs. all is every team’s result against all eleven other teams each week. Median record is the same idea against the weekly median.',
      tableEl(['Team', 'Record', 'PF', 'PA', 'Record vs. all', 'Median', 'Avg', 'SD'], rows))
  );

  const db = st.slice().sort((a, b) => b.all_play_pct - a.all_play_pct).map((r) => ({
    team_id: r.team_id,
    a: r.win_pct * 100,
    b: r.all_play_pct * 100,
    rows: [
      'Actual <b>' + pct(r.win_pct) + '</b> (' + rec(r.wins, r.losses) + ')',
      'All-play <b>' + pct(r.all_play_pct) + '</b> (' + rec(r.ap_wins, r.ap_losses) + ')',
    ],
  }));

  wrap.appendChild(
    card('Real record vs. all-play record',
      'A long connector means the schedule, not the scoring, decided the record.',
      legend([['Actual win %', 'var(--seq-250)'], ['All-play win %', 'var(--seq-550)']]),
      dumbbell(db, { format: (v) => fmt(v, 0) + '%' }))
  );
  return wrap;
};

views.expected = () => {
  const st = state.data.standings;
  const wrap = document.createDocumentFragment();

  const wae = st.slice().sort((a, b) => b.wins_above_expected - a.wins_above_expected).map((r) => ({
    team_id: r.team_id,
    value: r.wins_above_expected,
    rows: [
      'Actual <b>' + r.wins + '</b> wins',
      'Expected <b>' + fmt(r.expected_wins, 2) + '</b>',
      'Probability <b>' + pct(r.luck_probability, 1) + '</b>',
    ],
  }));

  wrap.appendChild(
    card('Wins above expected',
      'Expected wins is the sum of weekly all-play win percentages — the number of wins a team’s scoring earns against a random opponent each week.',
      legend([['Above expectation', 'var(--pole-pos)'], ['Below expectation', 'var(--pole-neg)']]),
      divergingBars(wae, { dp: 2 }),
      caption('Positive means the schedule handed a team wins its scoring did not earn.'))
  );

  const rows = st.slice().sort((a, b) => b.expected_wins - a.expected_wins).map((r) => ({
    team_id: r.team_id,
    selected: isSel(r.team_id),
    cells: [
      teamName(r.team_id),
      rec(r.wins, r.losses),
      fmt(r.expected_wins, 2),
      { text: signed(r.wins_above_expected), cls: r.wins_above_expected > 0 ? 'pos' : r.wins_above_expected < 0 ? 'neg' : '' },
      pct(r.luck_probability, 1),
      fmt(r.expected_wins_sd, 2),
    ],
  }));
  wrap.appendChild(
    card('Expected wins',
      'Probability is how ordinary a record is given the scoring behind it — near 100% means the record fits, near 0% means the schedule produced it.',
      tableEl(['Team', 'Record', 'Expected', 'Above exp.', 'Probability', 'SD'], rows))
  );

  const sos = st.slice().sort((a, b) => b.sos - a.sos).map((r) => ({
    team_id: r.team_id,
    value: r.sos,
    rows: [
      'Opponent PPG <b>' + fmt(r.opponent_ppg, 1) + '</b>',
      'League PPG <b>' + fmt(r.league_ppg, 1) + '</b>',
    ],
  }));
  wrap.appendChild(
    card('Strength of schedule',
      'Average opponent points per game against the league average, in points. Opponent win percentage would inherit those opponents’ own luck; points do not.',
      legend([['Harder schedule', 'var(--pole-pos)'], ['Easier schedule', 'var(--pole-neg)']]),
      divergingBars(sos, { dp: 1, unit: ' pts' }))
  );
  return wrap;
};

views.schedule = () => {
  const sw = state.data.schedule_swap;
  const wrap = document.createDocumentFragment();
  const spread = sw.summary.slice().sort((a, b) => (b.best_wins - b.worst_wins) - (a.best_wins - a.worst_wins));
  const worst = spread[0];

  wrap.appendChild(
    h('div', { class: 'tiles' },
      tile('Most schedule-dependent', worst ? teamName(worst.team_id) : '–',
        worst ? rec(worst.actual_wins, worst.actual_losses) + ' actual, ' + worst.worst_wins + '–' + worst.best_wins + ' wins possible' : '')
    )
  );

  const rows = sw.summary.slice().sort((a, b) => b.actual_wins - a.actual_wins).map((r) => ({
    team_id: r.team_id,
    lo: r.worst_wins,
    hi: r.best_wins,
    actual: r.actual_wins,
    rows: [
      'Actual <b>' + rec(r.actual_wins, r.actual_losses) + '</b>',
      'Best <b>' + rec(r.best_wins, r.best_losses) + '</b> on ' + r.best_schedule_owner + '’s schedule',
      'Worst <b>' + rec(r.worst_wins, r.worst_losses) + '</b> on ' + r.worst_schedule_owner + '’s schedule',
    ],
  }));

  wrap.appendChild(
    card('What every schedule in the league would have produced',
      'Each team’s weekly scores replayed against all twelve schedules. The bar is the full range of records those schedules produce; the dot is what actually happened.',
      legend([['Range across all schedules', 'var(--seq-100)'], ['Actual record', 'var(--accent)']]),
      rangeBars(rows),
      caption('A dot at the left end of a long bar is a team that got the worst schedule available to it.'))
  );

  const tbl = sw.summary.slice().sort((a, b) => b.actual_wins - a.actual_wins).map((r) => ({
    team_id: r.team_id,
    selected: isSel(r.team_id),
    cells: [
      teamName(r.team_id),
      rec(r.actual_wins, r.actual_losses),
      rec(r.best_wins, r.best_losses),
      r.best_schedule_owner,
      rec(r.worst_wins, r.worst_losses),
      r.worst_schedule_owner,
      fmt(r.mean_wins_all_schedules, 2),
    ],
  }));
  wrap.appendChild(
    card('Schedule analysis',
      'The team in each schedule column is whose schedule would have produced that record.',
      tableEl(['Team', 'Actual', 'Best', 'with schedule of', 'Worst', 'with schedule of', 'Avg'], tbl))
  );
  return wrap;
};

views.power = () => {
  const pr = state.data.power_rankings;
  const byTeam = new Map();
  for (const r of pr) {
    if (!byTeam.has(r.team_id)) byTeam.set(r.team_id, []);
    byTeam.get(r.team_id).push(r);
  }
  const series = [...byTeam.entries()].map(([team_id, rows]) => ({
    team_id,
    points: rows.sort((a, b) => a.week - b.week).map((r) => ({ x: r.week, y: r.power_rank })),
  }));

  const last = pr.filter((r) => r.week === Math.max(...pr.map((x) => x.week))).sort((a, b) => a.power_rank - b.power_rank);
  const wrap = document.createDocumentFragment();
  wrap.appendChild(
    card('Power ranking by week',
      'Rank 1 is at the top. Pick a team above to follow it through the season.',
      emphasisLines(series, { invertY: true, height: 400, format: (v) => '#' + fmt(v, 0) }))
  );
  wrap.appendChild(
    card('Final power ranking',
      'Score = ((average score × 6) + ((high + low) × 2) + (win % × 400)) ÷ 10',
      tableEl(['Team', 'Rank', 'Score', 'Avg', 'High', 'Low', 'Win %'],
        last.map((r) => ({
          team_id: r.team_id,
          selected: isSel(r.team_id),
          cells: [teamName(r.team_id), '#' + r.power_rank, fmt(r.power_score, 1), fmt(r.avg_score, 1), fmt(r.high, 1), fmt(r.low, 1), pct(r.win_pct)],
        }))))
  );
  return wrap;
};

views.quadrants = () => {
  const weeks = state.data.league.weeks_played;
  if (state.quadWeek === null) state.quadWeek = weeks[weeks.length - 1];
  const week = state.quadWeek;
  const pts = state.data.quad.filter((r) => r.week === week);
  const wrap = document.createDocumentFragment();

  const slider = h('div', { class: 'toolbar', style: 'padding-left:0;padding-top:0' },
    h('label', { for: 'quad-week', text: 'Week' }),
    h('select', {
      id: 'quad-week',
      onchange: (ev) => { state.quadWeek = Number(ev.target.value); render(); },
    }, weeks.map((w) => h('option', { value: w, selected: w === week ? 'selected' : null, text: 'Week ' + w })))
  );

  const L = layout();
  const quadH = L.narrow ? Math.round(L.width * 1.05) + 60
                        : Math.round(Math.min(560, Math.max(420, L.width * 0.66)));
  const f = frame(L.width, quadH,
                  { left: L.narrow ? 38 : 56, right: L.narrow ? 14 : 24, bottom: 44, top: 16 });
  const pf = pts.map((p) => p.cum_pf), pa = pts.map((p) => p.cum_pa);
  const padX = (Math.max(...pf) - Math.min(...pf)) * 0.12 || 10;
  const padY = (Math.max(...pa) - Math.min(...pa)) * 0.12 || 10;
  const x = linear([Math.min(...pf) - padX, Math.max(...pf) + padX], [0, f.plotW]);
  /* PA increases downward: lower on the chart is a worse defence. */
  const y = linear([Math.min(...pa) - padY, Math.max(...pa) + padY], [0, f.plotH]);
  const avgPf = pts[0].league_avg_pf, avgPa = pts[0].league_avg_pa;

  gridX(f.g, x, niceTicks(Math.min(...pf) - padX, Math.max(...pf) + padX, 5), f.plotH, (t) => fmt(t, 0));
  gridY(f.g, y, niceTicks(Math.min(...pa) - padY, Math.max(...pa) + padY, 5), f.plotW, (t) => fmt(t, 0));

  f.g.appendChild(el('line', { class: 'baseline', x1: x(avgPf), x2: x(avgPf), y1: 0, y2: f.plotH }));
  f.g.appendChild(el('line', { class: 'baseline', x1: 0, x2: f.plotW, y1: y(avgPa), y2: y(avgPa) }));

  const corner = (tx, ty, anchor, label) =>
    f.g.appendChild(el('text', { class: 'axis-label', x: tx, y: ty, 'text-anchor': anchor, opacity: 0.75 }, label));
  corner(f.plotW - 4, 16, 'end', L.narrow ? 'good' : 'scores a lot, gives up little');
  corner(4, 16, 'start', L.narrow ? 'stingy' : 'gives up little, scores little');
  corner(f.plotW - 4, f.plotH - 8, 'end', 'shootouts');
  corner(4, f.plotH - 8, 'start', 'ass');

  const quadLabels = [];
  for (const p of pts) {
    const sel = isSel(p.team_id);
    const cx = x(p.cum_pf), cy = y(p.cum_pa);
    f.g.appendChild(el('circle', {
      cx, cy, r: sel ? (L.narrow ? 8 : 7) : (L.narrow ? 6 : 5),
      fill: markColor(p.team_id),
      stroke: 'var(--surface-1)', 'stroke-width': 2,
      opacity: state.teamId && !sel ? 0.55 : 1,
    }));
    if (L.markLabels || sel) {
      quadLabels.push(f.g.appendChild(el('text', {
        class: 'mark-label' + (sel ? ' strong' : ''),
        x: cx, y: cy - 11, 'text-anchor': 'middle',
      }, shortName(p.team_id, L.narrow ? 16 : 14))));
    }
    const hit = el('circle', { class: 'hit', cx, cy, r: L.narrow ? 18 : 14 });
    hoverable(hit, teamName(p.team_id), [
      'Through week ' + week + ': <b>' + rec(p.cum_wins, p.cum_losses) + '</b>',
      'Points for <b>' + fmt(p.cum_pf, 1) + '</b>',
      'Points against <b>' + fmt(p.cum_pa, 1) + '</b>',
    ]);
    selectable(hit, p.team_id);
    f.g.appendChild(hit);
  }
  if (!L.narrow) {
    f.g.appendChild(el('text', { class: 'axis-label', x: f.plotW / 2, y: f.plotH + 34, 'text-anchor': 'middle' }, 'Points for →'));
    f.g.appendChild(el('text', { class: 'axis-label', x: -f.plotH / 2, y: -38, transform: 'rotate(-90)', 'text-anchor': 'middle' }, '← Points against'));
  }
  onMount(f.svg, () => decollide(quadLabels, { height: f.plotH }));

  wrap.appendChild(
    card('Quadrants',
      'Cumulative points for and against through the selected week, against the league average in each. All dots share one color — the quadrant is already carried by position.',
      slider, f.svg,
      detailsTable('Table view', ['Team', 'PF', 'PA', 'Record', 'Quadrant'],
        pts.slice().sort((a, b) => b.cum_pf - a.cum_pf).map((p) => ({
          team_id: p.team_id,
          selected: isSel(p.team_id),
          cells: [teamName(p.team_id), fmt(p.cum_pf, 1), fmt(p.cum_pa, 1), rec(p.cum_wins, p.cum_losses), p.quadrant],
        }))))
  );
  return wrap;
};

/* One team's projected final win total as of each origin week, against what
   actually happened. The question the forecast tab is really for: is this team
   beating the expectation its own scoring set? */
function projectionTracker(origins, points, wins, opts) {
  const L = layout();
  const o = Object.assign({ complete: true }, opts || {});
  const f = frame(L.width, L.narrow ? 270 : 310,
                  { left: L.narrow ? 32 : 40, right: 14, bottom: 34, top: 16 });

  /* The projection line stops at the last origin, but the wins line runs to
     the last week played - which on a finished season is one further. Give the
     axis the wider of the two so the wins line reaches its real total. */
  const lastOrigin = origins[origins.length - 1];
  const lastWeek = wins.length ? wins[wins.length - 1].week : lastOrigin;
  const xMax = Math.max(lastOrigin, lastWeek);

  const vals = [];
  for (const p of points) vals.push(p.p10, p.p90, p.avg);
  for (const w of wins) vals.push(w.cum);
  const lo = Math.max(0, Math.floor(Math.min.apply(null, vals) - 1));
  const hi = Math.ceil(Math.max.apply(null, vals) + 1);
  const x = linear([origins[0], xMax], [0, f.plotW]);
  const y = linear([lo, hi], [f.plotH, 0]);

  gridY(f.g, y, niceTicks(lo, hi, 5), f.plotW, (t) => fmt(t, 0));
  for (let w = origins[0]; w <= xMax; w++) {
    if (L.weekTickEvery > 1 && w % L.weekTickEvery !== 0
        && w !== origins[0] && w !== xMax) continue;
    f.g.appendChild(el('text', { class: 'axis-label', x: x(w), y: f.plotH + 18, 'text-anchor': 'middle' }, String(w)));
  }
  f.g.appendChild(el('line', { class: 'baseline', x1: 0, x2: f.plotW, y1: f.plotH, y2: f.plotH }));

  const top = points.map((p, i) => x(origins[i]) + ' ' + y(p.p90));
  const bottom = points.map((p, i) => x(origins[i]) + ' ' + y(p.p10)).reverse();
  f.g.appendChild(el('path', {
    d: 'M' + top.join(' L') + ' L' + bottom.join(' L') + ' Z',
    fill: 'var(--accent-soft)', opacity: 0.55,
  }));

  /* Wins arrive one game at a time, so they step rather than slope. */
  if (wins.length) {
    let d = 'M' + x(wins[0].week) + ' ' + y(wins[0].cum);
    for (let i = 1; i < wins.length; i++) {
      d += ' L' + x(wins[i].week) + ' ' + y(wins[i - 1].cum)
         + ' L' + x(wins[i].week) + ' ' + y(wins[i].cum);
    }
    f.g.appendChild(el('path', {
      d, fill: 'none', stroke: 'var(--text-secondary)', 'stroke-width': 2,
    }));
    const last = wins[wins.length - 1];
    f.g.appendChild(el('text', {
      class: 'mark-label strong', x: x(last.week) - 2, y: y(last.cum) - 8, 'text-anchor': 'end',
    }, last.cum + (last.cum === 1 ? ' win' : ' wins')));

    for (const w of wins) {
      const hit = el('circle', { class: 'hit', cx: x(w.week), cy: y(w.cum), r: L.narrow ? 15 : 12 });
      hoverable(hit, 'Through week ' + w.week, [
        'Record <b>' + rec(w.cum, w.losses) + '</b>',
        w.won === null ? '' : 'Week ' + w.week + ': <b>' + (w.won ? 'won' : 'lost') + '</b>',
      ].filter(Boolean));
      f.g.appendChild(hit);
    }
  }

  const path = points.map((p, i) => (i ? 'L' : 'M') + x(origins[i]) + ' ' + y(p.avg)).join(' ');
  f.g.appendChild(el('path', {
    d: path, fill: 'none', stroke: 'var(--accent)',
    'stroke-width': 2.5, 'stroke-dasharray': '5 4',
  }));

  points.forEach((p, i) => {
    const cx = x(origins[i]), cy = y(p.avg);
    f.g.appendChild(el('circle', {
      cx, cy, r: 4, fill: 'var(--surface-1)', stroke: 'var(--accent)', 'stroke-width': 2,
    }));
    const hit = el('circle', { class: 'hit', cx, cy, r: L.narrow ? 16 : 13 });
    hoverable(hit, 'Forecast after week ' + origins[i], [
      'Projected final <b>' + fmt(p.avg, 2) + '</b> wins',
      'Range <b>' + fmt(p.p10, 0) + '–' + fmt(p.p90, 0) + '</b>',
      'Playoff odds <b>' + pct(p.playoff_pct, 1) + '</b>',
    ]);
    f.g.appendChild(hit);
  });
  return f.svg;
}


views.forecast = () => {
  const fc = state.data.forecast;
  const wrap = document.createDocumentFragment();
  const origins = fc.origins || [];

  if (!origins.length) {
    wrap.appendChild(card('Forecast', 'Not enough completed weeks to simulate from.'));
    return wrap;
  }
  if (state.forecastOrigin === null || origins.indexOf(state.forecastOrigin) < 0) {
    state.forecastOrigin = fc.latest;
  }
  const origin = state.forecastOrigin;
  const cut = fc.by_origin[String(origin)];
  const isLatest = origin === fc.latest;

  const picker = h('div', { class: 'toolbar', style: 'padding-left:0;padding-top:0' },
    h('label', { for: 'fc-origin', text: 'Forecast from' }),
    h('select', {
      id: 'fc-origin',
      onchange: (ev) => { state.forecastOrigin = Number(ev.target.value); render(); },
    }, origins.map((w) => h('option', {
      value: w,
      selected: w === origin ? 'selected' : null,
      text: 'Week ' + w + (w === fc.latest ? ' (latest)' : ''),
    }))),
    h('span', { class: 'hint', text: 'of ' + fc.total_weeks + ' scheduled' })
  );

  const series = state.data.teams.map((t) => ({
    team_id: t.team_id,
    points: cut.race.map((r) => ({ x: r.week, y: r.avg_cumulative_wins[String(t.team_id)] || 0 })),
  }));

  wrap.appendChild(
    card('Projected season race',
      'Average cumulative wins across ' + fc.n_sims.toLocaleString() +
      ' simulated seasons run from the state after week ' + origin +
      '. Solid is what was played, dashed is simulated. Scores are drawn from each team’s own scoring distribution — no player projections.',
      picker,
      emphasisLines(series, { height: 380, solidUntil: origin, format: (v) => fmt(v, 1) }),
      caption(!isLatest
        ? 'Wound back to week ' + origin + ', so anything after it is ignored.'
        : fc.season_complete
          ? 'The last week with games still to play. Wind it back to see the season from earlier on.'
          : 'The live forecast: every result so far is counted.'))
  );

  if (state.teamId !== null) {
    const pts = origins.map((w) => {
      const rows = fc.by_origin[String(w)].teams;
      const row = rows.filter((t) => t.team_id === state.teamId)[0];
      return row
        ? { avg: row.avg_wins, p10: row.win_p10, p90: row.win_p90, playoff_pct: row.playoff_pct }
        : null;
    }).filter(Boolean);

    const st = state.data.standings.filter((r) => r.team_id === state.teamId)[0];
    const actual = st ? st.wins : 0;
    /* quad already carries cumulative wins per team per week. */
    const winsByWeek = state.data.quad
      .filter((r) => r.team_id === state.teamId)
      .sort((a, b) => a.week - b.week)
      .map((r, i, all) => ({
        week: r.week,
        cum: r.cum_wins,
        losses: r.cum_losses,
        won: i === 0 ? r.cum_wins > 0 : r.cum_wins > all[i - 1].cum_wins,
      }));
    const first = pts[0], last = pts[pts.length - 1];
    const gap = actual - first.avg;
    const verdict = Math.abs(gap) < 0.5
      ? 'essentially matching it.'
      : (gap > 0 ? 'beating' : 'falling short of') + ' it by ' + fmt(Math.abs(gap), 1) + ' wins.';

    wrap.appendChild(
      card(teamName(state.teamId) + ' against its own projections',
        'Dashed is projected, solid is what happened. The dashed line is the projected final win total as of each week, with its 10th to 90th percentile band; the stepped line is wins actually banked. Where they meet is when the model caught on.',
        legend([
          ['Projected final wins (dashed)', 'var(--accent)'],
          ['10th–90th percentile', 'var(--accent-soft)'],
          ['Wins after each week (solid)', 'var(--text-secondary)'],
        ]),
        projectionTracker(origins, pts, winsByWeek, { complete: fc.season_complete }),
        caption('Projected ' + fmt(first.avg, 2) + ' wins after week ' + origins[0] +
          ' and ' + fmt(last.avg, 2) + ' by week ' + origins[origins.length - 1] + '. ' +
          (fc.season_complete
            ? 'Finished with ' + actual + ', ' + verdict
            : 'Has banked ' + actual + ' with ' + (fc.total_weeks - state.data.league.weeks_played.length) + ' weeks left.')))
    );
  } else {
    wrap.appendChild(
      card('Track a team against its own projections',
        'Pick a team above — or tap any mark — to see how its projected final win total moved as the season went on.')
    );
  }

  const rows = cut.teams.slice().sort((a, b) => b.avg_wins - a.avg_wins).map((r) => ({
    team_id: r.team_id,
    selected: isSel(r.team_id),
    cells: [
      teamName(r.team_id),
      fmt(r.actual_wins, 0) + ' / #' + r.actual_seed,
      fmt(r.avg_wins, 2),
      fmt(r.win_p10, 0) + '–' + fmt(r.win_p90, 0),
      pct(r.playoff_pct, 1),
      '#' + fmt(r.avg_seed, 1),
      pct(r.same_finish_pct, 1),
    ],
  }));
  wrap.appendChild(
    card('Projected standings',
      (fc.season_complete
        ? 'What the season looked like it would do from week ' + origin + ', against what it actually did. A low “same finish” means the rest went off script.'
        : 'Where the season is heading from week ' + origin + '. “So far” is the record banked to date.'),
      tableEl(['Team', fc.season_complete ? 'Actual' : 'So far', 'Avg wins', 'Range (10–90%)', 'Playoffs', 'Avg seed', fc.season_complete ? 'Same finish' : 'Holds seed'], rows))
  );
  return wrap;
};

/* ---------------------------------------------------------------- shell */

/* `toTop: true` for a change that makes the old scroll position meaningless -
   switching view. Everything else (picking a team, a week, a season) keeps the
   reader where they were. */
function render(opts) {
  const main = $('#view');
  const toTop = !!(opts && opts.toTop);
  const scrollBefore = window.scrollY;

  /* Emptying the container collapses the document - on a phone, 2355px down to
     the 812px viewport - and the browser clamps the scroll position to that new
     maximum. Restoring the content afterwards does not restore the scroll, so
     tapping a mark threw the reader back to the top. Pin the height across the
     swap so the page never shrinks. */
  main.style.minHeight = main.offsetHeight + 'px';
  main.innerHTML = '';
  main.appendChild(views[state.view]());
  for (const svg of main.querySelectorAll('svg.chart')) {
    if (svg.__fixup) svg.__fixup();
  }
  main.style.minHeight = '';

  if (toTop) {
    window.scrollTo(0, 0);
  } else if (window.scrollY !== scrollBefore) {
    /* Clamps on its own if the new view is shorter. */
    window.scrollTo(0, scrollBefore);
  }

  for (const tab of document.querySelectorAll('.tab')) {
    tab.setAttribute('aria-selected', tab.dataset.view === state.view ? 'true' : 'false');
  }
  const url = new URL(location.href);
  url.searchParams.set('view', state.view);
  if (state.season) url.searchParams.set('season', state.season);
  if (state.teamId) url.searchParams.set('team', state.teamId);
  else url.searchParams.delete('team');
  history.replaceState(null, '', url);
}

function applyTheme(mode) {
  if (mode) document.documentElement.setAttribute('data-theme', mode);
  const dark =
    document.documentElement.getAttribute('data-theme') === 'dark' ||
    (!document.documentElement.getAttribute('data-theme') &&
      window.matchMedia('(prefers-color-scheme: dark)').matches);
  $('#theme-toggle').textContent = dark ? 'Light' : 'Dark';
}

function fail(message) {
  $('#view').innerHTML = '';
  $('#view').appendChild(card('Could not load league data', message));
}

/* Swap in a season. team_id is stable across seasons in this league, so the
   highlighted team survives the switch; a team that wasn't in that season
   falls back to none. */
async function loadSeason(year) {
  let data;
  try {
    /* Revalidate rather than trust the cache. GitHub Pages serves these with
       a ten-minute max-age, so after a refresh changes the JSON the page would
       otherwise run new code against old data - and when the shape changes,
       that is not stale, it is broken. A 304 costs almost nothing. */
    const res = await fetch('data/' + year + '.json', { cache: 'no-cache' });
    if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
    data = await res.json();
  } catch (err) {
    fail('data/' + year + '.json failed: ' + err.message +
      '. This page reads JSON files, so it needs to be served over http rather than opened from disk.');
    return false;
  }
  state.data = data;
  state.quadWeek = null;
  state.forecastOrigin = null;

  /* The league names itself, so a fork needs no edit here. */
  if (data.league.name) {
    const title = $('#league-name');
    if (title) title.textContent = data.league.name;
    document.title = data.league.name;
  }
  $('#season-line').textContent =
    data.season + ' season · ' + data.league.team_count + ' teams · ' +
    data.league.weeks_played.length + ' weeks played';
  $('#updated-line').textContent = 'updated ' + new Date(data.generated_at).toLocaleDateString();

  const sel = $('#team-select');
  const keep = state.teamId;
  sel.innerHTML = '';
  sel.appendChild(h('option', { value: '', text: 'None (all teams equal)' }));
  for (const t of data.teams) sel.appendChild(h('option', { value: t.team_id, text: t.name }));
  if (keep !== null && data.teams.some((t) => t.team_id === keep)) {
    sel.value = String(keep);
    state.teamId = keep;
  } else {
    sel.value = '';
    state.teamId = null;
  }
  return true;
}

async function boot() {
  const params = new URLSearchParams(location.search);

  let manifest;
  try {
    const res = await fetch('data/seasons.json', { cache: 'no-cache' });
    if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
    manifest = (await res.json()).seasons;
  } catch (err) {
    manifest = [{ season: Number(params.get('season')) || 2025 }];
  }
  state.seasons = manifest;

  const wanted = Number(params.get('season'));
  state.season = manifest.some((s) => s.season === wanted) ? wanted : manifest[0].season;

  const seasonSel = $('#season-select');
  for (const s of manifest) {
    seasonSel.appendChild(h('option', { value: s.season, text: String(s.season) }));
  }
  seasonSel.value = String(state.season);
  seasonSel.addEventListener('change', async (ev) => {
    state.season = Number(ev.target.value);
    if (await loadSeason(state.season)) render();
  });

  const team = Number(params.get('team'));
  if (team) state.teamId = team;
  if (!(await loadSeason(state.season))) return;

  $('#team-select').addEventListener('change', (ev) => {
    state.teamId = ev.target.value ? Number(ev.target.value) : null;
    render();
  });

  for (const tab of document.querySelectorAll('.tab')) {
    tab.addEventListener('click', () => { state.view = tab.dataset.view; render({ toTop: true }); });
  }
  const view = params.get('view');
  if (view && views[view]) state.view = view;

  $('#theme-toggle').addEventListener('click', () => {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark' ||
      (!document.documentElement.getAttribute('data-theme') && window.matchMedia('(prefers-color-scheme: dark)').matches);
    applyTheme(dark ? 'light' : 'dark');
    render();
  });
  /* Charts are built at a measured width, so a resize or rotate needs a
     rebuild. Debounced, and skipped when the width has not actually moved -
     mobile browsers fire resize on every address-bar show/hide. */
  let lastWidth = window.innerWidth;
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    if (window.innerWidth === lastWidth) return;
    lastWidth = window.innerWidth;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => render(), 150);
  });

  applyTheme(null);
  render();
}

boot();
