import unittest
from app.iam.models import IAMPolicyDocument, IAMStatement, EffectEnum, EvaluationContext, IAMRequest
from app.iam.evaluator import IAMEvaluator

class TestIAMEvaluator(unittest.TestCase):
    def test_iam_evaluator_allow(self):
        policy = IAMPolicyDocument(
            Statement=[
                IAMStatement(
                    Sid="AllowReadMeeting",
                    Effect=EffectEnum.ALLOW,
                    Action="rosense:meeting:read",
                    Resource="urn:rosense:acme:meeting:*"
                )
            ]
        )

        context = EvaluationContext(
            user_id="user_123",
            org_id="acme",
            role="member"
        )

        request = IAMRequest(
            action="rosense:meeting:read",
            resource="urn:rosense:acme:meeting:m_456",
            context=context
        )

        result = IAMEvaluator.evaluate_policies([policy], request)
        self.assertTrue(result.allowed)
        self.assertFalse(result.explicit_deny)

    def test_iam_evaluator_explicit_deny_overrides_allow(self):
        policy_allow = IAMPolicyDocument(
            Statement=[
                IAMStatement(
                    Sid="AllowAllMeetings",
                    Effect=EffectEnum.ALLOW,
                    Action="rosense:meeting:*",
                    Resource="*"
                )
            ]
        )

        policy_deny = IAMPolicyDocument(
            Statement=[
                IAMStatement(
                    Sid="DenyDeleteMeeting",
                    Effect=EffectEnum.DENY,
                    Action="rosense:meeting:delete",
                    Resource="*"
                )
            ]
        )

        context = EvaluationContext(
            user_id="user_123",
            org_id="acme",
            role="member"
        )

        request = IAMRequest(
            action="rosense:meeting:delete",
            resource="urn:rosense:acme:meeting:m_789",
            context=context
        )

        result = IAMEvaluator.evaluate_policies([policy_allow, policy_deny], request)
        self.assertFalse(result.allowed)
        self.assertTrue(result.explicit_deny)

    def test_iam_evaluator_condition_department(self):
        policy = IAMPolicyDocument(
            Statement=[
                IAMStatement(
                    Sid="AllowDeptLegalAccess",
                    Effect=EffectEnum.ALLOW,
                    Action="rosense:decision:read",
                    Resource="*",
                    Condition={
                        "StringEquals": {
                            "rosense:department_id": "${user:department_id}"
                        }
                    }
                )
            ]
        )

        context_matching = EvaluationContext(
            user_id="user_123",
            org_id="acme",
            role="member",
            department_id="legal_dept"
        )

        request_matching = IAMRequest(
            action="rosense:decision:read",
            resource="urn:rosense:acme:decision:d_1",
            context=context_matching
        )

        result = IAMEvaluator.evaluate_policies([policy], request_matching)
        self.assertTrue(result.allowed)

if __name__ == "__main__":
    unittest.main()
