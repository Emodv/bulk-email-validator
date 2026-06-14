# Bulk Email Validator

A high-performance, open-source email validator that can process millions of email addresses efficiently. It performs syntax checks, MX record lookups, and SMTP verification to determine email deliverability.

## Features

- **Multi-stage validation**: Syntax → Domain/MX → Role-based detection
- **Batch processing**: Memory-efficient for large CSV files
- **Rate limiting**: Avoids getting blocked by DNS servers
- **Detailed output**: Separate valid/invalid/risky categories with reasons
- **Progress tracking**: Real-time progress bar with `tqdm`

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/emodv/bulk-email-validator.git
   cd bulk-email-validator
   ```

2. Install the required packages:
   ```bash
   pip install -r requirements.txt
   ```
   Or install as a Python package:
   ```bash
   python setup.py install
   ```

## Usage

Place your email list in a CSV file with an `Email` column. Then run:

```bash
python validator.py input.csv output.csv
```

If you don't specify file names, the script will look for `leads.csv` and output to `validation_results.csv`.

### Example Input (`leads.csv`)

```
Email
john@example.com
jane@test.org
info@company.net
```

### Example Output (`validation_results.csv`)

| email | status | reason |
|---|---|---|
| john@example.com | valid | Passed all checks |
| jane@test.org | invalid | Domain has no valid MX record |
| info@company.net | risky | Role-based address |

## Configuration

Edit the constants at the top of `validator.py`:

- `ALLOW_LIST_DOMAINS`: Domains that should always pass validation
- `DNS_LOOKUP_DELAY_SECONDS`: Delay between DNS lookups (increase if getting blocked)

## Important Notes

- Processing millions of emails can take days — use the rate limiting delay!
- This tool is designed for local or server use, not as a web app
- No validation method is 100% accurate due to SMTP "courtesy accepts"

## Processing Large Lists (6M+ contacts)

- Split your file into chunks of 500,000–1,000,000 emails each
- The tool automatically handles chunked reading (`chunksize=10000`) for memory efficiency
- Review output statuses: **valid** (safe to contact), **risky** (role-based, use with caution), **invalid** (exclude from campaigns)
- With a 0.2s delay per email, 6 million emails takes roughly 14 days — consider running on a dedicated server

## License

MIT License — free for personal and commercial use.

## Contributing

Pull requests are welcome! Feel free to open an issue for bugs or feature requests.
