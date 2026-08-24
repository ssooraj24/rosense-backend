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

        # Prioritize explicitly provided target org_id in payload. Allow org_id to be None for system/internal roles (superadmin, admin)
        org_id = payload.org_id
        if not org_id and payload.role not in ["superadmin", "admin"]:
            org_id = get_caller_org_id(caller.user, admin_supabase)

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
    Lists users with populated role and organization details.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = authorization.split(" ")[1]
    admin_supabase = get_supabase_admin_client()

    try:
        users_data = admin_supabase.table("profiles").select("*, organizations(id, name), user_roles(role)").execute()
        
        # Query auth user metadata for persistent role and department info
        auth_metadata_map = {}
        try:
            auth_users_res = admin_supabase.auth.admin.list_users()
            for au in (auth_users_res or []):
                auth_metadata_map[au.id] = au.user_metadata or {}
        except Exception:
            pass

        formatted_users = []
        for u in users_data.data or []:
            meta = auth_metadata_map.get(u.get("id"), {})
            
            user_role = meta.get("role") or "member"
            if u.get("user_roles"):
                roles_list = u["user_roles"]
                if isinstance(roles_list, list) and len(roles_list) > 0:
                    user_role = roles_list[0].get("role", user_role)
                elif isinstance(roles_list, dict):
                    user_role = roles_list.get("role", user_role)

            org_name = None
            if u.get("organizations") and isinstance(u["organizations"], dict):
                org_name = u["organizations"].get("name")

            user_dept = meta.get("department") or u.get("department") or "General"

            formatted_users.append({
                "id": u.get("id"),
                "full_name": u.get("full_name") or meta.get("full_name") or u.get("email", "User").split("@")[0],
                "email": u.get("email"),
                "org_id": u.get("org_id") or meta.get("org_id"),
                "org_name": org_name,
                "role": user_role,
                "is_active": u.get("is_active", True),
                "is_mfa_enabled": u.get("is_mfa_enabled", False),
                "department": user_dept
            })

        return {"users": formatted_users}
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
        res = admin_supabase.table("user_roles").update({"role": payload.role}).eq("user_id", user_id).execute()

        if payload.department_id:
            admin_supabase.table("department_members").upsert({
                "department_id": payload.department_id,
                "user_id": user_id,
                "is_primary_dept": True
            }).execute()

        return {"message": "User role updated successfully", "user_id": user_id, "new_role": payload.role}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class UpdateFullUserRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    org_id: Optional[str] = None
    department_id: Optional[str] = None
    department: Optional[str] = None
    is_active: Optional[bool] = True

@router.put("/{user_id}")
async def update_user_full_record(
    user_id: str,
    payload: UpdateFullUserRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Updates full user profile, role assignment, organization scope, and status.
    """
    admin_supabase = get_supabase_admin_client()
    try:
        target_org_id = payload.org_id if payload.org_id else None
        target_dept = payload.department or payload.department_id

        # Update Profile
        update_data = {
            "org_id": target_org_id,
            "department": target_dept
        }
        if payload.full_name is not None:
            update_data["full_name"] = payload.full_name
        if payload.is_active is not None:
            update_data["is_active"] = payload.is_active

        # 1. Update Profile
        try:
            admin_supabase.table("profiles").update(update_data).eq("id", user_id).execute()
        except Exception as prof_err:
            print(f"Profile update note: {prof_err}")

        # 2. Update Auth User Metadata
        try:
            admin_supabase.auth.admin.update_user_by_id(user_id, {
                "user_metadata": {
                    "full_name": payload.full_name,
                    "role": payload.role,
                    "org_id": target_org_id,
                    "department": target_dept
                }
            })
        except Exception as auth_err:
            print(f"Auth metadata update note: {auth_err}")

        # 3. Update Role in user_roles
        if payload.role:
            try:
                existing_role = admin_supabase.table("user_roles").select("id").eq("user_id", user_id).execute()
                if existing_role.data and len(existing_role.data) > 0:
                    admin_supabase.table("user_roles").update({
                        "role": payload.role,
                        "org_id": target_org_id
                    }).eq("user_id", user_id).execute()
                else:
                    admin_supabase.table("user_roles").insert({
                        "user_id": user_id,
                        "role": payload.role,
                        "org_id": target_org_id
                    }).execute()
            except Exception as role_err:
                print(f"User role update note: {role_err}")

        return {"message": "User record updated successfully", "user_id": user_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{user_id}")
async def delete_user_record(
    user_id: str,
    authorization: Optional[str] = Header(None)
):
    """
    Deletes user profile, role bindings, and auth account.
    """
    admin_supabase = get_supabase_admin_client()
    try:
        # Delete profile & roles
        admin_supabase.table("user_roles").delete().eq("user_id", user_id).execute()
        admin_supabase.table("profiles").delete().eq("id", user_id).execute()
        try:
            admin_supabase.auth.admin.delete_user(user_id)
        except Exception:
            pass

        return {"message": f"User {user_id} deleted successfully", "user_id": user_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

