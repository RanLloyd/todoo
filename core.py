"""Database, settings, security helpers and seeding for the Pila SHS attendance system."""
import csv
import os
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor
from pymysql.constants import FIELD_TYPE

from werkzeug.security import generate_password_hash

try:  # Philippine time by default; falls back to the server clock if tzdata is missing
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(os.environ.get('SCHOOL_TZ', 'Asia/Manila'))
except Exception:  # pragma: no cover
    TZ = None

ROOT = Path(__file__).resolve().parent


def _load_dotenv():
    """Read KEY=VALUE lines from .env (if present) without overriding real environment variables."""
    f = ROOT / '.env'
    if f.is_file():
        for line in f.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))


_load_dotenv()

# MySQL / MariaDB connection (XAMPP defaults: user "root", empty password, port 3306)
DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
DB_PORT = int(os.environ.get('DB_PORT', 3306))
DB_USER = os.environ.get('DB_USER', 'root')
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_NAME = os.environ.get('DB_NAME', 'attendance_monitoring')
INSTANCE_DIR = ROOT / 'instance'   # secret key and HTTPS certificate live here (not the database)
SEED_CSV = ROOT / 'data' / 'students_HUMSS11_Magalang.csv'


def now():
    return datetime.now(TZ).replace(tzinfo=None) if TZ else datetime.now()


def today():
    return now().date()


IntegrityError = pymysql.err.IntegrityError

# Dates and times are stored as ISO text (YYYY-MM-DD, HH:MM:SS, YYYY-MM-DDTHH:MM:SS) exactly as the app has always done,
# so they sort and compare correctly as plain strings.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users(
      id INT AUTO_INCREMENT PRIMARY KEY, username VARCHAR(100) NOT NULL UNIQUE, password VARCHAR(255) NOT NULL,
      role ENUM('admin','teacher','student') NOT NULL, full_name VARCHAR(200) NOT NULL,
      active TINYINT(1) NOT NULL DEFAULT 1, must_change TINYINT(1) NOT NULL DEFAULT 0, created_at VARCHAR(19)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS students(
      id INT AUTO_INCREMENT PRIMARY KEY, user_id INT UNIQUE, lrn VARCHAR(20) NOT NULL UNIQUE,
      last_name VARCHAR(100) NOT NULL, first_name VARCHAR(100) NOT NULL, middle_name VARCHAR(100),
      sex VARCHAR(1), birthdate VARCHAR(10), age INT, address VARCHAR(500), previous_school VARCHAR(200), grade10_avg DOUBLE,
      contact VARCHAR(100), guardian VARCHAR(200), grade_level VARCHAR(10), strand VARCHAR(50), section VARCHAR(100),
      school_year VARCHAR(20), qr_token VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL UNIQUE,
      CONSTRAINT fk_students_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS terms(
      id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL, start_date VARCHAR(10) NOT NULL, end_date VARCHAR(10) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS attendance(
      id INT AUTO_INCREMENT PRIMARY KEY, student_id INT NOT NULL, day VARCHAR(10) NOT NULL, time_in VARCHAR(8), time_out VARCHAR(8),
      status ENUM('Present','Late','Absent','Excused') NOT NULL DEFAULT 'Present',
      remarks VARCHAR(500), source VARCHAR(20) DEFAULT 'qr',
      UNIQUE KEY uq_att_student_day (student_id, day), KEY idx_att_day (day),
      CONSTRAINT fk_att_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS recitation(
      id INT AUTO_INCREMENT PRIMARY KEY, student_id INT NOT NULL, day VARCHAR(10) NOT NULL, score DOUBLE NOT NULL,
      max_score DOUBLE NOT NULL DEFAULT 10, topic VARCHAR(150),
      UNIQUE KEY uq_rec (student_id, day, topic),
      CONSTRAINT fk_rec_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS assessments(
      id INT AUTO_INCREMENT PRIMARY KEY, kind ENUM('quiz','exam') NOT NULL, title VARCHAR(255) NOT NULL,
      instructions TEXT, term_id INT, time_limit INT DEFAULT 0,
      opens_at VARCHAR(19), due_at VARCHAR(19), published TINYINT(1) NOT NULL DEFAULT 0, show_answers TINYINT(1) NOT NULL DEFAULT 1,
      created_by INT, created_at VARCHAR(19) NOT NULL,
      CONSTRAINT fk_assess_term FOREIGN KEY (term_id) REFERENCES terms(id),
      CONSTRAINT fk_assess_user FOREIGN KEY (created_by) REFERENCES users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS questions(
      id INT AUTO_INCREMENT PRIMARY KEY, assessment_id INT NOT NULL, position INT NOT NULL DEFAULT 0,
      qtype ENUM('mcq','tf','text') NOT NULL, prompt TEXT NOT NULL, choices TEXT, answer TEXT NOT NULL, points DOUBLE NOT NULL DEFAULT 1,
      CONSTRAINT fk_q_assess FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS attempts(
      id INT AUTO_INCREMENT PRIMARY KEY, assessment_id INT NOT NULL, student_id INT NOT NULL,
      started_at VARCHAR(19) NOT NULL, submitted_at VARCHAR(19), score DOUBLE, total DOUBLE, answers LONGTEXT,
      UNIQUE KEY uq_attempt (assessment_id, student_id),
      CONSTRAINT fk_att_assess FOREIGN KEY (assessment_id) REFERENCES assessments(id) ON DELETE CASCADE,
      CONSTRAINT fk_attempt_student FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS settings(
      setting_key VARCHAR(64) NOT NULL PRIMARY KEY, setting_value VARCHAR(255) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS login_attempts(
      id INT AUTO_INCREMENT PRIMARY KEY, ident VARCHAR(200) NOT NULL, attempted_at VARCHAR(19) NOT NULL, KEY idx_login_ident (ident)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS activity(
      id INT AUTO_INCREMENT PRIMARY KEY, user_id INT, action VARCHAR(100) NOT NULL, details TEXT, created_at VARCHAR(19) NOT NULL,
      CONSTRAINT fk_activity_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
]

DEFAULT_SETTINGS = {
    'school_name': 'Pila Senior High School',
    'school_year': '2025-2026',
    'late_after': '08:00',          # time-in at or after this time is "Late"
    'scan_gap_seconds': '0',        # optional minimum seconds between Time In and Time Out scans (0 = the 2nd scan is Time Out right away)
    'late_credit': '0.75',          # attendance credit of a late student (present = 1)
    'w_attendance': '10', 'w_recitation': '20', 'w_quiz': '30', 'w_exam': '40',
    'passing': '75',
    'at_risk_attendance': '80',
}

DEFAULT_TERMS = [  # editable under Settings > Terms
    ('1st Quarter', '2026-06-08', '2026-08-14'),
    ('2nd Quarter', '2026-08-17', '2026-10-30'),
    ('3rd Quarter', '2026-11-02', '2027-01-22'),
    ('4th Quarter', '2027-01-25', '2027-03-31'),
]


class Row(dict):
    """A result row: row['name'] like sqlite3.Row, and row[0] by position."""
    def __getitem__(self, k):
        if isinstance(k, int):
            return list(self.values())[k]
        return super().__getitem__(k)


class _Cursor(DictCursor):
    dict_type = Row


def _number(s):
    """MySQL returns SUM()/AVG() as DECIMAL: whole numbers become int, the rest float."""
    s = s.decode() if isinstance(s, (bytes, bytearray)) else s
    whole, _, frac = s.partition('.')
    return float(s) if frac.strip('0') else int(whole)


_CONV = dict(pymysql.converters.conversions)
_CONV[FIELD_TYPE.NEWDECIMAL] = _number
_CONV[FIELD_TYPE.DECIMAL] = _number


class Connection:
    """Thin wrapper that keeps the sqlite-style API the app uses: execute('... ? ...', args) -> cursor."""
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, args=()):
        cur = self.raw.cursor()
        args = tuple(args) if args is not None else ()
        if args:
            cur.execute(sql.replace('%', '%%').replace('?', '%s'), args)
        else:
            cur.execute(sql)
        return cur

    def executemany(self, sql, seq):
        cur = self.raw.cursor()
        cur.executemany(sql.replace('%', '%%').replace('?', '%s'), [tuple(r) for r in seq])
        return cur

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        try:
            self.raw.close()
        except Exception:
            pass


class DatabaseUnavailable(RuntimeError):
    pass


def _raw_connect(database=DB_NAME):
    try:
        return pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=database,
                               charset='utf8mb4', cursorclass=_Cursor, conv=_CONV, autocommit=False, connect_timeout=10)
    except pymysql.err.OperationalError as exc:
        code = exc.args[0] if exc.args else 0
        if code == 1049:
            raise
        hint = ('Start MySQL in the XAMPP Control Panel (click Start next to MySQL).' if code in (2002, 2003, 2006, 2013)
                else 'Check DB_USER and DB_PASSWORD in the .env file (XAMPP default: user root, empty password).' if code == 1045
                else str(exc))
        raise DatabaseUnavailable(f'Cannot connect to MySQL at {DB_HOST}:{DB_PORT} as "{DB_USER}". {hint}') from exc


def ensure_database():
    """Create the database itself (utf8mb4) when it does not exist yet, e.g. on a fresh XAMPP."""
    try:
        _raw_connect().close()
    except pymysql.err.OperationalError:
        raw = _raw_connect(database=None)
        raw.cursor().execute(f'CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
        raw.close()


def connect():
    return Connection(_raw_connect())


def init_db(con):
    """Create any missing tables, default settings, terms, the admin and (first run only) the student list."""
    for stmt in SCHEMA:
        con.execute(stmt)
    for k, v in DEFAULT_SETTINGS.items():
        con.execute('INSERT IGNORE INTO settings(setting_key,setting_value) VALUES(?,?)', (k, v))
    # older databases used a 60 s wait, which made a student's 2nd scan fail as "just timed in"
    con.execute("UPDATE settings SET setting_value='0' WHERE setting_key='scan_gap_seconds' AND setting_value IN ('60','5')")
    if not con.execute('SELECT 1 FROM terms').fetchone():
        con.executemany('INSERT INTO terms(name,start_date,end_date) VALUES(?,?,?)', DEFAULT_TERMS)
    ensure_admin(con)
    if not con.execute('SELECT 1 FROM students').fetchone():
        import_students_csv(con, SEED_CSV)
        ensure_adviser(con)
    con.commit()
    return con


def ensure_admin(con):
    if not con.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        pw = os.environ.get('ADMIN_PASSWORD', 'ChangeMe123!')
        con.execute('INSERT INTO users(username,password,role,full_name,must_change,created_at) VALUES(?,?,?,?,?,?)',
                    (os.environ.get('ADMIN_USERNAME', 'admin').lower(), generate_password_hash(pw), 'admin',
                     'System Administrator', 1, now().isoformat(timespec='seconds')))


def ensure_adviser(con):
    if not con.execute("SELECT 1 FROM users WHERE role='teacher'").fetchone():
        con.execute('INSERT INTO users(username,password,role,full_name,must_change,created_at) VALUES(?,?,?,?,?,?)',
                    ('ndelrosario', generate_password_hash('Teacher@2025'), 'teacher',
                     'Noriel D. Del Rosario', 1, now().isoformat(timespec='seconds')))


def get_settings(con):
    return {r['setting_key']: r['setting_value'] for r in con.execute('SELECT setting_key,setting_value FROM settings')}


def title_case(s):
    return ' '.join(w.capitalize() for w in (s or '').split())


def import_students_csv(con, path_or_file):
    """Import students from the CSV made from the DepEd workbook. Returns (added, skipped)."""
    added = skipped = 0
    fh = open(path_or_file, newline='', encoding='utf-8-sig') if isinstance(path_or_file, (str, Path)) else path_or_file
    rows = csv.DictReader(fh)
    for r in rows:
        r = {(k or '').strip().lower().replace(' ', '_'): (v or '').strip() for k, v in r.items()}
        lrn = ''.join(ch for ch in r.get('lrn', '') if ch.isdigit())
        if not lrn or not r.get('last_name') or not r.get('first_name'):
            skipped += 1
            continue
        if con.execute('SELECT 1 FROM students WHERE lrn=?', (lrn,)).fetchone() or \
           con.execute('SELECT 1 FROM users WHERE username=?', (lrn,)).fetchone():
            skipped += 1
            continue
        full = f"{title_case(r['first_name'])} {title_case(r.get('middle_name', '')[:1])}. {title_case(r['last_name'])}".replace(' . ', ' ')
        cur = con.execute('INSERT INTO users(username,password,role,full_name,must_change,created_at) VALUES(?,?,?,?,?,?)',
                          (lrn, generate_password_hash(lrn), 'student', full, 1, now().isoformat(timespec='seconds')))
        try:
            age = int(float(r.get('age') or 0)) or None
        except ValueError:
            age = None
        try:
            avg = float(r.get('grade10_average') or 0) or None
        except ValueError:
            avg = None
        bd = r.get('birthdate', '')
        if '/' in bd:
            try:
                bd = datetime.strptime(bd, '%m/%d/%Y').date().isoformat()
            except ValueError:
                pass
        con.execute('''INSERT INTO students(user_id,lrn,last_name,first_name,middle_name,sex,birthdate,age,address,
                       previous_school,grade10_avg,grade_level,strand,section,school_year,qr_token)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (cur.lastrowid, lrn, title_case(r['last_name']), title_case(r['first_name']), title_case(r.get('middle_name', '')),
                     r.get('sex', '').upper()[:1], bd, age, r.get('address', ''), title_case(r.get('previous_school', '')), avg,
                     r.get('grade_level', '11'), r.get('strand', 'HUMSS'), r.get('section', 'Magalang'),
                     r.get('school_year', '2025-2026'), secrets.token_urlsafe(18)))
        added += 1
    if isinstance(path_or_file, (str, Path)):
        fh.close()
    con.commit()
    return added, skipped


# ---------- period / term helpers ----------
def monday(d):
    return d - timedelta(days=d.weekday())


def resolve_period(con, period, anchor, start, end, term_id):
    """Return (start_date, end_date, label) for the attendance filter."""
    def parse(s, default):
        try:
            return date.fromisoformat(s)
        except (TypeError, ValueError):
            return default
    anchor_d = parse(anchor, today())
    if period == 'weekly':
        s = monday(anchor_d)
        return s, s + timedelta(days=6), f"Week of {s:%b %d, %Y}"
    if period == 'monthly':
        s = anchor_d.replace(day=1)
        e = (s.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        return s, e, f"{s:%B %Y}"
    if period == 'term':
        t = con.execute('SELECT * FROM terms WHERE id=?', (term_id,)).fetchone() or current_term(con)
        if t:
            return date.fromisoformat(t['start_date']), date.fromisoformat(t['end_date']), t['name']
    if period == 'custom':
        s = parse(start, anchor_d - timedelta(days=30))
        e = parse(end, anchor_d)
        if e < s:
            s, e = e, s
        return s, e, f"{s:%b %d, %Y} – {e:%b %d, %Y}"
    return anchor_d, anchor_d, f"{anchor_d:%A, %B %d, %Y}"


def current_term(con):
    t = today().isoformat()
    row = con.execute('SELECT * FROM terms WHERE start_date<=? AND end_date>=? ORDER BY start_date LIMIT 1', (t, t)).fetchone()
    return row or con.execute('SELECT * FROM terms ORDER BY end_date DESC LIMIT 1').fetchone()
