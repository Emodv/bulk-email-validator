#!/usr/bin/env python3
"""
Deep Clean — Stage 1 of the list-hygiene pipeline.

Takes a raw contact CSV (any size — streamed in chunks) and produces:

  outdir/
    clean_master.csv          # deduped, structurally-valid rows (feeds the validator)
    rejects.csv               # everything removed, with a reason column
    segments/<segment>.csv    # clean rows split for targeting + <50MB validator chunks
    report.json               # counts at every stage
    report.txt                # human-readable summary

What this stage does (structural only — NO network / DNS):
  * normalizes each email (trim, lowercase, strip mailto:/quotes/whitespace)
  * drops structurally invalid addresses (regex + basic rules)
  * flags common typo/fake provider domains (yahool.com, gmial.com, ...)
  * flags disposable domains
  * flags role-based local parts (info@, sales@, ...)
  * de-duplicates on the normalized email (exact, case-insensitive)
  * segments the survivors by domain type and TLD

Deliverability (does the mailbox exist / MX) is Stage 2 — the existing
validator (validator.py / the Railway app). Keep the two stages separate so the
slow network checks only run on the small, clean set this stage produces.

Usage:
    python deep_clean.py INPUT.csv OUTDIR [--chunksize 50000] [--segment-rows 800000]

Memory note: de-dup keeps every unique normalized email in a Python set.
~6M uniques ≈ roughly 0.6–1.0 GB RAM. Fine on Colab / any modern laptop.
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict

# --- Classification data ------------------------------------------------------

# Structural email regex (deliberately conservative; final truth is Stage 2).
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# Common typo/harvest-garbage variants of the big free providers. These domains
# do not receive mail; the addresses are scraper noise.
TYPO_DOMAINS = {
    "gmial.com", "gmai.com", "gmil.com", "gamil.com", "gmail.co", "gmail.con",
    "gnail.com", "gmaill.com", "gmail.comm", "ymail.con",
    "yahool.com", "yahoo.con", "yaho.com", "yahooo.com",
    "yahoo-inc.com", "yahooinc.com", "yahooies.com",
    "yahooinc.solutions", "yahoo-inc.solutions",
    "hotmai.com", "hotmial.com", "hotmail.con", "hotmal.com", "hotmil.com",
    "outlok.com", "outlook.con", "iclod.com", "icloud.con",
}

# Minimal disposable/temp-mail seed list. Extend from a maintained list
# (e.g. github.com/disposable-email-domains) for production.
DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "temp-mail.org", "throwawaymail.com", "yopmail.com", "getnada.com",
    "trashmail.com", "sharklasers.com", "dispostable.com", "maildrop.cc",
    "fakeinbox.com", "mailnesia.com", "mintemail.com",
}

ROLE_PREFIXES = {
    "admin", "administrator", "contact", "hello", "info", "inquiry", "enquiries",
    "marketing", "noreply", "no-reply", "office", "sales", "support", "team",
    "webmaster", "hostmaster", "postmaster", "abuse", "billing", "help",
    "newsletter", "notifications", "donotreply",
}

FREE_PROVIDERS = {
    "gmail.com", "yahoo.com", "yahoo.ca", "yahoo.co.uk", "ymail.com",
    "hotmail.com", "hotmail.ca", "hotmail.co.uk", "outlook.com", "live.com",
    "msn.com", "aol.com", "icloud.com", "me.com", "mac.com", "gmx.com",
    "protonmail.com", "proton.me", "zoho.com", "rocketmail.com", "mail.com",
}

# --- Normalization ------------------------------------------------------------

def normalize_email(raw):
    """Return a cleaned, lowercased email, or '' if unrecoverable."""
    if raw is None:
        return ""
    e = str(raw).strip().strip('"').strip("'").strip()
    if not e or e.lower() == "nan":
        return ""
    # strip a leading mailto:
    if e.lower().startswith("mailto:"):
        e = e[7:]
    # remove all internal whitespace
    e = re.sub(r"\s+", "", e)
    # strip stray characters that scrapers leave right before the @
    e = e.replace("/@", "@").replace("\\@", "@")
    # collapse accidental double @
    if e.count("@") > 1:
        first = e.find("@")
        e = e[:first + 1] + e[first + 1:].replace("@", "")
    # trim leading/trailing dots on the whole thing
    e = e.strip(".")
    return e.lower()


def classify(email):
    """Return (status, reason). status == 'valid' means keep."""
    if not email:
        return "invalid_syntax", "Blank / unparseable"
    if not EMAIL_RE.match(email):
        return "invalid_syntax", "Fails email syntax"
    domain = email.split("@", 1)[1]
    local = email.split("@", 1)[0]
    if domain in TYPO_DOMAINS:
        return "typo_domain", f"Typo/fake provider domain: {domain}"
    if domain in DISPOSABLE_DOMAINS:
        return "disposable", f"Disposable domain: {domain}"
    if local in ROLE_PREFIXES or any(local.startswith(p + "+") for p in ROLE_PREFIXES):
        return "role_based", f"Role-based local part: {local}"
    return "valid", "Passed structural checks"


def segment_of(email):
    """Bucket a clean email for targeting."""
    domain = email.split("@", 1)[1]
    tld = domain.rsplit(".", 1)[-1]
    if domain in FREE_PROVIDERS:
        return "personal_freemail"
    # business/organization domains, split by TLD family
    if tld in ("edu",):
        return "edu"
    if tld in ("gov", "mil"):
        return "gov"
    if tld in ("org",):
        return "org"
    if tld in ("ca",):
        return "business_ca"
    return f"business_{tld}"


# --- Chunked CSV reading (dependency-free) ------------------------------------

def detect_email_column(header):
    for i, col in enumerate(header):
        if col and col.strip().lower().startswith("email"):
            return i
    return None


class SegmentWriter:
    """Writes rows to segments/<name>.csv, rolling to part files under a row cap."""

    def __init__(self, outdir, header, segment_rows):
        self.dir = os.path.join(outdir, "segments")
        os.makedirs(self.dir, exist_ok=True)
        self.header = header
        self.cap = segment_rows
        self._files = {}   # name -> (fh, writer, count, part)

    def write(self, name, row):
        entry = self._files.get(name)
        if entry is None or entry[2] >= self.cap:
            if entry is not None:
                entry[0].close()
                part = entry[3] + 1
            else:
                part = 0
            path = os.path.join(self.dir, f"{name}.part{part}.csv")
            fh = open(path, "w", newline="", encoding="utf-8")
            writer = csv.writer(fh)
            writer.writerow(self.header)
            entry = [fh, writer, 0, part]
            self._files[name] = entry
        entry[1].writerow(row)
        entry[2] += 1

    def close(self):
        for fh, *_ in self._files.values():
            fh.close()


def run(input_path, outdir, chunksize, segment_rows):
    os.makedirs(outdir, exist_ok=True)

    with open(input_path, "r", newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            print("Empty input file.")
            return

        email_idx = detect_email_column(header)
        if email_idx is None:
            print(f"ERROR: no 'Email' column found in header: {header}")
            sys.exit(1)

        out_header = ["email"] + [h for i, h in enumerate(header) if i != email_idx]

        clean_fh = open(os.path.join(outdir, "clean_master.csv"), "w", newline="", encoding="utf-8")
        clean_w = csv.writer(clean_fh)
        clean_w.writerow(out_header)

        rej_fh = open(os.path.join(outdir, "rejects.csv"), "w", newline="", encoding="utf-8")
        rej_w = csv.writer(rej_fh)
        rej_w.writerow(["email", "status", "reason"])

        segwriter = SegmentWriter(outdir, out_header, segment_rows)

        seen = set()
        stats = defaultdict(int)
        seg_counts = defaultdict(int)

        for row in reader:
            stats["total_rows"] += 1
            raw = row[email_idx] if email_idx < len(row) else ""
            email = normalize_email(raw)
            status, reason = classify(email)

            if status != "valid":
                stats[status] += 1
                rej_w.writerow([email, status, reason])
                continue

            if email in seen:
                stats["duplicate"] += 1
                rej_w.writerow([email, "duplicate", "Already seen earlier in file"])
                continue
            seen.add(email)

            rest = [row[i] if i < len(row) else "" for i in range(len(header)) if i != email_idx]
            out_row = [email] + rest
            clean_w.writerow(out_row)
            stats["clean"] += 1

            seg = segment_of(email)
            seg_counts[seg] += 1
            segwriter.write(seg, out_row)

    clean_fh.close()
    rej_fh.close()
    segwriter.close()

    report = {
        "input_file": input_path,
        "total_rows": stats["total_rows"],
        "clean_unique": stats["clean"],
        "removed": {
            "invalid_syntax": stats["invalid_syntax"],
            "typo_domain": stats["typo_domain"],
            "disposable": stats["disposable"],
            "role_based": stats["role_based"],
            "duplicate": stats["duplicate"],
        },
        "segments": dict(sorted(seg_counts.items(), key=lambda kv: -kv[1])),
    }
    with open(os.path.join(outdir, "report.json"), "w") as f:
        json.dump(report, f, indent=2)

    total = stats["total_rows"] or 1
    lines = [
        "=" * 60,
        "DEEP CLEAN REPORT",
        "=" * 60,
        f"Input file      : {input_path}",
        f"Total rows in   : {stats['total_rows']:,}",
        f"Clean & unique  : {stats['clean']:,}  ({100*stats['clean']/total:.1f}%)",
        "",
        "Removed:",
        f"  invalid syntax: {stats['invalid_syntax']:,}",
        f"  typo domains  : {stats['typo_domain']:,}",
        f"  disposable    : {stats['disposable']:,}",
        f"  role-based    : {stats['role_based']:,}",
        f"  duplicates    : {stats['duplicate']:,}",
        "",
        "Segments (clean rows):",
    ]
    for seg, n in sorted(seg_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {seg:<20}: {n:,}")
    lines.append("=" * 60)
    text = "\n".join(lines)
    with open(os.path.join(outdir, "report.txt"), "w") as f:
        f.write(text + "\n")
    print(text)


def main():
    ap = argparse.ArgumentParser(description="Deep clean a raw contact CSV.")
    ap.add_argument("input", help="Path to raw CSV")
    ap.add_argument("outdir", help="Output directory")
    ap.add_argument("--chunksize", type=int, default=50000, help="(reserved) rows per progress tick")
    ap.add_argument("--segment-rows", type=int, default=800000,
                    help="Max rows per segment part file (keeps parts <50MB for the validator)")
    args = ap.parse_args()
    run(args.input, args.outdir, args.chunksize, args.segment_rows)


if __name__ == "__main__":
    main()
