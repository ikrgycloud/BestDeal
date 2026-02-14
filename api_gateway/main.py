from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from routes.products import router as product_router
from routes.auth import router as auth_router
from routes.database import AuthDatabase
import os

app = FastAPI(title="Unified Commerce API Gateway")

# Default local origins
origins = ["*"]

# Add origins from environment variable (for AWS/Production)
if os.getenv("CORS_ORIGINS"):
    origins.extend(os.getenv("CORS_ORIGINS").split(","))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class EmailCheck(BaseModel):
    email: str

class LoginRequest(BaseModel):
    email: str
    password: str

db = AuthDatabase()

@app.post("/auth/check-email")
async def check_email(data: EmailCheck):
    exists = db.check_email_exists(data.email)
    return {"exists": exists}

@app.post("/auth/login")
async def login(data: LoginRequest):
    print(f"Login request received for: {data.email}")
    result = db.verify_user(data.email, data.password)
    if result["status"] == "ERROR":
        raise HTTPException(status_code=401, detail=result["message"])
    return result

@app.get("/logs", response_class=PlainTextResponse)
async def get_logs():
    log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'log.txt')
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "Log file not found."

# Include routers after defining custom overrides to ensure precedence
app.include_router(product_router, prefix="/products")
app.include_router(auth_router, prefix="/auth")

@app.get("/")
def health():
    return {"status": "API Gateway running"}
