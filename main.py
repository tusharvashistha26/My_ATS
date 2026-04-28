from fastapi import FastAPI, File, UploadFile, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from dotenv import load_dotenv
import uuid
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from starlette.middleware.sessions import SessionMiddleware
from ats_score import calculate_ats_score
from resume_generator import create_resume_docx
from openai import OpenAI
from pydantic import BaseModel
import os

load_dotenv()

# ---------------- OPENAI ----------------
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY not found")

client = OpenAI(api_key=api_key)

def improve_resume(text):
    prompt = f"""
    Improve the following resume bullet points.

    Make them:
    - professional
    - impactful
    - quantified
    - ATS friendly

    Resume:
    {text}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert resume writer."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content


# ---------------- DATABASE ----------------
from database import conn, cursor

# ---------------- PASSWORD ----------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password):
    return pwd_context.hash(password)

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


# ---------------- FOLDERS ----------------
UPLOAD_DIR = "uploads"
TEMP_DIR = "temp"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# ---------------- APP ----------------
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    SessionMiddleware,
    secret_key="SUPER_SECRET_KEY_123"
)

# ---------------- GOOGLE AUTH ----------------
config_data = {
    "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID"),
    "GOOGLE_CLIENT_SECRET": os.getenv("GOOGLE_CLIENT_SECRET")
}

config = Config(environ=config_data)
oauth = OAuth(config)

oauth.register(
    name="google",
    client_id=config("GOOGLE_CLIENT_ID"),
    client_secret=config("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"}
)


# ---------------- HOME ----------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = request.cookies.get("user")
    if not user:
        return RedirectResponse("/login")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})


# ---------------- AUTH ----------------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    email = form.get("email")
    password = form.get("password")

    cursor.execute("SELECT * FROM users WHERE email=?", (email,))
    user = cursor.fetchone()

    if not user:
        return HTMLResponse("User not found")

    if not verify_password(password, user[3]):
        return HTMLResponse("Wrong password")

    response = RedirectResponse("/", status_code=302)
    response.set_cookie("user", email, httponly=True)
    return response


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request})


@app.post("/signup")
async def signup(request: Request):
    form = await request.form()

    try:
        cursor.execute(
            "INSERT INTO users (name,email,password) VALUES (?,?,?)",
            (
                form.get("name"),
                form.get("email"),
                hash_password(form.get("password"))
            )
        )
        conn.commit()
    except:
        return HTMLResponse("User already exists")

    return RedirectResponse("/login", status_code=302)


@app.get("/logout")
def logout():
    response = RedirectResponse("/login")
    response.delete_cookie("user")
    return response


# ---------------- GOOGLE LOGIN ----------------
@app.get("/auth/google")
async def google_login(request: Request):
    redirect_uri = request.url_for("google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/google/callback")
async def google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user = token.get("userinfo")

    email = user["email"]
    name = user["name"]

    cursor.execute("SELECT * FROM users WHERE email=?", (email,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (name,email,password) VALUES (?,?,?)",
            (name, email, "google_login")
        )
        conn.commit()

    response = RedirectResponse("/")
    response.set_cookie("user", email)
    return response


# ---------------- GENERATE PAGE ----------------
@app.get("/generate", response_class=HTMLResponse)
def generate_page(request: Request):
    return templates.TemplateResponse("generate.html", {"request": request})

# ---------------- AI RESUME PAGE ----------------
@app.get("/ai-resume", response_class=HTMLResponse)
def ai_resume_page(request: Request):

    user = request.cookies.get("user")

    if not user:
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(
        "ai_resume.html",
        {
            "request": request,
            "user": user
        }
    )

# ---------------- DASHBOARD ----------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):

    user = request.cookies.get("user")

    if not user:
        return RedirectResponse("/login", status_code=302)

    # Fetch resumes
    cursor.execute(
        "SELECT file_name, created_at FROM resumes WHERE user_email=?",
        (user,)
    )
    resumes = cursor.fetchall()

    # Fetch ATS scores
    cursor.execute(
        "SELECT score, created_at FROM ats_history WHERE user_email=?",
        (user,)
    )
    ats_scores = cursor.fetchall()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "resumes": resumes,
            "ats_scores": ats_scores
        }
    )

# ---------------- CREATE RESUME ----------------
@app.post("/create-resume")
async def create_resume(request: Request):

    user = request.cookies.get("user")
    if not user:
        return RedirectResponse("/login")

    form = await request.form()

    resume_data = {
        "template": form.get("template"),
        "name": form.get("name"),
        "city": form.get("city"),
        "state": form.get("state"),
        "phone": form.get("phone"),
        "email": form.get("email"),
        "linkedin": form.get("linkedin"),
        "github": form.get("github"),
        "portfolio": form.get("portfolio"),

        "summary": form.get("summary"),
        "skills": form.get("skills"),
        "tools": form.get("tools"),

        # ✅ FIXED
        "achievements": form.get("achievements", "").split("\n"),
        "extracurricular_content": form.get("extracurricular"),
    }

    # EDUCATION
    resume_data["educations"] = [
        {
            "degree": d,
            "institution": i,
            "duration": du,
            "cgpa": c
        }
        for d, i, du, c in zip(
            form.getlist("education_degree[]"),
            form.getlist("education_institution[]"),
            form.getlist("education_duration[]"),
            form.getlist("education_cgpa[]")
        ) if d
    ]

    # EXPERIENCE
    resume_data["experiences"] = [
        {
            "title": t,
            "company": c,
            "duration": d,
            "description": desc
        }
        for t, c, d, desc in zip(
            form.getlist("exp_title[]"),
            form.getlist("exp_company[]"),
            form.getlist("exp_duration[]"),
            form.getlist("exp_description[]")
        ) if t
    ]

    # PROJECTS
    resume_data["projects"] = [
        {
            "title": t,
            "duration": d,
            "description": desc
        }
        for t, d, desc in zip(
            form.getlist("project_title[]"),
            form.getlist("project_duration[]"),
            form.getlist("project_description[]")
        ) if t
    ]

    # CERTIFICATES
    resume_data["certificates"] = [
        {
            "title": t,
            "issuer": i,
            "duration": d
        }
        for t, i, d in zip(
            form.getlist("certificate_title[]"),
            form.getlist("certificate_issuer[]"),
            form.getlist("certificate_duration[]")
        ) if t
    ]

    file_path = create_resume_docx(resume_data)
    file_name = os.path.basename(file_path)

    cursor.execute(
        "INSERT INTO resumes (user_email,file_name) VALUES (?,?)",
        (user, file_name)
    )
    conn.commit()

    return FileResponse(
        file_path,
        filename=file_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


# ---------------- ATS ----------------
@app.post("/check-ats", response_class=HTMLResponse)
async def check_ats(request: Request, file: UploadFile = File(...)):

    temp_path = os.path.join(TEMP_DIR, f"{uuid.uuid4().hex}.pdf")

    with open(temp_path, "wb") as f:
        f.write(await file.read())

    score, breakdown = calculate_ats_score(temp_path)

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "overall_score": score,
            "breakdown": breakdown
        }
    )