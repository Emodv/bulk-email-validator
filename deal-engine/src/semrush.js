const axios = require('axios');
const logger = require('./logger');

// Semrush domain analytics. Used as a coarse "is this firm investing in
// digital marketing?" signal to prioritize prospects. The Semrush API returns
// semicolon-delimited CSV text, not JSON.
async function getDomainAnalytics(domain) {
  if (!domain) return null;

  const apiKey = process.env.SEMRUSH_API_KEY;
  if (!apiKey) {
    logger.warn('SEMRUSH_API_KEY not set — skipping Semrush enrichment');
    return null;
  }

  try {
    const url = 'https://api.semrush.com/';
    const res = await axios.get(url, {
      params: {
        type: 'domain_rank',
        key: apiKey,
        domain,
        database: 'us',
        export_columns: 'Dn,Rk,Or,Ot,Oc,Ad,At,Ac'
      }
    });

    // Response is CSV: header line, then one data line.
    const lines = String(res.data).trim().split('\n');
    if (lines.length < 2) return null;

    const headers = lines[0].split(';');
    const values = lines[1].split(';');
    const row = {};
    headers.forEach((h, i) => { row[h.trim()] = values[i]; });

    const organicKeywords = parseInt(row['Organic Keywords'], 10) || 0;
    const paidKeywords = parseInt(row['Adwords Keywords'], 10) || 0;
    const paidTraffic = parseInt(row['Adwords Traffic'], 10) || 0;

    return {
      rank: parseInt(row['Rank'], 10) || null,
      organic_keywords: organicKeywords,
      paid_keywords: paidKeywords,
      // Coarse 0-5 signal: firms running paid search are higher priority.
      ad_spend_score: Math.min(5, Math.floor((paidKeywords + paidTraffic) / 50))
    };
  } catch (e) {
    logger.warn(`Semrush error for ${domain}: ${e.message}`);
    return null;
  }
}

module.exports = { getDomainAnalytics };
