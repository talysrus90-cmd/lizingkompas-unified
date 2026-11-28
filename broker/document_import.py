"""Local experimental import of trusted anonymised files only.
No document execution, external fetching, customer data, OCR or DB writes.
Source coordinates are physical PDF pages, DOCX body blocks, XLSX cells,
or delimited-file record numbers. Not a complete layout/legal reconstruction.
"""
import argparse
import csv
import hashlib
import io
import json
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path
from decimal import Decimal
from broker.payment_schedule import import_schedule, format_schedule

MAX_FILE=5*1024*1024
MAX_EXPANDED=32*1024*1024
MAX_PARTS=512
MAX_BLOCKS=12000
MAX_TEXT=500000
FORMATS=(".pdf",".docx",".xlsx",".txt",".csv",".tsv")

def read_file(path):
    if path.suffix.lower() not in FORMATS or not path.is_file():
        raise ValueError("Unsupported file format or not a regular file")
    with path.open("rb") as f:
        data=f.read(MAX_FILE+1)
    if not data or len(data)>MAX_FILE:
        raise ValueError("File is empty or exceeds 5 MiB")
    return data

def package_check(data,fmt):
    from defusedxml.ElementTree import fromstring
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        members=z.infolist()
        names=[i.filename for i in members]
        if len(members)>MAX_PARTS or len(set(names))!=len(names) or sum(i.file_size for i in members)>MAX_EXPANDED:
            raise ValueError("Oversized or ambiguous Office package")
        required="word/document.xml" if fmt==".docx" else "xl/workbook.xml"
        if required not in names or "[Content_Types].xml" not in names:
            raise ValueError("Office file type mismatch")
        for i in members:
            name=i.filename
            lower=name.lower()
            if i.flag_bits&1 or name.startswith("/") or "\\" in name or ".." in name.split("/") or "vbaproject" in lower or "/activex/" in lower or "/embeddings/" in lower:
                raise ValueError("Encrypted, active or embedded Office content refused")
            if lower.endswith((".xml",".rels")):
                with z.open(i) as f:
                    xml=f.read(MAX_EXPANDED+1)
                root=fromstring(xml,forbid_dtd=True,forbid_entities=True,forbid_external=True)
                if lower.endswith(".rels") and any(x.get("TargetMode","").lower()=="external" for x in root):
                    raise ValueError("External Office relationships refused")

def cell_text(value):
    if value is None:
        return ""
    if isinstance(value,datetime):
        return value.date().isoformat() if value.time().isoformat()=="00:00:00" else value.isoformat()
    if isinstance(value,date):
        return value.isoformat()
    if isinstance(value,bool):
        return str(value)
    if isinstance(value,(float,int,Decimal)):
        return format(Decimal(str(value)),"f")
    return str(value)

def extract_document(data,fmt):
    fmt=fmt.lower()
    if fmt not in FORMATS or not isinstance(data,bytes) or not 0<len(data)<=MAX_FILE:
        raise ValueError("Unsupported or oversized input")
    blocks=[]; warnings=[]; count=0
    def add(location,text,**extra):
        nonlocal count
        if not isinstance(text,str):
            raise ValueError("Invalid extracted text")
        count+=len(text)
        if count>MAX_TEXT or len(blocks)>=MAX_BLOCKS:
            raise ValueError("Extraction limit exceeded; split the document")
        blocks.append({"location":location,"text":text,**extra})
    if fmt==".pdf":
        from pypdf import PdfReader
        if not data.startswith(b"%PDF-"):
            raise ValueError("PDF signature mismatch")
        pdf=PdfReader(io.BytesIO(data),strict=True)
        if pdf.is_encrypted or len(pdf.pages)>100:
            raise ValueError("Encrypted or more than 100 pages")
        for n,page in enumerate(pdf.pages,1):
            contents=page.get_contents()
            if contents is not None and len(contents.get_data())>8*1024*1024:
                raise ValueError("Oversized PDF content stream")
            text=page.extract_text() or ""
            add({"page":n},text,needs_ocr=not bool(text.strip()))
        warnings.append("PDF text only; visual layout, scanned portions and reading order require review.")
    elif fmt==".docx":
        from docx import Document
        from docx.text.paragraph import Paragraph
        from docx.table import Table
        package_check(data,fmt)
        doc=Document(io.BytesIO(data))
        for n,item in enumerate(doc.iter_inner_content(),1):
            if isinstance(item,Paragraph):
                add({"body_block":n},item.text)
            elif isinstance(item,Table):
                for r,row in enumerate(item.rows,1):
                    for c,cell in enumerate(row.cells,1):
                        add({"body_block":n,"row":r,"column":c},cell.text)
        warnings.append("DOCX main body only: no reliable page numbering; headers, comments, nested tables, tracked changes and pictures may be omitted.")
    elif fmt==".xlsx":
        from openpyxl import load_workbook
        package_check(data,fmt)
        wb=load_workbook(io.BytesIO(data),read_only=True,data_only=False,keep_links=False)
        try:
            if len(wb.worksheets)>20:
                raise ValueError("Too many sheets")
            for sheet in wb.worksheets:
                if not sheet.max_row or not sheet.max_column or sheet.max_row>2000 or sheet.max_column>100 or sheet.max_row*sheet.max_column>40000:
                    raise ValueError("Missing or oversized worksheet dimensions")
                for r,row in enumerate(sheet.iter_rows(),1):
                    for c,cell in enumerate(row,1):
                        if cell.value is None:
                            continue
                        formula=cell.data_type=="f"
                        add({"sheet":sheet.title,"row":r,"column":c,"cell":cell.coordinate}, "" if formula else cell_text(cell.value),
                            formula_unresolved=formula,sheet_hidden=sheet.sheet_state!="visible")
        finally:
            wb.close()
        warnings.append("Formulas are never executed or interpreted as values. Hidden sheets are labelled. Cell display formatting is not preserved.")
    else:
        text=data.decode("utf-8-sig",errors="strict")
        if "\x00" in text:
            raise ValueError("Binary data in text file")
        if fmt==".txt":
            for n,line in enumerate(text.splitlines(),1):
                add({"line":n},line)
        else:
            delim="\t" if fmt==".tsv" else ";"
            for n,row in enumerate(csv.reader(io.StringIO(text),delimiter=delim,strict=True),1):
                if len(row)>100:
                    raise ValueError("Too many columns")
                for c,value in enumerate(row,1):
                    add({"record":n,"column":c},value)
    return {"format":fmt,"source_sha256":hashlib.sha256(data).hexdigest(),"blocks":blocks,
            "warnings":warnings,"requires_human_review":True}

def xlsx_schedule(document,sheet):
    if document["format"]!=".xlsx":
        raise ValueError("Select a worksheet only for XLSX")
    cells={}
    for b in document["blocks"]:
        loc=b["location"]
        if loc.get("sheet")!=sheet:
            continue
        if b.get("sheet_hidden") or b.get("formula_unresolved") or loc["column"]>3:
            raise ValueError("Only visible sheet with 3 literal columns; no formulas")
        cells.setdefault(loc["row"],{})[loc["column"]]=b["text"]
    if not cells or any(set(row)!={1,2,3} for row in cells.values()):
        raise ValueError("Missing or incomplete schedule rows")
    out=io.StringIO()
    writer=csv.writer(out,delimiter="\t",lineterminator="\n")
    for n,row in sorted(cells.items()):
        writer.writerow([row[i] for i in (1,2,3)])
    return format_schedule(import_schedule(out.getvalue()))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("file",type=Path)
    p.add_argument("--confirm-trusted-anonymised",action="store_true",required=True)
    p.add_argument("--schedule-sheet",help="Exact visible XLSX worksheet name; produce canonical schedule draft")
    p.add_argument("--text-encoding",choices=["utf-8"],default="utf-8")
    args=p.parse_args()
    try:
        data=read_file(args.file)
        doc=extract_document(data,args.file.suffix)
        if args.schedule_sheet is not None:
            doc["schedule_draft"]=xlsx_schedule(doc,args.schedule_sheet)
        print(json.dumps(doc,ensure_ascii=False,allow_nan=False))
    except Exception as exc:
        # Avoid leaking parser messages, filenames or document text in logs.
        print("Import failed: "+type(exc).__name__,file=sys.stderr)
        raise SystemExit(2)

if __name__=="__main__":
    main()
