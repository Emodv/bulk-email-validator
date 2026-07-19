const dns = require('dns').promises;
const logger = require('./logger');

// Pre-send deliverability check: does the domain have MX records (i.e. can it
// receive mail at all)?
//
// NOTE: ImprovMX's API (/v3/domains/{domain}) only reports on domains inside
// YOUR ImprovMX account — it is not a general MX-lookup service, so it cannot
// validate arbitrary prospect domains. A direct DNS MX lookup is the correct,
// dependency-free way to do this pre-check, so that's what we use here.
async function validateMX(domain) {
  if (!domain) return false;
  try {
    const records = await dns.resolveMx(domain);
    const hasMX = Array.isArray(records) && records.length > 0;
    if (!hasMX) logger.info(`No MX records found for ${domain}`);
    return hasMX;
  } catch (e) {
    // ENOTFOUND / ENODATA => no mail server. Treat as undeliverable.
    logger.warn(`MX lookup failed for ${domain}: ${e.code || e.message}`);
    return false;
  }
}

module.exports = { validateMX };
