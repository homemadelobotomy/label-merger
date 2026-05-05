from fastapi import FastAPI, File, UploadFile, HTTPException, Depends
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import tempfile
import shutil
import os
import uuid
import secrets

from merge_labels import merge_labels

app = FastAPI(title="Label Merger")
security = HTTPBasic()

# ─── Авторизация ──────────────────────────────────────────────────────────
# Логин и пароль берутся из переменных окружения.
# Задаются в docker-compose.yml в секции environment (или в .env файле).
# Если переменные не заданы — используются значения по умолчанию.
AUTH_USER = os.getenv("AUTH_USER", "admin")
AUTH_PASS = os.getenv("AUTH_PASS", "changeme")


def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(credentials.username.encode(), AUTH_USER.encode())
    ok_pass = secrets.compare_digest(credentials.password.encode(), AUTH_PASS.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=401,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ─── Маршруты ─────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def root(username: str = Depends(require_auth)):
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()


@app.post("/merge")
async def merge(
    barcodes: UploadFile = File(..., description="PDF со штрих-кодами"),
    assembly: UploadFile = File(..., description="Лист сборки"),
    username: str = Depends(require_auth),
):
    for f in (barcodes, assembly):
        if not f.filename.lower().endswith(".pdf"):
            raise HTTPException(400, detail=f"Файл '{f.filename}' должен быть PDF")

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
