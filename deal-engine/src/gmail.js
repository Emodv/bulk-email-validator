const { google } = require('googleapis');
const logger = require('./logger');

let gmailClient = null;

function getGmail() {
  if (gmailClient) return gmailClient;

  const { GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN } = process.env;
  if (!GOOGLE_CLIENT_ID || !GOOGLE_CLIENT_SECRET || !GOOGLE_REFRESH_TOKEN) {
    throw new Error('Gmail OAuth env vars missing (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN)');
  }

  const oAuth2Client = new google.auth.OAuth2(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET);
  oAuth2Client.setCredentials({ refresh_token: GOOGLE_REFRESH_TOKEN });
  gmailClient = google.gmail({ version: 'v1', auth: oAuth2Client });
  return gmailClient;
}

// RFC 2047 encode a header value so non-ASCII subjects survive transit.
function encodeHeader(value) {
  // eslint-disable-next-line no-control-regex
  if (/^[\x00-\x7F]*$/.test(value)) return value;
  return `=?UTF-8?B?${Buffer.from(value, 'utf8').toString('base64')}?=`;
}

async function createDraft(to, subject, body) {
  const gmail = getGmail();

  const fromName = process.env.SENDER_NAME;
  const fromEmail = process.env.SENDER_EMAIL;
  const from = fromName && fromEmail ? `${encodeHeader(fromName)} <${fromEmail}>` : fromEmail;

  const headers = [];
  if (from) headers.push(`From: ${from}`);
  headers.push(`To: ${to}`);
  headers.push(`Subject: ${encodeHeader(subject)}`);
  headers.push('Content-Type: text/plain; charset="UTF-8"');
  headers.push('MIME-Version: 1.0');

  const message = headers.join('\n') + '\n\n' + body;

  const encoded = Buffer.from(message)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');

  try {
    const res = await gmail.users.drafts.create({
      userId: 'me',
      requestBody: { message: { raw: encoded } }
    });
    logger.info(`Draft created for ${to}, draftId=${res.data.id}`);
    return res.data;
  } catch (e) {
    logger.error(`Gmail draft error for ${to}: ${e.message}`);
    throw e;
  }
}

module.exports = { createDraft };
