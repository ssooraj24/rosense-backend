from fastapi import APIRouter, HTTPException, Depends, Header, status
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from app.core.supabase_client import get_supabase_client, get_supabase_admin_client

router = APIRouter()

class InviteUserRequest(BaseModel):
    email: EmailStr
    full_name: str
    role: str = "member" # 'dept_manager', 'member', 'auditor', 'guest'
    department_id: Optional[str] = None
    temp_password: Optional[str] = "RoSensePass2026!"

class UpdateUserRoleRequest(BaseModel):
    role: str
    department_id: Optional[str] = None

@router.post("/invite")
async def invite_tenant_user(
    payload: InviteUserRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Organization Admin Endpoint: Invites a team member to their organization.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    user_jwt = authorization.split(" ")[1]
    client_supabase = get_supabase_client(user_jwt=user_jwt)
    admin_supabase = get_supabase_admin_client()

    try:
        # Get caller profile & org_id
        caller = client_supabase.auth.get_user(user_jwt)
        if not caller.user:
            raise HTTPException(status_code=401, detail="Invalid token")

        caller_profile = client_supabase.table("profiles").select("org_id").eq("id", caller.user.id).single().execute()
        org_id = caller_profile.data.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="User is not associated with an organization")

        # 1. Create auth user in Supabase
        auth_response = admin_supabase.auth.admin.create_user({
            "email": payload.email,
            "password": payload.temp_password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": payload.full_name,
                "org_id": org_id,
                "role": payload.role
            }
        })

        user_id = auth_response.user.id

        # 2. Update profiles & role assignment
        admin_supabase.table("user_roles").upsert({
            "user_id": user_id,
            "org_id": org_id,
            "role": payload.role
        }).execute()

        if payload.department_id:
            admin_supabase.table("department_members").upsert({
                "department_id": payload.department_id,
                "user_id": user_id,
                "is_primary_dept": True
            }).execute()

        return {
            "message": f"User {payload.email} invited successfully",
            "user_id": user_id,
            "org_id": org_id,
            "role": payload.role
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("")
async def list_organization_users(
    authorization: Optional[str] = Header(None)
):
    """
    Lists users belonging to the caller's organization (RLS Enforced).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = authorization.split(" ")[1]
    client_supabase = get_supabase_client(user_jwt=token)

    try:
        users_data = client_supabase.table("profiles").select("*, user_roles(role)").execute()
        return {"users": users_data.data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{user_id}/role")
async def update_user_role(
    user_id: str,
    payload: UpdateUserRoleRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Updates a user's role or department assignment.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = authorization.split(" ")[1]
    client_supabase = get_supabase_client(user_jwt=token)

    try:
        caller = client_supabase.auth.get_user(token)
        caller_profile = client_supabase.table("profiles").select("org_id").eq("id", caller.user.id).single().execute()
        org_id = caller_profile.data.get("org_id")

        # Update role
        res = client_supabase.table("user_roles").update({"role": payload.role}).eq("user_id", user_id).eq("org_id", org_id).execute()

        if payload.department_id:
            client_supabase.table("department_members").upsert({
                "department_id": payload.department_id,
                "user_id": user_id,
                "is_primary_dept": True
            }).execute()

        return {"message": "User role updated successfully", "user_id": user_id, "new_role": payload.role}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
