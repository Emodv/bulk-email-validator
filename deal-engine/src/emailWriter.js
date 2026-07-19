const axios = require('axios');
const logger = require('./logger');

const MODEL = process.env.ANTHROPIC_MODEL || 'claude-sonnet-5';

// CASL compliance: every commercial email sent to a Canadian recipient must
// clearly identify the sender and provide a working unsubscribe mechanism.
// We append this footer to every draft so messages start compliant. Review it
// and make sure the details in .env are accurate before sending.
function complianceFooter() {
  const name = process.env.SENDER_NAME || 'Sender';
  const company = process.env.SENDER_COMPANY || '';
  const address = process.env.SENDER_MAILING_ADDRESS || '';
  const unsub = process.env.UNSUBSCRIBE_EMAIL || process.env.SENDER_EMAIL || '';

  const lines = [
    '',
    '--',
    [name, company].filter(Boolean).join(', ')
  ];
  if (address) lines.push(address);
  if (unsub) {
    lines.push('');
    lines.push(`Don't want to hear from me? Reply "unsubscribe" or email ${unsub} and I'll remove you immediately.`);
  }
  return lines.join('\n');
}

function fallbackEmail(prospect) {
  const firstName = prospect.firstName || 'there';
  const company = prospect.company || 'your firm';
  return {
    subject: `Quick question about ${company}`,
    body: `Hi ${firstName},\n\nI help personal injury firms with lead generation and Google Ads. Would you be open to a quick 15-minute chat?\n\nBest,\n${process.env.SENDER_NAME || 'Emod'}`
  };
}

async function generateEmail(prospect, enrichments = {}) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  const senderName = process.env.SENDER_NAME || 'Emod Vafa';
  const senderCompany = process.env.SENDER_COMPANY || 'Banoo Marketing';

  let email;

  if (!apiKey) {
    logger.warn('ANTHROPIC_API_KEY not set — using fallback email template');
    email = fallbackEmail(prospect);
    return { ...email, body: email.body + '\n' + complianceFooter() };
  }

  const prompt = `You are ${senderName}, founder of ${senderCompany}. Write a short, professional cold email (3-4 sentences) to a personal injury lawyer.

Prospect details:
- Name: ${prospect.firstName || ''} ${prospect.lastName || ''}
- Title: ${prospect.title || 'unknown'}
- Firm: ${prospect.company || 'unknown'}
- Domain: ${prospect.domain || 'unknown'}

Enrichments (use only if present and specific; never invent facts):
- Paid-search / ad-spend signal (0-5): ${enrichments.semrush?.ad_spend_score ?? 'unknown'}
- Practice areas: ${JSON.stringify(enrichments.scrape?.practice_areas ?? 'not found')}
- Team size: ${enrichments.scrape?.team_size ?? 'unknown'}
- About: ${enrichments.scrape?.about ?? 'unknown'}

Reference something specific and true about the firm if the enrichments provide it. If they run paid ads, you may mention lead quality/cost; if they appear to be growing, mention scaling. Keep it direct and human, no hype. End with a clear, low-friction CTA (e.g. "open to a quick 15-min chat?"). Do NOT add a signature or unsubscribe line — those are appended separately.

Respond with ONLY a JSON object, no other text: {"subject": "...", "body": "..."}`;

  try {
    const res = await axios.post(
      'https://api.anthropic.com/v1/messages',
      {
        model: MODEL,
        max_tokens: 500,
        messages: [{ role: 'user', content: prompt }]
      },
      {
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': apiKey,
          'anthropic-version': '2023-06-01'
        }
      }
    );

    const content = res.data.content[0].text;
    const jsonMatch = content.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error('No JSON object in model response');

    const parsed = JSON.parse(jsonMatch[0]);
    if (!parsed.subject || !parsed.body) throw new Error('Missing subject/body in model response');
    email = { subject: parsed.subject, body: parsed.body };
  } catch (e) {
    logger.error(`Claude error: ${e.response?.status || ''} ${e.message} — using fallback template`);
    email = fallbackEmail(prospect);
  }

  return { ...email, body: email.body + '\n' + complianceFooter() };
}

module.exports = { generateEmail };
