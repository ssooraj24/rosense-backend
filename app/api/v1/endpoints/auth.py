from fastapi import APIRouter, HTTPException, Depends, Header, status
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.core.supabase_client import get_supabase_client, get_supabase_admin_client

router = APIRouter()

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str

@router.post("/login", response_model=TokenResponse)
async def login_user(credentials: LoginRequest):
    """
    Authenticate user via Supabase Auth and return session JWT.
    """
    try:
        supabase = get_supabase_client()
        response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })
        
        if not response.session or not response.user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        return TokenResponse(
            access_token=response.session.access_token,
            user_id=response.user.id,
            email=response.user.email
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/me")
async def get_current_user_profile(authorization: Optional[str] = Header(None)):
    """
    Returns authenticated user's profile, tenant org, and role metadata.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.split(" ")[1]
    try:
        supabase = get_supabase_client(user_jwt=token)
        user_response = supabase.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="Invalid session token")

        profile_data = supabase.table("profiles").select("*, organizations(*)").eq("id", user_response.user.id).single().execute()
        role_data = supabase.table("user_roles").select("*").eq("user_id", user_response.user.id).execute()

        return {
            "user": user_response.user,
            "profile": profile_data.data,
            "roles": role_data.data
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
