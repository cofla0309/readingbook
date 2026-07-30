/* 직접 만든 인라인 SVG 차트.
   외부 라이브러리도 CDN도 쓰지 않는다 — 인터넷이 끊겨도 그대로 뜨게.

   마크 규격은 고정이다: 막대 ≤24px + 데이터 끝만 4px 라운드,
   선 2px, 점 지름 ≥8px + 표면색 2px 링, 인접 막대 사이 2px 표면 갭,
   격자·축은 1px 실선으로 뒤로 물린다. 값 라벨은 전부가 아니라
   최고점·끝점처럼 이야기가 있는 곳에만 붙인다. */

const SVGNS = 'http://www.w3.org/2000/svg';

/* ── 툴팁 (전 차트 공용 하나) ─────────────────────────────── */

const tip = (() => {
  let el = null;
  const ensure = () => {
    if (!el) {
      el = document.createElement('div');
      el.className = 'tooltip';
      document.body.appendChild(el);
    }
    return el;
  };
  return {
    show(html, evt) {
      const t = ensure();
      t.innerHTML = html;
      t.classList.add('on');
      const pad = 12;
      const r = t.getBoundingClientRect();
      let x = evt.clientX + pad;
      let y = evt.clientY - r.height - pad;
      if (x + r.width > window.innerWidth - 8) x = evt.clientX - r.width - pad;
      if (y < 8) y = evt.clientY + pad;
      t.style.left = x + 'px';
      t.style.top = y + 'px';
    },
    hide() { if (el) el.classList.remove('on'); },
  };
})();

/* ── 헬퍼 ────────────────────────────────────────────────── */

function el(name, attrs = {}, text = null) {
  const node = document.createElementNS(SVGNS, name);
  for (const [k, v] of Object.entries(attrs)) {
    if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  if (text !== null) node.textContent = text;
  return node;
}

function svgRoot(w, h) {
  const s = el('svg', {
    viewBox: `0 0 ${w} ${h}`,
    width: w,
    height: h,
    role: 'img',
    preserveAspectRatio: 'xMinYMin meet',
  });
  return s;
}

/** 0 / 50 / 100 처럼 읽기 좋은 눈금. */
function niceTicks(max, count = 4) {
  if (!max || max <= 0) return [0, 1];
  const raw = max / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const ticks = [];
  for (let v = 0; v <= max + step * 0.001; v += step) ticks.push(Math.round(v * 100) / 100);
  if (ticks[ticks.length - 1] < max) ticks.push(ticks[ticks.length - 1] + step);
  return ticks;
}

const fmt = (n) => Number(n).toLocaleString('ko-KR');

/** 위쪽 두 모서리만 둥근 막대. 바닥(기준선)은 각지게 둔다. */
function barPathUp(x, y, w, h, r = 4) {
  if (h <= 0.5) return `M${x},${y + h} h${w} v${-Math.max(h, 0.5)} h${-w} Z`;
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h} L${x},${y + rr} Q${x},${y} ${x + rr},${y} ` +
         `L${x + w - rr},${y} Q${x + w},${y} ${x + w},${y + rr} L${x + w},${y + h} Z`;
}

/** 오른쪽 두 모서리만 둥근 가로 막대. */
function barPathRight(x, y, w, h, r = 4) {
  if (w <= 0.5) return `M${x},${y} h0.5 v${h} h-0.5 Z`;
  const rr = Math.min(r, h / 2, w);
  return `M${x},${y} L${x + w - rr},${y} Q${x + w},${y} ${x + w},${y + rr} ` +
         `L${x + w},${y + h - rr} Q${x + w},${y + h} ${x + w - rr},${y + h} L${x},${y + h} Z`;
}

function emptyNote(root, message) {
  root.innerHTML = `<div class="empty-state tiny">${message}</div>`;
}

/* ── ① 세로 막대 (월별, 최근 N일) ─────────────────────────── */

export function columnChart(root, opts) {
  const {
    data = [], value = 'value', label = 'label',
    unit = '', height = 190, title = '',
    tooltip = null, labelEvery = 1, highlightMax = true,
  } = opts;

  root.innerHTML = '';
  if (!data.length || data.every((d) => !d[value])) {
    emptyNote(root, '아직 기록이 없습니다.');
    return;
  }

  const padL = 44, padR = 12, padT = 16, padB = 26;
  const slot = Math.max(18, Math.min(56, 640 / data.length));
  const w = Math.max(280, padL + padR + slot * data.length);
  const h = height;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;

  const max = Math.max(...data.map((d) => d[value] || 0));
  const ticks = niceTicks(max);
  const top = ticks[ticks.length - 1] || 1;
  const yOf = (v) => padT + plotH - (v / top) * plotH;

  const s = svgRoot(w, h);
  if (title) s.appendChild(el('title', {}, title));

  // 격자 + y축 눈금
  for (const t of ticks) {
    const y = yOf(t);
    s.appendChild(el('line', {
      class: 'grid-line', x1: padL, x2: padL + plotW, y1: y, y2: y,
    }));
    s.appendChild(el('text', {
      class: 'tick', x: padL - 8, y: y + 4, 'text-anchor': 'end',
    }, fmt(t)));
  }
  s.appendChild(el('line', {
    class: 'axis-line', x1: padL, x2: padL + plotW, y1: yOf(0), y2: yOf(0),
  }));

  // 인접 막대 사이 2px 표면 갭 + 24px 상한
  const barW = Math.max(3, Math.min(24, slot - 2));
  const maxIdx = highlightMax ? data.indexOf(data.find((d) => d[value] === max)) : -1;

  data.forEach((d, i) => {
    const v = d[value] || 0;
    const cx = padL + slot * i + slot / 2;
    const x = cx - barW / 2;
    const y = yOf(v);
    const bh = yOf(0) - y;

    const path = el('path', {
      class: 'bar' + (v ? '' : ' muted'),
      d: barPathUp(x, y, barW, bh),
    });
    s.appendChild(path);

    // 히트 영역은 막대보다 넓게 잡는다(얇은 막대도 쉽게 잡히도록).
    const hit = el('rect', {
      class: 'hit', x: padL + slot * i, y: padT, width: slot, height: plotH,
    });
    hit.addEventListener('mousemove', (e) =>
      tip.show(tooltip ? tooltip(d) : `${d[label]}<br><span class="t-val">${fmt(v)}${unit}</span>`, e));
    hit.addEventListener('mouseleave', tip.hide);
    s.appendChild(hit);

    if (i % labelEvery === 0) {
      s.appendChild(el('text', {
        class: 'tick', x: cx, y: h - 8, 'text-anchor': 'middle',
      }, d[label]));
    }
    // 값 라벨은 최고점 하나만. 전부 붙이면 읽히지 않는다.
    if (i === maxIdx && v > 0) {
      s.appendChild(el('text', {
        class: 'val-label', x: cx, y: y - 6, 'text-anchor': 'middle',
      }, fmt(v)));
    }
  });

  root.appendChild(s);
}

/* ── ② 가로 막대 (카테고리·저자 순위) ─────────────────────── */

export function barChart(root, opts) {
  const {
    data = [], value = 'value', label = 'name',
    unit = '', rowH = 30, tooltip = null,
  } = opts;

  root.innerHTML = '';
  if (!data.length) {
    emptyNote(root, '아직 기록이 없습니다.');
    return;
  }

  const padL = 100, padR = 46, padT = 4, padB = 4;
  const w = 520;
  const h = padT + padB + rowH * data.length;
  const plotW = w - padL - padR;
  const max = Math.max(1, ...data.map((d) => d[value] || 0));
  const barH = Math.min(20, rowH - 8);

  const s = svgRoot(w, h);

  data.forEach((d, i) => {
    const y = padT + rowH * i + (rowH - barH) / 2;
    const bw = ((d[value] || 0) / max) * plotW;

    // 라벨은 텍스트 토큰으로. 막대 색을 글자에 입히지 않는다.
    const name = String(d[label] ?? '');
    const short = name.length > 9 ? name.slice(0, 8) + '…' : name;
    const t = el('text', {
      class: 'tick', x: padL - 10, y: y + barH / 2 + 4, 'text-anchor': 'end',
    }, short);
    t.appendChild(el('title', {}, name));
    s.appendChild(t);

    s.appendChild(el('path', { class: 'bar', d: barPathRight(padL, y, bw, barH) }));
    s.appendChild(el('text', {
      class: 'val-label', x: padL + bw + 8, y: y + barH / 2 + 4,
    }, fmt(d[value] || 0) + unit));

    const hit = el('rect', {
      class: 'hit', x: 0, y: padT + rowH * i, width: w, height: rowH,
    });
    hit.addEventListener('mousemove', (e) =>
      tip.show(tooltip ? tooltip(d) : `${name}<br><span class="t-val">${fmt(d[value])}${unit}</span>`, e));
    hit.addEventListener('mouseleave', tip.hide);
    s.appendChild(hit);
  });

  s.appendChild(el('line', {
    class: 'axis-line', x1: padL, x2: padL, y1: padT, y2: h - padB,
  }));
  root.appendChild(s);
}

/* ── ③ 선 그래프 (책 누적 진도) ───────────────────────────── */

export function lineChart(root, opts) {
  const {
    points = [], height = 180, unit = 'p', total = null,
    yLabel = '', tooltip = null,
  } = opts;

  root.innerHTML = '';
  if (points.length < 1) {
    emptyNote(root, '진도 기록이 쌓이면 그래프가 나옵니다.');
    return;
  }

  const padL = 46, padR = 44, padT = 14, padB = 26;
  const w = 620, h = height;
  const plotW = w - padL - padR;
  const plotH = h - padT - padB;

  const maxY = Math.max(total || 0, ...points.map((p) => p.y), 1);
  const ticks = niceTicks(maxY, 3);
  const top = ticks[ticks.length - 1];
  const n = Math.max(1, points.length - 1);
  const xOf = (i) => padL + (n === 0 ? plotW / 2 : (i / n) * plotW);
  const yOf = (v) => padT + plotH - (v / top) * plotH;

  const s = svgRoot(w, h);

  for (const t of ticks) {
    const y = yOf(t);
    s.appendChild(el('line', { class: 'grid-line', x1: padL, x2: padL + plotW, y1: y, y2: y }));
    s.appendChild(el('text', { class: 'tick', x: padL - 8, y: y + 4, 'text-anchor': 'end' }, fmt(t)));
  }

  const d = points.map((p, i) => `${i ? 'L' : 'M'}${xOf(i)},${yOf(p.y)}`).join(' ');
  if (points.length > 1) {
    s.appendChild(el('path', {
      class: 'area',
      d: `${d} L${xOf(points.length - 1)},${yOf(0)} L${xOf(0)},${yOf(0)} Z`,
    }));
  }
  s.appendChild(el('path', { class: 'line', d }));

  points.forEach((p, i) => {
    // 점은 지름 8px 이상 + 표면색 2px 링.
    s.appendChild(el('circle', { class: 'dot', cx: xOf(i), cy: yOf(p.y), r: 4 }));
    const hit = el('circle', { class: 'hit', cx: xOf(i), cy: yOf(p.y), r: 14 });
    hit.addEventListener('mousemove', (e) =>
      tip.show(tooltip ? tooltip(p) : `${p.x}<br><span class="t-val">${fmt(p.y)}${unit}</span>`, e));
    hit.addEventListener('mouseleave', tip.hide);
    s.appendChild(hit);
  });

  // 끝점 하나만 직접 라벨링.
  const last = points[points.length - 1];
  s.appendChild(el('text', {
    class: 'val-label', x: xOf(points.length - 1) + 9, y: yOf(last.y) + 4,
  }, fmt(last.y) + unit));

  s.appendChild(el('text', { class: 'tick', x: padL, y: h - 8 }, points[0].x));
  if (points.length > 1) {
    s.appendChild(el('text', {
      class: 'tick', x: padL + plotW, y: h - 8, 'text-anchor': 'end',
    }, last.x));
  }
  if (yLabel) s.appendChild(el('title', {}, yLabel));

  root.appendChild(s);
}

/* ── ④ 잔디 히트맵 ───────────────────────────────────────── */

const HEAT_STEPS = ['--surface-2', '--seq-100', '--seq-250', '--seq-400', '--seq-550', '--seq-700'];

export function heatmap(root, opts) {
  const { year, values = {}, unit = 'p' } = opts;

  root.innerHTML = '';
  const nums = Object.values(values).filter((v) => v > 0);
  const cell = 11, gap = 2, step = cell + gap;

  const start = new Date(year, 0, 1);
  const end = new Date(year, 11, 31);
  // 그 해 첫 일요일 이전까지 앞을 비워 주 단위 열을 맞춘다.
  const offset = start.getDay();
  const totalDays = Math.round((end - start) / 86400000) + 1;
  const weeks = Math.ceil((offset + totalDays) / 7);

  const padL = 26, padT = 16;
  const w = padL + weeks * step;
  const h = padT + 7 * step + 4;
  const s = svgRoot(w, h);

  // 값 → 5단계. 최댓값 기준 사분위로 나눈다.
  const max = nums.length ? Math.max(...nums) : 0;
  const level = (v) => {
    if (!v || v <= 0) return 0;
    if (!max) return 1;
    return Math.min(5, 1 + Math.floor((v / max) * 4.999));
  };

  const dayNames = ['일', '', '화', '', '목', '', '토'];
  dayNames.forEach((name, i) => {
    if (name) {
      s.appendChild(el('text', {
        class: 'tick', x: padL - 6, y: padT + i * step + cell - 1, 'text-anchor': 'end',
      }, name));
    }
  });

  let lastMonth = -1;
  for (let d = 0; d < totalDays; d++) {
    const date = new Date(year, 0, 1 + d);
    const idx = offset + d;
    const col = Math.floor(idx / 7);
    const row = idx % 7;
    const key = `${year}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    const v = values[key] || 0;

    const rect = el('rect', {
      class: 'cell',
      x: padL + col * step,
      y: padT + row * step,
      width: cell,
      height: cell,
      fill: `var(${HEAT_STEPS[level(v)]})`,
    });
    rect.addEventListener('mousemove', (e) =>
      tip.show(`${key}<br><span class="t-val">${v ? fmt(v) + unit : '기록 없음'}</span>`, e));
    rect.addEventListener('mouseleave', tip.hide);
    s.appendChild(rect);

    if (date.getMonth() !== lastMonth && date.getDate() <= 7) {
      lastMonth = date.getMonth();
      s.appendChild(el('text', {
        class: 'tick', x: padL + col * step, y: padT - 5,
      }, `${lastMonth + 1}월`));
    }
  }

  root.appendChild(s);
}

export function heatLegend(root) {
  root.innerHTML =
    '<span>적음</span>' +
    HEAT_STEPS.map((v) => `<span class="sw" style="background:var(${v})"></span>`).join('') +
    '<span>많음</span>';
}

/* ── ⑤ 목표 링 (대시보드 히어로) ──────────────────────────── */

export function progressRing(root, opts) {
  const { pct = 0, size = 132, stroke = 11, late = false } = opts;
  root.innerHTML = '';

  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, pct));

  const s = svgRoot(size, size);
  s.setAttribute('class', 'ring');
  s.appendChild(el('circle', {
    cx: size / 2, cy: size / 2, r,
    fill: 'none', stroke: 'var(--seq-100)', 'stroke-width': stroke,
  }));
  s.appendChild(el('circle', {
    cx: size / 2, cy: size / 2, r,
    fill: 'none',
    stroke: late ? 'var(--critical)' : 'var(--series-1)',
    'stroke-width': stroke,
    'stroke-linecap': 'round',
    'stroke-dasharray': `${(c * clamped) / 100} ${c}`,
    transform: `rotate(-90 ${size / 2} ${size / 2})`,
  }));
  root.appendChild(s);
}

export { tip };
