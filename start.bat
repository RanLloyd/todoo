@echo off
rem Starts the Attendance Monitoring System (make sure MySQL is running in the XAMPP Control Panel first).
cd /d "%~dp0"
if not exist venv ( py -3 -m venv venv )
call venv\Scripts\activate
pip install -r requirements.txt
if not exist .env copy .env.example .env >nul
python app.py
pause
