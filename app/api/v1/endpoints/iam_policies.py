from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.core.supabase_client import get_supabase_client
from app.iam.models import IAMPolicyDocument, IAMRequest, EvaluationResult
from app.iam.evaluator import IAMEvaluator

router = APIRouter()

class CreateIAMPolicyRequest(BaseModel):
    name: str
    description: Optional[str] = None
    policy_document: IAMPolicyDocument

class EvaluatePermissionRequest(BaseModel):
    action: str
    resource: str
    context_overrides: Optional[Dict[str, Any]] = None

@router.post("")
async def create_custom_iam_policy(
    payload: CreateIAMPolicyRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Organization Admin Endpoint: Creates a custom AWS IAM-style JSON Policy for the tenant.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = authorization.split(" ")[1]
    client_supabase = get_supabase_client(user_jwt=token)

    try:
        caller = client_supabase.auth.get_user(token)
        caller_profile = client_supabase.table("profiles").select("org_id").eq("id", caller.user.id).single().execute()
        org_id = caller_profile.data.get("org_id")

        policy_res = client_supabase.table("iam_policies").insert({
            "org_id": org_id,
            "name": payload.name,
            "description": payload.description,
            "policy_document": payload.policy_document.model_dump()
        }).execute()

        return {
            "message": "IAM Policy created successfully",
            "policy": policy_res.data[0]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/evaluate", response_model=EvaluationResult)
async def evaluate_access_permission(
    payload: EvaluatePermissionRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Evaluates whether an action on a resource is allowed for the caller under active IAM policies.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = authorization.split(" ")[1]
    client_supabase = get_supabase_client(user_jwt=token)

    try:
        caller = client_supabase.auth.get_user(token)
        profile_res = client_supabase.table("profiles").select("*, user_roles(role)").eq("id", caller.user.id).single().execute()

        user_profile = profile_res.data
        user_role = user_profile.get("user_roles", [{}])[0].get("role", "member") if user_profile.get("user_roles") else "member"

        # Fetch policies attached to user / role / org
        policies_data = client_supabase.table("iam_policies").select("policy_document").execute()
        
        parsed_policies = []
        for p in policies_data.data:
            try:
                parsed_policies.append(IAMPolicyDocument.model_validate(p["policy_document"]))
            except Exception:
                pass

        # Build context
        from app.iam.models import EvaluationContext
        context = EvaluationContext(
            user_id=caller.user.id,
            org_id=user_profile.get("org_id", ""),
            role=user_role,
            attributes=payload.context_overrides or {}
        )

        iam_req = IAMRequest(
            action=payload.action,
            resource=payload.resource,
            context=context
        )

        result = IAMEvaluator.evaluate_policies(parsed_policies, iam_req)
        return result

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("")
async def list_iam_policies(
    authorization: Optional[str] = Header(None)
):
    """
    Lists system and custom IAM policies for the tenant.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = authorization.split(" ")[1]
    client_supabase = get_supabase_client(user_jwt=token)

    try:
        policies_data = client_supabase.table("iam_policies").select("*").execute()
        return {"policies": policies_data.data}
    except Exception as e:
        # Provide built-in standard default policies as fallback
        return {
            "policies": [
                {
                    "id": "sys-pol-001",
                    "name": "RoSenseAuditorReadOnly",
                    "description": "Read-only access to meeting summaries and decision lineage logs.",
                    "is_system_policy": True,
                    "policy_document": {
                        "Version": "2026-08-24",
                        "Statement": [
                            {
                                "Sid": "AuditorRead",
                                "Effect": "Allow",
                                "Action": ["rosense:meeting:read", "rosense:decision:read", "rosense:audit:read"],
                                "Resource": "urn:rosense:*:meeting:*"
                            }
                        ]
                    }
                },
                {
                    "id": "sys-pol-002",
                    "name": "RoSenseDeptManagerFullAccess",
                    "description": "Full management access for departmental meeting recordings and decision approvals.",
                    "is_system_policy": True,
                    "policy_document": {
                        "Version": "2026-08-24",
                        "Statement": [
                            {
                                "Sid": "DeptManagerAccess",
                                "Effect": "Allow",
                                "Action": "rosense:*",
                                "Resource": "urn:rosense:*:department:*",
                                "Condition": {
                                    "StringEquals": {
                                        "rosense:department_id": "${user:department_id}"
                                    }
                                }
                            }
                        ]
                    }
                },
                {
                    "id": "sys-pol-003",
                    "name": "RoSenseVaultKeyDecryptPolicy",
                    "description": "Restricted decryption policy for AES-256 vault protected documents.",
                    "is_system_policy": True,
                    "policy_document": {
                        "Version": "2026-08-24",
                        "Statement": [
                            {
                                "Sid": "VaultDecrypt",
                                "Effect": "Allow",
                                "Action": "rosense:vault:decrypt",
                                "Resource": "urn:rosense:*:vault:kek:*"
                            }
                        ]
                    }
                }
            ]
        }


class UpdateIAMPolicyRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    policy_document: Optional[IAMPolicyDocument] = None

@router.put("/{policy_id}")
async def update_custom_iam_policy(
    policy_id: str,
    payload: UpdateIAMPolicyRequest,
    authorization: Optional[str] = Header(None)
):
    """
    Updates an existing custom IAM Policy's document statement or description.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = authorization.split(" ")[1]
    client_supabase = get_supabase_client(user_jwt=token)

    try:
        update_data = {}
        if payload.name:
            update_data["name"] = payload.name
        if payload.description:
            update_data["description"] = payload.description
        if payload.policy_document:
            update_data["policy_document"] = payload.policy_document.model_dump()

        res = client_supabase.table("iam_policies").update(update_data).eq("id", policy_id).execute()
        return {"message": "IAM Policy updated successfully", "policy_id": policy_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{policy_id}")
async def delete_custom_iam_policy(
    policy_id: str,
    authorization: Optional[str] = Header(None)
):
    """
    Deletes a custom IAM Policy.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")

    token = authorization.split(" ")[1]
    client_supabase = get_supabase_client(user_jwt=token)

    try:
        client_supabase.table("iam_policies").delete().eq("id", policy_id).execute()
        return {"message": f"IAM Policy {policy_id} deleted successfully", "policy_id": policy_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

