/* Page behaviour for the Pila SHS attendance system (no inline scripts, so a strict CSP can be used). */
(function () {
  'use strict';
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var csrf = (document.querySelector('meta[name=csrf]') || {}).content || '';
  function json(id) {
    var n = document.getElementById(id);
    try { return n ? JSON.parse(n.textContent) : null; } catch (e) { return null; }
  }
  function esc(s) { var d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }
  function initials(name) { return (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(function (w) { return w[0]; }).join('').toUpperCase(); }
  function t12(t) {
    if (!t) return '—';
    var p = t.split(':'), h = +p[0], ap = h >= 12 ? 'PM' : 'AM';
    return ((h % 12) || 12) + ':' + p[1] + ' ' + ap;
  }

  /* ---------- global: mobile menu, confirm, auto-submit ---------- */
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-nav-toggle]');
    if (t) { document.body.classList.toggle('nav-open'); t.setAttribute('aria-expanded', document.body.classList.contains('nav-open')); }
    if (e.target.closest('.scrim') || (e.target.closest('.sidebar a') && window.innerWidth <= 900)) document.body.classList.remove('nav-open');
  });
  document.addEventListener('submit', function (e) {
    var m = e.target.getAttribute('data-confirm');
    if (m && !window.confirm(m)) e.preventDefault();
  });
  $$('[data-autosubmit]').forEach(function (n) { n.addEventListener('change', function () { n.form.submit(); }); });
  $$('[data-check-all]').forEach(function (box) {
    box.addEventListener('change', function () { $$(box.getAttribute('data-check-all')).forEach(function (c) { c.checked = box.checked; }); });
  });
  $$('[data-print]').forEach(function (b) { b.addEventListener('click', function () { window.print(); }); });

  /* ---------- filters on attendance / reports ---------- */
  var period = $('#period');
  if (period) {
    var sync = function () {
      $$('[data-show]').forEach(function (n) { n.hidden = n.getAttribute('data-show').split(' ').indexOf(period.value) < 0; });
    };
    period.addEventListener('change', sync);
    sync();
  }

  /* ---------- staff dashboard (live) ---------- */
  var reduceMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  var firstPaint = true;
  /* numbers count up/down to their new value and flash briefly when they change */
  function setNum(node, v) {
    var txt = String(v), m = /^(-?\d+(?:\.\d+)?)(.*)$/.exec(txt);
    if (node.textContent === txt && !node._tween) return;
    if (!m || reduceMotion) { node.textContent = txt; return; }
    var to = parseFloat(m[1]), suffix = m[2], dec = (m[1].split('.')[1] || '').length;
    var from = node._val != null ? node._val : (parseFloat(node.textContent) || 0);
    cancelAnimationFrame(node._tween);
    node._val = to;
    var t0 = null;
    (function step(now) {
      if (t0 === null) t0 = now;
      var p = Math.min(1, (now - t0) / 600), e = 1 - Math.pow(1 - p, 3);
      node.textContent = (from + (to - from) * e).toFixed(dec) + suffix;
      node._tween = p < 1 ? requestAnimationFrame(step) : 0;
      if (p >= 1) node.textContent = txt;
    })(performance.now());
    if (!firstPaint) { node.classList.remove('bump'); void node.offsetWidth; node.classList.add('bump'); }
  }
  /* lists: only new rows slide in, existing rows are not redrawn */
  function fillList(ul, rows, html, emptyText, keyOf) {
    if (!ul) return;
    if (!rows.length) { ul.innerHTML = '<li class="empty">' + emptyText + '</li>'; ul._keys = []; return; }
    var seen = ul._keys || [], keys = rows.map(keyOf);
    ul.innerHTML = rows.map(function (r, i) {
      var fresh = !firstPaint && seen.indexOf(keys[i]) < 0;
      return html(r, i).replace('<li>', fresh ? '<li class="fresh">' : '<li>');
    }).join('');
    ul._keys = keys;
  }
  function renderDashboard(d) {
    var C = window.Charts, col = C.colors;
    function bind(k, v) { $$('[data-bind="' + k + '"]').forEach(function (n) { if (k === 'stamp') n.textContent = v; else setNum(n, v); }); }
    bind('present', d.today.present); bind('late', d.today.late); bind('absent', d.today.absent);
    bind('excused', d.today.excused); bind('timed_out', d.today.timed_out); bind('rate', d.today.rate);
    bind('total', d.today.total); bind('avg_att', d.avg_attendance == null ? '—' : d.avg_attendance + '%');
    bind('avg_grade', d.avg_grade == null ? '—' : d.avg_grade); bind('pass_rate', d.passing_rate == null ? '—' : d.passing_rate + '%');
    bind('risk', d.at_risk_count); bind('class_days', d.class_days); bind('stamp', d.generated);
    C.line($('#c-trend'), d.trend.map(function (p) { return {x: C.label(p.day), y: p.rate}; }), {unit: '%', empty: 'No attendance recorded in this term yet. Scan a QR code to begin.'});
    var tt = d.term_totals, parts = [
      {x: 'Present', y: tt.present, color: col.green}, {x: 'Late', y: tt.late, color: col.gold},
      {x: 'Excused', y: tt.excused, color: col.blue}, {x: 'Absent', y: tt.absent, color: col.orange}];
    C.donut($('#c-split'), parts, {caption: 'records', empty: 'No records yet'});
    C.legend($('#c-split-legend'), parts);
    /* the server sends the bins as an object whose keys may arrive sorted alphabetically, so fix the order here */
    var order = ['Below 75', '75–79', '80–84', '85–89', '90–100'];
    var bins = order.filter(function (k) { return k in d.grade_bins; }).map(function (k, i) {
      return {x: k, y: d.grade_bins[k], color: i === 0 ? col.orange : i === 1 ? col.gold : i === 2 ? col.blue : col.green};
    });
    C.bars($('#c-bins'), bins, {height: 250, empty: 'Grades appear once attendance, recitation or scores exist.'});
    C.bars($('#c-perf'), d.performance.map(function (p) { return {x: p.name, y: p.final, color: p.final < d.passing ? col.orange : col.crimson}; }),
      {max: 100, rot: true, height: 280, threshold: d.passing, empty: 'No student grades yet for this term.'});
    C.bars($('#c-assess'), d.assessments.filter(function (a) { return a.avg != null; }).map(function (a) { return {x: a.title, y: a.avg, color: a.kind === 'exam' ? col.crimson : col.blue}; }),
      {max: 100, unit: '%', empty: 'No quiz or exam results yet.'});
    fillList($('#feed'), d.recent, function (r) {
      var out = r.time_out ? ' · out ' + t12(r.time_out) : '';
      return '<li><span class="avatar">' + esc(initials(r.name)) + '</span><span class="who"><b>' + esc(r.name) + '</b><span class="muted small">' +
        esc(r.day) + ' · in ' + t12(r.time_in) + out + '</span></span><span class="badge ' + r.status.toLowerCase() + '">' + r.status + '</span></li>';
    }, 'No scans yet.', function (r) { return [r.day, r.name, r.time_in, r.time_out, r.status].join('|'); });
    fillList($('#risk-list'), d.at_risk, function (r) {
      return '<li><span class="avatar">' + esc(initials(r.name)) + '</span><span class="who"><b>' + esc(r.name) + '</b><span class="muted small">' + esc(r.reason) + '</span></span></li>';
    }, 'No students flagged.', function (r) { return r.name + r.reason; });
    fillList($('#top-list'), d.top, function (r, i) {
      return '<li><span class="avatar">' + (i + 1) + '</span><span class="who"><b>' + esc(r.name) + '</b></span><b>' + r.final + '</b></li>';
    }, 'No grades yet.', function (r) { return r.name + r.final; });
    firstPaint = false;
  }
  var initial = json('payload');
  if ($('#c-trend') && initial) {
    renderDashboard(initial);
    var termId = initial.term.id, live = $('#live'), liveText = $('#live-text'), fails = 0, busy = false, pollTimer = null;
    var refresh = function () {
      if (busy || document.hidden) return;
      busy = true;
      fetch('/api/dashboard?term=' + termId, {credentials: 'same-origin', cache: 'no-store'})
        .then(function (r) {
          if (r.status === 401 || r.status === 403 || r.redirected) { window.location.reload(); return null; }
          return r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status));
        })
        .then(function (d) {
          fails = 0;
          if (live) live.classList.remove('off');
          if (liveText) liveText.textContent = 'Live · updated';
          if (d) renderDashboard(d);
        })
        .catch(function () {
          if (++fails >= 2 && live) { live.classList.add('off'); if (liveText) liveText.textContent = 'Reconnecting… last update'; }
        })
        .then(function () { busy = false; });
    };
    var schedule = function () { clearInterval(pollTimer); pollTimer = setInterval(refresh, 5000); };
    schedule();
    document.addEventListener('visibilitychange', function () { if (!document.hidden) { refresh(); schedule(); } });
    window.addEventListener('online', refresh);
    window.addEventListener('focus', refresh);
    /* a scan made in another tab/window of this browser updates the dashboard immediately */
    window.addEventListener('storage', function (e) { if (e.key === 'att:scan') refresh(); });
    if (window.BroadcastChannel) { try { new BroadcastChannel('att').onmessage = refresh; } catch (e) {} }
  }

  /* ---------- attendance trend on attendance page ---------- */
  var at = $('#c-att-trend'), series = json('series');
  if (at) window.Charts.line(at, (series || []).map(function (p) { return {x: window.Charts.label(p.day), y: p.rate}; }), {unit: '%', height: 200, empty: 'No attendance in this period.'});

  /* ---------- student dashboard ---------- */
  var st = $('#c-student-trend'), strend = json('trend');
  if (st) window.Charts.bars(st, (strend || []).map(function (p) {
    return {x: window.Charts.label(p.day), y: p.v, color: p.v >= 100 ? '#3f8a2b' : p.v >= 75 ? '#e9a716' : '#e8452c'};
  }), {max: 100, height: 190, empty: 'Your attendance will appear here after your first scan.'});

  /* ---------- QR scanner ---------- */
  var reader = $('#reader');
  if (reader) {
    var logEl = $('#scan-log'), resultEl = $('#scan-result'), noticeEl = $('#cam-notice'), last = {code: '', at: 0}, scanner = null, count = 0, running = false;
    var startBtn = $('#scan-start'), stopBtn = $('#scan-stop'), torchBtn = $('#torch-btn'), camBar = $('#cam-bar'), camSel = $('#cam-select');
    var photoBtn = $('#photo-btn'), photoInput = $('#photo-input'), secureUrl = ($('#scanner') || {}).getAttribute ? $('#scanner').getAttribute('data-secure-url') : '';
    var store = {get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) {} }};
    var channel = null; try { channel = window.BroadcastChannel ? new BroadcastChannel('att') : null; } catch (e) {}

    var beep = function (ok) {
      try {
        var a = new (window.AudioContext || window.webkitAudioContext)(), o = a.createOscillator(), g = a.createGain();
        o.frequency.value = ok ? 880 : 220; g.gain.value = .08; o.connect(g); g.connect(a.destination); o.start(); o.stop(a.currentTime + (ok ? .12 : .35));
      } catch (e) {}
    };
    /* spoken announcements: "Welcome, <name>" on Time In, "Thank you, <name>" on Time Out */
    var voiceBox = $('#voice-on'), synth = window.speechSynthesis;
    if (voiceBox) { voiceBox.checked = store.get('att:voice') !== '0'; voiceBox.addEventListener('change', function () { store.set('att:voice', voiceBox.checked ? '1' : '0'); if (synth && !voiceBox.checked) synth.cancel(); }); }
    var speak = function (text) {
      if (!synth || !window.SpeechSynthesisUtterance || (voiceBox && !voiceBox.checked)) return false;
      try {
        synth.cancel();
        var u = new window.SpeechSynthesisUtterance(text); u.rate = .95; u.volume = 1; u.lang = 'en-PH';
        var vs = synth.getVoices(), v = vs.filter(function (x) { return /^en[-_](PH|US|GB|AU)/i.test(x.lang); })[0] || vs.filter(function (x) { return /^en/i.test(x.lang); })[0];
        if (v) u.voice = v;
        synth.speak(u); return true;
      } catch (e) { return false; }
    };
    var unlockVoice = function () { try { if (synth) { synth.getVoices(); var u = new window.SpeechSynthesisUtterance(' '); u.volume = 0; synth.speak(u); } } catch (e) {} };
    var notice = function (html, kind) {
      if (!html) { noticeEl.hidden = true; noticeEl.innerHTML = ''; return; }
      noticeEl.className = 'notice ' + (kind || 'warn'); noticeEl.innerHTML = html; noticeEl.hidden = false;
    };
    var send = function (code) {
      var now = Date.now();
      if (code === last.code && now - last.at < 5000) return;
      last = {code: code, at: now};
      fetch('/api/scan', {method: 'POST', credentials: 'same-origin', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: JSON.stringify({token: code})})
        .then(function (r) { return r.json().then(function (j) { return {ok: r.ok, j: j}; }); })
        .then(function (res) {
          var j = res.j, cls = !res.ok ? 'err' : j.status === 'Late' ? 'late' : 'ok';
          resultEl.className = 'scan-result ' + cls;
          resultEl.innerHTML = res.ok ? '<b>' + esc(j.student) + '</b>' + j.event + ' recorded at ' + j.time + ' · <span class="badge ' + j.status.toLowerCase() + '">' + j.status + '</span>'
            : '<b>' + esc(j.student || 'Not recorded') + '</b>' + esc(j.message);
          if (!res.ok) beep(false);
          else if (!speak((j.event === 'Time Out' ? 'Thank you, ' : 'Welcome, ') + j.student)) beep(true);
          try { if (navigator.vibrate) navigator.vibrate(res.ok ? 60 : [80, 60, 80]); } catch (e) {}
          reader.classList.remove('flash-ok', 'flash-err'); void reader.offsetWidth; reader.classList.add(res.ok ? 'flash-ok' : 'flash-err');
          if (res.ok) {
            count++; $('#scan-count').textContent = count;
            var empty = logEl.querySelector('.empty'); if (empty) empty.remove();
            var li = document.createElement('li'); li.className = 'fresh';
            li.innerHTML = '<span class="avatar">' + esc(initials(j.student)) + '</span><span class="who"><b>' + esc(j.student) + '</b><span class="muted small">' + j.event + ' · ' + j.time + '</span></span><span class="badge ' + j.status.toLowerCase() + '">' + j.status + '</span>';
            logEl.insertBefore(li, logEl.firstChild);
            store.set('att:scan', String(Date.now())); if (channel) channel.postMessage('scan'); /* tell open dashboards */
          }
        }).catch(function () { resultEl.className = 'scan-result err'; resultEl.innerHTML = '<b>Network problem</b>The scan was not saved. Check the connection and scan again.'; });
    };

    /* ----- why the camera might not work, in plain words ----- */
    var hasMedia = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    var secureOk = window.isSecureContext !== false && hasMedia;
    var insecureHelp = function () {
      var here = location.protocol === 'https:' ? '' : (secureUrl ? '<p><a class="btn primary" href="' + esc(secureUrl) + '">Open the secure (https) version</a></p>' : '');
      var how = location.protocol === 'https:'
        ? '<p>This browser does not offer camera access on this page. Update the browser, or use Chrome / Safari / Edge.</p>'
        : '<p>Browsers only turn the camera on for <b>https://</b> pages (or <b>http://localhost</b> on the same computer). You opened this page over plain <b>http://</b>' + (location.hostname && location.hostname !== 'localhost' ? ' at <b>' + esc(location.host) + '</b>' : '') + '.</p>' +
          (secureUrl ? '' : '<p>Start the app with <code>python app.py</code> and open the <b>https://</b> address it prints, or host the site on HTTPS.</p>');
      return '<b>Camera needs a secure connection</b>' + how + here + '<p class="small">Meanwhile you can use <b>Scan from photo</b>, a USB/Bluetooth scanner, or type the LRN below.</p>';
    };
    var explain = function (err) {
      var s = ((err && err.name) || '') + ' ' + String(err && err.message || err);
      if (/NotAllowed|Permission|denied|dismissed/i.test(s)) return '<b>Camera permission is blocked</b><p>Tap the lock / camera icon next to the address, set <b>Camera → Allow</b>, then press <b>Start camera</b> again. On iPhone: Settings → Safari → Camera → Allow.</p>';
      if (/NotFound|DevicesNotFound|no camera|Requested device not found/i.test(s)) return '<b>No camera found</b><p>This device has no camera, or it is turned off. Use <b>Scan from photo</b> or type the LRN below.</p>';
      if (/NotReadable|TrackStart|Could not start video|in use|Starting videoinput/i.test(s)) return '<b>The camera is busy</b><p>Another app or browser tab is using it. Close it, then press <b>Start camera</b> again.</p>';
      if (/Security|secure|streaming not supported/i.test(s)) return insecureHelp();
      return '<b>Camera unavailable</b><p>' + esc(String(err && err.message || err)) + '</p><p class="small">You can still use <b>Scan from photo</b> or type the LRN below.</p>';
    };

    /* ----- load the QR library (cdnjs first, then jsDelivr) ----- */
    var libPromise = null;
    var loadLib = function () {
      if (window.Html5Qrcode) return Promise.resolve();
      if (libPromise) return libPromise;
      var urls = ['https://cdnjs.cloudflare.com/ajax/libs/html5-qrcode/2.3.8/html5-qrcode.min.js', 'https://cdn.jsdelivr.net/npm/html5-qrcode@2.3.8/html5-qrcode.min.js'];
      var tryNext = function (i) {
        if (window.Html5Qrcode) return Promise.resolve();
        if (i >= urls.length) return Promise.reject(new Error('The QR scanner library could not be loaded. Check the internet connection.'));
        return new Promise(function (ok, no) { var sc = document.createElement('script'); sc.src = urls[i]; sc.onload = ok; sc.onerror = no; document.head.appendChild(sc); })
          .then(function () { return window.Html5Qrcode ? null : tryNext(i + 1); }, function () { return tryNext(i + 1); });
      };
      libPromise = tryNext(0).catch(function (e) { libPromise = null; throw e; });
      return libPromise;
    };

    /* ----- camera control ----- */
    var cams = [];
    var cfg = function () {
      var c = {fps: 12, disableFlip: false, qrbox: function (w, h) { var s = Math.max(120, Math.floor(Math.min(w, h) * .72)); return {width: s, height: s}; }};
      try { c.formatsToSupport = [window.Html5QrcodeSupportedFormats.QR_CODE]; c.experimentalFeatures = {useBarCodeDetectorIfSupported: true}; } catch (e) {}
      return c;
    };
    var pickDefault = function () {
      var saved = store.get('att:cam');
      if (saved && cams.some(function (c) { return c.id === saved; })) return saved;
      var back = cams.filter(function (c) { return /back|rear|environment|world/i.test(c.label); })[0];
      if (back) return back.id;
      return (cams.length > 1 && /Android|iPhone|iPad|Mobile/i.test(navigator.userAgent) ? cams[cams.length - 1] : cams[0]).id;
    };
    var setRunning = function (on) {
      running = on; startBtn.hidden = on; stopBtn.hidden = !on; reader.classList.toggle('live', on);
      camBar.hidden = !(on && cams.length > 1 || on && torchBtn && !torchBtn.hidden);
      if (!on) { torchBtn.hidden = true; camBar.hidden = true; }
    };
    var setupTorch = function () {
      torchBtn.hidden = true;
      try {
        var cap = scanner.getRunningTrackCameraCapabilities().torchFeature();
        if (cap && cap.isSupported()) {
          torchBtn.hidden = false; var on = false;
          torchBtn.onclick = function () { on = !on; cap.apply(on).then(function () { torchBtn.classList.toggle('on', on); }).catch(function () {}); };
          camBar.hidden = false;
        }
      } catch (e) {}
    };
    var begin = function (idOrFacing) {
      scanner = new window.Html5Qrcode('reader', {verbose: false});
      return scanner.start(idOrFacing, cfg(), function (text) { send(text); }, function () {});
    };
    var halt = function () {
      var sc = scanner; scanner = null;
      if (!sc) return Promise.resolve();
      return Promise.resolve().then(function () { return sc.stop(); }).catch(function () {}).then(function () { try { sc.clear(); } catch (e) {} });
    };
    var startCamera = function (wantedId) {
      notice('');
      if (!secureOk) { notice(insecureHelp(), 'warn'); reader.innerHTML = '<span class="reader-idle">Camera blocked<small>See the message above</small></span>'; return; }
      startBtn.disabled = true; startBtn.textContent = 'Starting…';
      var done = function () { startBtn.disabled = false; startBtn.textContent = 'Start camera'; };
      loadLib().then(function () {
        reader.innerHTML = ''; reader.classList.add('live');
        /* getUserMedia first: it shows the permission prompt and gives clear error names; labels are only available after it */
        return navigator.mediaDevices.getUserMedia({video: true, audio: false}).then(function (stream) { stream.getTracks().forEach(function (t) { t.stop(); }); });
      }).then(function () { return window.Html5Qrcode.getCameras().catch(function () { return []; }); })
        .then(function (list) {
          cams = list || [];
          camSel.innerHTML = cams.map(function (c, i) { return '<option value="' + esc(c.id) + '">' + esc(c.label || ('Camera ' + (i + 1))) + '</option>'; }).join('');
          var attempts = [];
          if (cams.length) attempts.push(wantedId && cams.some(function (c) { return c.id === wantedId; }) ? wantedId : pickDefault());
          attempts.push({facingMode: 'environment'}, {facingMode: 'user'});
          var go = function (i) {
            return begin(attempts[i]).catch(function (err) {
              if (i + 1 < attempts.length && !/NotAllowed|Permission|denied/i.test(String(err && err.name) + String(err))) return halt().then(function () { return go(i + 1); });
              throw err;
            });
          };
          return go(0);
        })
        .then(function () {
          try { var tr = scanner.getRunningTrackSettings(); if (tr && tr.deviceId) { camSel.value = tr.deviceId; store.set('att:cam', tr.deviceId); } } catch (e) {}
          setRunning(true); camBar.hidden = cams.length < 2; setupTorch(); done();
        })
        .catch(function (err) {
          done(); setRunning(false);
          reader.innerHTML = '<span class="reader-idle">Camera is off<small>Use the buttons below</small></span>';
          notice(explain(err), 'warn');
        });
    };
    startBtn.addEventListener('click', function () { unlockVoice(); startCamera(); });
    stopBtn.addEventListener('click', function () { halt().then(function () { reader.innerHTML = '<span class="reader-idle">Camera stopped<small>Press “Start camera”</small></span>'; setRunning(false); }); });
    camSel.addEventListener('change', function () { store.set('att:cam', camSel.value); halt().then(function () { startCamera(camSel.value); }); });
    document.addEventListener('visibilitychange', function () { if (document.hidden && running) { halt().then(function () { reader.innerHTML = '<span class="reader-idle">Camera paused<small>Press “Start camera”</small></span>'; setRunning(false); }); } });
    window.addEventListener('pagehide', function () { halt(); });

    /* ----- photo fallback: works on plain http too, because it needs no live camera stream ----- */
    var decodeNative = function (file) {
      if (!('BarcodeDetector' in window) || !window.createImageBitmap) return Promise.reject(new Error('native unsupported'));
      return window.createImageBitmap(file).then(function (bmp) { return new window.BarcodeDetector({formats: ['qr_code']}).detect(bmp); })
        .then(function (r) { if (r && r.length) return r[0].rawValue; throw new Error('none'); });
    };
    var decodeLib = function (file) {
      return loadLib().then(function () { var h = new window.Html5Qrcode('file-reader', {verbose: false}); return h.scanFile(file, false).then(function (t) { try { h.clear(); } catch (e) {} return t; }); });
    };
    photoBtn.addEventListener('click', function () { unlockVoice(); photoInput.value = ''; photoInput.click(); });
    photoInput.addEventListener('change', function () {
      var f = photoInput.files && photoInput.files[0];
      if (!f) return;
      notice(''); resultEl.className = 'scan-result'; resultEl.innerHTML = '<b>Reading photo…</b>Looking for a QR code.';
      decodeNative(f).catch(function () { return decodeLib(f); })
        .then(function (text) { last = {code: '', at: 0}; send(text); })
        .catch(function () { resultEl.className = 'scan-result err'; resultEl.innerHTML = '<b>No QR code found</b>Hold the phone steady, fill the frame with the code, and try again.'; });
    });

    /* ----- first look: tell people up front when the camera cannot work on this address ----- */
    if (!secureOk) { notice(insecureHelp(), 'warn'); startBtn.textContent = 'Start camera'; }
    var manual = $('#manual-form');
    manual.addEventListener('submit', function (e) {
      e.preventDefault();
      var inp = $('#manual-code'), v = inp.value.trim();
      unlockVoice();
      if (v) { last = {code: '', at: 0}; send(v); }
      inp.value = ''; inp.focus();
    });
    if (window.matchMedia && !window.matchMedia('(pointer: coarse)').matches) $('#manual-code').focus();
  }

  /* ---------- quiz / exam builder ---------- */
  var builder = $('#builder');
  if (builder) {
    var qs = json('questions-data') || [], list = $('#q-list'), hidden = $('#questions-input'), locked = builder.hasAttribute('data-locked');
    var blank = function (t) { return {qtype: t, prompt: '', choices: t === 'mcq' ? ['', '', '', ''] : [], answer: t === 'tf' ? 'True' : '', points: 1}; };
    var render = function () {
      list.innerHTML = '';
      qs.forEach(function (q, i) {
        var c = document.createElement('div'); c.className = 'q-card';
        var typeName = {mcq: 'Multiple choice', tf: 'True / False', text: 'Identification'}[q.qtype];
        var h = '<div class="q-head"><b>Question ' + (i + 1) + ' <span class="badge info">' + typeName + '</span></b>' +
          (locked ? '' : '<span class="actions"><button type="button" class="btn sm" data-act="up">↑</button><button type="button" class="btn sm" data-act="down">↓</button><button type="button" class="btn sm danger" data-act="del">Remove</button></span>') + '</div>' +
          '<label>Question<textarea data-f="prompt" rows="2" ' + (locked ? 'disabled' : '') + '>' + esc(q.prompt) + '</textarea></label>';
        if (q.qtype === 'mcq') {
          h += '<div style="margin-top:.6rem"><b class="small">Choices — select the correct one</b>';
          q.choices.forEach(function (ch, j) {
            h += '<div class="q-choice"><input type="radio" name="ans' + i + '" data-correct="' + j + '" ' + (ch && ch === q.answer ? 'checked' : '') + ' ' + (locked ? 'disabled' : '') + ' aria-label="Correct choice ' + (j + 1) + '">' +
              '<input type="text" data-choice="' + j + '" value="' + esc(ch) + '" placeholder="Choice ' + String.fromCharCode(65 + j) + '" ' + (locked ? 'disabled' : '') + '></div>';
          });
          h += '</div>';
        } else if (q.qtype === 'tf') {
          h += '<label style="margin-top:.6rem">Correct answer<select data-f="answer" ' + (locked ? 'disabled' : '') + '><option ' + (q.answer === 'True' ? 'selected' : '') + '>True</option><option ' + (q.answer === 'False' ? 'selected' : '') + '>False</option></select></label>';
        } else {
          h += '<label style="margin-top:.6rem">Accepted answer(s) — separate alternatives with |<input data-f="answer" value="' + esc(q.answer) + '" ' + (locked ? 'disabled' : '') + ' placeholder="e.g. photosynthesis|Photosynthesis"></label>';
        }
        h += '<label style="margin-top:.6rem;max-width:140px">Points<input type="number" min="0.5" step="0.5" data-f="points" value="' + q.points + '" ' + (locked ? 'disabled' : '') + '></label>';
        c.innerHTML = h;
        c.addEventListener('input', function (e) {
          var f = e.target.getAttribute('data-f'), ch = e.target.getAttribute('data-choice');
          if (f) q[f] = e.target.value;
          if (ch != null) { var old = q.choices[ch]; q.choices[ch] = e.target.value; if (q.answer === old) q.answer = e.target.value; }
          sync();
        });
        c.addEventListener('change', function (e) {
          var k = e.target.getAttribute('data-correct');
          if (k != null) { q.answer = q.choices[k]; sync(); }
          if (e.target.getAttribute('data-f') === 'answer') { q.answer = e.target.value; sync(); }
        });
        c.addEventListener('click', function (e) {
          var a = e.target.getAttribute('data-act');
          if (!a) return;
          if (a === 'del') qs.splice(i, 1);
          if (a === 'up' && i > 0) qs.splice(i - 1, 0, qs.splice(i, 1)[0]);
          if (a === 'down' && i < qs.length - 1) qs.splice(i + 1, 0, qs.splice(i, 1)[0]);
          render(); sync();
        });
        list.appendChild(c);
      });
      sync();
    };
    var sync = function () {
      hidden.value = JSON.stringify(qs);
      var pts = qs.reduce(function (a, q) { return a + (parseFloat(q.points) || 0); }, 0);
      $('#q-summary').textContent = qs.length + ' question' + (qs.length === 1 ? '' : 's') + ' · ' + pts + ' point' + (pts === 1 ? '' : 's');
    };
    $$('[data-add]').forEach(function (b) { b.addEventListener('click', function () { qs.push(blank(b.getAttribute('data-add'))); render(); }); });
    if (!qs.length && !locked) qs.push(blank('mcq'));
    render();
  }

  /* ---------- taking a quiz ---------- */
  var timer = $('#timer');
  if (timer) {
    var left = parseInt(timer.getAttribute('data-seconds'), 10), form = $('#take-form'), disp = $('#timer-value');
    var tick = function () {
      var m = Math.floor(left / 60), s = left % 60;
      disp.textContent = m + ':' + (s < 10 ? '0' : '') + s;
      if (left <= 0) { form.submit(); return; }
      left--; setTimeout(tick, 1000);
    };
    tick();
  }
  var takeForm = $('#take-form');
  if (takeForm) {
    takeForm.addEventListener('submit', function () { $$('button[type=submit]', takeForm).forEach(function (b) { b.disabled = true; }); });
    window.addEventListener('beforeunload', function (e) { if (!takeForm.dataset.done) { /* warn only while answering */ } });
  }

  /* ---------- password show/hide ---------- */
  $$('[data-toggle-pw]').forEach(function (b) {
    b.addEventListener('click', function () {
      var i = $(b.getAttribute('data-toggle-pw')); i.type = i.type === 'password' ? 'text' : 'password'; b.textContent = i.type === 'password' ? 'Show' : 'Hide';
    });
  });
})();
