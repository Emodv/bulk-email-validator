import os
import io
import redis as redis_client
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, Response
from celery import Celery
import pandas as pd

app = FastAPI()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)

MAX_FILE_BYTES = 50 * 1024 * 1024  # 50MB (~1.5M emails per batch)

# ------------------ Celery Task ------------------
@celery_app.task(bind=True)
def validate_email_batch(self, csv_content: str):
    from email_validator import validate_email, EmailNotValidError
    import dns.resolver

    def is_role_based(email):
        local = email.split('@')[0].lower()
        role_prefixes = {
            'info', 'sales', 'support', 'admin', 'contact', 'hello',
            'noreply', 'no-reply', 'office', 'team', 'webmaster',
            'postmaster', 'hostmaster', 'marketing', 'enquiries'
        }
        return local in role_prefixes

    def has_mx(domain):
        try:
            dns.resolver.resolve(domain, 'MX')
            return True
        except Exception:
            return False

    df = pd.read_csv(io.StringIO(csv_content))

    # Auto-detect email column
    email_col = next((c for c in df.columns if c.lower().startswith('email')), None)
    if email_col is None:
        raise ValueError("No 'Email' column found. Your CSV must have a column named 'Email'.")

    results = []
    total = len(df)

    for idx, row in df.iterrows():
        raw = str(row[email_col]).strip()
        if not raw or raw.lower() == 'nan':
            results.append({"email": "", "status": "invalid", "confidence": "high", "reason": "Blank entry"})
            self.update_state(state="PROGRESS", meta={"current": idx + 1, "total": total})
            continue

        email = raw.lower()
        try:
            v = validate_email(email, check_deliverability=True)
            email = v.normalized
            domain = email.split('@')[1]
            if is_role_based(email):
                status, confidence, reason = "likely_junk", "low", "Role-based address (e.g. info@, sales@)"
            elif not has_mx(domain):
                status, confidence, reason = "invalid", "high", f"No MX record — {domain} cannot receive email"
            else:
                status, confidence, reason = "likely_valid", "high", "Passed all checks"
        except EmailNotValidError as e:
            status, confidence, reason = "invalid", "high", str(e)
        except Exception as e:
            status, confidence, reason = "uncertain", "low", f"Could not verify: {str(e)}"

        results.append({"email": email, "status": status, "confidence": confidence, "reason": reason})
        self.update_state(state="PROGRESS", meta={"current": idx + 1, "total": total})

    results_df = pd.DataFrame(results)

    # Write CSV to memory and store in Redis (2-hour expiry)
    buf = io.StringIO()
    results_df.to_csv(buf, index=False)
    r = redis_client.from_url(REDIS_URL)
    r.setex(f"result:{self.request.id}", 7200, buf.getvalue())

    counts = results_df['status'].value_counts().to_dict()
    return {"total": total, "counts": counts}

# ------------------ API Endpoints ------------------
@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")
    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Max 50MB per upload (~1.5M emails). Split larger files into chunks.")
    task = validate_email_batch.delay(content.decode('utf-8', errors='replace'))
    return {"job_id": task.id, "message": "Validation started"}

@app.get("/status/{job_id}")
def get_status(job_id: str):
    task = validate_email_batch.AsyncResult(job_id)
    if task.state == "PENDING":
        return {"status": "queued"}
    elif task.state == "PROGRESS":
        return {"status": "processing", "progress": task.info}
    elif task.state == "SUCCESS":
        return {"status": "completed", "summary": task.result}
    else:
        return {"status": "failed", "error": str(task.info)}

@app.get("/download/{job_id}")
def download_result(job_id: str):
    task = validate_email_batch.AsyncResult(job_id)
    if task.state != "SUCCESS":
        raise HTTPException(status_code=404, detail="Result not ready yet.")
    r = redis_client.from_url(REDIS_URL)
    csv_data = r.get(f"result:{job_id}")
    if not csv_data:
        raise HTTPException(status_code=410, detail="Results expired (2-hour limit). Please re-upload.")
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=validation_results.csv"}
    )

@app.get("/", response_class=HTMLResponse)
def root():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Bulk Email Validator — Free Tool</title>
  <meta name="description" content="Free bulk email validator. Upload a CSV and instantly check syntax, DNS, and MX records for every email address. Download clean results.">
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px}
    .card{background:#fff;border-radius:12px;padding:40px 36px;width:100%;max-width:480px;box-shadow:0 4px 20px rgba(0,0,0,0.08)}
    h1{font-size:22px;font-weight:700;margin-bottom:4px;color:#111}
    .sub{color:#666;font-size:13px;margin-bottom:28px;line-height:1.6}
    .checks{display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap}
    .check{font-size:11px;color:#555;background:#f5f5f5;padding:4px 10px;border-radius:20px}
    .upload-box{border:2px dashed #d0d0d0;border-radius:10px;padding:32px 16px;text-align:center;cursor:pointer;margin-bottom:14px;transition:all 0.2s}
    .upload-box:hover,.upload-box.drag-over{border-color:#111;background:#fafafa}
    .upload-box p{font-size:14px;color:#444;margin-bottom:4px}
    .upload-box span{font-size:12px;color:#aaa}
    #fileInput{display:none}
    #fileName{margin-top:10px;font-size:13px;color:#111;font-weight:600}
    .btn{width:100%;padding:14px;background:#111;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;transition:background 0.2s}
    .btn:hover{background:#333}
    .btn:disabled{background:#ccc;cursor:not-allowed}
    .section{margin-top:24px}
    .label{font-size:13px;color:#666;margin-bottom:8px}
    progress{width:100%;height:8px;border-radius:4px;appearance:none}
    progress::-webkit-progress-bar{background:#eee;border-radius:4px}
    progress::-webkit-progress-value{background:#111;border-radius:4px}
    .summary{display:flex;gap:8px;margin-top:16px;flex-wrap:wrap}
    .pill{padding:6px 14px;border-radius:20px;font-size:13px;font-weight:600}
    .pill-valid{background:#d4edda;color:#155724}
    .pill-junk{background:#fff3cd;color:#856404}
    .pill-invalid{background:#f8d7da;color:#721c24}
    .pill-uncertain{background:#e2e3e5;color:#383d41}
    .dl-btn{display:block;margin-top:14px;text-align:center;padding:14px;background:#111;color:#fff;text-decoration:none;border-radius:8px;font-size:15px;font-weight:600}
    .dl-btn:hover{background:#333}
    .error{margin-top:14px;font-size:13px;color:#c0392b;padding:10px;background:#fdf0f0;border-radius:6px}
    .hidden{display:none}
    footer{margin-top:24px;font-size:12px;color:#aaa;text-align:center}
  </style>
</head>
<body>
  <div class="card">
    <h1>Bulk Email Validator</h1>
    <p class="sub">Upload a CSV file with an <strong>Email</strong> column. We check every address and give you a clean results file — free, no signup needed.</p>

    <div class="checks">
      <span class="check">✓ Syntax check</span>
      <span class="check">✓ DNS lookup</span>
      <span class="check">✓ MX record</span>
      <span class="check">✓ Role-based detection</span>
    </div>

    <div class="upload-box" id="uploadBox" onclick="document.getElementById('fileInput').click()">
      <p>Drag & drop your CSV here, or click to browse</p>
      <span>CSV only · Max 50MB (~1.5M emails)</span>
      <input type="file" id="fileInput" accept=".csv" onchange="onFileSelected(this)">
      <div id="fileName"></div>
    </div>

    <button class="btn" id="btn" onclick="startValidation()" disabled>Validate Emails</button>

    <div id="progressSection" class="section hidden">
      <p class="label" id="statusText">Uploading...</p>
      <progress id="bar" max="100" value="0"></progress>
    </div>

    <div id="summarySection" class="summary hidden"></div>
    <a id="dlBtn" class="dl-btn hidden" href="#">Download Results CSV</a>
    <div id="errorMsg" class="error hidden"></div>
  </div>

  <footer>Free · No signup · Results expire after 2 hours</footer>

  <script>
    let jobId = null, poll = null;

    const box = document.getElementById('uploadBox');
    box.addEventListener('dragover', e => { e.preventDefault(); box.classList.add('drag-over'); });
    box.addEventListener('dragleave', () => box.classList.remove('drag-over'));
    box.addEventListener('drop', e => {
      e.preventDefault(); box.classList.remove('drag-over');
      const f = e.dataTransfer.files[0];
      if (f && f.name.endsWith('.csv')) { setFile(f); }
    });

    function setFile(f) {
      const dt = new DataTransfer(); dt.items.add(f);
      document.getElementById('fileInput').files = dt.files;
      document.getElementById('fileName').textContent = f.name;
      document.getElementById('btn').disabled = false;
      ['dlBtn','summarySection','errorMsg'].forEach(id => document.getElementById(id).classList.add('hidden'));
    }

    function onFileSelected(input) {
      if (input.files[0]) setFile(input.files[0]);
    }

    async function startValidation() {
      const file = document.getElementById('fileInput').files[0];
      if (!file) return;
      document.getElementById('btn').disabled = true;
      ['dlBtn','summarySection','errorMsg'].forEach(id => document.getElementById(id).classList.add('hidden'));
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
        document.getElementById('statusText').textContent = 'Queued — starting validation...';
        poll = setInterval(checkStatus, 2500);
      } catch(e) { showError(e.message); }
    }

    async function checkStatus() {
      try {
        const res = await fetch('/status/' + jobId);
        const data = await res.json();
        if (data.status === 'processing' && data.progress) {
          const p = data.progress;
          const pct = Math.round((p.current / p.total) * 100);
          document.getElementById('bar').value = pct;
          document.getElementById('statusText').textContent =
            `Validating... ${p.current.toLocaleString()} / ${p.total.toLocaleString()} emails (${pct}%)`;
        } else if (data.status === 'completed') {
          clearInterval(poll);
          document.getElementById('bar').value = 100;
          document.getElementById('statusText').textContent = 'Done!';
          showSummary(data.summary);
          document.getElementById('dlBtn').href = '/download/' + jobId;
          document.getElementById('dlBtn').classList.remove('hidden');
          document.getElementById('btn').disabled = false;
        } else if (data.status === 'failed') {
          clearInterval(poll); showError('Validation failed: ' + data.error);
        }
      } catch(e) { clearInterval(poll); showError('Connection lost. Please try again.'); }
    }

    function showSummary(s) {
      if (!s || !s.counts) return;
      const c = s.counts;
      const map = {
        'likely_valid':   ['pill-valid',     'Likely Valid'],
        'likely_junk':    ['pill-junk',      'Likely Junk'],
        'invalid':        ['pill-invalid',   'Invalid'],
        'uncertain':      ['pill-uncertain', 'Uncertain'],
      };
      const sec = document.getElementById('summarySection');
      sec.innerHTML = '';
      for (const [key, [cls, label]] of Object.entries(map)) {
        if (c[key]) {
          const el = document.createElement('span');
          el.className = 'pill ' + cls;
          el.textContent = `${label}: ${c[key].toLocaleString()}`;
          sec.appendChild(el);
        }
      }
      sec.classList.remove('hidden');
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
