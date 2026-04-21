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
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise ValueError("OPENAI_API_KEY not found. Check your .env or environment variables.")

client = OpenAI(api_key=api_key)

def improve_resume(text):

    prompt = f"""
    Improve the following resume bullet points.

    Make them:
    - professional
    - impactful
    - quantified if possible
    - ATS friendly

    Resume content:
    {text}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system","content":"You are an expert resume writer."},
            {"role":"user","content":prompt}
        ]
    )

    return response.choices[0].message.content

# ---------------- DATABASE ----------------
from database import conn, cursor

# ---------------- PASSWORD HASHING ----------------
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

# ---------------- APP INIT ----------------
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    SessionMiddleware,
    secret_key="SUPER_SECRET_KEY_123"
)

config_data = {
    "GOOGLE_CLIENT_ID": "YOUR_GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET": "YOUR_GOOGLE_CLIENT_SECRET"
}

config = Config(environ=config_data)

oauth = OAuth(config)

oauth.register(
    name="google",
    client_id=config("GOOGLE_CLIENT_ID"),
    client_secret=config("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={
        "scope": "openid email profile"
    }
)

@app.post("/ai-improve")
async def ai_improve(resume: UploadFile = File(...)):

    content = await resume.read()
    text = content.decode("utf-8", errors="ignore")

    improved = improve_resume(text)

    return {"result": improved}


class ResumeText(BaseModel):
    text: str


@app.post("/ai-improve-text")
def ai_improve_text(data: ResumeText):

    improved = improve_resume(data.text)

    return {"result": improved}

@app.get("/ai-resume", response_class=HTMLResponse)
def ai_resume_page(request: Request):
    return templates.TemplateResponse("ai_resume.html", {"request": request})

# ---------------- HOME ----------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):

    user = request.cookies.get("user")

    if not user:
        return RedirectResponse("/login")

    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user
    })

# ---------------- SIGNUP ----------------
@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):

    user = request.cookies.get("user")

    if user:
        return RedirectResponse("/dashboard", status_code=302)

    return templates.TemplateResponse("signup.html", {"request": request})


@app.post("/signup")
async def signup(request: Request):

    form = await request.form()

    name = form.get("name")
    email = form.get("email")
    password = hash_password(form.get("password"))

    try:
        cursor.execute(
            "INSERT INTO users (name,email,password) VALUES (?,?,?)",
            (name, email, password)
        )
        conn.commit()

    except:
        return HTMLResponse("User already exists")

    return RedirectResponse("/login", status_code=302)

# ---------------- LOGIN ----------------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):

    user = request.cookies.get("user")

    if user:
        return RedirectResponse("/", status_code=302)

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

    response.set_cookie(
        key="user",
        value=email,
        httponly=True,
        samesite="lax"
    )

    return response

# ---------------- LOGOUT ----------------
@app.get("/logout")
def logout():

    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("user")

    return response

# ---------------- Google route --------@app.get("/auth/google")
@app.get("/auth/google")
async def google_login(request: Request):

    redirect_uri = request.url_for("google_callback")

    return await oauth.google.authorize_redirect(request, redirect_uri)

#--------- Google callback route ---------
@app.get("/auth/google/callback")
async def google_callback(request: Request):

    token = await oauth.google.authorize_access_token(request)

    user = token.get("userinfo")

    email = user["email"]
    name = user["name"]

    # check if user exists
    cursor.execute("SELECT * FROM users WHERE email=?", (email,))
    existing = cursor.fetchone()

    if not existing:
        cursor.execute(
            "INSERT INTO users (name,email,password) VALUES (?,?,?)",
            (name, email, "google_login")
        )
        conn.commit()

    response = RedirectResponse("/")
    response.set_cookie("user", email)

    return response

# ---------------- DASHBOARD ----------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):

    user = request.cookies.get("user")

    if not user:
        return RedirectResponse("/login", status_code=302)

    cursor.execute(
        "SELECT file_name, created_at FROM resumes WHERE user_email=?",
        (user,)
    )
    resumes = cursor.fetchall()

    cursor.execute(
        "SELECT score, created_at FROM ats_history WHERE user_email=?",
        (user,)
    )
    ats_scores = cursor.fetchall()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "resumes": resumes,
            "ats_scores": ats_scores,
            "user": user
        }
    )

# ---------------- GENERATE FORM ----------------
@app.get("/generate", response_class=HTMLResponse)
def generate_form(request: Request):

    user = request.cookies.get("user")

    if not user:
        return RedirectResponse("/login", status_code=302)

    return templates.TemplateResponse(
        "generate.html",
        {
            "request": request,
            "user": user
        }
    )

# ---------------- CREATE RESUME ----------------
@app.post("/create-resume")
async def generate_resume(request: Request):

    user = request.cookies.get("user")

    if not user:
        return RedirectResponse("/login", status_code=302)

    form = await request.form()

    # -------- BASIC INFO --------
    resume_data = {
        "name": form.get("name"),
        "city": form.get("city"),
        "state": form.get("state"),
        "phone": form.get("phone"),
        "email": form.get("email"),
        "linkedin": form.get("linkedin"),
        "github": form.get("github"),
        "portfolio": form.get("portfolio"),
        "skills": form.get("skills"),
        "tools": form.get("tools"),
        "achievement": form.get("achievement"),
    }

    # -------- EDUCATION --------
    degrees = form.getlist("education_degree[]")
    institutions = form.getlist("education_institution[]")
    durations = form.getlist("education_duration[]")
    cgpas = form.getlist("education_cgpa[]")

    educations = []
    for i in range(len(degrees)):
        if degrees[i]:
            educations.append({
                "degree": degrees[i],
                "institution": institutions[i],
                "duration": durations[i],
                "cgpa": cgpas[i]
            })

    resume_data["educations"] = educations

    # -------- INTERNSHIPS --------
    titles = form.getlist("internship_title[]")
    durations = form.getlist("internship_duration[]")
    descriptions = form.getlist("internship_description[]")

    internships = []
    for i in range(len(titles)):
        if titles[i]:
            internships.append({
                "title": titles[i],
                "duration": durations[i],
                "description": descriptions[i]
            })

    resume_data["internships"] = internships

    # -------- PROJECTS --------
    titles = form.getlist("project_title[]")
    durations = form.getlist("project_duration[]")
    descriptions = form.getlist("project_description[]")

    projects = []
    for i in range(len(titles)):
        if titles[i]:
            projects.append({
                "title": titles[i],
                "duration": durations[i],
                "description": descriptions[i]
            })

    resume_data["projects"] = projects

    # -------- CERTIFICATES --------
    titles = form.getlist("certificate_title[]")
    durations = form.getlist("certificate_duration[]")

    certificates = []
    for i in range(len(titles)):
        if titles[i]:
            certificates.append({
                "title": titles[i],
                "duration": durations[i]
            })

    resume_data["certificates"] = certificates

    # -------- EXTRACURRICULAR --------
    resume_data["extracurricular_content"] = form.get("extracurricular_content")

    # -------- GENERATE FILE --------
    file_path = create_resume_docx(resume_data, out_dir=UPLOAD_DIR)
    file_name = os.path.basename(file_path)

    cursor.execute(
        "INSERT INTO resumes (user_email,file_name) VALUES (?,?)",
        (user, file_name)
    )
    conn.commit()

    return FileResponse(
        path=file_path,
        filename=file_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

# ---------------- ATS CHECK ----------------
@app.post("/check-ats", response_class=HTMLResponse)
async def check_ats(request: Request, file: UploadFile = File(...)):

    user = request.cookies.get("user")

    file_id = f"{uuid.uuid4().hex}_{file.filename}"
    temp_path = os.path.join(TEMP_DIR, file_id)

    with open(temp_path, "wb") as f:
        content = await file.read()
        f.write(content)

    overall_score, breakdown = calculate_ats_score(temp_path)

    if user:
        cursor.execute(
            "INSERT INTO ats_history (user_email,score) VALUES (?,?)",
            (user, overall_score)
        )
        conn.commit()

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "overall_score": overall_score,
            "breakdown": breakdown
        }
    )

# ---------------- DOWNLOAD ----------------
@app.get("/download/{file_name}")
def download(file_name: str):

    path = os.path.join(UPLOAD_DIR, file_name)

    if os.path.exists(path):
        return FileResponse(path, filename=file_name)

    return RedirectResponse("/", status_code=302)