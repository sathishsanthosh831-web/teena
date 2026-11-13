import random

from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)
from sqlalchemy import func

from . import db
from .models import AptitudeResult, InterviewResult, ResumeResult, User
from .questions import APTITUDE, INTERVIEW, pick_aptitude, score_answer
from .resume import ROLE_SKILLS, analyze, extract_text

bp = Blueprint("main", __name__)


def current_user():
    uid = session.get("uid")
    return db.session.get(User, uid) if uid else None


def login_required(view):
    from functools import wraps

    @wraps(view)
    def wrapper(*a, **kw):
        if not current_user():
            flash("Enter your name first.")
            return redirect(url_for("main.index"))
        return view(*a, **kw)

    return wrapper


@bp.app_context_processor
def inject_user():
    return {"user": current_user(), "roles": list(ROLE_SKILLS)}


@bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:80]
        if not name:
            flash("Please enter a name.")
            return redirect(url_for("main.index"))
        u = User.query.filter_by(name=name).first()
        if not u:
            u = User(name=name)
            db.session.add(u)
            db.session.commit()
        session["uid"] = u.id
        return redirect(url_for("main.dashboard"))
    return render_template("index.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.index"))


@bp.route("/resume", methods=["GET", "POST"])
@login_required
def resume():
    result = None
    if request.method == "POST":
        role = request.form.get("role", "")
        f = request.files.get("file")
        text = request.form.get("text", "")
        try:
            if f and f.filename:
                text = extract_text(f.filename, f.read())
            if len(text.split()) < 20:
                flash("Upload a PDF/TXT or paste at least a few lines of resume text.")
            else:
                result = analyze(text, role)
                db.session.add(ResumeResult(user_id=current_user().id, role=role, score=result["score"]))
                db.session.commit()
        except ValueError as e:
            flash(str(e))
        except Exception:
            flash("Could not read that file. Try a text-based PDF or paste the text.")
    return render_template("resume.html", result=result)


@bp.route("/aptitude", methods=["GET", "POST"])
@login_required
def aptitude():
    if request.method == "POST":
        ids = session.get("apt_ids", [])
        if not ids:
            return redirect(url_for("main.aptitude"))
        review, correct = [], 0
        for qid in ids:
            q, opts, ans, why = APTITUDE[qid]
            chosen = request.form.get(f"q{qid}")
            ok = chosen == opts[ans]
            correct += ok
            review.append({"q": q, "chosen": chosen, "answer": opts[ans], "ok": ok, "why": why})
        db.session.add(AptitudeResult(user_id=current_user().id, correct=correct, total=len(ids)))
        db.session.commit()
        session.pop("apt_ids", None)
        return render_template("aptitude.html", review=review, correct=correct, total=len(ids))

    ids = pick_aptitude(5)
    session["apt_ids"] = ids
    quiz = []
    for qid in ids:
        q, opts, _, _ = APTITUDE[qid]
        shuffled = opts[:]
        random.shuffle(shuffled)
        quiz.append({"id": qid, "q": q, "opts": shuffled})
    return render_template("aptitude.html", quiz=quiz)


@bp.route("/interview", methods=["GET", "POST"])
@login_required
def interview():
    role = request.values.get("role", "python-developer")
    if role not in INTERVIEW:
        role = "python-developer"
    questions = INTERVIEW[role]
    result = None
    if request.method == "POST":
        try:
            idx = int(request.form.get("idx", 0))
            q, keywords = questions[idx]
        except (ValueError, IndexError):
            return redirect(url_for("main.interview", role=role))
        answer = request.form.get("answer", "")
        score, hit, feedback = score_answer(answer, keywords)
        db.session.add(InterviewResult(user_id=current_user().id, role=role, question=q[:300], score=score))
        db.session.commit()
        result = {"q": q, "score": score, "hit": hit, "feedback": feedback}
    idx = random.randrange(len(questions))
    return render_template("interview.html", role=role, idx=idx, question=questions[idx][0], result=result)


@bp.route("/dashboard")
@login_required
def dashboard():
    uid = current_user().id
    resumes = ResumeResult.query.filter_by(user_id=uid).order_by(ResumeResult.id.desc()).limit(5).all()
    apts = AptitudeResult.query.filter_by(user_id=uid).order_by(AptitudeResult.id.desc()).limit(5).all()
    ints = InterviewResult.query.filter_by(user_id=uid).order_by(InterviewResult.id.desc()).limit(5).all()
    stats = {
        "best_resume": db.session.query(func.max(ResumeResult.score)).filter_by(user_id=uid).scalar(),
        "avg_interview": db.session.query(func.avg(InterviewResult.score)).filter_by(user_id=uid).scalar(),
        "quizzes": AptitudeResult.query.filter_by(user_id=uid).count(),
    }
    return render_template("dashboard.html", resumes=resumes, apts=apts, ints=ints, stats=stats)
