#!/usr/bin/env python3
"""
Persona Analysis — "who is actually in this list?"

Single streaming pass over clean_master.csv. Answers, from the data itself:
  * how many are business-domain vs free personal inboxes
  * the top email domains (where these people's mail actually lives)
  * industry signal — keyword frequency in the domain name
  * how personal the data is (share of rows with a real first name)
  * a random, unbiased sample of contacts to eyeball

Writes persona_report.txt next to the input and prints it.

Usage:
    python analyze_persona.py CLEAN_MASTER.csv [OUT_persona_report.txt]

Stdlib only.
"""

import csv
import os
import random
import sys
from collections import Counter

FREE_PROVIDERS = {
    "gmail.com", "yahoo.com", "yahoo.ca", "yahoo.co.uk", "ymail.com",
    "hotmail.com", "hotmail.ca", "hotmail.co.uk", "outlook.com", "live.com",
    "msn.com", "aol.com", "icloud.com", "me.com", "mac.com", "gmx.com",
    "protonmail.com", "proton.me", "zoho.com", "rocketmail.com", "mail.com",
}

# Industry -> substrings we look for inside the domain name.
INDUSTRY_KEYWORDS = {
    "legal": ["law", "legal", "attorney", "lawyer", "injury", "counsel", "solicitor", "advocate", "barrister"],
    "real_estate": ["realty", "realestate", "realtor", "property", "properties", "homes", "mortgage", "estate", "brokerage"],
    "health_medical": ["dental", "dentist", "clinic", "health", "medical", "med", "care", "pharma", "physio", "chiro", "wellness", "therapy", "rehab", "vision", "optical"],
    "beauty_salon": ["salon", "beauty", "spa", "hair", "nails", "skin", "aesthetic", "barber"],
    "construction_trades": ["construction", "build", "contractor", "plumbing", "roofing", "hvac", "electric", "flooring", "renovation", "landscap", "painting", "concrete", "drywall"],
    "automotive": ["auto", "motors", "cars", "garage", "tire", "collision", "automotive"],
    "food_hospitality": ["restaurant", "cafe", "catering", "pizza", "kitchen", "bakery", "grill", "bistro", "hotel", "hospitality"],
    "finance_accounting": ["account", "cpa", "tax", "finance", "financial", "insurance", "bookkeep", "wealth", "capital", "invest", "advisor", "advisory"],
    "marketing_agency_design": ["marketing", "agency", "media", "design", "studio", "creative", "digital", "seo", "advertis", "brand"],
    "retail_ecommerce": ["shop", "store", "boutique", "market", "retail", "commerce"],
    "tech_it": ["tech", "software", "systems", "solutions", "cloud", "data", "digital", "cyber", "network", "consulting"],
    "education": ["academy", "school", "college", "institute", "education", "tutor", "learning", "training", "coach"],
    "fitness": ["fitness", "gym", "yoga", "pilates", "sport", "crossfit", "athletic"],
    "nonprofit_org": ["foundation", "charity", "ngo", "nonprofit", "association", "society", "ministry", "church"],
}


def registrable(domain):
    """Best-effort 'name' part of a domain for keyword matching (drop the TLD)."""
    parts = domain.split(".")
    if len(parts) >= 2:
        return ".".join(parts[:-1])
    return domain


def run(input_path, out_path):
    total = 0
    freemail = 0
    business = 0
    with_name = 0
    domain_counts = Counter()
    industry_counts = Counter()
    sample = []          # reservoir sample of (email, name)
    RESERVOIR = 40

    with open(input_path, "r", newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        # locate name column (first column after 'email' that looks like a first name)
        name_idx = None
        if header:
            for i, h in enumerate(header):
                if h and "first" in h.strip().lower():
                    name_idx = i
                    break

        for row in reader:
            if not row:
                continue
            email = row[0].strip().lower()
            if "@" not in email:
                continue
            total += 1
            domain = email.split("@", 1)[1]
            domain_counts[domain] += 1

            if domain in FREE_PROVIDERS:
                freemail += 1
            else:
                business += 1

            name = ""
            if name_idx is not None and name_idx < len(row):
                name = row[name_idx].strip()
            if name:
                with_name += 1

            reg = registrable(domain)
            for industry, kws in INDUSTRY_KEYWORDS.items():
                if any(kw in reg for kw in kws):
                    industry_counts[industry] += 1

            # reservoir sampling for an unbiased eyeball set
            if len(sample) < RESERVOIR:
                sample.append((email, name))
            else:
                j = random.randint(0, total - 1)
                if j < RESERVOIR:
                    sample[j] = (email, name)

    t = total or 1
    lines = []
    lines.append("=" * 64)
    lines.append("PERSONA ANALYSIS")
    lines.append("=" * 64)
    lines.append(f"Input                : {input_path}")
    lines.append(f"Contacts analyzed    : {total:,}")
    lines.append(f"Business-domain      : {business:,} ({100*business/t:.1f}%)")
    lines.append(f"Free personal inbox  : {freemail:,} ({100*freemail/t:.1f}%)")
    lines.append(f"Rows with a name     : {with_name:,} ({100*with_name/t:.1f}%)")
    lines.append(f"Distinct domains     : {len(domain_counts):,}")
    lines.append("")
    lines.append("TOP 60 DOMAINS (where their mail lives):")
    for dom, n in domain_counts.most_common(60):
        lines.append(f"  {dom:<32}: {n:,}")
    lines.append("")
    lines.append("INDUSTRY SIGNAL (domain-name keyword matches; a contact can match >1):")
    for ind, n in industry_counts.most_common():
        lines.append(f"  {ind:<26}: {n:,} ({100*n/t:.1f}%)")
    lines.append("")
    lines.append(f"RANDOM SAMPLE ({len(sample)} contacts):")
    for email, name in sample:
        lines.append(f"  {email:<44} {name}")
    lines.append("=" * 64)

    text = "\n".join(lines)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_persona.py CLEAN_MASTER.csv [out.txt]")
        sys.exit(1)
    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(inp) or ".", "persona_report.txt")
    run(inp, out)


if __name__ == "__main__":
    main()
