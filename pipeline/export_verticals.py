#!/usr/bin/env python3
"""
Export by vertical — split clean_master.csv into one CSV per industry.

Two streaming passes over clean_master.csv:
  pass 1: count contacts per domain (to tag company size)
  pass 2: classify each contact by industry keyword(s) and write it into
          every matching vertical file, tagged with domain size.

Output (in OUTDIR/verticals/):
  <vertical>.csv           columns: email, domain, domain_contacts, size_band
  _unclassified.csv        contacts matching no industry keyword (optional, big)
  _summary.txt             row counts per vertical, and per size band within it

A contact can appear in more than one vertical (e.g. "dentalcarelaw" — rare).
size_band lets you later keep only owners (solo/micro/small) and drop big corps.

Usage:
    python export_verticals.py CLEAN_MASTER.csv OUTDIR [--include-unclassified]

Stdlib only.
"""

import argparse
import csv
import os
import sys
from collections import Counter, defaultdict

INDUSTRY_KEYWORDS = {
    "legal": ["law", "legal", "attorney", "lawyer", "injury", "counsel", "solicitor", "advocate", "barrister", "paralegal"],
    "real_estate": ["realty", "realestate", "realtor", "property", "properties", "homes", "mortgage", "estate", "brokerage", "remax", "century21"],
    "health_dental_clinic": ["dental", "dentist", "clinic", "ortho", "physio", "chiro", "wellness", "therapy", "rehab", "vision", "optical", "medic", "healthcare", "familyhealth", "veterin"],
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
    ("solo", 1, 1),
    ("micro", 2, 5),
    ("small", 6, 20),
    ("medium", 21, 100),
    ("large", 101, 1000),
    ("enterprise", 1001, 10**12),
]


def registrable(domain):
    parts = domain.split(".")
    return ".".join(parts[:-1]) if len(parts) >= 2 else domain


def size_band(n):
    for label, lo, hi in SIZE_BANDS:
        if lo <= n <= hi:
            return label
    return "unknown"


def industries_for(domain):
    reg = registrable(domain)
    return [ind for ind, kws in INDUSTRY_KEYWORDS.items() if any(kw in reg for kw in kws)]


def run(input_path, outdir, include_unclassified):
    vdir = os.path.join(outdir, "verticals")
    os.makedirs(vdir, exist_ok=True)

    # pass 1: domain frequency
    domain_counts = Counter()
    with open(input_path, "r", newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        next(reader, None)
        for row in reader:
            if row and "@" in row[0]:
                domain_counts[row[0].strip().lower().split("@", 1)[1]] += 1

    # pass 2: classify + write
    writers = {}
    files = {}
    counts = defaultdict(int)
    band_counts = defaultdict(lambda: Counter())

    def writer_for(name):
        if name not in writers:
            f = open(os.path.join(vdir, f"{name}.csv"), "w", newline="", encoding="utf-8")
            w = csv.writer(f)
            w.writerow(["email", "domain", "domain_contacts", "size_band"])
            writers[name] = w
            files[name] = f
        return writers[name]

    with open(input_path, "r", newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh)
        next(reader, None)
        for row in reader:
            if not row or "@" not in row[0]:
                continue
            email = row[0].strip().lower()
            domain = email.split("@", 1)[1]
            n = domain_counts[domain]
            band = size_band(n)
            inds = industries_for(domain)
            if not inds:
                if include_unclassified:
                    writer_for("_unclassified").writerow([email, domain, n, band])
                    counts["_unclassified"] += 1
                continue
            for ind in inds:
                writer_for(ind).writerow([email, domain, n, band])
                counts[ind] += 1
                band_counts[ind][band] += 1

    for f in files.values():
        f.close()

    # summary
    lines = ["=" * 60, "VERTICAL EXPORT SUMMARY", "=" * 60,
             f"Source: {input_path}", ""]
    order = ["solo", "micro", "small", "medium", "large", "enterprise"]
    for ind in sorted(counts, key=lambda k: -counts[k]):
        if ind == "_unclassified":
            continue
        bc = band_counts[ind]
        owners = bc["solo"] + bc["micro"] + bc["small"]
        lines.append(f"{ind:<26}: {counts[ind]:>8,}   (owners solo+micro+small = {owners:,})")
        lines.append("      " + "  ".join(f"{b}:{bc[b]:,}" for b in order if bc[b]))
    if "_unclassified" in counts:
        lines.append("")
        lines.append(f"{'_unclassified':<26}: {counts['_unclassified']:>8,}")
    lines.append("=" * 60)
    text = "\n".join(lines)
    with open(os.path.join(vdir, "_summary.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)
    print(f"\nWrote {len([k for k in counts if k!='_unclassified'])} vertical files to {vdir}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("outdir")
    ap.add_argument("--include-unclassified", action="store_true",
                    help="also write _unclassified.csv (large — ~90%% of the list)")
    args = ap.parse_args()
    run(args.input, args.outdir, args.include_unclassified)


if __name__ == "__main__":
    main()
