import io

import pytest

from app import create_app
from app.resume import analyze

SAMPLE = """Sathish Kumar sathish@example.com +91 98765 43210 github.com/sathish
Summary: Final year student. Education: B.E. Computer Science.
Skills: Python, Flask, SQL, Git, API, OOP, testing, linux.
Projects: Built an AI pitch deck generator used by 50+ users. Developed and deployed a
music player. Optimized API response time by 30%. Experience: Internship at a startup where I
implemented REST endpoints and automated reports. """ + "More detail about projects. " * 20


@pytest.fixture
def client():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    return app.test_client()


def login(c):
    return c.post("/", data={"name": "tester"}, follow_redirects=True)


def test_analyzer_scores_good_resume_high():
    r = analyze(SAMPLE, "python-developer")
    assert r["score"] >= 70
    assert "python" in r["matched"]


def test_analyzer_rejects_unknown_role():
    with pytest.raises(ValueError):
        analyze(SAMPLE, "astronaut")


def test_requires_login(client):
    assert client.get("/resume").status_code == 302


def test_pages_flow(client):
    assert b"Hi tester" in login(client).data
    r = client.post("/resume", data={"role": "python-developer", "text": SAMPLE})
    assert b"/100" in r.data
    r = client.post("/resume", data={"role": "python-developer", "file": (io.BytesIO(SAMPLE.encode()), "cv.txt")},
                    content_type="multipart/form-data")
    assert b"/100" in r.data
    r = client.post("/interview", data={"role": "python-developer", "idx": "0", "answer": "A list is mutable but a tuple is immutable and hashable. " * 5})
    assert b"/100" in r.data
    assert client.get("/dashboard").status_code == 200


def test_aptitude_roundtrip(client):
    login(client)
    page = client.get("/aptitude").data.decode()
    assert "Submit" in page
    r = client.post("/aptitude", data={})
    assert b"/5" in r.data
