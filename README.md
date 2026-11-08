# Pila Senior High School – Attendance Monitoring System

Flask + MySQL (XAMPP) web app with QR attendance, quizzes and exams, automatic grading, term-based grades, reports and real-time analytics. Works on desktop and phones.

## Run it with XAMPP (Windows)

The app is a Python (Flask) web app that stores everything in **MySQL**, which XAMPP provides. XAMPP's Apache is not needed; you use XAMPP for MySQL and phpMyAdmin.

1. Install **Python 3.10+** (tick *Add Python to PATH*) and **XAMPP**.
2. Open the **XAMPP Control Panel** and click **Start** next to **MySQL**.
3. Create the database (pick one):
   - **Easiest (phpMyAdmin):** open `http://localhost/phpmyadmin` → **Import** → choose `database/attendance_monitoring.sql` → **Import**. This creates the `attendance_monitoring` database with the 27 HUMSS 11 – Magalang students, the accounts and the settings.
   - **Or let the app do it:** skip this step. On first start the app creates the database, tables, admin and student list by itself.
4. Copy `.env.example` to `.env`. The defaults match XAMPP (`DB_USER=root`, empty `DB_PASSWORD`, `DB_NAME=attendance_monitoring`). Change them only if you set a MySQL password.
5. Double-click **`start.bat`** (or run `pip install -r requirements.txt` then `python app.py`). It prints two addresses:
   - **This computer:** `http://localhost:5000`
   - **Phones & tablets on the same Wi-Fi:** `https://<computer-IP>:5443` (this is the one where the **camera works**)
6. The first time a phone opens the https address it shows a certificate warning (the certificate is created automatically for this computer). Tap **Advanced → Proceed / Visit this website**.

If the app says *Cannot connect to MySQL*, MySQL is not started in XAMPP (or the port/password in `.env` differs). Other optional `.env` values: `SECRET_KEY`, `HTTPS=0` to turn local HTTPS off, `TRUST_PROXY=1` behind an HTTPS reverse proxy.

**Database:** MySQL/MariaDB database `attendance_monitoring` (InnoDB, utf8mb4). Back it up from phpMyAdmin → *Export*, or with XAMPP's `mysqldump`. Dates and times are stored as ISO text (`2026-10-17`, `07:45:00`) just like before.

## Sign-in

The home page only offers **Student** and **Teacher**. Each has its own sign-in page (`/student/login`, `/teacher/login`). The administrator is not listed; the admin signs in on the Teacher page and gets full access automatically.

| Account | Username | First password |
|---|---|---|
| Administrator | `admin` | `ChangeMe123!` |
| Teacher (adviser) | `ndelrosario` | `Teacher@2025` |
| Students | their 12-digit LRN | their LRN |

Every account must choose a new password at first sign-in. Admins add or reset staff accounts under *Staff Accounts*; teachers can reset a student's password to the LRN under *Students*. No demo or test accounts exist.

## What is included

- **Accounts** – Admin/Teacher (students, attendance, quizzes, exams, grades) and Student (own attendance, scores, grades).
- **QR attendance** – Teacher opens *QR Scanner* (phone camera, USB/Bluetooth scanner, or type the LRN). First scan = Time In, next scan = Time Out. Time in at or after the *Late after* time (default 08:00) is Late. Students show their code from *My QR Code*; teachers can print all cards.
- **Quizzes & exams** – Multiple choice, True/False and Identification questions, time limit, open/due dates, publish switch. Students take them online; scores are calculated on submit.
- **Term grades** – Attendance + Recitation + Quiz + Exam, weights set in *Settings* (default 10/20/30/40, passing 75). Components without data yet are left out and weights rescale. Late counts 75% attendance credit (changeable).
- **Attendance filters** – Daily, Weekly, Monthly, Term, or Custom date range with dropdowns, plus a per-student summary and daily log.
- **Analytics** – Today's present/late/absent, attendance trend, breakdown, grade distribution, student performance, quiz averages, students needing attention. Updates itself every 5 seconds (and instantly when a scan is made in another tab), with animated charts and counters; a green “Live” dot turns orange if the connection drops.
- **Reports** – CSV for attendance summary/log, term grades, quiz & exam results, recitation, student list.

## Notes

- **Terms**: *Settings → Terms* holds four quarters whose dates are placeholders (2026-06 to 2027-03). Edit them to your school calendar; they decide which records count toward each term.
- **Camera scanner**: browsers allow the camera only on `https://` or `http://localhost`. The app serves HTTPS for you on port 5443 (see *Run it*). The scanner lets you pick the front/back camera, turn on the flashlight where supported, and falls back to **Scan from photo** (works even without a live camera) plus the manual/USB field. Its library loads from cdnjs (jsDelivr as backup), so the scanner page needs internet once. If the camera is blocked, the page explains why in plain words (permission, busy camera, no camera, or insecure address).
- **Preview analytics**: `python seed_demo.py` adds sample attendance, recitation, quizzes and exam scores; `python seed_demo.py --clear` removes them. Use a test copy of the database.
- **Import more students**: *Students → Import* with a CSV shaped like `data/students_HUMSS11_Magalang.csv`.
- Student data is personal information of minors. Keep the database private and use HTTPS when hosting.

## Files

`app.py` routes · `core.py` MySQL connection/schema/settings/import · `database/attendance_monitoring.sql` ready-to-import database · `grading.py` attendance and grade formulas · `templates/` pages · `static/css/style.css` theme · `static/js/` charts and scanner · `static/images/` crest, favicons, login background · `data/` student CSV and original workbook.
