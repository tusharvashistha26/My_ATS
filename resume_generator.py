from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import os
import uuid


def create_resume_docx(data, out_dir="uploads"):

    doc = Document()

    # ---------------- TEMPLATE ----------------
    template = data.get("template", "modern")

    # ---------------- GLOBAL STYLE ----------------
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(11)

    # ---------------- HEADER ----------------
    header = doc.add_paragraph()
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = header.add_run(data.get("name", ""))
    run.bold = True
    run.font.size = Pt(16)

    location = doc.add_paragraph()
    location.alignment = WD_ALIGN_PARAGRAPH.CENTER
    location.add_run(f"{data.get('city','')}, {data.get('state','')}")

    contact = doc.add_paragraph()
    contact.alignment = WD_ALIGN_PARAGRAPH.CENTER

    contact_items = [
        data.get("phone", ""),
        data.get("email", ""),
        data.get("linkedin", ""),
        data.get("github", ""),
        data.get("portfolio", "")
    ]

    contact.add_run(" | ".join([i for i in contact_items if i]))

    # ---------------- EDUCATION ----------------
    if data.get("educations"):
        doc.add_heading("Education", level=2)

        for edu in data["educations"]:
            p = doc.add_paragraph()
            p.add_run(f"{edu['degree']} ({edu['duration']})").bold = True

            p2 = doc.add_paragraph(edu["institution"])

            if edu.get("cgpa"):
                p2.add_run(f" | CGPA: {edu['cgpa']}")

    # ---------------- SKILLS ----------------
    if data.get("skills") or data.get("tools"):
        doc.add_heading("Technical Skills", level=2)

        if data.get("tools"):
            doc.add_paragraph(f"Tools: {data['tools']}")

        if data.get("skills"):
            doc.add_paragraph(f"Skills: {data['skills']}")

    # ---------------- INTERNSHIPS ----------------
    if data.get("internships"):
        doc.add_heading("Internships", level=2)

        for i in data["internships"]:
            doc.add_paragraph(
                f"{i['title']} ({i['duration']})"
            ).runs[0].bold = True

            for line in i["description"].split("\n"):
                if line.strip():
                    doc.add_paragraph(line.strip(), style="List Bullet")

    # ---------------- PROJECTS ----------------
    if data.get("projects"):
        doc.add_heading("Projects", level=2)

        for p in data["projects"]:
            doc.add_paragraph(
                f"{p['title']} ({p['duration']})"
            ).runs[0].bold = True

            for line in p["description"].split("\n"):
                if line.strip():
                    doc.add_paragraph(line.strip(), style="List Bullet")

    # ---------------- CERTIFICATES ----------------
    if data.get("certificates"):
        doc.add_heading("Certificates", level=2)

        for c in data["certificates"]:
            doc.add_paragraph(
                f"{c['title']} ({c['duration']})"
            ).runs[0].bold = True

    # ---------------- EXTRA ----------------
    if data.get("extracurricular_content"):
        doc.add_heading("Extracurricular", level=2)

        for line in data["extracurricular_content"].split("\n"):
            if line.strip():
                doc.add_paragraph(line.strip(), style="List Bullet")

    # ---------------- SAVE ----------------
    os.makedirs(out_dir, exist_ok=True)

    filename = f"{uuid.uuid4().hex}_Resume.docx"
    path = os.path.join(out_dir, filename)

    doc.save(path)

    return path