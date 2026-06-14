#!/usr/bin/env python3
"""
Bulk Email Validator
Checks emails for valid syntax, domain existence, and mail server (MX) presence.
Does NOT perform final SMTP verification to avoid being blocked.
"""

import pandas as pd
import dns.resolver
import dns.exception
from email_validator import validate_email, EmailNotValidError
from tqdm import tqdm
import sys
import time
from pathlib import Path

# --- Configuration ---
# Add domains you know are safe but might fail checks. Add more as needed.
ALLOW_LIST_DOMAINS = {
    'aol.com', 'mail.com', 'yahoo.com', 'yahoo.co.uk', 'icloud.com', 'me.com',
    'mac.com', 'zoho.com', 'protonmail.com', 'protonmail.ch', 'gmx.com', 'gmx.net'
}
# Rate limiting: Add a small delay to avoid overwhelming DNS servers
# Set to 0.2 to 0.5 seconds for large lists to prevent temporary blocks
DNS_LOOKUP_DELAY_SECONDS = 0.2

# --- Helper Functions ---

def is_role_based(email: str) -> bool:
    """
    Checks if the email's local part (the part before the @) is a role-based address.
    These addresses (like info@, sales@) often bounce or go unread.
    """
    if not isinstance(email, str):
        return False
    local_part = email.split('@')[0].lower()
    # A set of common role-based prefixes
    role_prefixes = {
        'admin', 'administrator', 'contact', 'hello', 'info', 'inquiry',
        'marketing', 'noreply', 'no-reply', 'office', 'sales', 'support',
        'team', 'webmaster', 'hostmaster', 'postmaster'
    }
    return local_part in role_prefixes or any(local_part.startswith(p + '+') for p in role_prefixes)

def has_valid_mx(domain: str) -> bool:
    """
    Performs a DNS lookup to check if the domain has a valid MX (mail exchanger) record.
    This is a strong indicator that the domain is set up to receive email.
    """
    try:
        # Look up the MX records for the given domain
        mx_records = dns.resolver.resolve(domain, 'MX')
        # If we found any MX records, the domain can receive email
        return len(mx_records) > 0
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout):
        # The domain doesn't exist or has no mail server configured
        return False

def validate_single_email(email: str) -> dict:
    """
    The main validation logic for a single email address.
    Returns a dictionary with the validation result and a detailed reason.
    """
    if not isinstance(email, str):
        return {"email": email, "status": "invalid", "reason": "Not a string"}
    email = email.strip().lower()

    # Stage 1: Syntax and Deliverability Check (using email-validator library)
    try:
        # Check for basic syntax and domain existence
        # `check_deliverability` also checks if the domain has MX or A records
        validation = validate_email(email, check_deliverability=True)
        # Normalize the email (ensures consistent format)
        normalized_email = validation.normalized
        domain = normalized_email.split('@')[1]
    except EmailNotValidError as e:
        # The email failed the syntax or deliverability check
        return {"email": email, "status": "invalid", "reason": str(e)}

    # Stage 2: Role-based Address Check
    if is_role_based(normalized_email):
        return {"email": normalized_email, "status": "risky", "reason": "Role-based address"}

    # Stage 3: MX Record Lookup (fallback for some domains that might have been missed)
    if not has_valid_mx(domain) and domain not in ALLOW_LIST_DOMAINS:
        # Even if the domain has an A record, it might still not accept email without an MX record
        # However, we're performing a second check here as a more thorough validation.
        return {"email": normalized_email, "status": "invalid", "reason": f"Domain '{domain}' has no valid MX record"}

    # If all checks passed
    return {"email": normalized_email, "status": "valid", "reason": "Passed all checks"}

def process_file(input_file: str, output_file: str):
    """
    The main function that reads a CSV file, validates each email, and writes the results.
    It's designed to be memory-efficient for large files.
    """
    print(f"Loading emails from: {input_file}")
    try:
        # Read the CSV in chunks to avoid loading everything into memory at once
        chunk_iter = pd.read_csv(input_file, chunksize=10000)
    except FileNotFoundError:
        print(f"Error: File '{input_file}' not found. Please check the path and try again.")
        return

    all_results = []
    total_processed = 0
    # Using a progress bar from tqdm for visual feedback
    with tqdm(desc="Validating emails", unit=" emails") as pbar:
        for chunk in chunk_iter:
            # Assuming the email column is named 'Email'. Change 'Email' to your column's name if needed.
            # Common column names: 'email', 'Email', 'EMAIL', 'Email Address', 'e-mail'
            email_column = None
            for col in chunk.columns:
                if col.lower().startswith('email'):
                    email_column = col
                    break
            if email_column is None:
                print("Error: Could not find an 'Email' column in the CSV. Please ensure your file has a column like 'Email'.")
                return

            chunk_results = []
            for email in chunk[email_column]:
                # Skip blank or NaN entries
                if pd.isna(email):
                    chunk_results.append({"email": "", "status": "invalid", "reason": "Blank entry"})
                    continue

                result = validate_single_email(email)
                chunk_results.append(result)
                total_processed += 1
                pbar.update(1)

                # Add a small delay to avoid rate-limiting by DNS servers
                time.sleep(DNS_LOOKUP_DELAY_SECONDS)

            all_results.extend(chunk_results)

    # Create a DataFrame from the results
    results_df = pd.DataFrame(all_results)

    # Save the results to a new CSV file
    results_df.to_csv(output_file, index=False)
    print(f"\nValidation complete!")
    print(f"Total emails processed: {total_processed}")
    print(f"Results saved to: {output_file}")

    # Print a quick summary
    status_counts = results_df['status'].value_counts()
    print("\nSummary of results:")
    for status, count in status_counts.items():
        print(f"  {status}: {count}")

if __name__ == "__main__":
    # --- Script Entry Point ---
    # Check if the user provided the input and output file names as command line arguments
    if len(sys.argv) == 3:
        input_file = sys.argv[1]
        output_file = sys.argv[2]
    else:
        # Default file names if none were provided
        # Make sure to change 'leads.csv' to the actual name of your file
        input_file = "leads.csv"
        output_file = "validation_results.csv"
        print(f"Using default file names. To specify your own, run: python validator.py <input_file.csv> <output_file.csv>")
        print(f"Looking for input file: {input_file}")

    # Check if the input file exists, if not, show a helpful error
    if not Path(input_file).exists():
        print(f"\nError: Could not find the input file '{input_file}'.")
        print("Please make sure the file is in the same folder as this script.")
        print(f"If your file is named differently, run the script with:")
        print(f"python validator.py your_input_file.csv your_output_file.csv")
        sys.exit(1)

    # Call the main processing function
    process_file(input_file, output_file)
