# Placement Prep Platform

Final year project: a web app that helps students prepare for campus placements.

## Features
- **Resume Analyzer**: upload a PDF/TXT or paste text, pick a target role, get an ATS-style score (0-100), matched and missing skills, and tips.
- **Aptitude Tests**: 5 random questions per set, instant score and explanations.
- **Mock Interview**: pick a role, answer a question, get a scored answer with feedback on missing key points.
- **Dashboard**: best resume score, average interview score, recent attempts (stored in PostgreSQL).

## Tech
Python, Flask, Flask-SQLAlchemy, PostgreSQL (SQLite for local dev), HTML/CSS, gunicorn. Deployed on Render.

## Run locally
```bash
pip install -r requirements.txt
python wsgi.py          # http://127.0.0.1:5000 (uses SQLite)
python -m pytest tests  # run tests
```

## Deploy on Render
1. Create a Render Postgres database and copy its **Internal Database URL**.
2. Create a Web Service from this repo (`render.yaml` is included).
3. Set `DATABASE_URL` to that URL. `SECRET_KEY` is generated automatically.

## Project layout
```
app/__init__.py    app factory, DB setup
app/models.py      User, ResumeResult, AptitudeResult, InterviewResult
app/resume.py      resume scoring logic
app/questions.py   aptitude + interview question banks, answer scoring
app/routes.py      pages and form handling
app/templates/     HTML pages
tests/             pytest tests
```

## Future work
- LLM-based interview feedback and resume rewriting
- Proper login (passwords / OAuth)
- More roles, company-specific question sets, coding round
