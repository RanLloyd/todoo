"""Attendance summaries and term-based grade computation."""
from datetime import date

from core import get_settings, now, today


def fnum(settings, key, default=0.0):
    try:
        return float(settings.get(key, default))
    except (TypeError, ValueError):
        return default


def class_days(con, start, end):
    """Days (up to today) on which at least one attendance record exists."""
    rows = con.execute('SELECT DISTINCT day FROM attendance WHERE day BETWEEN ? AND ? AND day<=? ORDER BY day',
                       (start.isoformat(), end.isoformat(), today().isoformat())).fetchall()
    return [r['day'] for r in rows]


def attendance_summary(con, start, end, student_ids=None):
    """Return {student_id: {...}} with counts, class days and credit-based attendance percentage."""
    s = get_settings(con)
    credit = fnum(s, 'late_credit', 0.75)
    days = class_days(con, start, end)
    n = len(days)
    out = {}
    q = 'SELECT s.id FROM students s JOIN users u ON u.id=s.user_id WHERE u.active=1'
    ids = [r['id'] for r in con.execute(q)] if student_ids is None else list(student_ids)
    for sid in ids:
        out[sid] = {'present': 0, 'late': 0, 'excused': 0, 'absent': 0, 'days': n, 'rate': None, 'credit_rate': None}
    if n:
        for r in con.execute('SELECT student_id,status,COUNT(*) c FROM attendance WHERE day BETWEEN ? AND ? AND day<=? GROUP BY student_id,status',
                             (start.isoformat(), end.isoformat(), today().isoformat())):
            if r['student_id'] in out:
                out[r['student_id']][r['status'].lower()] += r['c']
        for v in out.values():
            attended = v['present'] + v['late'] + v['excused']
            v['absent'] = max(n - attended, 0)
            v['rate'] = round(attended / n * 100, 1)
            v['credit_rate'] = round((v['present'] + v['excused'] + v['late'] * credit) / n * 100, 1)
    return out


def daily_series(con, start, end):
    """Per class-day totals for trend charts."""
    total = con.execute('SELECT COUNT(*) c FROM students s JOIN users u ON u.id=s.user_id WHERE u.active=1').fetchone()['c']
    rows = con.execute('''SELECT a.day, SUM(a.status='Present') p, SUM(a.status='Late') l, SUM(a.status='Excused') e,
                          SUM(a.status='Absent') ab FROM attendance a JOIN students s ON s.id=a.student_id
                          JOIN users u ON u.id=s.user_id WHERE u.active=1 AND a.day BETWEEN ? AND ? AND a.day<=?
                          GROUP BY a.day ORDER BY a.day''', (start.isoformat(), end.isoformat(), today().isoformat())).fetchall()
    series = []
    for r in rows:
        p, l, e = r['p'] or 0, r['l'] or 0, r['e'] or 0
        absent = max(total - (p + l + e), 0)
        series.append({'day': r['day'], 'present': p, 'late': l, 'excused': e, 'absent': absent,
                       'rate': round((p + l + e) / total * 100, 1) if total else 0})
    return series


def recitation_pct(con, term):
    out = {}
    for r in con.execute('''SELECT student_id, AVG(score*100.0/max_score) pct FROM recitation
                            WHERE day BETWEEN ? AND ? AND max_score>0 GROUP BY student_id''', (term['start_date'], term['end_date'])):
        out[r['student_id']] = round(r['pct'], 1)
    return out


def assessment_pct(con, term, kind):
    """Average % for quizzes or exams in the term. Missed items count as 0 once their due date has passed."""
    items = con.execute('SELECT id,due_at FROM assessments WHERE term_id=? AND kind=? AND published=1', (term['id'], kind)).fetchall()
    if not items:
        return {}, 0
    stamp = now().isoformat(timespec='minutes')
    students = [r['id'] for r in con.execute('SELECT s.id FROM students s JOIN users u ON u.id=s.user_id WHERE u.active=1')]
    pcts = {sid: [] for sid in students}
    for it in items:
        taken = {r['student_id']: r for r in con.execute(
            'SELECT student_id,score,total FROM attempts WHERE assessment_id=? AND submitted_at IS NOT NULL', (it['id'],))}
        overdue = bool(it['due_at']) and it['due_at'] < stamp
        for sid in students:
            a = taken.get(sid)
            if a and a['total']:
                pcts[sid].append(a['score'] * 100.0 / a['total'])
            elif overdue:
                pcts[sid].append(0.0)
    return {sid: round(sum(v) / len(v), 1) for sid, v in pcts.items() if v}, len(items)


def term_grades(con, term):
    """Combine attendance, recitation, quiz and exam into one grade per student for the term."""
    s = get_settings(con)
    weights = {k: fnum(s, 'w_' + k) for k in ('attendance', 'recitation', 'quiz', 'exam')}
    passing = fnum(s, 'passing', 75)
    start, end = date.fromisoformat(term['start_date']), date.fromisoformat(term['end_date'])
    att = attendance_summary(con, start, end)
    rec = recitation_pct(con, term)
    quiz, _ = assessment_pct(con, term, 'quiz')
    exam, _ = assessment_pct(con, term, 'exam')
    rows = con.execute('''SELECT s.*, u.full_name FROM students s JOIN users u ON u.id=s.user_id
                          WHERE u.active=1 ORDER BY s.last_name, s.first_name''').fetchall()
    out = []
    for st in rows:
        a = att.get(st['id'], {})
        comp = {
            'attendance': a.get('credit_rate'),
            'recitation': rec.get(st['id']),
            'quiz': quiz.get(st['id']),
            'exam': exam.get(st['id']),
        }
        used = {k: v for k, v in comp.items() if v is not None and weights[k] > 0}
        wsum = sum(weights[k] for k in used)
        final = round(sum(v * weights[k] for k, v in used.items()) / wsum, 1) if wsum else None
        out.append({'student': st, 'name': st['full_name'], 'components': comp, 'final': final,
                    'remarks': None if final is None else ('Passed' if final >= passing else 'Failed'),
                    'attendance': a})
    return out, weights, passing


def grade_for_student(con, term, student_id):
    rows, weights, passing = term_grades(con, term)
    for r in rows:
        if r['student']['id'] == student_id:
            return r, weights, passing
    return None, weights, passing


def score_answers(questions, answers):
    """Auto-grade submitted answers. Returns (score, total, per-question detail)."""
    score = total = 0.0
    detail = {}
    for q in questions:
        total += q['points']
        given = (answers.get(str(q['id'])) or '').strip()
        accepted = [a.strip().lower() for a in q['answer'].split('|') if a.strip()]
        ok = bool(given) and given.lower() in accepted
        if ok:
            score += q['points']
        detail[q['id']] = {'given': given, 'correct': ok}
    return score, total, detail
