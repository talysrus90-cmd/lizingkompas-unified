/* Local browser import: file contents stay in existing textarea until manual submit. */
(() => {
  "use strict";
  const fileInput=document.getElementById("schedule-file");
  const button=document.getElementById("schedule-file-read");
  const status=document.getElementById("schedule-file-status");
  const encoding=document.getElementById("schedule-file-encoding");
  const field=document.getElementById("id_schedule");
  const complete=document.getElementById("id_complete");
  if (!fileInput || !button || !status || !encoding || !field || !complete) return;
  let ticket=0;
  fileInput.addEventListener("change",()=>{++ticket;status.textContent="";});
  encoding.addEventListener("change",()=>{++ticket;status.textContent="";});
  button.addEventListener("click",async()=>{
    const id=++ticket;
    const file=fileInput.files[0];
    if (!file || !/\.(csv|tsv|txt)$/i.test(file.name) || !file.size || file.size>131072) {
      status.textContent="Выберите CSV, TSV или TXT до 128 КиБ.";
      return;
    }
    try {
      const value=new TextDecoder(encoding.value,{fatal:true}).decode(await file.arrayBuffer());
      if(id!==ticket)return;
      if(!value.trim() || value.length>32000 || value.includes("\0"))throw Error("invalid input");
      field.value=value;
      complete.checked=false;
      status.textContent="Текст загружен в поле. Сверьте график с оригиналом перед сохранением.";
      field.focus();
    } catch (_) {
      if(id===ticket)status.textContent="Не удалось прочитать файл. Проверьте кодировку и формат.";
    }
  });
  field.addEventListener("input",()=>{++ticket;complete.checked=false;});
})();
