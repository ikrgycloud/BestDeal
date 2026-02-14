from fastapi import APIRouter
from pydantic import BaseModel
import uuid
from rabbitmq.publisher import publish_event
import os
import requests
import jwt
import datetime
from routes.database import AuthDatabase

router = APIRouter()

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    username: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str


class GoogleAuthRequest(BaseModel):
    code: str
    redirect_uri: str = None

@router.post("/register")
def register(payload: RegisterRequest):
    request_id = str(uuid.uuid4())

    publish_event(
        event_type="USER_REGISTER",
        data={
            "requestId": request_id,
            "username": payload.username,
            "email": payload.email,
            "password": payload.password
        }
    )

    return {
        "requestId": request_id,
        "status": "PROCESSING",
        "message": "Registration request queued"
    }

@router.post("/login")
def login(payload: LoginRequest):
    request_id = str(uuid.uuid4())

    publish_event(
        event_type="USER_LOGIN",
        data={
            "requestId": request_id,
            "username": payload.username,
            "password": payload.password
        }
    )

    return {
        "requestId": request_id,
        "status": "PROCESSING",
        "message": "Login request queued"
    }

@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    request_id = str(uuid.uuid4())

    publish_event(
        event_type="FORGOT_PASSWORD",
        data={
            "requestId": request_id,
            "email": payload.email
        }
    )

    return {
        "requestId": request_id,
        "status": "PROCESSING",
        "message": "OTP request queued"
    }

@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest):
    request_id = str(uuid.uuid4())

    publish_event(
        event_type="RESET_PASSWORD",
        data={
            "requestId": request_id,
            "email": payload.email,
            "otp": payload.otp,
            "new_password": payload.new_password
        }
    )

    return {
        "requestId": request_id,
        "status": "PROCESSING",
        "message": "Password reset request queued"
    }


@router.post("/google")
def google_login(payload: GoogleAuthRequest):
    """Exchange Google auth code for tokens and store user email in DB."""
    # Load Google OAuth2 credentials from env
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    # Use redirect_uri from payload if provided, else from env
    redirect_uri = payload.redirect_uri or os.getenv("GOOGLE_REDIRECT_URI")

    if not (client_id and client_secret and redirect_uri):
        return {"status": "ERROR", "message": "Google OAuth not configured on server"}

    # Exchange code for access token
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": payload.code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }

    try:
        resp = requests.post(token_url, data=data, timeout=10)
        resp.raise_for_status()
        token_data = resp.json()
    except Exception as e:
        return {"status": "ERROR", "message": f"Token exchange failed: {e}"}

    access_token = token_data.get("access_token")
    if not access_token:
        return {"status": "ERROR", "message": "No access token from Google"}

    # Fetch user info
    try:
        userinfo_resp = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        userinfo_resp.raise_for_status()
        profile = userinfo_resp.json()
    except Exception as e:
        return {"status": "ERROR", "message": f"Failed to fetch user info: {e}"}

    email = profile.get("email")
    name = profile.get("name") or profile.get("given_name") or ""

    if not email:
        return {"status": "ERROR", "message": "Google account has no email"}

    # Store or update user in DB
    db = AuthDatabase()
    # Ensure DB/tables exist
    db.setup_database()

    exists = db.check_email_exists(email)
    if not exists:
        # Create a username from email prefix and random suffix to avoid collisions
        username = email.split("@")[0]
        username = f"{username}_{uuid.uuid4().hex[:6]}"
        # generate a random password (user will login via Google)
        random_password = uuid.uuid4().hex
        reg = db.register_user(username=username, email=email, password=random_password)
        if reg.get("status") != "SUCCESS":
            return {"status": "ERROR", "message": reg.get("message", "Failed to create user")}

    # Fetch user id from database
    conn = db.get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, username FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
    finally:
        conn.close()

    if not user:
        return {"status": "ERROR", "message": "Failed to retrieve user after creation"}

    # Create JWT token for the mobile client
    SECRET_KEY = os.getenv("SECRET_KEY", "your_secret_key")
    payload_token = {
        "user_id": str(user.get("id")),
        "email": email,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24),
        "iat": datetime.datetime.utcnow(),
    }
    token = jwt.encode(payload_token, SECRET_KEY, algorithm="HS256")

    return {"status": "SUCCESS", "message": "Google login successful", "email": email, "name": name, "token": token}