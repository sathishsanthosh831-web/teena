"""Rule-based resume analyzer: ATS-style score plus concrete tips."""
import io
import re

ROLE_SKILLS = {
    "python-developer": ["python", "flask", "django", "sql", "git", "api", "oop", "pandas", "testing", "linux"],
    "web-developer": ["html", "css", "javascript", "react", "git", "responsive", "api", "node", "sql", "figma"],
    "data-analyst": ["sql", "excel", "python", "pandas", "tableau", "power bi", "statistics", "visualization", "etl", "dashboard"],
    "java-developer": ["java", "spring", "oop", "sql", "maven", "git", "rest", "junit", "hibernate", "microservices"],
}

SECTIONS = {
    "education": ["education", "academic"],
    "skills": ["skills", "technologies", "technical"],
    "projects": ["projects", "project"],
    "experience": ["experience", "internship", "work history"],
    "summary": ["summary", "objective", "profile"],
}

ACTION_VERBS = [
    "built", "developed", "designed", "implemented", "created", "led", "optimized",
    "automated", "deployed", "improved", "analyzed", "integrated", "launched",
]


def extract_text(filename, data):
    if filename.lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    return data.decode("utf-8", errors="ignore")


def analyze(text, role):
    if role not in ROLE_SKILLS:
        raise ValueError(f"unknown role: {role}")
    low = text.lower()
    tips = []
    score = 0

    # Contact info (15)
    has_email = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text))
    has_phone = bool(re.search(r"(\+?\d[\d\s-]{8,}\d)", text))
    has_link = "github.com" in low or "linkedin.com" in low
    contact = 5 * has_email + 5 * has_phone + 5 * has_link
    score += contact
    if not has_email:
        tips.append("Add a professional email address.")
    if not has_phone:
        tips.append("Add a phone number.")
    if not has_link:
        tips.append("Add your GitHub or LinkedIn link.")

    # Sections (25)
    found = [s for s, keys in SECTIONS.items() if any(k in low for k in keys)]
    score += 5 * len(found)
    for s in SECTIONS:
        if s not in found:
            tips.append(f"Add a clear '{s.title()}' section.")

    # Role skills (30)
    wanted = ROLE_SKILLS[role]
    matched = [s for s in wanted if s in low]
    missing = [s for s in wanted if s not in low]
    score += round(30 * len(matched) / len(wanted))
    if missing:
        tips.append("Skills to add if you have them: " + ", ".join(missing[:5]) + ".")

    # Action verbs (10)
    verbs = [v for v in ACTION_VERBS if v in low]
    score += min(10, len(verbs) * 2)
    if len(verbs) < 5:
        tips.append("Start bullet points with action verbs (built, developed, deployed...).")

    # Quantified impact (10)
    numbers = re.findall(r"\b\d+(?:\.\d+)?\s?(?:%|\+|x|users|ms|k\b)", low)
    score += min(10, len(numbers) * 3)
    if not numbers:
        tips.append("Add numbers to show impact (e.g. 'reduced load time by 30%').")

    # Length (10)
    words = len(text.split())
    if 200 <= words <= 800:
        score += 10
    elif words < 200:
        tips.append("Resume looks too short; add project and skill details.")
    else:
        score += 5
        tips.append("Resume is long; keep it to 1 page for freshers.")

    return {
        "score": min(100, score),
        "matched": matched,
        "missing": missing,
        "sections_found": found,
        "words": words,
        "tips": tips,
    }
