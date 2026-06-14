import os
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from celery import Celery
import pandas as pd
from pathlib import Path

app = FastAPI()

# Celery configuration using Redis (Railway will provide REDIS_URL)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)

# Directory for uploads and results
UPLOAD_DIR = Path("/tmp/uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# ------------------ Celery Task Definition ------------------
@celery_app.task(bind=True)
def validate_email_batch(self, file_path: str, email_column: str = "Email"):
    """Background task that processes the CSV and saves results."""
    from email_validator import validate_email, EmailNotValidError
    import dns.resolver

    def is_role_based(email):
        local = email.split('@')[0].lower()
        role_prefixes = {'info', 'sales', 'support', 'admin', 'contact', 'hello', 'noreply', 'no-reply', 'office', 'team', 'webmaster'}
        return local in role_prefixes

    def has_mx(domain):
        try:
            dns.resolver.resolve(domain, 'MX')
            return True
        except Exception:
            return False

    df = pd.read_csv(file_path)
    results = []
    total = len(df)
    for idx, row in df.iterrows():
        email = str(row[email_column]).strip().lower()
        try:
            validation = validate_email(email, check_deliverability=True)
            email = validation.normalized
            domain = email.split('@')[1]
            if is_role_based(email):
                status = "risky"
                reason = "Role-based address"
            elif not has_mx(domain):
                status = "invalid"
                reason = f"No MX record for {domain}"
            else:
                status = "valid"
                reason = "Passed all checks"
        except EmailNotValidError as e:
            status = "invalid"
            reason = str(e)
        except Exception as e:
            status = "invalid"
            reason = f"Unexpected error: {str(e)}"

        results.append({"email": email, "status": status, "reason": reason})
        self.update_state(state="PROGRESS", meta={"current": idx + 1, "total": total})

    results_df = pd.DataFrame(results)
    output_path = file_path.replace(".csv", "_results.csv")
    results_df.to_csv(output_path, index=False)
    return output_path

# ------------------ API Endpoints ------------------
@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files allowed")
    job_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{job_id}_{file.filename}"
    with open(file_path, "wb") as f:
        f.write(await file.read())
    task = validate_email_batch.delay(str(file_path))
    return {"job_id": task.id, "message": "Validation started"}

@app.get("/status/{job_id}")
def get_status(job_id: str):
    task = validate_email_batch.AsyncResult(job_id)
    if task.state == "PENDING":
        return {"status": "queued"}
    elif task.state == "PROGRESS":
        return {"status": "processing", "progress": task.info}
    elif task.state == "SUCCESS":
        return {"status": "completed", "download_url": f"/download/{job_id}"}
    else:
        return {"status": "failed", "error": str(task.info)}

@app.get("/download/{job_id}")
def download_result(job_id: str):
    task = validate_email_batch.AsyncResult(job_id)
    if task.state != "SUCCESS":
        raise HTTPException(status_code=404, detail="Result not ready")
    return FileResponse(task.result, filename="validation_results.csv")

@app.get("/")
def root():
    return {"message": "Bulk Email Validator API is running"}
