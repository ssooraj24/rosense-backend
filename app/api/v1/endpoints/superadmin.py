from fastapi import APIRouter, HTTPException, Depends, Header, status
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from app.core.supabase_client import get_supabase_admin_client, get_supabase_client

router = APIRouter()

class CreateOrganizationRequest(BaseModel):
    name: str
    slug: str
    tier: Optional[str] = "enterprise"

class InviteOrgAdminRequest(BaseModel):
    email: EmailStr
    full_name: str
    temp_password: Optional[str] = "RoSenseInitial123!"

@router.post("/organizations")
async def create_organization(
    payload: CreateOrganizationRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Superadmin Endpoint: Provisions a new client tenant organization.
    """
    # Use Admin client to insert org
    admin_supabase = get_supabase_admin_client()
    try:
        org_data = admin_supabase.table("organizations").insert({
            "name": payload.name,
            "slug": payload.slug.lower().strip(),
            "tier": payload.tier
        }).execute()

        return {
            "message": "Organization created successfully",
            "organization": org_data.data[0]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/organizations/{org_id}/invite-admin")
async def invite_org_admin(
    org_id: str,
    payload: InviteOrgAdminRequest
):
    """
    Superadmin Endpoint: Invites and creates the initial Organization Admin user for a client.
    """
    admin_supabase = get_supabase_admin_client()
    try:
        # 1. Create auth user in Supabase Auth via Admin Client
        auth_response = admin_supabase.auth.admin.create_user({
            "email": payload.email,
            "password": payload.temp_password,
            "email_confirm": True,
            "user_metadata": {
                "full_name": payload.full_name,
                "org_id": org_id,
                "role": "org_admin"
            }
        })

        if not auth_response.user:
            raise HTTPException(status_code=400, detail="Failed to create auth user")

        # 2. Assign org_admin role in user_roles table
        admin_supabase.table("user_roles").upsert({
            "user_id": auth_response.user.id,
            "org_id": org_id,
            "role": "org_admin"
        }).execute()

        return {
            "message": "Organization Admin created successfully",
            "user_id": auth_response.user.id,
            "email": payload.email,
            "temp_password": payload.temp_password
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
