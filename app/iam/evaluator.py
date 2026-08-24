import fnmatch
import re
from typing import List, Dict, Any
from app.iam.models import (
    IAMPolicyDocument, 
    IAMStatement, 
    EvaluationContext, 
    IAMRequest, 
    EvaluationResult, 
    EffectEnum
)

class IAMEvaluator:
    """
    AWS IAM-Style Policy Evaluation Engine.
    Evaluates JSON policies against incoming action + resource + context requests.
    Enforces Explicit Deny override and Default Deny rule.
    """

    @staticmethod
    def _match_pattern(pattern: str, target: str) -> bool:
        """Helper for wildcard pattern matching (e.g., 'rosense:meeting:*' vs 'rosense:meeting:read')."""
        if pattern == "*":
            return True
        return fnmatch.fnmatch(target, pattern)

    @staticmethod
    def _resolve_variable(value: str, context: EvaluationContext) -> str:
        """Resolves dynamic policy variables like '${user:department_id}' or '${user:org_id}'."""
        if not isinstance(value, str):
            return value
        
        replacements = {
            "${user:user_id}": context.user_id,
            "${user:org_id}": context.org_id,
            "${user:role}": context.role,
            "${user:department_id}": context.department_id or "",
        }
        
        resolved = value
        for key, val in replacements.items():
            resolved = resolved.replace(key, str(val))
        return resolved

    @classmethod
    def evaluate_condition(cls, condition_block: Dict[str, Dict[str, Any]], context: EvaluationContext) -> bool:
        """
        Evaluates condition statements such as StringEquals, Bool, IpAddress.
        """
        if not condition_block:
            return True

        for operator, rules in condition_block.items():
            for key, expected_val in rules.items():
                resolved_expected = cls._resolve_variable(expected_val, context) if isinstance(expected_val, str) else expected_val
                
                # Fetch actual context value
                actual_val = None
                if key == "rosense:department_id":
                    actual_val = context.department_id
                elif key == "rosense:mfa_authenticated":
                    actual_val = context.mfa_authenticated
                elif key == "rosense:is_guest":
                    actual_val = context.is_guest
                elif key == "rosense:role":
                    actual_val = context.role
                elif key in context.attributes:
                    actual_val = context.attributes[key]

                # Operator evaluations
                if operator == "StringEquals":
                    if str(actual_val) != str(resolved_expected):
                        return False
                elif operator == "StringNotEquals":
                    if str(actual_val) == str(resolved_expected):
                        return False
                elif operator == "Bool":
                    expected_bool = str(resolved_expected).lower() in ("true", "1")
                    if bool(actual_val) != expected_bool:
                        return False
                elif operator == "IpAddress":
                    if context.ip_address != str(resolved_expected):
                        return False

        return True

    @classmethod
    def evaluate_statement(cls, statement: IAMStatement, request: IAMRequest) -> bool:
        """Checks if a statement matches the requested Action, Resource, and Conditions."""
        # 1. Check Action
        actions = statement.Action if isinstance(statement.Action, list) else [statement.Action]
        action_matched = any(cls._match_pattern(act_pat, request.action) for act_pat in actions)
        if not action_matched:
            return False

        # 2. Check Resource
        resources = statement.Resource if isinstance(statement.Resource, list) else [statement.Resource]
        resource_matched = any(cls._match_pattern(res_pat, request.resource) for res_pat in resources)
        if not resource_matched:
            return False

        # 3. Check Conditions
        if statement.Condition:
            if not cls.evaluate_condition(statement.Condition, request.context):
                return False

        return True

    @classmethod
    def evaluate_policies(cls, policies: List[IAMPolicyDocument], request: IAMRequest) -> EvaluationResult:
        """
        Evaluates a list of IAM Policy Documents against a Request.
        Order of evaluation:
        1. Explicit Deny -> If matched, ACCESS DENIED immediately.
        2. Explicit Allow -> If matched (and no Deny), ALLOW ACCESS.
        3. No Match -> DEFAULT DENY.
        """
        allowed = False
        matched_allow_sid = None

        for policy in policies:
            for statement in policy.Statement:
                if cls.evaluate_statement(statement, request):
                    if statement.Effect == EffectEnum.DENY:
                        return EvaluationResult(
                            allowed=False,
                            reason=f"Explicit Deny statement matched (Sid: {statement.Sid or 'N/A'})",
                            matched_statement_sid=statement.Sid,
                            explicit_deny=True
                        )
                    elif statement.Effect == EffectEnum.ALLOW:
                        allowed = True
                        matched_allow_sid = statement.Sid or "MatchedAllow"

        if allowed:
            return EvaluationResult(
                allowed=True,
                reason=f"Matched Allow statement (Sid: {matched_allow_sid})",
                matched_statement_sid=matched_allow_sid,
                explicit_deny=False
            )

        return EvaluationResult(
            allowed=False,
            reason="Implicit Deny: No matching Allow statement found",
            explicit_deny=False
        )
