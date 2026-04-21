import fitz
import docx
import re
from collections import Counter


# ---------------- TEXT EXTRACTION ----------------

def extract_text_from_pdf(path):
    try:
        text = ""
        with fitz.open(path) as doc:
            for page in doc:
                text += page.get_text("text")
        return text
    except Exception as e:
        print("PDF Error:", e)
        return ""


def extract_text_from_docx(path):
    try:
        doc = docx.Document(path)
        return "\n".join([p.text for p in doc.paragraphs])
    except:
        return ""


def extract_text(path):
    path_lower = path.lower()

    if path_lower.endswith(".pdf"):
        return extract_text_from_pdf(path)

    if path_lower.endswith((".docx", ".doc")):
        return extract_text_from_docx(path)

    return ""


# ---------------- CONSTANTS ----------------

TECH_KEYWORDS = {
    "python","java","c++","c#","javascript","sql",
    "aws","azure","docker","kubernetes","linux",
    "django","flask","fastapi","react","node",
    "machine learning","data science","api"
}

ACTION_VERBS = {
    "developed","designed","implemented","built",
    "optimized","created","led","managed",
    "analyzed","improved","engineered"
}

SOFT_SKILLS = {
    "communication","leadership","teamwork",
    "problem solving","adaptability","collaboration"
}

ESSENTIAL_SECTIONS = [
    "education",
    "experience",
    "skills",
    "projects"
]


# ---------------- CONTENT CHECKS ----------------

def ats_parse_rate(text):
    if len(text.strip()) < 200:
        return 50
    if len(text.split()) < 300:
        return 70
    return 100


def quantify_impact_score(text):
    numbers = re.findall(r'\b\d+%?|\$\d+|\b\d+\b', text)
    return min(len(numbers) * 5, 100)


def repetition_score(text):
    words = text.lower().split()
    counter = Counter(words)
    repeated = sum(1 for w, c in counter.items() if c > 8 and len(w) > 4)
    penalty = min(repeated * 5, 30)
    return max(100 - penalty, 50)


def grammar_score(text):
    sentences = re.split(r'[.!?]', text)
    if len(sentences) < 5:
        return 60
    return 90


# ---------------- SECTION CHECKS ----------------

def essential_sections_score(text):
    score = 0
    text_lower = text.lower()
    for sec in ESSENTIAL_SECTIONS:
        if sec in text_lower:
            score += 25
    return score


def contact_info_score(text):
    email = re.search(r'\S+@\S+', text)
    phone = re.search(r'\b\d{10}\b', text)
    score = 0
    if email:
        score += 50
    if phone:
        score += 50
    return score


# ---------------- ATS ESSENTIALS ----------------

def file_format_score(path):
    if path.lower().endswith((".pdf", ".docx")):
        return 100
    return 60


def design_score(text):
    if len(text.split()) < 150:
        return 60
    return 90


def email_quality_score(text):
    email = re.search(r'\S+@\S+', text)
    if not email:
        return 0
    if any(x in email.group().lower() for x in ["cool", "ninja", "rockstar"]):
        return 50
    return 100


def hyperlink_header_score(text):
    if "http" in text[:300]:
        return 100
    return 70


# ---------------- TAILORING ----------------

def hard_skill_score(text):
    found = [kw for kw in TECH_KEYWORDS if kw in text.lower()]
    return min(len(found) * 10, 100)


def action_verb_score(text):
    found = [v for v in ACTION_VERBS if v in text.lower()]
    return min(len(found) * 10, 100)


def soft_skill_score(text):
    found = [s for s in SOFT_SKILLS if s in text.lower()]
    return min(len(found) * 15, 100)


# ---------------- MAIN FUNCTION ----------------

def calculate_ats_score(resume_path):

    resume_text = extract_text(resume_path)

    content_scores = {
        "ATS Parse Rate": ats_parse_rate(resume_text),
        "Quantifying Impact": quantify_impact_score(resume_text),
        "Repetition": repetition_score(resume_text),
        "Spelling & Grammar": grammar_score(resume_text)
    }

    section_scores = {
        "Essential Sections": essential_sections_score(resume_text),
        "Contact Information": contact_info_score(resume_text)
    }

    ats_essentials = {
        "File Format & Size": file_format_score(resume_path),
        "Design": design_score(resume_text),
        "Email Address": email_quality_score(resume_text),
        "Hyperlink in Header": hyperlink_header_score(resume_text)
    }

    tailoring_scores = {
        "Hard Skills": hard_skill_score(resume_text),
        "Soft Skills": soft_skill_score(resume_text),
        "Action Verbs": action_verb_score(resume_text)
    }

    overall_score = round(
        (
            sum(content_scores.values()) +
            sum(section_scores.values()) +
            sum(ats_essentials.values()) +
            sum(tailoring_scores.values())
        ) / (
            len(content_scores) +
            len(section_scores) +
            len(ats_essentials) +
            len(tailoring_scores)
        ), 2
    )

    return overall_score, {
        "Content": content_scores,
        "Sections": section_scores,
        "ATS Essentials": ats_essentials,
        "Tailoring": tailoring_scores
    }