from __future__ import annotations
from enum import Enum
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field

class EffectEnum(str, Enum):
    ALLOW = "Allow"
    DENY = "Deny"

class IAMStatement(BaseModel):
    Sid: Optional[str] = Field(None, description="Optional Statement Identifier")
    Effect: EffectEnum = Field(..., description="Allow or Deny access")
    Action: Union[str, List[str]] = Field(..., description="Action pattern or list of actions e.g. 'rosense:meeting:read'")
    Resource: Union[str, List[str]] = Field(..., description="Resource URN pattern or list e.g. 'urn:rosense:acme:meeting:*'")
    Condition: Optional[Dict[str, Dict[str, Any]]] = Field(
        None, 
        description="Optional conditions e.g. {'StringEquals': {'rosense:department_id': '${user:department_id}'}}"
    )

class IAMPolicyDocument(BaseModel):
    Version: str = Field("2026-08-24", description="Policy specification version")
    Statement: List[IAMStatement] = Field(..., description="List of policy statements")

class EvaluationContext(BaseModel):
    user_id: str
    org_id: str
    role: str
    department_id: Optional[str] = None
    ip_address: Optional[str] = None
    mfa_authenticated: bool = False
    is_guest: bool = False
    attributes: Dict[str, Any] = Field(default_factory=dict)

class IAMRequest(BaseModel):
    action: str
    resource: str
    context: EvaluationContext

class EvaluationResult(BaseModel):
    allowed: bool
    reason: str
    matched_statement_sid: Optional[str] = None
    explicit_deny: bool = False
