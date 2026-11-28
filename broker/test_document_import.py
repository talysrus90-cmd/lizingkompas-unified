import io
import unittest
import zipfile
import importlib.util
from broker.document_import import extract_document,xlsx_schedule,MAX_FILE

OFFICE=all(importlib.util.find_spec(x) for x in ("defusedxml","docx","openpyxl","pypdf"))

class TextImportTests(unittest.TestCase):
    def test_text_and_csv_coordinates(self):
        result=extract_document("Аванс 100\nСрок 36".encode(),".txt")
        self.assertEqual(result["blocks"][1]["location"],{"line":2})
        self.assertTrue(result["requires_human_review"])
        csv=extract_document("Дата;Вид;Сумма\n01.01.2027;Аванс;100".encode(),".csv")
        self.assertEqual(csv["blocks"][-1]["location"],{"record":2,"column":3})
        self.assertEqual(csv["blocks"][-1]["text"],"100")
    def test_refuses_unsupported_and_binary(self):
        for data,fmt in ((b"x",".doc"),(b"x",".zip"),(b"x\0",".txt"),(b"x"*(MAX_FILE+1),".txt")):
            with self.subTest(fmt=fmt),self.assertRaises(ValueError):
                extract_document(data,fmt)

@unittest.skipUnless(OFFICE,"Separate document-parser environment not installed")
class OfficeImportTests(unittest.TestCase):
    def test_word_paragraph_and_table(self):
        from docx import Document
        doc=Document()
        doc.add_paragraph("Аванс 200000")
        doc.add_table(rows=1,cols=2).cell(0,1).text="36 месяцев"
        b=io.BytesIO();doc.save(b)
        r=extract_document(b.getvalue(),".docx")
        self.assertEqual(r["blocks"][0]["location"],{"body_block":1})
        self.assertEqual(r["blocks"][-1]["location"],{"body_block":2,"row":1,"column":2})
        self.assertEqual(r["blocks"][-1]["text"],"36 месяцев")
    def test_excel_schedule_and_formula_refusal(self):
        from openpyxl import Workbook
        from datetime import date
        wb=Workbook(); ws=wb.active;ws.title="График"
        ws.append(["Дата","Вид","Сумма"])
        ws.append([date(2027,1,1),"Аванс",200000])
        ws.append([date(2027,2,1),"Лизинговый платёж",30000])
        b=io.BytesIO();wb.save(b)
        r=extract_document(b.getvalue(),".xlsx")
        self.assertEqual(r["blocks"][-1]["location"]["cell"],"C3")
        self.assertEqual(xlsx_schedule(r,"График"),"2027-01-01;advance;200000.00\n2027-02-01;lease;30000.00")
        ws["C3"]="=15000*2"
        b=io.BytesIO();wb.save(b)
        r=extract_document(b.getvalue(),".xlsx")
        self.assertTrue(r["blocks"][-1]["formula_unresolved"])
        self.assertEqual(r["blocks"][-1]["text"],"")
        with self.assertRaises(ValueError):xlsx_schedule(r,"График")
    def test_pdf_pages_and_blank_page_ocr_flag(self):
        from pypdf import PdfWriter
        wb=PdfWriter();wb.add_blank_page(width=300,height=300)
        b=io.BytesIO();wb.write(b)
        r=extract_document(b.getvalue(),".pdf")
        self.assertEqual(r["blocks"][0]["location"],{"page":1})
        self.assertTrue(r["blocks"][0]["needs_ocr"])
        wb.encrypt("synthetic-password")
        b=io.BytesIO();wb.write(b)
        with self.assertRaises(ValueError):extract_document(b.getvalue(),".pdf")
    def test_office_active_content_and_type_mismatch(self):
        for marker in ("word/vbaProject.bin","word/embeddings/payload.bin","word/../bad"):
            b=io.BytesIO()
            with zipfile.ZipFile(b,"w") as z:
                z.writestr("word/document.xml","<document/>")
                z.writestr("[Content_Types].xml","<types/>")
                z.writestr(marker,b"synthetic")
            with self.assertRaises(ValueError):extract_document(b.getvalue(),".docx")
