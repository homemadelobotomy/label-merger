from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import tempfile
import shutil
import os
import uuid

from merge_labels import merge_labels

app = FastAPI(title="Label Merger")

# Отдаём статику (index.html)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()


@app.post("/merge")
async def merge(
    barcodes: UploadFile = File(..., description="PDF со штрих-кодами"),
    assembly: UploadFile = File(..., description="Лист сборки"),
):
    # Проверяем типы файлов
    for f in (barcodes, assembly):
        if not f.filename.lower().endswith(".pdf"):
            raise HTTPException(400, detail=f"Файл '{f.filename}' должен быть PDF")

    # Работаем во временной директории — автоматически удалится после ответа
    tmp_dir = tempfile.mkdtemp()
    try:
        barcodes_path = os.path.join(tmp_dir, "barcodes.pdf")
        assembly_path = os.path.join(tmp_dir, "assembly.pdf")
        output_path   = os.path.join(tmp_dir, f"result_{uuid.uuid4().hex[:8]}.pdf")

        with open(barcodes_path, "wb") as f:
            shutil.copyfileobj(barcodes.file, f)
        with open(assembly_path, "wb") as f:
            shutil.copyfileobj(assembly.file, f)

        stats = merge_labels(barcodes_path, assembly_path, output_path)

        # Отдаём файл; background_tasks удалит tmp_dir после отправки
        return FileResponse(
            output_path,
            media_type="application/pdf",
            filename="merged_labels.pdf",
            headers={
                "X-Matched":     str(stats["matched"]),
                "X-Unmatched":   str(stats["unmatched"]),
                "X-Total-Pages": str(stats["total_pages"]),
            },
        )
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise HTTPException(500, detail=str(e))
