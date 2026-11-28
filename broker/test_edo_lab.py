import unittest
from broker.edo_lab import Envelope, synthetic_demo, MAX_BYTES, RECEIPTS

class EDOLabTests(unittest.TestCase):
    def setUp(self):
        self.e=Envelope("QA-LESSOR",b"synthetic")
    def step(self,action,actor,key):
        return self.e.transition(action,actor,key,self.e.version,self.e.sha256,self.e.dispatch_id if action in RECEIPTS else None)
    def test_default_off(self):
        with self.assertRaises(PermissionError):self.step("submit_review","author","1")
        self.assertEqual(self.e.events,())
    def test_full_lifecycle(self):
        e=synthetic_demo()
        self.assertEqual(e.state,"accepted_test")
        self.assertEqual(len(e.events),5)
        self.assertTrue(all(x.environment=="LOCAL_SIMULATOR" for x in e.events))
        self.assertEqual([x.sequence for x in e.events],list(range(1,6)))
    def test_roles_and_order(self):
        self.e.enabled=True
        with self.assertRaises(ValueError):self.step("simulate_send","dispatcher","1")
        self.step("submit_review","author","2")
        with self.assertRaises(PermissionError):self.step("approve","author","3")
        self.step("approve","reviewer","4")
        self.step("simulate_send","dispatcher","5")
        with self.assertRaises(PermissionError):self.step("receipt_delivery","dispatcher","6")
    def test_retry_and_duplicate(self):
        self.e.enabled=True
        first=self.step("submit_review","author","1")
        self.assertEqual(self.step("submit_review","author","1"),first)
        self.assertEqual(len(self.e.events),1)
        with self.assertRaises(ValueError):self.step("approve","reviewer","1")
        self.step("approve","reviewer","2")
        self.step("simulate_send","dispatcher","3")
        self.step("receipt_failure","local_simulator","4")
        with self.assertRaises(ValueError):self.step("simulate_send","dispatcher","5")
        self.step("retry_review","author","6")
        self.assertEqual(self.e.state,"review")
    def test_revision_invalidation(self):
        self.e.enabled=True
        self.step("submit_review","author","1")
        self.step("approve","reviewer","2")
        v,h=self.e.version,self.e.sha256
        with self.assertRaises(ValueError):self.e.replace_draft(b"new",v,h)
        self.step("request_revision","reviewer","3")
        self.e.replace_draft(b"new",v,h)
        self.assertEqual(self.e.version,2)
        self.assertNotEqual(self.e.sha256,h)
        with self.assertRaises(ValueError):self.e.transition("submit_review","author","4",v,h)
        self.step("submit_review","author","5")
        self.assertEqual(self.e.state,"review")
    def test_bytes_tamper(self):
        self.e.enabled=True
        self.e.content=b"changed"
        with self.assertRaises(ValueError):self.step("submit_review","author","1")
        self.assertEqual(self.e.events,())
    def test_disable_mid_process(self):
        self.e.enabled=True
        self.step("submit_review","author","1")
        self.e.enabled=False
        with self.assertRaises(PermissionError):self.step("approve","reviewer","2")
        self.assertEqual(self.e.state,"review")
    def test_synthetic_recipients_and_bounds(self):
        for recipient,data in [("real@example.test",b"x"),("QA-LESSOR",b""),("QA-LESSOR",b"x"*(MAX_BYTES+1))]:
            with self.subTest(recipient=recipient,size=len(data)),self.assertRaises(ValueError):
                Envelope(recipient,data)
    def test_rejection_path(self):
        self.e.enabled=True
        for n,(action,actor) in enumerate([("submit_review","author"),("approve","reviewer"),("simulate_send","dispatcher"),("receipt_delivery","local_simulator"),("receipt_reject","local_simulator"),("retry_review","author")]):
            self.step(action,actor,str(n))
        self.assertEqual(self.e.state,"review")


    def test_old_receipt_cannot_advance_new_attempt(self):
        self.e.enabled=True
        for n,(action,actor) in enumerate([("submit_review","author"),("approve","reviewer"),("simulate_send","dispatcher")]):
            self.step(action,actor,str(n))
        old=self.e.dispatch_id
        self.step("receipt_failure","local_simulator","3")
        self.step("retry_review","author","4")
        self.step("approve","reviewer","5")
        self.step("simulate_send","dispatcher","6")
        self.assertNotEqual(self.e.dispatch_id,old)
        with self.assertRaises(ValueError):
            self.e.transition("receipt_delivery","local_simulator","7",self.e.version,self.e.sha256,old)
        self.assertEqual(self.e.state,"sent")
        self.step("receipt_delivery","local_simulator","8")
        self.assertEqual(self.e.state,"delivered")
