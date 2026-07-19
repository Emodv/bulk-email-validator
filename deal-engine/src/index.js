require('dotenv').config();
const cron = require('node-cron');
const logger = require('./logger');
const { searchProspects } = require('./apollo');
const { verifyLocation } = require('./maps');
const { getDomainAnalytics } = require('./semrush');
const { scrapeWebsite } = require('./scrapegraph');
const { validateMX } = require('./improvmx');
const { generateEmail } = require('./emailWriter');
const { createDraft } = require('./gmail');
const { isAlreadyContacted, markContacted } = require('./cache');

const DRAFTS_PER_RUN = parseInt(process.env.DRAFTS_PER_RUN, 10) || 2;
const PROSPECTS_PER_RUN = parseInt(process.env.PROSPECTS_PER_RUN, 10) || 10;
const CRON_SCHEDULE = process.env.CRON_SCHEDULE || '0 */3 * * *';

async function runPipeline() {
  logger.info('=== Starting deal engine run ===');
  const prospects = await searchProspects(PROSPECTS_PER_RUN);

  let draftsCreated = 0;
  for (const prospect of prospects) {
    if (draftsCreated >= DRAFTS_PER_RUN) break;

    if (!prospect.email) {
      logger.info(`Skipping ${prospect.company || prospect.id} — no email address`);
      continue;
    }

    // 1. De-dupe against prior runs.
    if (isAlreadyContacted(prospect.id)) {
      logger.info(`Skipping ${prospect.email} — already contacted`);
      continue;
    }

    // 2. Geo filter (only if we have location data to check).
    const addressParts = [prospect.city, prospect.state, prospect.country].filter(Boolean);
    if (addressParts.length > 0) {
      const location = await verifyLocation(addressParts.join(', '));
      if (!location.valid) {
        logger.info(`Skipping ${prospect.email} — location invalid: ${location.reason}`);
        continue;
      }
    }

    // 3. Deliverability pre-check.
    const hasMX = await validateMX(prospect.domain);
    if (!hasMX) {
      logger.info(`Skipping ${prospect.email} — no MX for ${prospect.domain}`);
      continue;
    }

    // 4-5. Enrich.
    const semrushData = await getDomainAnalytics(prospect.domain);
    const scrapeData = prospect.domain ? await scrapeWebsite(`https://${prospect.domain}`) : null;

    // 6. Generate the personalized draft (with compliance footer appended).
    const email = await generateEmail(prospect, { semrush: semrushData, scrape: scrapeData });

    // 7. Create a Gmail DRAFT — never auto-send. A human reviews before sending.
    try {
      await createDraft(prospect.email, email.subject, email.body);
    } catch (e) {
      logger.error(`Failed to create draft for ${prospect.email}: ${e.message}`);
      continue;
    }

    // 8. Record so we don't re-contact.
    markContacted(prospect.id);
    draftsCreated++;
    logger.info(`Drafted email for ${prospect.email}`);
  }

  logger.info(`=== Run complete, created ${draftsCreated} draft(s) ===`);
  return draftsCreated;
}

if (process.argv.includes('--test')) {
  runPipeline()
    .then(() => process.exit(0))
    .catch(err => {
      logger.error(`Run error: ${err.stack || err}`);
      process.exit(1);
    });
} else {
  cron.schedule(CRON_SCHEDULE, () => {
    runPipeline().catch(err => logger.error(`Cron error: ${err.stack || err}`));
  });
  logger.info(`Cron scheduled: "${CRON_SCHEDULE}". Waiting for next run…`);
}

module.exports = { runPipeline };
