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
