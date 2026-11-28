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
    def test_explicit_windows_1251(self):
        r=extract_document("Аванс".encode("cp1251"),".txt","cp1251")
        self.assertEqual(r["blocks"][0]["text"],"Аванс")
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
    def test_pdf_actual_text_source_page(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
        writer=PdfWriter()
        page=writer.add_blank_page(width=300,height=300)
        font=DictionaryObject({NameObject("/Type"):NameObject("/Font"),
                               NameObject("/Subtype"):NameObject("/Type1"),
                               NameObject("/BaseFont"):NameObject("/Helvetica")})
        page[NameObject("/Resources")]=DictionaryObject({NameObject("/Font"):DictionaryObject({NameObject("/F1"):writer._add_object(font)})})
        stream=DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 20 200 Td (Advance 200000 RUB) Tj ET")
        page[NameObject("/Contents")]=writer._add_object(stream)
        b=io.BytesIO();writer.write(b)
        result=extract_document(b.getvalue(),".pdf")
        self.assertIn("Advance 200000 RUB",result["blocks"][0]["text"])
        self.assertFalse(result["blocks"][0]["needs_ocr"])
        self.assertEqual(result["blocks"][0]["location"],{"page":1})
    def test_office_active_content_and_type_mismatch(self):
        for marker in ("word/vbaProject.bin","word/embeddings/payload.bin","word/../bad"):
            b=io.BytesIO()
            with zipfile.ZipFile(b,"w") as z:
                z.writestr("word/document.xml","<document/>")
                z.writestr("[Content_Types].xml","<types/>")
                z.writestr(marker,b"synthetic")
            with self.assertRaises(ValueError):extract_document(b.getvalue(),".docx")


class EmailImportTests(unittest.TestCase):
    def test_plain_text_and_attachment_inventory(self):
        from email.message import EmailMessage
        msg=EmailMessage()
        msg["Subject"]="Synthetic offer"
        msg.set_content("Advance 200000 RUB")
        msg.add_attachment(b"DO NOT OPEN THIS",maintype="application",subtype="octet-stream",filename="example.bin")
        r=extract_document(msg.as_bytes(),".eml")
        self.assertTrue(any("Advance 200000 RUB" in x["text"] for x in r["blocks"]))
        self.assertTrue(any(x.get("attachment_not_opened") and x["text"]=="example.bin" for x in r["blocks"]))
        self.assertFalse(any("DO NOT OPEN THIS" in x["text"] for x in r["blocks"]))

@unittest.skipUnless(importlib.util.find_spec("defusedxml"),"Document parser dependencies not installed")
class OpenDocumentTests(unittest.TestCase):
    def package(self,fmt,body,extra=None):
        from broker.document_extra import OFFICE,TEXT,TABLE
        mime="application/vnd.oasis.opendocument."+("text" if fmt==".odt" else "spreadsheet")
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w") as z:
            z.writestr("mimetype",mime)
            z.writestr("META-INF/manifest.xml","<manifest/>")
            z.writestr("content.xml",f'<office:document-content xmlns:office="{OFFICE}" xmlns:text="{TEXT}" xmlns:table="{TABLE}"><office:body>{body}</office:body></office:document-content>')
            if extra:z.writestr(extra,b"synthetic")
        return b.getvalue()
    def test_odt_paragraph_and_spacing(self):
        doc=self.package(".odt","<office:text><text:p>Аванс<text:s text:c='2'/>200000</text:p><text:p>36 месяцев</text:p></office:text>")
        r=extract_document(doc,".odt")
        self.assertEqual(r["blocks"][0]["text"],"Аванс  200000")
        self.assertIn("paragraph_element",r["blocks"][0]["location"])
    def test_ods_coordinates_and_formula_refusal(self):
        doc=self.package(".ods","<office:spreadsheet><table:table table:name='График'><table:table-row><table:table-cell office:value-type='float' office:value='200000'/><table:table-cell table:formula='of:=1+1' office:value='2'/></table:table-row></table:table></office:spreadsheet>")
        r=extract_document(doc,".ods")
        self.assertEqual(r["blocks"][0]["text"],"200000")
        self.assertEqual(r["blocks"][1]["location"],{"sheet":"График","row":1,"column":2})
        self.assertTrue(r["blocks"][1]["formula_unresolved"])
        self.assertEqual(r["blocks"][1]["text"],"")
    def test_refuses_active_and_oversized_repetition(self):
        doc=self.package(".odt","<office:text><text:p>Test</text:p></office:text>","Scripts/test.js")
        with self.assertRaises(ValueError):extract_document(doc,".odt")
        doc=self.package(".ods","<office:spreadsheet><table:table table:name='x'><table:table-row table:number-rows-repeated='999999'/></table:table></office:spreadsheet>")
        with self.assertRaises(ValueError):extract_document(doc,".ods")

@unittest.skipUnless(importlib.util.find_spec("tkinter"),"Tk not installed")
class WorkbenchTests(unittest.TestCase):
    def test_csv_handoff_without_auto_save(self):
        from broker.document_workbench import schedule_draft
        doc=extract_document("Дата;Вид;Сумма\n01.01.2027;Аванс;200000\n01.02.2027;Лизинговый платёж;30000".encode(),".csv")
        self.assertEqual(schedule_draft(doc,""),"2027-01-01;advance;200000.00\n2027-02-01;lease;30000.00")
    def test_subprocess_import_utf8(self):
        from broker.document_workbench import run_import
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as folder:
            path=Path(folder)/"test.txt"
            path.write_text("Аванс 200000",encoding="utf-8")
            result=run_import(path,"utf-8")
            self.assertEqual(result["blocks"][0]["text"],"Аванс 200000")
