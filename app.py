"""Pila Senior High School – Attendance Monitoring System with real-time analytics.

Run:  python app.py      (this computer: http://localhost:5000 · phones on the same Wi-Fi: the https:// address it prints)
"""
import csv
import io
import json
import os
import secrets
import ssl
import threading
from datetime import date, datetime, timedelta
from functools import wraps
from io import BytesIO, StringIO

from flask import (Flask, Response, abort, flash, g, jsonify, redirect, render_template, request,
                   send_file, session, url_for)
from urllib.parse import urlsplit

from werkzeug.security import check_password_hash, generate_password_hash

import core
import grading
from core import INSTANCE_DIR, ROOT, connect, current_term, get_settings, init_db, now, resolve_period, today

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('HTTPS_ONLY', '0') == '1',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=10), MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    TEMPLATES_AUTO_RELOAD=False)


def _secret_key():
    if os.environ.get('SECRET_KEY'):
        return os.environ['SECRET_KEY']
    key_file = INSTANCE_DIR / 'secret.key'  # persisted so sessions survive restarts
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
    return key_file.read_text().strip()


app.secret_key = _secret_key()
if os.environ.get('TRUST_PROXY') == '1':  # behind nginx / a hosting panel that terminates HTTPS
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
STAFF = ('admin', 'teacher')
STATUSES = ('Present', 'Late', 'Excused', 'Absent')


# ------------------------------------------------------------------ plumbing
def db():
    if 'db' not in g:
        g.db = connect()
    return g.db


@app.teardown_appcontext
def close_db(_e=None):
    con = g.pop('db', None)
    if con is not None:
        con.close()


with app.app_context():
    try:
        core.ensure_database()
        init_db(connect()).close()
    except core.DatabaseUnavailable as exc:
        raise SystemExit(f'\n!! {exc}\n')


LOCAL_HOSTS = ('localhost', '127.0.0.1', '::1')


def https_url(path=''):
    """Secure address of this same page for phones/tablets, or None when HTTPS is not being served."""
    port = app.config.get('HTTPS_PORT')
    if not port:
        return None
    host = urlsplit('//' + request.host).hostname or 'localhost'
    host = f'[{host}]' if ':' in host else host
    return f'https://{host}:{port}{path}'


@app.before_request
def load_user():
    # Cameras only work on https:// (or localhost): send other http:// visitors to the secure port.
    if not request.is_secure and app.config.get('HTTPS_PORT') and (urlsplit('//' + request.host).hostname or '') not in LOCAL_HOSTS:
        return redirect(https_url(request.full_path.rstrip('?')), 307)
    g.user = None
    if session.get('uid'):
        g.user = db().execute('SELECT * FROM users WHERE id=? AND active=1', (session['uid'],)).fetchone()
        if not g.user:
            session.clear()
    if request.method == 'POST':
        token = request.form.get('csrf') or request.headers.get('X-CSRF-Token')
        if not token or not secrets.compare_digest(token, session.get('csrf', '')):
            abort(400, 'Your session expired. Please reload the page and try again.')
    if (g.user and g.user['must_change'] and request.endpoint not in ('change_password', 'logout', 'static')):
        return redirect(url_for('change_password'))


@app.after_request
def secure_headers(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Referrer-Policy'] = 'same-origin'
    resp.headers['Permissions-Policy'] = 'camera=(self), fullscreen=(self)'
    resp.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
    if request.endpoint not in ('static',):
        resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.context_processor
def inject():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(24)
    return {'csrf': session['csrf'], 'user': g.get('user'), 'is_staff': bool(g.get('user') and g.user['role'] in STAFF),
            'school': get_settings(db()) if g.get('db') or True else {}, 'today': today(), 'nav_endpoint': request.endpoint}


def log(action, details=''):
    db().execute('INSERT INTO activity(user_id,action,details,created_at) VALUES(?,?,?,?)',
                 (g.user['id'] if g.get('user') else None, action, details, now().isoformat(timespec='seconds')))
    db().commit()


def staff_required(fn):
    @wraps(fn)
    def w(*a, **k):
        if not g.user:
            return redirect(url_for('portal'))
        if g.user['role'] not in STAFF:
            abort(403)
        return fn(*a, **k)
    return w


def admin_required(fn):
    @wraps(fn)
    def w(*a, **k):
        if not g.user:
            return redirect(url_for('portal'))
        if g.user['role'] != 'admin':
            abort(403)
        return fn(*a, **k)
    return w


def student_required(fn):
    @wraps(fn)
    def w(*a, **k):
        if not g.user:
            return redirect(url_for('student_login'))
        if g.user['role'] != 'student':
            abort(403)
        g.student = db().execute('SELECT * FROM students WHERE user_id=?', (g.user['id'],)).fetchone()
        if not g.student:
            abort(404)
        return fn(*a, **k)
    return w


def csv_response(filename, header, rows):
    buf = StringIO()
    w = csv.writer(buf)

    def safe(v):  # neutralise spreadsheet formulas
        return "'" + v if isinstance(v, str) and v[:1] in ('=', '+', '-', '@') else v
    w.writerow(header)
    for r in rows:
        w.writerow([safe(c) for c in r])
    return Response('﻿' + buf.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


def fullname(st):
    mid = f" {st['middle_name'][:1]}." if st['middle_name'] else ''
    return f"{st['last_name']}, {st['first_name']}{mid}"


@app.template_filter('t12')
def t12(v):
    try:
        return datetime.strptime(v, '%H:%M:%S').strftime('%I:%M %p').lstrip('0') if v else '—'
    except ValueError:
        return v or '—'


@app.template_filter('dlong')
def dlong(v):
    try:
        return date.fromisoformat(v[:10]).strftime('%b %d, %Y')
    except (ValueError, TypeError):
        return v or ''


@app.template_filter('dt')
def dtfmt(v):
    try:
        return datetime.fromisoformat(v).strftime('%b %d, %Y %I:%M %p')
    except (ValueError, TypeError):
        return v or '—'


@app.template_filter('num')
def numfmt(v, digits=1):
    return '—' if v is None else (f'{v:.{digits}f}'.rstrip('0').rstrip('.') if digits else f'{v:.0f}')


# ------------------------------------------------------------------ auth
def throttled(ident):
    since = (now() - timedelta(minutes=10)).isoformat(timespec='seconds')
    n = db().execute('SELECT COUNT(*) c FROM login_attempts WHERE ident=? AND attempted_at>?', (ident, since)).fetchone()['c']
    return n >= 6


def do_login(roles, template, home_endpoint):
    if g.user:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        ident = f"{username}|{request.remote_addr}"
        if throttled(ident):
            flash('Too many failed attempts. Please wait 10 minutes and try again.', 'error')
        else:
            u = db().execute('SELECT * FROM users WHERE lower(username)=? AND active=1', (username,)).fetchone()
            if u and u['role'] in roles and check_password_hash(u['password'], request.form.get('password', '')):
                session.clear()
                session['uid'] = u['id']
                session['csrf'] = secrets.token_urlsafe(24)
                session.permanent = True
                g.user = u
                log('login', u['role'])
                nxt = request.args.get('next', '')
                return redirect(nxt if nxt.startswith('/') and not nxt.startswith('//') else url_for('dashboard'))
            db().execute('INSERT INTO login_attempts(ident,attempted_at) VALUES(?,?)', (ident, now().isoformat(timespec='seconds')))
            db().commit()
            flash('Incorrect username or password.', 'error')
    return render_template(template)


@app.route('/')
def portal():
    if g.user:
        return redirect(url_for('dashboard'))
    return render_template('portal.html')


@app.route('/teacher/login', methods=['GET', 'POST'])
def teacher_login():
    return do_login(('teacher', 'admin'), 'login_teacher.html', 'teacher_login')


@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    return do_login(('student',), 'login_student.html', 'student_login')


@app.route('/admin')
def admin_entry():  # admins use the teacher sign-in; they are not listed on the portal
    return redirect(url_for('teacher_login'))


@app.post('/logout')
def logout():
    role = g.user['role'] if g.user else 'teacher'
    session.clear()
    return redirect(url_for('student_login' if role == 'student' else 'teacher_login'))


@app.route('/account/password', methods=['GET', 'POST'])
def change_password():
    if not g.user:
        return redirect(url_for('portal'))
    if request.method == 'POST':
        cur, new, conf = (request.form.get(k, '') for k in ('current', 'new', 'confirm'))
        if not check_password_hash(g.user['password'], cur):
            flash('Your current password is incorrect.', 'error')
        elif len(new) < 8 or new.isdigit() or new.lower() == g.user['username']:
            flash('Use at least 8 characters, not only digits, and not your username.', 'error')
        elif new != conf:
            flash('The new passwords do not match.', 'error')
        else:
            db().execute('UPDATE users SET password=?,must_change=0 WHERE id=?', (generate_password_hash(new), g.user['id']))
            db().commit()
            log('password_changed')
            flash('Password updated.', 'success')
            return redirect(url_for('dashboard'))
    return render_template('change_password.html')


# ------------------------------------------------------------------ analytics
def dashboard_payload(term):
    con = db()
    s = get_settings(con)
    t0 = today().isoformat()
    total = con.execute('SELECT COUNT(*) c FROM students s JOIN users u ON u.id=s.user_id WHERE u.active=1').fetchone()['c']
    row = con.execute('''SELECT SUM(a.status='Present') p, SUM(a.status='Late') l, SUM(a.status='Excused') e, SUM(a.status='Absent') ab,
                         SUM(a.time_out IS NOT NULL) o FROM attendance a JOIN students s ON s.id=a.student_id
                         JOIN users u ON u.id=s.user_id WHERE u.active=1 AND a.day=?''', (t0,)).fetchone()
    p, l, e, ab, o = (row[k] or 0 for k in ('p', 'l', 'e', 'ab', 'o'))
    tstart, tend = date.fromisoformat(term['start_date']), date.fromisoformat(term['end_date'])
    summ = grading.attendance_summary(con, tstart, tend)
    series = grading.daily_series(con, tstart, tend)
    grades, weights, passing = grading.term_grades(con, term)
    tot = {k: sum(v[k] for v in summ.values()) for k in ('present', 'late', 'excused', 'absent')}
    risk_thr = grading.fnum(s, 'at_risk_attendance', 80)
    at_risk = []
    for g_ in grades:
        a = g_['attendance']
        reasons = []
        if a.get('rate') is not None and a['rate'] < risk_thr:
            reasons.append(f"Attendance {a['rate']:.0f}%")
        if g_['final'] is not None and g_['final'] < passing:
            reasons.append(f"Grade {g_['final']:.0f}")
        if reasons:
            at_risk.append({'name': g_['name'], 'reason': ' · '.join(reasons)})
    ranked = sorted([x for x in grades if x['final'] is not None], key=lambda x: -x['final'])
    bins = {'Below 75': 0, '75–79': 0, '80–84': 0, '85–89': 0, '90–100': 0}
    for x in ranked:
        f = x['final']
        bins['Below 75' if f < 75 else '75–79' if f < 80 else '80–84' if f < 85 else '85–89' if f < 90 else '90–100'] += 1
    assess = []
    for a in con.execute('''SELECT a.id,a.title,a.kind, COUNT(t.id) n, AVG(t.score*100.0/t.total) avg
                            FROM assessments a LEFT JOIN attempts t ON t.assessment_id=a.id AND t.submitted_at IS NOT NULL AND t.total>0
                            WHERE a.term_id=? AND a.published=1 GROUP BY a.id ORDER BY a.id''', (term['id'],)):
        assess.append({'title': a['title'], 'kind': a['kind'], 'n': a['n'], 'avg': round(a['avg'], 1) if a['avg'] is not None else None})
    recent = [dict(day=r['day'], name=r['full_name'], status=r['status'], time_in=r['time_in'], time_out=r['time_out'])
              for r in con.execute('''SELECT a.*,u.full_name FROM attendance a JOIN students s ON s.id=a.student_id JOIN users u ON u.id=s.user_id
                                      ORDER BY a.day DESC, COALESCE(a.time_out,a.time_in) DESC LIMIT 8''')]
    avg_att = [v['rate'] for v in summ.values() if v['rate'] is not None]
    finals = [x['final'] for x in ranked]
    return {
        'generated': now().strftime('%I:%M:%S %p').lstrip('0'),
        'term': {'id': term['id'], 'name': term['name']},
        'today': {'total': total, 'present': p, 'late': l, 'excused': e, 'marked_absent': ab,
                  'absent': max(total - p - l - e, 0), 'timed_out': o,
                  'rate': round((p + l + e) / total * 100, 1) if total else 0},
        'term_totals': tot, 'class_days': len(series),
        'avg_attendance': round(sum(avg_att) / len(avg_att), 1) if avg_att else None,
        'avg_grade': round(sum(finals) / len(finals), 1) if finals else None,
        'passing_rate': round(sum(1 for f in finals if f >= passing) / len(finals) * 100) if finals else None,
        'trend': series[-31:], 'grade_bins': bins, 'assessments': assess, 'at_risk': at_risk[:8], 'at_risk_count': len(at_risk),
        'top': [{'name': x['name'], 'final': x['final']} for x in ranked[:5]],
        'performance': [{'name': x['student']['last_name'], 'final': x['final']} for x in ranked][:30],
        'recent': recent, 'passing': passing,
    }


@app.route('/api/dashboard')
@staff_required
def api_dashboard():
    term = db().execute('SELECT * FROM terms WHERE id=?', (request.args.get('term', type=int),)).fetchone() or current_term(db())
    return jsonify(dashboard_payload(term))


@app.route('/dashboard')
def dashboard():
    if not g.user:
        return redirect(url_for('portal'))
    con = db()
    if g.user['role'] in STAFF:
        terms = con.execute('SELECT * FROM terms ORDER BY start_date').fetchall()
        term = con.execute('SELECT * FROM terms WHERE id=?', (request.args.get('term', type=int),)).fetchone() or current_term(con)
        return render_template('dashboard_staff.html', terms=terms, term=term, payload=dashboard_payload(term))
    return student_dashboard()


@student_required
def student_dashboard():
    con, st = db(), g.student
    terms = con.execute('SELECT * FROM terms ORDER BY start_date').fetchall()
    term = con.execute('SELECT * FROM terms WHERE id=?', (request.args.get('term', type=int),)).fetchone() or current_term(con)
    rec = con.execute('SELECT * FROM attendance WHERE student_id=? AND day=?', (st['id'], today().isoformat())).fetchone()
    mine, weights, passing = grading.grade_for_student(con, term, st['id'])
    summ = grading.attendance_summary(con, date.fromisoformat(term['start_date']), date.fromisoformat(term['end_date']), [st['id']])[st['id']]
    hist = con.execute('SELECT * FROM attendance WHERE student_id=? ORDER BY day DESC LIMIT 12', (st['id'],)).fetchall()
    stamp = now().isoformat(timespec='minutes')
    upcoming = con.execute('''SELECT a.*, t.submitted_at FROM assessments a LEFT JOIN attempts t ON t.assessment_id=a.id AND t.student_id=?
                              WHERE a.published=1 AND (t.submitted_at IS NULL) AND (a.due_at IS NULL OR a.due_at>=?)
                              ORDER BY COALESCE(a.due_at,'9999') LIMIT 5''', (st['id'], stamp)).fetchall()
    scores = con.execute('''SELECT a.title,a.kind,t.score,t.total,t.submitted_at FROM attempts t JOIN assessments a ON a.id=t.assessment_id
                            WHERE t.student_id=? AND t.submitted_at IS NOT NULL ORDER BY t.submitted_at DESC LIMIT 6''', (st['id'],)).fetchall()
    trend = [{'day': h['day'], 'v': {'Present': 100, 'Excused': 100, 'Late': 75, 'Absent': 0}[h['status']]} for h in reversed(hist)]
    return render_template('dashboard_student.html', st=st, rec=rec, grade=mine, weights=weights, passing=passing, summ=summ,
                           hist=hist, upcoming=upcoming, scores=scores, terms=terms, term=term, trend=trend)


# ------------------------------------------------------------------ students
def student_rows(q='', section=''):
    like = f'%{q}%'
    sql = '''SELECT s.*, u.full_name, u.active, u.must_change FROM students s JOIN users u ON u.id=s.user_id
             WHERE (s.last_name LIKE ? OR s.first_name LIKE ? OR s.lrn LIKE ?)'''
    args = [like, like, like]
    if section:
        sql += ' AND s.section=?'
        args.append(section)
    return db().execute(sql + ' ORDER BY u.active DESC, s.last_name, s.first_name', args).fetchall()


@app.route('/students')
@staff_required
def students():
    q = request.args.get('q', '').strip()
    section = request.args.get('section', '')
    sections = [r[0] for r in db().execute('SELECT DISTINCT section FROM students WHERE section IS NOT NULL ORDER BY 1')]
    return render_template('students.html', rows=student_rows(q, section), q=q, section=section, sections=sections)


def save_student(form, student=None):
    f = {k: form.get(k, '').strip() for k in ('lrn', 'last_name', 'first_name', 'middle_name', 'sex', 'birthdate', 'address',
                                             'contact', 'guardian', 'grade_level', 'strand', 'section', 'school_year')}
    f['lrn'] = ''.join(c for c in f['lrn'] if c.isdigit())
    if not (f['lrn'] and f['last_name'] and f['first_name']):
        raise ValueError('LRN, last name and first name are required.')
    if len(f['lrn']) != 12:
        raise ValueError('An LRN has 12 digits.')
    full = f"{core.title_case(f['first_name'])} {core.title_case(f['middle_name'][:1]) + '. ' if f['middle_name'] else ''}{core.title_case(f['last_name'])}"
    con = db()
    age = None
    if f['birthdate']:
        try:
            b = date.fromisoformat(f['birthdate'])
            age = today().year - b.year - ((today().month, today().day) < (b.month, b.day))
        except ValueError:
            raise ValueError('Birthdate must be a valid date.')
    if student is None:
        cur = con.execute('INSERT INTO users(username,password,role,full_name,must_change,created_at) VALUES(?,?,?,?,1,?)',
                          (f['lrn'], generate_password_hash(f['lrn']), 'student', full, now().isoformat(timespec='seconds')))
        con.execute('''INSERT INTO students(user_id,lrn,last_name,first_name,middle_name,sex,birthdate,age,address,contact,guardian,
                       grade_level,strand,section,school_year,qr_token) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (cur.lastrowid, f['lrn'], core.title_case(f['last_name']), core.title_case(f['first_name']), core.title_case(f['middle_name']),
                     f['sex'][:1].upper(), f['birthdate'], age, f['address'], f['contact'], f['guardian'], f['grade_level'], f['strand'],
                     f['section'], f['school_year'], secrets.token_urlsafe(18)))
    else:
        con.execute('''UPDATE students SET last_name=?,first_name=?,middle_name=?,sex=?,birthdate=?,age=?,address=?,contact=?,guardian=?,
                       grade_level=?,strand=?,section=?,school_year=? WHERE id=?''',
                    (core.title_case(f['last_name']), core.title_case(f['first_name']), core.title_case(f['middle_name']), f['sex'][:1].upper(),
                     f['birthdate'], age, f['address'], f['contact'], f['guardian'], f['grade_level'], f['strand'], f['section'],
                     f['school_year'], student['id']))
        con.execute('UPDATE users SET full_name=? WHERE id=?', (full, student['user_id']))
    con.commit()


@app.route('/students/new', methods=['GET', 'POST'])
@staff_required
def student_new():
    if request.method == 'POST':
        try:
            save_student(request.form)
            log('student_created', request.form.get('lrn', ''))
            flash('Student added. Their first password is their LRN and must be changed at first sign-in.', 'success')
            return redirect(url_for('students'))
        except core.IntegrityError:
            db().rollback()
            flash('A student with that LRN already exists.', 'error')
        except ValueError as e:
            flash(str(e), 'error')
    return render_template('student_form.html', st=request.form if request.method == 'POST' else {'grade_level': '11', 'strand': 'HUMSS', 'section': 'Magalang', 'school_year': get_settings(db())['school_year']}, new=True)


@app.route('/students/<int:sid>', methods=['GET', 'POST'])
@staff_required
def student_edit(sid):
    st = db().execute('SELECT s.*,u.active FROM students s JOIN users u ON u.id=s.user_id WHERE s.id=?', (sid,)).fetchone() or abort(404)
    if request.method == 'POST':
        form = request.form.copy()
        form = {**form.to_dict(), 'lrn': st['lrn']}
        try:
            save_student(form, st)
            log('student_updated', st['lrn'])
            flash('Student updated.', 'success')
            return redirect(url_for('students'))
        except ValueError as e:
            flash(str(e), 'error')
    summ = grading.attendance_summary(db(), date(today().year - 1, 1, 1), today(), [sid])[sid]
    return render_template('student_form.html', st=st, new=False, summ=summ)


@app.post('/students/<int:sid>/reset')
@staff_required
def student_reset(sid):
    st = db().execute('SELECT * FROM students WHERE id=?', (sid,)).fetchone() or abort(404)
    db().execute('UPDATE users SET password=?,must_change=1 WHERE id=?', (generate_password_hash(st['lrn']), st['user_id']))
    db().commit()
    log('password_reset', st['lrn'])
    flash('Password reset to the student\'s LRN. They must choose a new one at next sign-in.', 'success')
    return redirect(request.referrer or url_for('students'))


@app.post('/students/<int:sid>/toggle')
@staff_required
def student_toggle(sid):
    st = db().execute('SELECT * FROM students WHERE id=?', (sid,)).fetchone() or abort(404)
    db().execute('UPDATE users SET active=1-active WHERE id=?', (st['user_id'],))
    db().commit()
    log('student_toggled', st['lrn'])
    return redirect(request.referrer or url_for('students'))


@app.post('/students/import')
@staff_required
def students_import():
    f = request.files.get('file')
    if not f or not f.filename.lower().endswith('.csv'):
        flash('Choose a .csv file (see data/students_HUMSS11_Magalang.csv for the format).', 'error')
        return redirect(url_for('students'))
    try:
        added, skipped = core.import_students_csv(db(), io.StringIO(f.read().decode('utf-8-sig')))
        log('students_imported', f'{added} added')
        flash(f'Import finished: {added} added, {skipped} skipped (duplicates or missing LRN/name).', 'success')
    except Exception as e:  # malformed file
        db().rollback()
        flash(f'Could not read that file: {e}', 'error')
    return redirect(url_for('students'))


@app.route('/students/qr-cards')
@staff_required
def qr_cards():
    return render_template('qr_cards.html', rows=student_rows(request.args.get('q', ''), request.args.get('section', '')))


def make_qr_png(payload):
    try:
        import qrcode
        img = qrcode.make(payload, box_size=10, border=2)
        buf = BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue()
    except ImportError:  # fall back to OpenCV if the qrcode package is unavailable
        import cv2
        import numpy as np
        m = cv2.QRCodeEncoder.create().encode(payload)
        m = cv2.resize(m, None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST)
        return cv2.imencode('.png', np.pad(m, 40, constant_values=255))[1].tobytes()


@app.route('/qr/<token>.png')
def qr_image(token):
    if not g.user:
        abort(403)
    st = db().execute('SELECT user_id FROM students WHERE qr_token=?', (token,)).fetchone() or abort(404)
    if g.user['role'] == 'student' and st['user_id'] != g.user['id']:
        abort(403)
    return Response(make_qr_png('PILASHS:' + token), mimetype='image/png', headers={'Cache-Control': 'private, max-age=3600'})


# ------------------------------------------------------------------ attendance
def record_scan(token):
    con = db()
    token = (token or '').strip()
    if token.upper().startswith('PILASHS:'):
        token = token[8:]
    st = con.execute('''SELECT s.*,u.full_name FROM students s JOIN users u ON u.id=s.user_id
                        WHERE (s.qr_token=? OR s.lrn=?) AND u.active=1''', (token, token)).fetchone()
    if not st:
        return {'ok': False, 'message': 'Unknown QR code or inactive student.'}, 404
    s = get_settings(con)
    n = now()
    day, stamp = n.date().isoformat(), n.strftime('%H:%M:%S')
    rec = con.execute('SELECT * FROM attendance WHERE student_id=? AND day=?', (st['id'], day)).fetchone()
    base = {'ok': True, 'student': st['full_name'], 'lrn': st['lrn'], 'time': n.strftime('%I:%M %p').lstrip('0')}
    if rec is None or not rec['time_in']:
        status = 'Late' if n.strftime('%H:%M') >= s['late_after'] else 'Present'
        if rec is None:
            con.execute('INSERT INTO attendance(student_id,day,time_in,status,source) VALUES(?,?,?,?,?)', (st['id'], day, stamp, status, 'qr'))
        else:  # a manual Absent/Excused row exists but the student actually arrived
            con.execute('UPDATE attendance SET time_in=?,status=?,source=? WHERE id=?', (stamp, status, 'qr', rec['id']))
        event = 'Time In'
    else:
        gap = (datetime.combine(n.date(), n.time()) - datetime.combine(n.date(), datetime.strptime(rec['time_in'], '%H:%M:%S').time())).total_seconds()
        if rec['time_out']:
            return {**base, 'ok': False, 'message': f"{st['full_name']} already has Time In ({t12(rec['time_in'])}) and Time Out ({t12(rec['time_out'])}) today."}, 409
        if gap < grading.fnum(s, 'scan_gap_seconds', 60):
            return {**base, 'ok': False, 'message': f"{st['full_name']} just timed in. Wait a moment before scanning for Time Out."}, 409
        con.execute('UPDATE attendance SET time_out=? WHERE id=?', (stamp, rec['id']))
        event, status = 'Time Out', rec['status']
    con.commit()
    log('attendance_' + event.lower().replace(' ', '_'), st['lrn'])
    return {**base, 'event': event, 'status': status}, 200


@app.post('/api/scan')
@staff_required
def api_scan():
    data = request.get_json(silent=True) or request.form
    result, code = record_scan(data.get('token'))
    return jsonify(result), code


@app.route('/attendance/scan')
@staff_required
def scan_page():
    return render_template('scan.html', secure_url=None if request.is_secure else https_url(url_for('scan_page')))


def attendance_filters():
    period = request.args.get('period', 'daily')
    if period not in ('daily', 'weekly', 'monthly', 'term', 'custom'):
        period = 'daily'
    term_id = request.args.get('term', type=int) or current_term(db())['id']
    start, end, label = resolve_period(db(), period, request.args.get('date'), request.args.get('start'), request.args.get('end'), term_id)
    return period, term_id, start, end, label


def attendance_log_rows(start, end, q=''):
    return db().execute('''SELECT a.*, s.lrn, s.section, s.last_name, s.first_name, u.full_name FROM attendance a
                           JOIN students s ON s.id=a.student_id JOIN users u ON u.id=s.user_id
                           WHERE a.day BETWEEN ? AND ? AND (s.last_name LIKE ? OR s.first_name LIKE ? OR s.lrn LIKE ?)
                           ORDER BY a.day DESC, s.last_name, s.first_name''', (start.isoformat(), end.isoformat(), f'%{q}%', f'%{q}%', f'%{q}%')).fetchall()


@app.route('/attendance')
@staff_required
def attendance():
    period, term_id, start, end, label = attendance_filters()
    q = request.args.get('q', '').strip()
    summ = grading.attendance_summary(db(), start, end)
    studs = {r['id']: r for r in student_rows(q)}
    rows = [{'st': studs[i], **v} for i, v in summ.items() if i in studs and studs[i]['active']]
    tot = {k: sum(r[k] for r in rows) for k in ('present', 'late', 'excused', 'absent')}
    days = next(iter(summ.values()))['days'] if summ else 0
    series = grading.daily_series(db(), start, end)
    daily = period == 'daily'
    detail = attendance_log_rows(start, end, q) if daily or (end - start).days <= 31 else []
    missing = []
    if daily:
        recorded = {d['student_id'] for d in detail}
        missing = [s for s in studs.values() if s['id'] not in recorded and s['active']]
    return render_template('attendance.html', period=period, term_id=term_id, start=start, end=end, label=label, q=q, rows=rows, tot=tot,
                           days=days, series=series, detail=detail, missing=missing, terms=db().execute('SELECT * FROM terms ORDER BY start_date').fetchall(),
                           anchor=request.args.get('date') or today().isoformat(), statuses=STATUSES)


@app.post('/attendance/mark')
@staff_required
def attendance_mark():
    day = request.form.get('day', today().isoformat())
    status = request.form.get('status')
    ids = request.form.getlist('student_id')
    if status not in STATUSES or not ids:
        flash('Choose students and a status.', 'error')
        return redirect(request.referrer or url_for('attendance'))
    for sid in ids:
        db().execute('''INSERT INTO attendance(student_id,day,status,remarks,source) VALUES(?,?,?,?,'manual')
                        ON DUPLICATE KEY UPDATE status=VALUES(status), remarks=VALUES(remarks)''',
                     (sid, day, status, request.form.get('remarks', '').strip()))
    db().commit()
    log('attendance_marked', f'{len(ids)} → {status} on {day}')
    flash(f'Marked {len(ids)} student(s) as {status}.', 'success')
    return redirect(request.referrer or url_for('attendance'))


@app.post('/attendance/<int:aid>/delete')
@staff_required
def attendance_delete(aid):
    db().execute('DELETE FROM attendance WHERE id=?', (aid,))
    db().commit()
    log('attendance_deleted', str(aid))
    return redirect(request.referrer or url_for('attendance'))


@app.route('/attendance/export.csv')
@staff_required
def attendance_export():
    period, term_id, start, end, label = attendance_filters()
    kind = request.args.get('kind', 'summary')
    if kind == 'log':
        rows = [[r['day'], r['lrn'], f"{r['last_name']}, {r['first_name']}", r['section'], r['status'], r['time_in'] or '', r['time_out'] or '', r['remarks'] or '']
                for r in attendance_log_rows(start, end)]
        return csv_response(f'attendance-log_{start}_{end}.csv', ['Date', 'LRN', 'Name', 'Section', 'Status', 'Time In', 'Time Out', 'Remarks'], rows)
    summ = grading.attendance_summary(db(), start, end)
    studs = {r['id']: r for r in student_rows()}
    rows = [[s['lrn'], f"{s['last_name']}, {s['first_name']}", s['section'], v['days'], v['present'], v['late'], v['excused'], v['absent'],
             '' if v['rate'] is None else v['rate']] for i, v in summ.items() if (s := studs.get(i))]
    return csv_response(f'attendance-summary_{start}_{end}.csv', ['LRN', 'Name', 'Section', 'Class days', 'Present', 'Late', 'Excused', 'Absent', 'Attendance %'], rows)


# ------------------------------------------------------------------ recitation
@app.route('/recitation', methods=['GET', 'POST'])
@staff_required
def recitation():
    con = db()
    day = request.values.get('day', today().isoformat())
    topic = request.values.get('topic', '').strip()
    if request.method == 'POST':
        maxs = request.form.get('max_score', type=float) or 10
        saved = 0
        for k, v in request.form.items():
            if k.startswith('score_') and v.strip() != '':
                try:
                    val = float(v)
                except ValueError:
                    continue
                if 0 <= val <= maxs:
                    con.execute('''INSERT INTO recitation(student_id,day,score,max_score,topic) VALUES(?,?,?,?,?)
                                   ON DUPLICATE KEY UPDATE score=VALUES(score), max_score=VALUES(max_score)''',
                                (int(k[6:]), day, val, maxs, topic))
                    saved += 1
        con.commit()
        log('recitation_saved', f'{saved} scores on {day}')
        flash(f'Saved {saved} recitation score(s).', 'success')
        return redirect(url_for('recitation', day=day, topic=topic))
    existing = {r['student_id']: r for r in con.execute('SELECT * FROM recitation WHERE day=? AND topic=?', (day, topic))}
    maxs = next((r['max_score'] for r in existing.values()), 10)
    recent = con.execute('SELECT day,topic,COUNT(*) n,AVG(score*100.0/max_score) avg FROM recitation GROUP BY day,topic ORDER BY day DESC LIMIT 8').fetchall()
    return render_template('recitation.html', rows=[r for r in student_rows() if r['active']], existing=existing, day=day, topic=topic, maxs=maxs, recent=recent)


# ------------------------------------------------------------------ quizzes & exams
@app.route('/assessments')
@staff_required
def assessments():
    rows = db().execute('''SELECT a.*, t.name term_name, (SELECT COUNT(*) FROM questions q WHERE q.assessment_id=a.id) nq,
                           (SELECT SUM(points) FROM questions q WHERE q.assessment_id=a.id) pts,
                           (SELECT COUNT(*) FROM attempts x WHERE x.assessment_id=a.id AND x.submitted_at IS NOT NULL) taken,
                           (SELECT AVG(x.score*100.0/x.total) FROM attempts x WHERE x.assessment_id=a.id AND x.submitted_at IS NOT NULL AND x.total>0) avg
                           FROM assessments a LEFT JOIN terms t ON t.id=a.term_id ORDER BY a.created_at DESC''').fetchall()
    return render_template('assessments.html', rows=rows)


def parse_questions(raw):
    try:
        items = json.loads(raw or '[]')
    except ValueError:
        raise ValueError('Questions could not be read. Please reload and try again.')
    out = []
    for i, it in enumerate(items, 1):
        prompt = (it.get('prompt') or '').strip()
        qtype = it.get('qtype')
        if not prompt:
            raise ValueError(f'Question {i} has no text.')
        if qtype not in ('mcq', 'tf', 'text'):
            raise ValueError(f'Question {i} has an unknown type.')
        try:
            points = float(it.get('points') or 1)
        except ValueError:
            points = 1
        if points <= 0:
            raise ValueError(f'Question {i} needs points above zero.')
        choices, answer = None, (it.get('answer') or '').strip()
        if qtype == 'mcq':
            ch = [c.strip() for c in it.get('choices', []) if c and c.strip()]
            if len(ch) < 2 or len(set(c.lower() for c in ch)) != len(ch):
                raise ValueError(f'Question {i} needs at least two different choices.')
            if answer not in ch:
                raise ValueError(f'Question {i}: pick the correct choice.')
            choices = json.dumps(ch)
        elif qtype == 'tf':
            answer = 'True' if answer.lower() == 'true' else 'False'
        elif not answer:
            raise ValueError(f'Question {i} needs a correct answer.')
        out.append((i, qtype, prompt, choices, answer, points))
    if not out:
        raise ValueError('Add at least one question.')
    return out


@app.route('/assessments/new', methods=['GET', 'POST'])
@app.route('/assessments/<int:aid>/edit', methods=['GET', 'POST'])
@staff_required
def assessment_form(aid=None):
    con = db()
    a = con.execute('SELECT * FROM assessments WHERE id=?', (aid,)).fetchone() if aid else None
    if aid and not a:
        abort(404)
    attempts = con.execute('SELECT COUNT(*) c FROM attempts WHERE assessment_id=?', (aid,)).fetchone()['c'] if aid else 0
    terms = con.execute('SELECT * FROM terms ORDER BY start_date').fetchall()
    if request.method == 'POST':
        f = request.form
        try:
            title = f.get('title', '').strip()
            if not title:
                raise ValueError('Give the assessment a title.')
            kind = 'exam' if f.get('kind') == 'exam' else 'quiz'
            qs = parse_questions(f.get('questions')) if not attempts else None
            vals = (kind, title, f.get('instructions', '').strip(), f.get('term_id', type=int), f.get('time_limit', type=int) or 0,
                    f.get('opens_at') or None, f.get('due_at') or None, 1 if f.get('published') else 0, 1 if f.get('show_answers') else 0)
            if a:
                con.execute('UPDATE assessments SET kind=?,title=?,instructions=?,term_id=?,time_limit=?,opens_at=?,due_at=?,published=?,show_answers=? WHERE id=?', vals + (aid,))
            else:
                cur = con.execute('''INSERT INTO assessments(kind,title,instructions,term_id,time_limit,opens_at,due_at,published,show_answers,created_by,created_at)
                                     VALUES(?,?,?,?,?,?,?,?,?,?,?)''', vals + (g.user['id'], now().isoformat(timespec='seconds')))
                aid = cur.lastrowid
            if qs is not None:
                con.execute('DELETE FROM questions WHERE assessment_id=?', (aid,))
                con.executemany('INSERT INTO questions(assessment_id,position,qtype,prompt,choices,answer,points) VALUES(?,?,?,?,?,?,?)', [(aid,) + q for q in qs])
            con.commit()
            log('assessment_saved', title)
            flash('Saved.' + ('' if qs is not None else ' Questions are locked because students have already taken it.'), 'success')
            return redirect(url_for('assessments'))
        except ValueError as e:
            con.rollback()
            flash(str(e), 'error')
    qs = [{'qtype': q['qtype'], 'prompt': q['prompt'], 'choices': json.loads(q['choices']) if q['choices'] else [], 'answer': q['answer'], 'points': q['points']}
          for q in con.execute('SELECT * FROM questions WHERE assessment_id=? ORDER BY position', (aid,))] if aid else []
    return render_template('assessment_form.html', a=a, terms=terms, questions=qs, attempts=attempts,
                           cur_term=current_term(con)['id'])


@app.post('/assessments/<int:aid>/publish')
@staff_required
def assessment_publish(aid):
    db().execute('UPDATE assessments SET published=1-published WHERE id=?', (aid,))
    db().commit()
    return redirect(url_for('assessments'))


@app.post('/assessments/<int:aid>/delete')
@staff_required
def assessment_delete(aid):
    db().execute('DELETE FROM assessments WHERE id=?', (aid,))
    db().commit()
    log('assessment_deleted', str(aid))
    flash('Deleted.', 'success')
    return redirect(url_for('assessments'))


@app.route('/assessments/<int:aid>/results')
@staff_required
def assessment_results(aid):
    a = db().execute('SELECT a.*,t.name term_name FROM assessments a LEFT JOIN terms t ON t.id=a.term_id WHERE a.id=?', (aid,)).fetchone() or abort(404)
    rows = db().execute('''SELECT s.id,s.lrn,s.last_name,s.first_name, t.score,t.total,t.submitted_at FROM students s JOIN users u ON u.id=s.user_id
                           LEFT JOIN attempts t ON t.student_id=s.id AND t.assessment_id=? WHERE u.active=1 ORDER BY s.last_name,s.first_name''', (aid,)).fetchall()
    if request.args.get('csv'):
        return csv_response(f'{a["kind"]}-{aid}-results.csv', ['LRN', 'Name', 'Score', 'Total', 'Percent', 'Submitted'],
                            [[r['lrn'], f"{r['last_name']}, {r['first_name']}", r['score'] if r['submitted_at'] else '', r['total'] if r['submitted_at'] else '',
                              round(r['score'] * 100 / r['total'], 1) if r['submitted_at'] and r['total'] else '', r['submitted_at'] or 'Not taken'] for r in rows])
    done = [r for r in rows if r['submitted_at'] and r['total']]
    avg = sum(r['score'] * 100 / r['total'] for r in done) / len(done) if done else None
    return render_template('assessment_results.html', a=a, rows=rows, avg=avg, done=len(done))


# ------------------------------------------------------------------ grades & reports
def pick_term():
    terms = db().execute('SELECT * FROM terms ORDER BY start_date').fetchall()
    term = db().execute('SELECT * FROM terms WHERE id=?', (request.args.get('term', type=int),)).fetchone() or current_term(db())
    return terms, term


@app.route('/grades')
@staff_required
def grades():
    terms, term = pick_term()
    rows, weights, passing = grading.term_grades(db(), term)
    if request.args.get('csv'):
        return grades_csv(term, rows, weights)
    return render_template('grades.html', terms=terms, term=term, rows=rows, weights=weights, passing=passing)


def grades_csv(term, rows, weights):
    f = lambda v: '' if v is None else v
    return csv_response(f"grades_{term['name'].replace(' ', '-')}.csv",
                        ['LRN', 'Name', 'Attendance %', 'Recitation %', 'Quiz %', 'Exam %', f"Final ({', '.join(f'{k} {v:g}%' for k, v in weights.items())})", 'Remarks'],
                        [[r['student']['lrn'], fullname(r['student'])] + [f(r['components'][k]) for k in ('attendance', 'recitation', 'quiz', 'exam')] + [f(r['final']), r['remarks'] or ''] for r in rows])


@app.route('/reports')
@staff_required
def reports():
    terms, term = pick_term()
    period, term_id, start, end, label = attendance_filters()
    return render_template('reports.html', terms=terms, term=term, period=period, start=start, end=end, label=label,
                           anchor=request.args.get('date') or today().isoformat(), term_id=term_id)


@app.route('/reports/export.csv')
@staff_required
def report_export():
    kind = request.args.get('kind', 'grades')
    if kind in ('attendance_summary', 'attendance_log'):
        return redirect(url_for('attendance_export', kind='log' if kind == 'attendance_log' else 'summary',
                                **{k: v for k, v in request.args.items() if k != 'kind'}))
    if kind == 'students':
        rows = [[s['lrn'], s['last_name'], s['first_name'], s['middle_name'], s['sex'], s['birthdate'], s['age'], s['address'], s['previous_school'],
                 s['grade10_avg'], s['grade_level'], s['strand'], s['section'], s['school_year'], 'Active' if s['active'] else 'Inactive'] for s in student_rows()]
        return csv_response('students.csv', ['LRN', 'Last name', 'First name', 'Middle name', 'Sex', 'Birthdate', 'Age', 'Address', 'Previous school',
                                             'Grade 10 average', 'Grade', 'Strand', 'Section', 'School year', 'Status'], rows)
    terms, term = pick_term()
    if kind == 'assessments':
        rows = db().execute('''SELECT a.kind,a.title,s.lrn,s.last_name,s.first_name,t.score,t.total,t.submitted_at FROM attempts t
                               JOIN assessments a ON a.id=t.assessment_id JOIN students s ON s.id=t.student_id
                               WHERE a.term_id=? AND t.submitted_at IS NOT NULL ORDER BY a.id,s.last_name''', (term['id'],)).fetchall()
        return csv_response(f"quiz-exam-results_{term['name'].replace(' ', '-')}.csv", ['Type', 'Title', 'LRN', 'Name', 'Score', 'Total', 'Percent', 'Submitted'],
                            [[r['kind'], r['title'], r['lrn'], f"{r['last_name']}, {r['first_name']}", r['score'], r['total'], round(r['score'] * 100 / r['total'], 1) if r['total'] else '', r['submitted_at']] for r in rows])
    if kind == 'recitation':
        rows = db().execute('''SELECT r.day,r.topic,s.lrn,s.last_name,s.first_name,r.score,r.max_score FROM recitation r JOIN students s ON s.id=r.student_id
                               WHERE r.day BETWEEN ? AND ? ORDER BY r.day,s.last_name''', (term['start_date'], term['end_date'])).fetchall()
        return csv_response('recitation.csv', ['Date', 'Topic', 'LRN', 'Name', 'Score', 'Max'], [[r['day'], r['topic'], r['lrn'], f"{r['last_name']}, {r['first_name']}", r['score'], r['max_score']] for r in rows])
    rows, weights, _ = grading.term_grades(db(), term)
    return grades_csv(term, rows, weights)


# ------------------------------------------------------------------ settings & accounts
@app.route('/settings', methods=['GET', 'POST'])
@staff_required
def settings():
    con = db()
    if request.method == 'POST':
        f = request.form
        try:
            w = {k: float(f.get('w_' + k, 0)) for k in ('attendance', 'recitation', 'quiz', 'exam')}
            if any(v < 0 for v in w.values()) or abs(sum(w.values()) - 100) > 0.01:
                raise ValueError('Grade weights must be zero or more and add up to 100.')
            for k in ('school_year', 'late_after', 'scan_gap_seconds', 'late_credit', 'passing', 'at_risk_attendance'):
                v = f.get(k, '').strip()
                if not v:
                    raise ValueError('Fill in every setting.')
                con.execute('REPLACE INTO settings(setting_key,setting_value) VALUES(?,?)', (k, v))
            for k, v in w.items():
                con.execute('REPLACE INTO settings(setting_key,setting_value) VALUES(?,?)', ('w_' + k, f'{v:g}'))
            for tid, name, s_, e_ in zip(f.getlist('term_id'), f.getlist('term_name'), f.getlist('term_start'), f.getlist('term_end')):
                if name.strip() and s_ and e_:
                    if e_ < s_:
                        raise ValueError(f'{name}: the end date is before the start date.')
                    if tid:
                        con.execute('UPDATE terms SET name=?,start_date=?,end_date=? WHERE id=?', (name.strip(), s_, e_, tid))
                    else:
                        con.execute('INSERT INTO terms(name,start_date,end_date) VALUES(?,?,?)', (name.strip(), s_, e_))
            con.commit()
            log('settings_saved')
            flash('Settings saved.', 'success')
            return redirect(url_for('settings'))
        except ValueError as e:
            con.rollback()
            flash(str(e) if 'could not convert' not in str(e) else 'Enter numbers in the number fields.', 'error')
    return render_template('settings.html', terms=con.execute('SELECT * FROM terms ORDER BY start_date').fetchall(), s=get_settings(con))


@app.route('/accounts', methods=['GET', 'POST'])
@admin_required
def accounts():
    con = db()
    if request.method == 'POST':
        f = request.form
        username, name, pw = f.get('username', '').strip().lower(), f.get('full_name', '').strip(), f.get('password', '')
        role = 'admin' if f.get('role') == 'admin' else 'teacher'
        if not (username and name) or len(pw) < 8:
            flash('Name, username and a temporary password of 8+ characters are required.', 'error')
        else:
            try:
                con.execute('INSERT INTO users(username,password,role,full_name,must_change,created_at) VALUES(?,?,?,?,1,?)',
                            (username, generate_password_hash(pw), role, name, now().isoformat(timespec='seconds')))
                con.commit()
                log('account_created', username)
                flash(f'{role.title()} account created. They must change the password at first sign-in.', 'success')
            except core.IntegrityError:
                flash('That username is taken.', 'error')
        return redirect(url_for('accounts'))
    return render_template('accounts.html', rows=con.execute("SELECT * FROM users WHERE role IN ('admin','teacher') ORDER BY role,full_name").fetchall())


@app.post('/accounts/<int:uid>/reset')
@admin_required
def account_reset(uid):
    pw = request.form.get('password', '')
    if len(pw) < 8:
        flash('Temporary password needs 8+ characters.', 'error')
    else:
        db().execute("UPDATE users SET password=?,must_change=1 WHERE id=? AND role IN ('admin','teacher')", (generate_password_hash(pw), uid))
        db().commit()
        flash('Password reset. They must change it at next sign-in.', 'success')
    return redirect(url_for('accounts'))


@app.post('/accounts/<int:uid>/toggle')
@admin_required
def account_toggle(uid):
    if uid == g.user['id']:
        flash('You cannot deactivate your own account.', 'error')
    else:
        db().execute("UPDATE users SET active=1-active WHERE id=? AND role IN ('admin','teacher')", (uid,))
        db().commit()
    return redirect(url_for('accounts'))


# ------------------------------------------------------------------ student area
@app.route('/my/qr')
@student_required
def my_qr():
    return render_template('my_qr.html', st=g.student)


@app.route('/my/attendance')
@student_required
def my_attendance():
    period = request.args.get('period', 'term')
    term_id = request.args.get('term', type=int) or current_term(db())['id']
    start, end, label = resolve_period(db(), 'term' if period == 'term' else 'monthly', request.args.get('date'), None, None, term_id)
    rows = db().execute('SELECT * FROM attendance WHERE student_id=? AND day BETWEEN ? AND ? ORDER BY day DESC', (g.student['id'], start.isoformat(), end.isoformat())).fetchall()
    summ = grading.attendance_summary(db(), start, end, [g.student['id']])[g.student['id']]
    return render_template('my_attendance.html', rows=rows, summ=summ, label=label, period=period, term_id=term_id,
                           terms=db().execute('SELECT * FROM terms ORDER BY start_date').fetchall())


@app.route('/my/assessments')
@student_required
def my_assessments():
    stamp = now().isoformat(timespec='minutes')
    rows = db().execute('''
        SELECT a.*, tm.name term_name, t.submitted_at, t.score, t.total, t.started_at,
               (SELECT COUNT(*) FROM questions q WHERE q.assessment_id=a.id) nq
        FROM assessments a LEFT JOIN terms tm ON tm.id=a.term_id
        LEFT JOIN attempts t ON t.assessment_id=a.id AND t.student_id=?
        WHERE a.published=1 ORDER BY COALESCE(a.due_at,'9999'), a.id''', (g.student['id'],)).fetchall()
    return render_template('my_assessments.html', rows=rows, stamp=stamp)


def load_questions(aid):
    out = []
    for q in db().execute('SELECT * FROM questions WHERE assessment_id=? ORDER BY position', (aid,)):
        d = dict(q)
        d['choices'] = json.loads(q['choices']) if q['choices'] else []
        out.append(d)
    return out


def finalize_attempt(att, a, answers):
    qs = load_questions(a['id'])
    score, total, detail = grading.score_answers(qs, answers)
    db().execute('UPDATE attempts SET submitted_at=?,score=?,total=?,answers=? WHERE id=?',
                 (now().isoformat(timespec='seconds'), score, total, json.dumps(answers), att['id']))
    db().commit()
    log('assessment_submitted', f"{a['title']} {score:g}/{total:g}")


def attempt_deadline(att, a):
    if not a['time_limit']:
        return None
    return datetime.fromisoformat(att['started_at']) + timedelta(minutes=a['time_limit'])


@app.route('/my/assessments/<int:aid>', methods=['GET', 'POST'])
@student_required
def take_assessment(aid):
    con = db()
    a = con.execute('SELECT * FROM assessments WHERE id=? AND published=1', (aid,)).fetchone() or abort(404)
    att = con.execute('SELECT * FROM attempts WHERE assessment_id=? AND student_id=?', (aid, g.student['id'])).fetchone()
    n = now()
    stamp = n.isoformat(timespec='minutes')
    if att and att['submitted_at']:
        return result_view(a, att)
    if att:  # in progress – honour the time limit even if the browser was closed
        dl = attempt_deadline(att, a)
        if dl and n > dl + timedelta(seconds=60):
            finalize_attempt(att, a, {})
            flash('Time ran out before you submitted, so this attempt was closed.', 'error')
            return redirect(url_for('take_assessment', aid=aid))
    if request.method == 'POST':
        if not att:
            abort(400)
        finalize_attempt(att, a, {k[2:]: v for k, v in request.form.items() if k.startswith('q_')})
        flash('Submitted. Your score was calculated automatically.', 'success')
        return redirect(url_for('take_assessment', aid=aid))
    if not att:
        if a['opens_at'] and stamp < a['opens_at']:
            flash(f"This opens on {dtfmt(a['opens_at'])}.", 'error')
            return redirect(url_for('my_assessments'))
        if a['due_at'] and stamp > a['due_at']:
            flash('This is already closed.', 'error')
            return redirect(url_for('my_assessments'))
        if request.args.get('start') != '1':
            return render_template('take_intro.html', a=a, nq=len(load_questions(aid)))
        con.execute('INSERT INTO attempts(assessment_id,student_id,started_at) VALUES(?,?,?)', (aid, g.student['id'], n.isoformat(timespec='seconds')))
        con.commit()
        att = con.execute('SELECT * FROM attempts WHERE assessment_id=? AND student_id=?', (aid, g.student['id'])).fetchone()
    dl = attempt_deadline(att, a)
    return render_template('take.html', a=a, qs=load_questions(aid), seconds_left=max(int((dl - n).total_seconds()), 0) if dl else None)


def result_view(a, att):
    qs = load_questions(a['id'])
    answers = json.loads(att['answers'] or '{}')
    _, _, detail = grading.score_answers(qs, answers)
    return render_template('my_result.html', a=a, att=att, qs=qs, detail=detail)


@app.route('/my/grades')
@student_required
def my_grades():
    terms = db().execute('SELECT * FROM terms ORDER BY start_date').fetchall()
    term = db().execute('SELECT * FROM terms WHERE id=?', (request.args.get('term', type=int),)).fetchone() or current_term(db())
    mine, weights, passing = grading.grade_for_student(db(), term, g.student['id'])
    summ = grading.attendance_summary(db(), date.fromisoformat(term['start_date']), date.fromisoformat(term['end_date']), [g.student['id']])[g.student['id']]
    return render_template('my_grades.html', terms=terms, term=term, grade=mine, weights=weights, passing=passing, summ=summ)


# ------------------------------------------------------------------ errors
def error_page(code, title, msg):
    return render_template('error.html', code=code, title=title, msg=msg), code


@app.errorhandler(400)
def e400(e): return error_page(400, 'Request problem', getattr(e, 'description', 'Bad request.'))


@app.errorhandler(403)
def e403(_): return error_page(403, 'Not allowed', 'Your account does not have access to this page.')


@app.errorhandler(404)
def e404(_): return error_page(404, 'Page not found', 'That page does not exist or was moved.')


@app.errorhandler(413)
def e413(_): return error_page(413, 'File too large', 'Upload a file smaller than 2 MB.')


@app.errorhandler(500)
def e500(_): return error_page(500, 'Something went wrong', 'The error was logged. Please try again.')


def _serve():
    """Serve plain HTTP (localhost) and, when possible, HTTPS (phones need it for the camera)."""
    from werkzeug.serving import make_server
    import tls

    host = os.environ.get('HOST', '0.0.0.0')
    http_port = int(os.environ.get('PORT', 5000))
    https_port = int(os.environ.get('HTTPS_PORT', 5443))
    secure = None
    if os.environ.get('HTTPS', '1') != '0':
        try:
            cert, key = tls.ensure_cert(INSTANCE_DIR / 'certs')
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(cert, key)
            secure = make_server(host, https_port, app, threaded=True, ssl_context=ctx)
            app.config['HTTPS_PORT'] = https_port
        except ImportError:
            print('\n!! HTTPS is off: run  pip install cryptography  so phones can use the camera.\n')
        except OSError as exc:
            print(f'\n!! Could not start HTTPS on port {https_port}: {exc}\n')
    web = make_server(host, http_port, app, threaded=True)
    ips = tls.lan_ips()
    print('\nPila SHS Attendance is running.')
    print(f'  This computer :  http://localhost:{http_port}')
    if secure:
        for ip in ips or ['<computer-IP>']:
            print(f'  Phones / tablets (same Wi-Fi) :  https://{ip}:{https_port}   <- camera works here')
        print('  The first time, the browser warns about the certificate: tap Advanced -> Proceed / Visit this website.')
    else:
        for ip in ips:
            print(f'  Phones (camera will NOT work without HTTPS) :  http://{ip}:{http_port}')
    print('  Press Ctrl+C to stop.\n')
    if secure:
        threading.Thread(target=secure.serve_forever, daemon=True).start()
    try:
        web.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    if os.environ.get('FLASK_DEBUG') == '1':
        app.run(host=os.environ.get('HOST', '0.0.0.0'), port=int(os.environ.get('PORT', 5000)), debug=True)
    else:
        _serve()
