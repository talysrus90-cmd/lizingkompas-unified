"""Local Windows/Linux document workbench for trusted anonymised files only.
Parser runs in a separate process with a time limit, not inside the CRM.
This is process separation, not a secure sandbox for untrusted files.
"""
import json
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from broker.document_import import FORMATS, xlsx_schedule
from broker.payment_schedule import import_schedule, format_schedule

ROOT=Path(__file__).resolve().parents[1]

def run_import(path,encoding):
    """No temporary output files; no shell or external network requests."""
    proc=subprocess.run([sys.executable,"-m","broker.document_import",str(path),
        "--confirm-trusted-anonymised","--text-encoding",encoding],
        cwd=ROOT,capture_output=True,timeout=45,check=True)
    if len(proc.stdout)>16*1024*1024:
        raise ValueError("Response exceeds limit")
    return json.loads(proc.stdout.decode("utf-8"))

def schedule_draft(doc,sheet):
    if doc["format"]==".xlsx":
        return xlsx_schedule(doc,sheet)
    if doc["format"] in (".csv",".tsv"):
        import csv,io
        rows={}
        for block in doc["blocks"]:
            loc=block["location"]
            rows.setdefault(loc["record"],{})[loc["column"]]=block["text"]
        out=io.StringIO()
        writer=csv.writer(out,delimiter="\t",lineterminator="\n")
        for _,row in sorted(rows.items()):
            if set(row)!={1,2,3}:
                raise ValueError("Expected three literal columns")
            writer.writerow([row[n] for n in (1,2,3)])
        return format_schedule(import_schedule(out.getvalue()))
    raise ValueError("Schedule conversion is available for XLSX, CSV, TSV")

def main():
    root=tk.Tk()
    root.title("Лизинг Компас — документы")
    root.geometry("1000x680")
    root.minsize(650,480)
    shell=ttk.Frame(root,padding=16)
    shell.pack(fill="both",expand=True)
    ttk.Label(shell,text="Compass Document",font=("Segoe UI",19,"bold")).pack(anchor="w")
    ttk.Label(shell,text="Локальный пилот. Только доверенные обезличенные файлы. Не загружайте реальные клиентские документы.",wraplength=850).pack(anchor="w",pady=(5,10))
    consent=tk.BooleanVar(value=False)
    ttk.Checkbutton(shell,text="Подтверждаю: файл доверенный и обезличенный",variable=consent).pack(anchor="w")
    bar=ttk.Frame(shell);bar.pack(fill="x",pady=8)
    encoding=tk.StringVar(value="utf-8")
    ttk.Label(bar,text="Кодировка текста").pack(side="left")
    ttk.Combobox(bar,textvariable=encoding,values=("utf-8","cp1251"),state="readonly",width=12).pack(side="left",padx=6)
    status=tk.StringVar(value="Выберите документ")
    doc=None; draft=""
    tabs=ttk.Notebook(shell);tabs.pack(fill="both",expand=True)
    preview_frame=ttk.Frame(tabs);schedule_frame=ttk.Frame(tabs)
    tabs.add(preview_frame,text="Извлечённые данные")
    tabs.add(schedule_frame,text="Черновик графика")
    def text_area(parent):
        area=ttk.Frame(parent);area.pack(fill="both",expand=True)
        view=tk.Text(area,wrap="word",font=("Segoe UI",11),state="disabled")
        scroll=ttk.Scrollbar(area,orient="vertical",command=view.yview)
        view.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right",fill="y");view.pack(side="left",fill="both",expand=True)
        return view
    preview=text_area(preview_frame)
    ttk.Label(schedule_frame,text="Лист Excel (явный выбор). Для CSV/TSV лист не нужен.").pack(anchor="w")
    sheet=tk.StringVar()
    sheets=ttk.Combobox(schedule_frame,textvariable=sheet,state="readonly");sheets.pack(fill="x",pady=4)
    draft_view=text_area(schedule_frame)
    def show(view,text):
        view.configure(state="normal");view.delete("1.0","end");view.insert("1.0",text);view.configure(state="disabled")
    def clear():
        nonlocal doc,draft
        doc=None;draft="";sheets.configure(values=());sheet.set("")
        show(preview,"");show(draft_view,"");make.configure(state="disabled");copy.configure(state="disabled")
    def done(result,error):
        nonlocal doc
        choose.configure(state="normal")
        if error:
            status.set("Импорт не выполнен: "+error);return
        doc=result
        lines=["SHA-256: "+doc["source_sha256"],*doc["warnings"],""]
        for b in doc["blocks"]:
            loc=" / ".join(f"{k}: {v}" for k,v in b["location"].items())
            flags=" | ".join(k for k in ("needs_ocr","formula_unresolved","sheet_hidden") if b.get(k))
            lines.append(f"[{loc}] {flags}\n{b['text']}")
        show(preview,"\n\n".join(lines))
        names=sorted({b["location"]["sheet"] for b in doc["blocks"] if "sheet" in b["location"] and not b.get("sheet_hidden")})
        sheets.configure(values=names)
        if doc["format"] in (".xlsx",".csv",".tsv"):
            make.configure(state="normal")
        status.set(f"Извлечено блоков: {len(doc['blocks'])}. Сверьте с оригиналом.")
    def open_file():
        if not consent.get():
            messagebox.showwarning("Подтверждение","Сначала подтвердите доверенный обезличенный источник.");return
        name=filedialog.askopenfilename(filetypes=[("Документы"," ".join("*"+ext for ext in FORMATS))])
        if not name:return
        clear();choose.configure(state="disabled");status.set("Извлечение…")
        enc=encoding.get()
        def worker():
            try:
                result=run_import(Path(name),enc)
            except Exception as exc:
                root.after(0,lambda err=type(exc).__name__:done(None,err))
            else:
                root.after(0,lambda:done(result,None))
        threading.Thread(target=worker,daemon=True).start()
    def build():
        nonlocal draft
        draft="";copy.configure(state="disabled");show(draft_view,"")
        if doc is None:return
        try:
            draft=schedule_draft(doc,sheet.get())
        except Exception:
            status.set("График не сформирован: нужны три колонки, допустимые даты и числа без формул.");return
        show(draft_view,draft);copy.configure(state="normal")
        status.set("Черновик. Вставьте в Finance Pro и подтвердите полноту по оригиналу.")
    def copy_draft():
        if draft:
            root.clipboard_clear();root.clipboard_append(draft)
            status.set("Черновик скопирован. Данные в CRM не сохранены.")
    choose=ttk.Button(bar,text="Открыть файл",command=open_file);choose.pack(side="right")
    make=ttk.Button(schedule_frame,text="Сформировать черновик",command=build,state="disabled");make.pack(side="left",pady=8)
    copy=ttk.Button(schedule_frame,text="Копировать в Finance Pro",command=copy_draft,state="disabled");copy.pack(side="right",pady=8)
    ttk.Label(shell,textvariable=status,wraplength=850).pack(anchor="w",pady=(8,0))
    root.mainloop()

if __name__=="__main__":
    main()
