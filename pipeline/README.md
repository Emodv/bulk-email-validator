# List-Hygiene Pipeline

Three stages, run in order. Stage 1 lives here; Stage 2 is the existing
validator; Stage 3 is targeting.

```
raw 6M CSV
   │
   ▼  Stage 1 — deep_clean.py   (structural, offline, no network)
clean_master.csv  +  segments/*.csv  +  report
   │
   ▼  Stage 2 — validator.py / Railway app   (DNS + MX, per segment)
likely_valid emails
   │
   ▼  Stage 3 — segment for real, compliant targeting
```

## Stage 1 — Deep clean

Normalizes, removes junk (invalid syntax, typo/fake domains, disposable,
role-based), **de-duplicates**, and **segments** by domain type. No network
calls, so it's fast and safe to run on the full file.

```bash
python3 deep_clean.py "Untitled Workbook - All 6 M Emails.csv" out/
```

Outputs in `out/`:
- `clean_master.csv` — deduped, structurally valid rows
- `rejects.csv` — everything removed + the reason
- `segments/<segment>.part0.csv …` — clean rows split by segment and capped
  at 800k rows/file so each part is **under the validator's 50 MB limit**
- `report.txt` / `report.json` — counts at every stage

Segments produced: `personal_freemail`, `business_ca`, `business_com`,
`org`, `edu`, `gov`, `business_<tld>`, …

No dependencies — pure Python 3 standard library.

### Running on the full 6M file

**Option A — Google Colab (recommended, no local setup):**
```python
from google.colab import drive; drive.mount('/content/drive')
!python3 deep_clean.py "/content/drive/MyDrive/<folder>/Untitled Workbook - All 6 M Emails.csv" /content/out
```
(Copy `deep_clean.py` into the Colab session first, or `!git clone` this repo.)

**Option B — Local:** download the 152 MB CSV from Drive, then run the command
above. Needs ~1 GB RAM free (the de-dup set holds every unique email).

## Stage 2 — Validate (existing tool)

Feed each `segments/*.csv` part into the validator, which does the slow
network checks (DNS + MX + role) and tags `likely_valid` / `invalid` /
`likely_junk`:
- Web app: upload each part at the Railway URL, or
- CLI: `python3 ../validator.py out/segments/business_ca.part0.csv validated_ca.csv`

Running validation **after** the clean means the network checks only touch the
small, deduped set — much faster and gentler on DNS.

## Stage 3 — Target

Use the segments to focus outreach on the defensible, business-domain buckets
rather than personal freemail inboxes. This is where the Deal Engine
(`../deal-engine`) takes over, one reviewed draft at a time.
