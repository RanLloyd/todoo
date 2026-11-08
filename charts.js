/* Tiny dependency-free SVG charts (line, bar, donut) used by the dashboards.
   - Animated: bars grow, lines rise and donut arcs sweep from the previous values to the new ones.
   - Responsive: each chart redraws at its container's real width (ResizeObserver) so text stays readable on phones.
   - Calm: a chart whose data and width did not change is left alone, so tooltips do not flicker during live refresh. */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  var C = {crimson: '#8a0f14', gold: '#e9a716', green: '#3f8a2b', blue: '#1f5fa8', orange: '#e8452c', grey: '#cfc6c7'};
  var reduce = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  var states = new WeakMap(), hosts = [], DUR = 650;

  function el(name, attrs, parent) {
    var n = document.createElementNS(NS, name);
    for (var k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function ease(t) { return 1 - Math.pow(1 - t, 3); }
  function width(host) { return Math.max(240, Math.round(host.clientWidth || 0) || 640); }
  function mount(host, w, h) {
    host.innerHTML = '';
    host.classList.add('chart');
    var svg = el('svg', {viewBox: '0 0 ' + w + ' ' + h, role: 'img', preserveAspectRatio: 'xMidYMid meet'});
    host.appendChild(svg);
    var tip = document.createElement('div');
    tip.className = 'chart-tip';
    host.appendChild(tip);
    return {svg: svg, tip: tip};
  }
  function showTip(host, tip, x, y, w, text) {
    tip.textContent = text;
    var r = host.getBoundingClientRect();
    tip.style.left = Math.min(Math.max(x / w * r.width, 40), r.width - 40) + 'px';
    tip.style.top = y + 'px';
    tip.style.opacity = 1;
    clearTimeout(tip._t);
    tip._t = setTimeout(function () { tip.style.opacity = 0; }, 2600); /* touch screens have no mouseleave */
  }
  function wire(shape, host, tip, x, y, h, w, txt) {
    var go = function () { showTip(host, tip, x, y / h * host.getBoundingClientRect().height, w, txt); };
    shape.addEventListener('mouseenter', go);
    shape.addEventListener('click', go);
    shape.addEventListener('mouseleave', function () { tip.style.opacity = 0; });
  }
  function empty(host, msg) {
    states.delete(host);
    host.classList.remove('chart');
    host.innerHTML = '<div class="empty">' + (msg || 'No data yet') + '</div>';
  }
  function label(d) {
    var p = String(d).split('-');
    return p.length === 3 ? ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+p[1] - 1] + ' ' + (+p[2]) : d;
  }
  function fmt(v, target) { return target % 1 === 0 ? String(Math.round(v)) : (Math.round(v * 10) / 10).toFixed(1); }

  /* ---- animation / resize engine shared by all chart kinds ---- */
  function run(host, kind, fn, items, opt, draw, valsOf) {
    opt = opt || {};
    var W = width(host), old = states.get(host);
    var key = JSON.stringify([kind, items, opt, W]);
    if (old && old.key === key) return;
    var to = valsOf(items), from;
    if (old) { clearTimeout(old.rt); cancelAnimationFrame(old.raf); }
    from = to.map(function (v, i) { return old && old.kind === kind && old.vals[i] != null ? old.vals[i] : 0; });
    var st = {kind: kind, fn: fn, items: items, opt: opt, key: key, vals: to, W: W, raf: 0, rt: 0};
    states.set(host, st);
    if (hosts.indexOf(host) < 0) { hosts.push(host); if (ro) ro.observe(host); }
    var same = from.every(function (v, i) { return Math.abs(v - to[i]) < 1e-9; });
    if (reduce || same) { draw(host, items, to, opt, W, false); return; }
    var t0 = null;
    function frame(now) {
      if (t0 === null) t0 = now;
      var p = Math.min(1, (now - t0) / DUR), e = ease(p);
      draw(host, items, to.map(function (v, i) { return from[i] + (v - from[i]) * e; }), opt, W, p < 1);
      st.raf = p < 1 ? requestAnimationFrame(frame) : 0;
    }
    st.raf = requestAnimationFrame(frame);
  }
  var ro = window.ResizeObserver ? new ResizeObserver(function (entries) {
    entries.forEach(function (en) {
      var st = states.get(en.target);
      if (!st || Math.abs(width(en.target) - st.W) < 6) return;
      clearTimeout(st.rt);
      st.rt = setTimeout(function () { if (en.target.isConnected) st.fn(en.target, st.items, st.opt); }, 80);
    });
  }) : null;
  if (!ro) {
    var rz;
    window.addEventListener('resize', function () {
      clearTimeout(rz);
      rz = setTimeout(function () { hosts.forEach(function (h) { var st = states.get(h); if (st && h.isConnected) st.fn(h, st.items, st.opt); }); }, 150);
    });
  }

  /* ---- line / area: points=[{x:'label', y:number}] ---- */
  function lineDraw(host, pts, vals, opt, W, busy) {
    var H = opt.height || 240, L = 36, R = 14, T = 14, B = 30;
    var m = mount(host, W, H), svg = m.svg, max = opt.max || 100, min = opt.min || 0;
    var g = el('g', {class: 'grid'}, svg);
    [0, .25, .5, .75, 1].forEach(function (f) {
      var y = T + (H - T - B) * (1 - f);
      el('line', {x1: L, x2: W - R, y1: y, y2: y}, g);
      el('text', {x: L - 6, y: y + 4, 'text-anchor': 'end'}, svg).textContent = Math.round(min + (max - min) * f);
    });
    var n = pts.length, step = n > 1 ? (W - L - R) / (n - 1) : 0;
    var xy = vals.map(function (v, i) {
      return [n > 1 ? L + step * i : (W + L - R) / 2, T + (H - T - B) * (1 - (Math.min(Math.max(v, min), max) - min) / (max - min))];
    });
    var color = opt.color || C.crimson;
    var d = xy.map(function (p, i) { return (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1); }).join(' ');
    el('path', {d: d + ' L' + xy[n - 1][0].toFixed(1) + ' ' + (H - B) + ' L' + xy[0][0].toFixed(1) + ' ' + (H - B) + ' Z', fill: color, opacity: .1}, svg);
    el('path', {d: d, fill: 'none', stroke: color, 'stroke-width': 2.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round'}, svg);
    var every = Math.ceil(n / Math.max(3, Math.floor((W - L - R) / 70)));
    xy.forEach(function (p, i) {
      if (!busy && i === n - 1) el('circle', {cx: p[0], cy: p[1], r: 5, class: 'ping', fill: color}, svg);
      el('circle', {cx: p[0], cy: p[1], r: n > 20 ? 3 : 4, fill: '#fff', stroke: color, 'stroke-width': 2}, svg);
      var hit = el('circle', {cx: p[0], cy: p[1], r: 14, fill: 'transparent'}, svg);
      wire(hit, host, m.tip, p[0], p[1], H, W, pts[i].x + ': ' + pts[i].y + (opt.unit || ''));
      if (i % every === 0 || i === n - 1) el('text', {x: p[0], y: H - 10, 'text-anchor': 'middle'}, svg).textContent = pts[i].x;
    });
    svg.setAttribute('aria-label', opt.title || 'Line chart');
  }
  function line(host, points, opt) {
    if (!points || !points.length) return empty(host, (opt || {}).empty);
    run(host, 'line', line, points, opt, lineDraw, function (a) { return a.map(function (p) { return +p.y || 0; }); });
  }

  /* ---- bars: items=[{x:'label', y:number, color?}] ---- */
  function barsDraw(host, items, vals, opt, W) {
    var H = opt.height || 240, L = 36, R = 8, T = 16, B = opt.rot ? 70 : 34;
    var m = mount(host, W, H), svg = m.svg;
    var max = opt.max || Math.max.apply(null, items.map(function (i) { return i.y; }).concat([1]));
    var g = el('g', {class: 'grid'}, svg);
    [0, .5, 1].forEach(function (f) {
      var y = T + (H - T - B) * (1 - f);
      el('line', {x1: L, x2: W - R, y1: y, y2: y}, g);
      el('text', {x: L - 6, y: y + 4, 'text-anchor': 'end'}, svg).textContent = Math.round(max * f);
    });
    if (opt.threshold != null) {
      var ty = T + (H - T - B) * (1 - opt.threshold / max);
      el('line', {x1: L, x2: W - R, y1: ty, y2: ty, stroke: C.orange, 'stroke-dasharray': '5 4', 'stroke-width': 1.5}, svg);
    }
    var slot = (W - L - R) / items.length, bw = Math.min(slot * .68, 44);
    items.forEach(function (it, i) {
      var h = Math.max((H - T - B) * (vals[i] / max), 0), x = L + slot * i + (slot - bw) / 2, y = H - B - h;
      var r = el('rect', {x: x, y: y, width: bw, height: h, rx: 4, fill: it.color || opt.color || C.crimson}, svg);
      wire(r, host, m.tip, x + bw / 2, y, H, W, it.x + ': ' + it.y + (opt.unit || ''));
      if (items.length <= 12 && slot >= 26) el('text', {x: x + bw / 2, y: y - 4, 'text-anchor': 'middle', style: 'fill:#4a4244;font-weight:600'}, svg).textContent = fmt(vals[i], it.y);
      var lbl = String(it.x), t;
      if (opt.rot) {
        t = el('text', {x: x + bw / 2, y: H - B + 12, 'text-anchor': 'end', transform: 'rotate(-45 ' + (x + bw / 2) + ' ' + (H - B + 12) + ')'}, svg);
        if (slot < 14 && i % Math.ceil(14 / slot) !== 0) t.setAttribute('visibility', 'hidden');
      } else {
        t = el('text', {x: x + bw / 2, y: H - 12, 'text-anchor': 'middle'}, svg);
        var cap = Math.max(4, Math.floor(slot / 6.2)); if (lbl.length > cap) lbl = lbl.slice(0, cap - 1) + '…';
      }
      t.textContent = lbl;
    });
    svg.setAttribute('aria-label', opt.title || 'Bar chart');
  }
  function bars(host, items, opt) {
    if (!items || !items.length) return empty(host, (opt || {}).empty);
    run(host, 'bars', bars, items, opt, barsDraw, function (a) { return a.map(function (p) { return +p.y || 0; }); });
  }

  /* ---- donut: parts=[{x:'label', y:number, color}] ---- */
  function donutDraw(host, parts, vals, opt) {
    var S = 180, cx = S / 2, cy = S / 2, r = 70, w = 26;
    var m = mount(host, S, S), svg = m.svg, a0 = -Math.PI / 2;
    var total = vals.reduce(function (a, v) { return a + v; }, 0), target = parts.reduce(function (a, p) { return a + p.y; }, 0);
    var live = vals.filter(function (v) { return v > 1e-6; }).length;
    el('circle', {cx: cx, cy: cy, r: r, fill: 'none', stroke: '#f1eaea', 'stroke-width': w}, svg);
    if (total > 1e-6) parts.forEach(function (p, i) {
      if (vals[i] <= 1e-6) return;
      var span = vals[i] / total * Math.PI * 2, a1 = a0 + span - (live > 1 ? .02 : 0);
      if (live === 1) a1 = a0 + Math.PI * 2 - .001;
      var large = a1 - a0 > Math.PI ? 1 : 0;
      var path = el('path', {d: 'M' + (cx + r * Math.cos(a0)) + ' ' + (cy + r * Math.sin(a0)) + ' A' + r + ' ' + r + ' 0 ' + large + ' 1 ' + (cx + r * Math.cos(a1)) + ' ' + (cy + r * Math.sin(a1)), fill: 'none', stroke: p.color, 'stroke-width': w}, svg);
      wire(path, host, m.tip, cx, 20, S, S, p.x + ': ' + p.y + ' (' + Math.round(p.y / target * 100) + '%)');
      a0 += span;
    });
    el('text', {x: cx, y: cy + 4, 'text-anchor': 'middle', style: 'font-size:26px;font-weight:700;fill:#1f1a1b;font-family:Georgia,serif'}, svg).textContent = opt.center != null ? opt.center : Math.round(total);
    if (opt.caption) el('text', {x: cx, y: cy + 22, 'text-anchor': 'middle', style: 'font-size:10px'}, svg).textContent = opt.caption;
    svg.setAttribute('aria-label', opt.title || 'Donut chart');
  }
  function donut(host, parts, opt) {
    if (!parts.reduce(function (a, p) { return a + p.y; }, 0)) return empty(host, (opt || {}).empty);
    run(host, 'donut', donut, parts, opt, donutDraw, function (a) { return a.map(function (p) { return +p.y || 0; }); });
  }

  function legend(host, parts) {
    host.innerHTML = parts.map(function (p) { return '<span><i style="background:' + p.color + '"></i>' + p.x + ' <b>' + p.y + '</b></span>'; }).join('');
  }

  window.Charts = {line: line, bars: bars, donut: donut, legend: legend, colors: C, label: label};
})();
