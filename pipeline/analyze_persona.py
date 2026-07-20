#!/usr/bin/env python3
"""
Persona Analysis — "who is actually in this list?" (full population, no sampling)

Single streaming pass over EVERY row of clean_master.csv. Reports:
  * business vs free personal inbox
  * company-size split — for each contact, how many colleagues share its domain
    (this is what separates big-corporation employees from small-business owners)
  * top domains and top country TLDs
  * industry signal by keyword, with total coverage
  * a tiny random spot-check sample (clearly labelled — not used for any stat)

Every percentage below is computed over all rows, not a sample.

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

INDUSTRY_KEYWORDS = {
    "legal": ["law", "legal", "attorney", "lawyer", "injury", "counsel", "solicitor", "advocate", "barrister", "paralegal"],
    "real_estate": ["realty", "realestate", "realtor", "property", "properties", "homes", "mortgage", "estate", "brokerage", "remax", "century21", "kw."],
    "health_dental_clinic": ["dental", "dentist", "clinic", "ortho", "physio", "chiro", "wellness", "therapy", "rehab", "vision", "optical", "medic", "healthcare", "familyhealth", "veterin", "vet"],
    "beauty_salon": ["salon", "beauty", "spa", "hair", "nails", "skin", "aesthetic", "barber", "lash", "brow", "makeup"],
    "construction_trades": ["construction", "build", "contractor", "plumb", "roof", "hvac", "electric", "flooring", "renovation", "landscap", "painting", "concrete", "drywall", "remodel", "handyman", "fencing"],
    "automotive": ["auto", "motors", "cars", "garage", "tire", "collision", "automotive", "bodyshop", "detailing"],
    "food_hospitality": ["restaurant", "cafe", "catering", "pizza", "kitchen", "bakery", "grill", "bistro", "diner", "eatery"],
    "finance_accounting": ["cpa", "tax", "bookkeep", "accountancy", "accounting", "wealth", "advisory", "advisors", "financialplan"],
    "marketing_agency_design": ["marketing", "agency", "creative", "studio", "design", "seo", "advertis", "branding", "webdesign", "socialmedia"],
    "retail_ecommerce": ["boutique", "shopify", "ecommerce", "storefront", "retailers"],
    "trades_home_services": ["cleaning", "pest", "moving", "movers", "locksmith", "septic", "pool", "gutter", "windows", "doors"],
    "education_coaching": ["academy", "tutor", "learning", "coaching", "montessori", "daycare", "preschool", "drivingschool"],
    "fitness": ["fitness", "gym", "yoga", "pilates", "crossfit", "martialarts", "personaltrainer"],
    "nonprofit_org": ["foundation", "charity", "ngo", "nonprofit", "ministry", "church", "temple"],
}

SIZE_BANDS = [
    ("solo (1 contact)", 1, 1),
    ("micro (2-5)", 2, 5),
    ("small (6-20)", 6, 20),
    ("medium (21-100)", 21, 100),
    ("large (101-1000)", 101, 1000),
    ("enterprise (1000+)", 1001, 10**12),
]


def registrable(domain):
    parts = domain.split(".")
    return ".".join(parts[:-1]) if len(parts) >= 2 else domain


def run(input_path, out_path):
    total = 0
    freemail = 0
    domain_counts = Counter()
    tld_counts = Counter()
    industry_counts = Counter()
    matched_any = 0
    sample = []
    RESERVOIR = 30

    with open(input_path, "r", newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # header
        for row in reader:
            if not row:
                continue
            email = row[0].strip().lower()
            if "@" not in email:
                continue
            total += 1
            domain = email.split("@", 1)[1]
            domain_counts[domain] += 1
            tld_counts[domain.rsplit(".", 1)[-1]] += 1
            if domain in FREE_PROVIDERS:
                freemail += 1

            reg = registrable(domain)
            hit = False
            for industry, kws in INDUSTRY_KEYWORDS.items():
                if any(kw in reg for kw in kws):
                    industry_counts[industry] += 1
                    hit = True
            if hit:
                matched_any += 1

            if len(sample) < RESERVOIR:
                sample.append(email)
            else:
                j = random.randint(0, total - 1)
                if j < RESERVOIR:
                    sample[j] = email

    # Company-size split, derived from the full domain-frequency table (all rows).
    band_contacts = Counter()
    band_domains = Counter()
    for dom, n in domain_counts.items():
        for label, lo, hi in SIZE_BANDS:
            if lo <= n <= hi:
                band_contacts[label] += n
                band_domains[label] += 1
                break

    t = total or 1
    L = []
    L.append("=" * 66)
    L.append("PERSONA ANALYSIS  (full population — every row counted)")
    L.append("=" * 66)
    L.append(f"Input                : {input_path}")
    L.append(f"Contacts analyzed    : {total:,}")
    L.append(f"Business-domain      : {total-freemail:,} ({100*(total-freemail)/t:.1f}%)")
    L.append(f"Free personal inbox  : {freemail:,} ({100*freemail/t:.1f}%)")
    L.append(f"Distinct domains     : {len(domain_counts):,}")
    L.append("")
    L.append("COMPANY SIZE  (contacts grouped by how many share their domain):")
    L.append(f"  {'band':<22} {'contacts':>14} {'% of list':>10} {'domains':>12}")
    for label, lo, hi in SIZE_BANDS:
        c = band_contacts[label]
        L.append(f"  {label:<22} {c:>14,} {100*c/t:>9.1f}% {band_domains[label]:>12,}")
    L.append("")
    L.append("TOP 40 DOMAINS:")
    for dom, n in domain_counts.most_common(40):
        L.append(f"  {dom:<34}: {n:,}")
    L.append("")
    L.append("TOP 30 COUNTRY / TLD:")
    for tld, n in tld_counts.most_common(30):
        L.append(f"  .{tld:<12}: {n:,} ({100*n/t:.1f}%)")
    L.append("")
    L.append(f"INDUSTRY SIGNAL  (keyword match in domain; {100*matched_any/t:.1f}% of list matched at least one):")
    for ind, n in industry_counts.most_common():
        L.append(f"  {ind:<26}: {n:,} ({100*n/t:.1f}%)")
    L.append("")
    L.append(f"RANDOM SPOT-CHECK ({len(sample)} contacts — illustration only, not used for stats):")
    for e in sample:
        L.append(f"  {e}")
    L.append("=" * 66)

    text = "\n".join(L)
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
