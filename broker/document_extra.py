"""Bounded additional adapters for trusted, anonymised local documents."""
import io
import zipfile
from email import policy
from email.parser import BytesParser

OFFICE="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
TEXT="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
TABLE="urn:oasis:names:tc:opendocument:xmlns:table:1.0"
MANIFEST="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"

def q(ns,name):
    return "{"+ns+"}"+name

def odf_root(data,fmt):
    from defusedxml.ElementTree import fromstring
    mime={".odt":"application/vnd.oasis.opendocument.text",
          ".ods":"application/vnd.oasis.opendocument.spreadsheet"}[fmt]
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        entries=z.infolist()
        names=[i.filename for i in entries]
        if len(entries)>512 or len(set(names))!=len(names) or sum(i.file_size for i in entries)>32*1024*1024:
            raise ValueError("Oversized ODF package")
        if not {"mimetype","content.xml","META-INF/manifest.xml"}<=set(names):
            raise ValueError("ODF parts missing")
        for i in entries:
            name=i.filename
            low=name.lower()
            if i.flag_bits&1 or name.startswith("/") or "\\" in name or ".." in name.split("/") or low.startswith(("basic/","scripts/","object ","objectreplacements/")):
                raise ValueError("Active or embedded ODF content refused")
        if z.read("mimetype").decode("ascii")!=mime:
            raise ValueError("ODF type mismatch")
        for name in names:
            if name.endswith(".xml"):
                node=fromstring(z.read(name),forbid_dtd=True,forbid_entities=True,forbid_external=True)
                if any(x.tag in (q(MANIFEST,"encryption-data"),q(OFFICE,"scripts"),q(TEXT,"execute-macro")) for x in node.iter()):
                    # Empty office:scripts containers are common in valid files.
                    if any(x.tag!=q(OFFICE,"scripts") or len(x) for x in node.iter() if x.tag in (q(MANIFEST,"encryption-data"),q(OFFICE,"scripts"),q(TEXT,"execute-macro"))):
                        raise ValueError("Active or encrypted ODF content refused")
                if name=="content.xml":
                    content=node
        return content

def paragraph_text(node):
    parts=[]
    def visit(n,depth):
        if depth>80:
            raise ValueError("ODF text too deeply nested")
        if n.text:parts.append(n.text)
        for child in n:
            if child.tag==q(TEXT,"s"):
                raw=child.get(q(TEXT,"c"),"1")
                if len(raw)>4 or not raw.isascii() or not raw.isdigit() or not 1<=int(raw)<=1000:
                    raise ValueError("ODF space repeat out of range")
                parts.append(" "*int(raw))
            elif child.tag==q(TEXT,"tab"):
                parts.append("\t")
            elif child.tag==q(TEXT,"line-break"):
                parts.append("\n")
            else:
                visit(child,depth+1)
            if child.tail:parts.append(child.tail)
    visit(node,0)
    return "".join(parts)

def repeat(node,attr,maximum):
    raw=node.get(q(TABLE,attr),"1")
    if len(raw)>7 or not raw.isascii() or not raw.isdigit() or int(raw)<1:
        raise ValueError("Invalid ODF repeat")
    n=int(raw)
    if n>maximum:
        raise ValueError("ODF repeat limit exceeded")
    return n

def extract_odf(data,fmt,add,warnings):
    root=odf_root(data,fmt)
    body=root.find(q(OFFICE,"body"))
    if body is None:raise ValueError("ODF body missing")
    if fmt==".odt":
        text=body.find(q(OFFICE,"text"))
        if text is None:raise ValueError("ODT body missing")
        for n,node in enumerate(text.iter(),1):
            if node.tag in (q(TEXT,"p"),q(TEXT,"h")):
                add({"paragraph_element":n},paragraph_text(node))
        warnings.append("ODT paragraph order only; no page numbers or reliable table layout.")
        return
    spreadsheet=body.find(q(OFFICE,"spreadsheet"))
    if spreadsheet is None:raise ValueError("ODS body missing")
    tables=spreadsheet.findall(q(TABLE,"table"))
    if len(tables)>20:raise ValueError("Too many ODS sheets")
    for table in tables:
        name=table.get(q(TABLE,"name"),"")
        row_no=0
        # Reject grouped/indirect rows rather than silently re-indexing.
        rows=table.findall(q(TABLE,"table-row"))
        if len(rows)!=len(list(table.iter(q(TABLE,"table-row")))):
            raise ValueError("Grouped or nested ODS rows not supported")
        for row in rows:
            nr=repeat(row,"number-rows-repeated",2000)
            row_no_end=row_no+nr
            if row_no_end>2000:raise ValueError("ODS row limit")
            col=0
            cells=[]
            for cell in row:
                if cell.tag not in (q(TABLE,"table-cell"),q(TABLE,"covered-table-cell")):continue
                nc=repeat(cell,"number-columns-repeated",100)
                if col+nc>100:raise ValueError("ODS column limit")
                formula=cell.get(q(TABLE,"formula")) is not None
                text="\n".join(paragraph_text(p) for p in cell.findall(q(TEXT,"p")))
                value=cell.get(q(OFFICE,"value"))
                value_type=cell.get(q(OFFICE,"value-type"))
                if value_type in ("float","currency","percentage") and value is not None:
                    text=value if value_type=="float" else text
                elif value_type=="date":
                    text=cell.get(q(OFFICE,"date-value"),text)
                if text or formula:
                    cells.extend((c, "" if formula else text, formula) for c in range(col+1,col+nc+1))
                col+=nc
            for r in range(row_no+1,row_no_end+1):
                for c,text,formula in cells:
                    add({"sheet":name,"row":r,"column":c},text,formula_unresolved=formula)
            row_no=row_no_end
    warnings.append("ODS literal cells only; formulas not executed; layout and visibility not reconstructed. No automatic schedule conversion.")

def extract_eml(data,add,warnings):
    message=BytesParser(policy=policy.default).parsebytes(data)
    parts=list(message.walk())
    if len(parts)>100 or any(p.defects for p in parts):
        raise ValueError("Malformed or oversized MIME structure")
    for key in ("Subject","Date","From","To"):
        if message.get(key):
            add({"header":key},str(message[key]))
    body=message.get_body(preferencelist=("plain",))
    if body is not None and body.get_content_type()=="text/plain":
        content=body.get_content()
        if not isinstance(content,str):raise ValueError("Invalid mail body")
        add({"mime_part":parts.index(body)+1},content)
    else:
        warnings.append("No plain-text body; HTML is not rendered or fetched.")
    for i,part in enumerate(parts,1):
        if part.get_content_disposition()=="attachment" or part.get_filename():
            add({"mime_part":i,"attachment":True},str(part.get_filename() or "unnamed"),
                content_type=part.get_content_type(),attachment_not_opened=True)
    warnings.append("EML headers are unverified. Attachments listed only, not extracted or opened.")
