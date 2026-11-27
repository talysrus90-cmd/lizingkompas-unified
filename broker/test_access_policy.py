"""Run: python -m unittest discover -s broker -p 'test_*.py' -v"""
import unittest
from access_policy import Actor, Resource, allowed, require_access


class AccessPolicyTests(unittest.TestCase):
    def setUp(self):
        self.case = Resource(tenant_id="tenant-a", kind="case", case_id="case-1")
        self.document = Resource(tenant_id="tenant-a", kind="document", case_id="case-1")
        self.offer = Resource(tenant_id="tenant-a", kind="offer", case_id="case-1")
        self.broker = Actor(user_id="broker-1", tenant_id="tenant-a",
                            role="broker", case_ids=frozenset(("case-1",)))

    def test_assigned_broker_scopes(self):
        self.assertTrue(allowed(self.broker, self.case, "read"))
        self.assertTrue(allowed(self.broker, self.case, "update"))
        self.assertTrue(allowed(self.broker, self.document, "create"))
        self.assertTrue(allowed(self.broker, self.offer, "read"))
        self.assertFalse(allowed(self.broker, self.offer, "approve"))
        self.assertFalse(allowed(self.broker, self.case, "delete"))

    def test_missing_or_other_case_denied(self):
        for case in ("case-2", ""):
            self.assertFalse(allowed(self.broker, Resource("tenant-a", "case", case), "read"))
            self.assertFalse(allowed(self.broker, Resource("tenant-a", "offer", case), "create"))
        with self.assertRaisesRegex(PermissionError, "access_denied"):
            require_access(self.broker, Resource("tenant-a", "case", "case-2"), "read")

    def test_cross_tenant_denied_even_if_case_id_matches(self):
        for kind in ("case", "document", "offer"):
            self.assertFalse(allowed(self.broker, Resource("tenant-b", kind, "case-1"), "read"))

    def test_admin_does_not_get_customer_documents(self):
        admin = Actor("admin-1", "tenant-a", "admin", frozenset(("case-1",)))
        self.assertTrue(allowed(admin, Resource("tenant-a", "settings"), "configure"))
        self.assertTrue(allowed(admin, Resource("tenant-a", "audit"), "read"))
        self.assertFalse(allowed(admin, self.case, "read"))
        self.assertFalse(allowed(admin, self.document, "read"))
        self.assertFalse(allowed(admin, self.offer, "approve"))

    def test_supervisor_and_reviewer_scope(self):
        supervisor = Actor("sup-1", "tenant-a", "supervisor", frozenset(("case-1",)))
        reviewer = Actor("rev-1", "tenant-a", "document_reviewer", frozenset(("case-1",)))
        self.assertTrue(allowed(supervisor, self.offer, "approve"))
        self.assertTrue(allowed(reviewer, self.document, "approve"))
        self.assertFalse(allowed(reviewer, self.case, "read"))
        self.assertFalse(allowed(reviewer, Resource("tenant-a", "document", "case-2"), "approve"))

    def test_auditor_has_only_audit_read(self):
        auditor = Actor("audit-1", "tenant-a", "auditor")
        self.assertTrue(allowed(auditor, Resource("tenant-a", "audit"), "read"))
        self.assertFalse(allowed(auditor, Resource("tenant-a", "settings"), "read"))
        self.assertFalse(allowed(auditor, self.document, "read"))

    def test_fail_closed_for_unknown_roles_actions_or_missing_context(self):
        self.assertFalse(allowed(None, self.case, "read"))
        self.assertFalse(allowed(self.broker, None, "read"))
        self.assertFalse(allowed(self.broker, self.case, "export_all"))
        self.assertFalse(allowed(Actor("", "tenant-a", "broker", frozenset(("case-1",))), self.case, "read"))
        self.assertFalse(allowed(Actor("x", "tenant-a", "not-a-role", frozenset(("case-1",))), self.case, "read"))
        self.assertFalse(allowed(self.broker, Resource("tenant-a", "audit", "case-1"), "read"))


if __name__ == "__main__":
    unittest.main()
