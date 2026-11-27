import io,json,pathlib,sqlite3,tempfile,unittest,uuid
from server import Intake,inn_valid

class TestIntake(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=pathlib.Path(self.tmp.name)/"private.sqlite"
        self.app=Intake(self.db,"https://example.test","approved-v1",True)
        self.data={"kind":"callback","fields":{"phone":"+7 000 000 00 00"},"consent":True,"consent_version":"approved-v1","request_id":str(uuid.uuid4())}
    def tearDown(self):
        self.tmp.cleanup()
    def send(self,obj=None,origin="https://example.test",app=None,method="POST",path="/api/leads",ctype="application/json",raw=None):
        body=raw if raw is not None else json.dumps(self.data if obj is None else obj).encode()
        env={"PATH_INFO":path,"REQUEST_METHOD":method,"HTTP_ORIGIN":origin,"CONTENT_TYPE":ctype,"CONTENT_LENGTH":str(len(body)),"wsgi.input":io.BytesIO(body)}
        result=[]
        out=b"".join((app or self.app)(env,lambda s,h:result.append((s,h))))
        return int(result[0][0].split()[0]),json.loads(out)
    def test_closed_default(self):
        self.assertEqual(self.send(app=Intake(self.db))[0],503)
    def test_approval_config(self):
        with self.assertRaises(ValueError):Intake(self.db,"http://example.test","x",True)
    def test_origin(self):
        self.assertEqual(self.send(origin="https://other.test")[0],403)
    def test_content_type(self):
        self.assertEqual(self.send(ctype="text/plain")[0],415)
    def test_consent(self):
        self.assertEqual(self.send({**self.data,"consent":False})[0],400)
        self.assertEqual(self.send({**self.data,"consent_version":"old"})[0],400)
    def test_invalid_body(self):
        self.assertEqual(self.send(raw=b"x"*8193)[0],413)
        self.assertEqual(self.send(raw=b"{")[0],400)
        self.assertEqual(self.send(obj=[])[0],400)
    def test_phone(self):
        self.assertEqual(self.send({**self.data,"fields":{"phone":"123"}})[0],400)
    def test_minimize(self):
        self.assertEqual(self.send({**self.data,"fields":{**self.data["fields"],"name":"Synthetic"}})[0],400)
    def test_idempotent(self):
        a=self.send();b=self.send()
        self.assertEqual(a[0],201);self.assertEqual(b[0],200)
        self.assertEqual(a[1],b[1])
        self.assertEqual(self.send({**self.data,"fields":{"phone":"+7 000 000 00 01"}})[0],409)
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM leads").fetchone()[0],1)
    def test_request_fields(self):
        self.assertEqual(self.send({**self.data,"kind":"request"})[0],400)
    def test_inn(self):
        self.assertTrue(inn_valid("7707083893"))
        self.assertFalse(inn_valid("7707083894"))
        self.assertFalse(inn_valid("000"))
    def test_bad_attribution(self):
        self.assertEqual(self.send({**self.data,"attribution":{"utm_source":"<script>"}})[0],400)
    def test_no_public_read(self):
        self.assertEqual(self.send(method="GET")[0],405)
        self.assertEqual(self.send(path="/api/export")[0],404)
    def test_rate_limit(self):
        for i in range(30):
            self.assertEqual(self.send({**self.data,"request_id":str(uuid.uuid4())})[0],201)
        self.assertEqual(self.send({**self.data,"request_id":str(uuid.uuid4())})[0],429)

if __name__=="__main__":unittest.main()
