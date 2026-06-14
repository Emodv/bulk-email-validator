import os
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
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
                status = "likely_junk"
                confidence = "low"
                reason = "Role-based address"
            elif not has_mx(domain):
                status = "invalid"
                confidence = "high"
                reason = f"No MX record for {domain}"
            else:
                status = "likely_valid"
                confidence = "high"
                reason = "Passed all checks"
        except EmailNotValidError as e:
            status = "invalid"
            confidence = "high"
            reason = str(e)
        except Exception as e:
            status = "uncertain"
            confidence = "low"
            reason = f"Could not verify: {str(e)}"

        results.append({"email": email, "status": status, "confidence": confidence, "reason": reason})
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

@app.get("/", response_class=HTMLResponse)
def root():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Bulk Email Validator</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: sans-serif; background: #f4f4f4; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }
    .card { background: #fff; border-radius: 10px; padding: 36px 32px; width: 100%; max-width: 460px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
    h1 { font-size: 20px; margin-bottom: 6px; }
    .sub { color: #666; font-size: 13px; margin-bottom: 28px; line-height: 1.5; }
    .upload-box { border: 2px dashed #ccc; border-radius: 8px; padding: 28px 16px; text-align: center; cursor: pointer; margin-bottom: 14px; transition: border-color 0.2s, background 0.2s; }
    .upload-box:hover, .upload-box.drag-over { border-color: #111; background: #f9f9f9; }
    .upload-box p { font-size: 14px; color: #555; }
    .upload-box span { font-size: 12px; color: #999; }
    #fileInput { display: none; }
    #fileName { margin-top: 8px; font-size: 13px; color: #333; font-weight: 600; }
    button { width: 100%; padding: 13px; background: #111; color: #fff; border: none; border-radius: 7px; font-size: 15px; cursor: pointer; }
    button:disabled { background: #bbb; cursor: not-allowed; }
    .section { margin-top: 22px; }
    .label { font-size: 13px; color: #555; margin-bottom: 6px; }
    progress { width: 100%; height: 10px; border-radius: 5px; appearance: none; }
    progress::-webkit-progress-bar { background: #eee; border-radius: 5px; }
    progress::-webkit-progress-value { background: #111; border-radius: 5px; }
    .badges { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
    .badge { padding: 5px 12px; border-radius: 20px; font-size: 13px; font-weight: 600; }
    .valid   { background: #d4edda; color: #155724; }
    .risky   { background: #fff3cd; color: #856404; }
    .invalid { background: #f8d7da; color: #721c24; }
    .dl-btn { display: block; margin-top: 16px; text-align: center; padding: 13px; background: #111; color: #fff; text-decoration: none; border-radius: 7px; font-size: 15px; }
    .dl-btn:hover { background: #333; }
    .error { margin-top: 14px; font-size: 13px; color: #c0392b; }
    .hidden { display: none; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Bulk Email Validator</h1>
    <p class="sub">Upload a CSV with an <strong>Email</strong> column. The tool checks syntax, DNS, and MX records — then gives you a clean results file.</p>

    <div class="upload-box" id="uploadBox" onclick="document.getElementById('fileInput').click()">
      <p>Drag & drop a CSV file here, or click to browse</p>
      <span>Only .csv files supported</span>
      <input type="file" id="fileInput" accept=".csv" onchange="onFileSelected(this)">
      <div id="fileName"></div>
    </div>

    <button id="btn" onclick="startValidation()" disabled>Validate Emails</button>

    <div id="progressSection" class="section hidden">
      <p class="label" id="statusText">Uploading...</p>
      <progress id="bar" max="100" value="0"></progress>
    </div>

    <div id="badgeSection" class="badges hidden"></div>

    <a id="dlBtn" class="dl-btn hidden" href="#">Download Results CSV</a>

    <p id="errorMsg" class="error hidden"></p>
  </div>

  <script>
    let jobId = null;
    let poll = null;

    // Drag and drop
    const box = document.getElementById('uploadBox');
    box.addEventListener('dragover', e => { e.preventDefault(); box.classList.add('drag-over'); });
    box.addEventListener('dragleave', () => box.classList.remove('drag-over'));
    box.addEventListener('drop', e => {
      e.preventDefault();
      box.classList.remove('drag-over');
      const file = e.dataTransfer.files[0];
      if (file && file.name.endsWith('.csv')) {
        const dt = new DataTransfer();
        dt.items.add(file);
        document.getElementById('fileInput').files = dt.files;
        onFileSelected(document.getElementById('fileInput'));
      }
    });

    function onFileSelected(input) {
      const name = input.files[0]?.name || '';
      document.getElementById('fileName').textContent = name;
      document.getElementById('btn').disabled = !name;
      document.getElementById('dlBtn').classList.add('hidden');
      document.getElementById('badgeSection').classList.add('hidden');
      document.getElementById('errorMsg').classList.add('hidden');
    }

    async function startValidation() {
      const file = document.getElementById('fileInput').files[0];
      if (!file) return;

      document.getElementById('btn').disabled = true;
      document.getElementById('dlBtn').classList.add('hidden');
      document.getElementById('badgeSection').classList.add('hidden');
      document.getElementById('errorMsg').classList.add('hidden');
      document.getElementById('progressSection').classList.remove('hidden');
      document.getElementById('statusText').textContent = 'Uploading...';
      document.getElementById('bar').value = 0;

      const form = new FormData();
      form.append('file', file);

      try {
        const res = await fetch('/upload/', { method: 'POST', body: form });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Upload failed');
        jobId = data.job_id;
        document.getElementById('statusText').textContent = 'Validating emails...';
        poll = setInterval(checkStatus, 2500);
      } catch (e) { showError(e.message); }
    }

    async function checkStatus() {
      try {
        const res = await fetch('/status/' + jobId);
        const data = await res.json();

        if (data.status === 'processing' && data.progress) {
          const p = data.progress;
          const pct = Math.round((p.current / p.total) * 100);
          document.getElementById('bar').value = pct;
          document.getElementById('statusText').textContent = `Validating... ${p.current.toLocaleString()} / ${p.total.toLocaleString()} emails`;
        } else if (data.status === 'completed') {
          clearInterval(poll);
          document.getElementById('bar').value = 100;
          document.getElementById('statusText').textContent = 'Done!';
          document.getElementById('dlBtn').href = '/download/' + jobId;
          document.getElementById('dlBtn').classList.remove('hidden');
          document.getElementById('btn').disabled = false;
        } else if (data.status === 'failed') {
          clearInterval(poll);
          showError('Validation failed: ' + data.error);
        }
      } catch (e) { clearInterval(poll); showError('Connection lost. Please try again.'); }
    }

    function showError(msg) {
      document.getElementById('errorMsg').textContent = msg;
      document.getElementById('errorMsg').classList.remove('hidden');
      document.getElementById('progressSection').classList.add('hidden');
      document.getElementById('btn').disabled = false;
    }
  </script>
</body>
</html>"""
