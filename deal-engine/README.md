# Deal Engine

Autonomous outbound opportunity engine. On a schedule it:

1. Pulls prospects from **Apollo** (personal-injury lawyers, small Ontario firms)
2. Filters by geography (**Google Maps** geocoding → Ontario bounding box)
3. Runs a deliverability pre-check (**DNS MX lookup**)
4. Enriches with a marketing-spend signal (**Semrush**) and firm context (**ScrapeGraphAI**)
5. Writes a personalized email with **Claude**
6. Creates a **Gmail draft** — for you to review and send manually

> **It never auto-sends.** Every message is created as a draft so a human
> reviews it before it goes out.

---

## Setup

```bash
cd deal-engine
npm install
cp .env.example .env
# then edit .env and fill in your real keys
```

### Fill in `.env`

`.env` is git-ignored. **Never** put real keys in `.env.example` (that file is
committed). See the comments in `.env.example` for every variable.

### Generate a Gmail refresh token

1. Go to the [OAuth 2.0 Playground](https://developers.google.com/oauthplayground/).
2. Click the gear (top right) → "Use your own OAuth credentials" → paste your
   `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
3. In the scope list, authorize `https://www.googleapis.com/auth/gmail.compose`
   (or `.../gmail.drafts`).
4. Exchange the authorization code for tokens and copy the **refresh token**
   into `GOOGLE_REFRESH_TOKEN` in `.env`.

## Run

```bash
npm test     # single run, logs to console + logs/run.log
npm start    # starts the cron scheduler (default: every 3 hours)
```

Tune behavior in `.env`: `DRAFTS_PER_RUN`, `PROSPECTS_PER_RUN`, `CRON_SCHEDULE`.

---

## Compliance (read this)

You are sending commercial email to recipients in Ontario, Canada, so
**CASL** applies. Each draft includes a footer that identifies the sender and
offers an unsubscribe path (configured via `SENDER_NAME`, `SENDER_COMPANY`,
`SENDER_MAILING_ADDRESS`, `UNSUBSCRIBE_EMAIL`). Before sending, make sure:

- You have consent or an existing business relationship with the recipient,
  **or** are relying on a valid CASL exemption.
- The identification and unsubscribe details in the footer are accurate.
- You honor unsubscribe requests promptly.

This tool creates drafts for human review; you are responsible for what you
actually send.

## Security

- Real secrets live **only** in `.env` (git-ignored). `cache.json` and
  `logs/` are also git-ignored.
- If a key is ever pasted into a chat, doc, or commit, **rotate it** — treat
  it as compromised.
