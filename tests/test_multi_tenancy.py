import unittest
from app.iam.models import IAMPolicyDocument, IAMStatement, EffectEnum, EvaluationContext, IAMRequest
from app.iam.evaluator import IAMEvaluator

class TestMultiTenancyIAM(unittest.TestCase):
    def test_tenant_isolation_iam_evaluator(self):
        """
        Tests that a user belonging to Tenant A (Acme) is blocked from accessing resources in Tenant B (InfoTech).
        """
        policy_tenant_a = IAMPolicyDocument(
            Statement=[
                IAMStatement(
                    Sid="AllowTenantAOnly",
                    Effect=EffectEnum.ALLOW,
                    Action="rosense:meeting:*",
                    Resource="urn:rosense:acme_corp:*"
                )
            ]
        )

        context_tenant_a_user = EvaluationContext(
            user_id="user_acme_1",
            org_id="acme_corp",
            role="member"
        )

        # 1. Attempting access within own tenant -> ALLOWED
        request_own_tenant = IAMRequest(
            action="rosense:meeting:read",
            resource="urn:rosense:acme_corp:meeting:m_100",
            context=context_tenant_a_user
        )
        res_own = IAMEvaluator.evaluate_policies([policy_tenant_a], request_own_tenant)
        self.assertTrue(res_own.allowed)

        # 2. Attempting access to another tenant's resource -> DENIED
        request_other_tenant = IAMRequest(
            action="rosense:meeting:read",
            resource="urn:rosense:infotech_corp:meeting:m_200",
            context=context_tenant_a_user
        )
        res_other = IAMEvaluator.evaluate_policies([policy_tenant_a], request_other_tenant)
        self.assertFalse(res_other.allowed)
        self.assertIn("Implicit Deny", res_other.reason)

if __name__ == "__main__":
    unittest.main()
