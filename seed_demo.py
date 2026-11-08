"""Optional: fill the database with SAMPLE attendance, recitation, quizzes and exam results
so you can preview the analytics. Run it only on a test copy:   python seed_demo.py
Remove the sample data again with:                              python seed_demo.py --clear
"""
import json
import random
import sys
from datetime import date, timedelta

import core
import grading

MARK = '[Sample] '


def main():
    con = core.connect()
    core.init_db(con)
    if '--clear' in sys.argv:
        con.execute("DELETE FROM assessments WHERE title LIKE ?", (MARK + '%',))
        con.execute("DELETE FROM attendance WHERE source='sample'")
        con.execute("DELETE FROM recitation WHERE topic LIKE ?", (MARK + '%',))
        con.commit()
        print('Sample data removed.')
        return
    rnd = random.Random(7)
    term = core.current_term(con)
    start, end = date.fromisoformat(term['start_date']), min(date.fromisoformat(term['end_date']), core.today() - timedelta(days=1))
    students = con.execute('SELECT id FROM students').fetchall()
    habit = {s['id']: rnd.choice([.98, .95, .92, .88, .8, .7]) for s in students}
    d, days = start, []
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    for d in days:
        for s in students:
            r = rnd.random()
            if r < habit[s['id']]:
                late = rnd.random() < .12
                h, m = (8, rnd.randint(1, 40)) if late else (7, rnd.randint(0, 29))
                con.execute('INSERT IGNORE INTO attendance(student_id,day,time_in,time_out,status,source) VALUES(?,?,?,?,?,?)',
                            (s['id'], d.isoformat(), f'{h:02d}:{m:02d}:00', f'{rnd.randint(16, 17)}:{rnd.randint(0, 59):02d}:00', 'Late' if late else 'Present', 'sample'))
            elif rnd.random() < .15:
                con.execute('INSERT IGNORE INTO attendance(student_id,day,status,remarks,source) VALUES(?,?,?,?,?)',
                            (s['id'], d.isoformat(), 'Excused', 'Sample: excused', 'sample'))
    for d in days[::3]:
        for s in students:
            con.execute('INSERT IGNORE INTO recitation(student_id,day,score,max_score,topic) VALUES(?,?,?,?,?)',
                        (s['id'], d.isoformat(), rnd.randint(5, 10), 10, MARK + 'Oral recitation'))
    banks = [
        ('quiz', 'Quiz 1: Introduction to Humanities', 10), ('quiz', 'Quiz 2: Social Sciences Basics', 10),
        ('exam', 'Midterm Examination', 20)]
    for kind, title, n in banks:
        cur = con.execute('''INSERT INTO assessments(kind,title,instructions,term_id,time_limit,due_at,published,show_answers,created_at)
                             VALUES(?,?,?,?,?,?,1,1,?)''', (kind, MARK + title, 'Sample assessment for previewing analytics.', term['id'], 20,
                                                           (core.now() - timedelta(days=3)).isoformat(timespec='minutes'), core.now().isoformat(timespec='seconds')))
        aid = cur.lastrowid
        for i in range(1, 6):
            if i <= 3:
                con.execute('INSERT INTO questions(assessment_id,position,qtype,prompt,choices,answer,points) VALUES(?,?,?,?,?,?,?)',
                            (aid, i, 'mcq', f'Sample multiple-choice question {i}?', json.dumps(['Option A', 'Option B', 'Option C', 'Option D']), 'Option B', 2))
            elif i == 4:
                con.execute('INSERT INTO questions(assessment_id,position,qtype,prompt,answer,points) VALUES(?,?,?,?,?,?)', (aid, i, 'tf', 'Sample true or false statement.', 'True', 2))
            else:
                con.execute('INSERT INTO questions(assessment_id,position,qtype,prompt,answer,points) VALUES(?,?,?,?,?,?)', (aid, i, 'text', 'Sample identification question.', 'answer|Answer', 2))
        for s in students:
            if rnd.random() < .9:
                total = 10
                score = max(0, min(total, round(rnd.gauss(8 if kind == 'quiz' else 7.5, 1.6))))
                con.execute('INSERT INTO attempts(assessment_id,student_id,started_at,submitted_at,score,total,answers) VALUES(?,?,?,?,?,?,?)',
                            (aid, s['id'], (core.now() - timedelta(days=4)).isoformat(timespec='seconds'), (core.now() - timedelta(days=4)).isoformat(timespec='seconds'), score, total, '{}'))
    con.commit()
    print(f'Sample data added for {term["name"]} ({len(days)} class days). Remove it with: python seed_demo.py --clear')


if __name__ == '__main__':
    main()
