from fastapi import APIRouter, HTTPException, Depends, Header, status
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from app.core.supabase_client import get_supabase_client, get_supabase_admin_client

router = APIRouter()

class InviteUserRequest(BaseModel):
    email: EmailStr
    full_name: str
    role: str = "member" # 'dept_manager', 'member', 'auditor', 'guest'
    org_id: Optional[str] = None
    department_id: Optional[str] = None
    temp_password: Optional[str] = "RoSensePass2026!"

class UpdateUserRoleRequest(BaseModel):
    role: str
    department_id: Optional[str] = None

def get_caller_org_id(caller_user, admin_supabase) -> Optional[str]:
    """Helper to safely determine organization ID across metadata, profiles, user_roles, or default RoSense AI Internal org."""
    if caller_user.user_metadata and caller_user.user_metadata.get("org_id"):
        return caller_user.user_metadata.get("org_id")

    try:
        profile_res = admin_supabase.table("profiles").select("org_id").eq("id", caller_user.id).execute()
        if profile_res.data and len(profile_res.data) > 0 and profile_res.data[0].get("org_id"):
            return profile_res.data[0].get("org_id")
    except Exception:
        pass

    try:
        roles_res = admin_supabase.table("user_roles").select("org_id").eq("user_id", caller_user.id).execute()
        if roles_res.data and len(roles_res.data) > 0 and roles_res.data[0].get("org_id"):
            return roles_res.data[0].get("org_id")
    except Exception:
        pass

    try:
        # Search specifically for RoSense AI Internal system org first
        internal_org = admin_supabase.table("organizations").select("id").eq("name", "RoSense AI Internal").limit(1).execute()
        if internal_org.data and len(internal_org.data) > 0:
            return internal_org.data[0].get("id")

        orgs_res = admin_supabase.table("organizations").select("id").limit(1).execute()
        if orgs_res.data and len(orgs_res.data) > 0:
            return orgs_res.data[0].get("id")
    except Exception:
        pass

    return None

@router.post("/invite")
async def invite_tenant_user(
    payload: InviteUserRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Organization Admin Endpoint: Invites a team member to a specified or caller organization.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    user_jwt = authorization.split(" ")[1]
    client_supabase = get_supabase_client(user_jwt=user_jwt)
    admin_supabase = get_supabase_admin_client()

    try:
        # Get caller user
        caller = client_supabase.auth.get_user(user_jwt)
        if not caller.user:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Prioritize explicitly provided target org_id in payload, fallback to caller's org_id
        org_id = payload.org_id or get_caller_org_id(caller.user, admin_supabase)
        if not org_id:
            raise HTTPException(status_code=400, detail="Organization ID is required to invite user")

        user_id = None

        # 1. Create auth user in Supabase (with clean metadata to prevent DB trigger typecast failures)
        try:
            auth_response = admin_supabase.auth.admin.create_user({
                "email": payload.email,
                "password": payload.temp_password,
                "email_confirm": True,
                "user_metadata": {
                    "full_name": payload.full_name
                }
            })
            if auth_response and auth_response.user:
                user_id = auth_response.user.id
        except Exception as create_err:
            err_str = str(create_err)
            # If user already exists in auth, retrieve their ID
            if "already registered" in err_str.lower() or "already exists" in err_str.lower():
                try:
                    users_list = admin_supabase.auth.admin.list_users()
                    for u in users_list:
                        if u.email.lower() == payload.email.lower():
                            user_id = u.id
                            break
                except Exception:
                    pass
            
            if not user_id:
                raise HTTPException(status_code=400, detail=f"Failed to create user in Auth: {err_str}")

        # 2. Explicitly update profile with org_id and full_name
        try:
            admin_supabase.table("profiles").upsert({
                "id": user_id,
                "email": payload.email,
                "full_name": payload.full_name,
                "org_id": org_id,
                "is_active": True
            }).execute()
        except Exception as profile_err:
            print(f"Profile upsert warning: {profile_err}")

        # 3. Assign role in user_roles table
        try:
            admin_supabase.table("user_roles").upsert({
                "user_id": user_id,
                "org_id": org_id,
                "role": payload.role
            }).execute()
        except Exception as role_err:
            print(f"User role assignment warning: {role_err}")

        # 4. Department assignment if specified
        if payload.department_id:
            try:
                admin_supabase.table("department_members").upsert({
                    "department_id": payload.department_id,
                    "user_id": user_id,
                    "is_primary_dept": True
                }).execute()
            except Exception as dept_err:
                print(f"Department membership warning: {dept_err}")

        return {
            "message": f"User {payload.email} invited successfully",
            "user_id": user_id,
            "org_id": org_id,
            "role": payload.role
        }

    except HTTPException:
        raise
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
    admin_supabase = get_supabase_admin_client()

    try:
        caller = client_supabase.auth.get_user(token)
        org_id = get_caller_org_id(caller.user, admin_supabase)

        # Update role
        res = admin_supabase.table("user_roles").update({"role": payload.role}).eq("user_id", user_id).eq("org_id", org_id).execute()

        if payload.department_id:
            admin_supabase.table("department_members").upsert({
                "department_id": payload.department_id,
                "user_id": user_id,
                "is_primary_dept": True
            }).execute()

        return {"message": "User role updated successfully", "user_id": user_id, "new_role": payload.role}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

