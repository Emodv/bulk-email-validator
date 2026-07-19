const axios = require('axios');
const logger = require('./logger');

// Scrape a firm's website for context we can use to personalize the draft.
async function scrapeWebsite(url) {
  if (!url) return null;

  const apiKey = process.env.SCRAPEGRAPHAI_API_KEY;
  if (!apiKey) {
    logger.warn('SCRAPEGRAPHAI_API_KEY not set — skipping website enrichment');
    return null;
  }

  try {
    const response = await axios.post(
      'https://api.scrapegraphai.com/v1/smartscraper',
      {
        website_url: url,
        user_prompt:
          'Extract the following as JSON: practice_areas (array), team_size (number or string), ' +
          'about (short summary), recent_news (array of recent updates or announcements).'
      },
      {
        headers: {
          'Content-Type': 'application/json',
          'SGAI-APIKEY': apiKey
        },
        timeout: 60000
      }
    );

    return response.data?.result || response.data?.data || response.data || null;
  } catch (e) {
    logger.warn(`ScrapeGraphAI error for ${url}: ${e.message}`);
    return null;
  }
}

module.exports = { scrapeWebsite };
