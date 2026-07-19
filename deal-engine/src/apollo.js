const axios = require('axios');
const logger = require('./logger');

async function searchProspects(limit = 10) {
  const apiKey = process.env.APOLLO_API_KEY;
  if (!apiKey) {
    logger.error('APOLLO_API_KEY not set — cannot search prospects');
    return [];
  }

  try {
    const response = await axios.post(
      'https://api.apollo.io/v1/people/search',
      {
        person_titles: ['personal injury lawyer', 'personal injury attorney', 'PI attorney'],
        person_locations: ['Ontario, Canada', 'Toronto, Canada', 'Mississauga, Canada', 'Brampton, Canada', 'Hamilton, Canada', 'Ottawa, Canada'],
        organization_num_employees_ranges: ['1,10', '11,20'],
        per_page: limit
      },
      {
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache',
          'X-Api-Key': apiKey
        }
      }
    );

    const people = response.data.people || [];
    logger.info(`Found ${people.length} prospects from Apollo`);
    return people.map(p => ({
      id: p.id,
      email: p.email,
      firstName: p.first_name,
      lastName: p.last_name,
      title: p.title,
      company: p.organization?.name,
      domain: p.organization?.primary_domain || p.organization?.domain,
      linkedin: p.linkedin_url,
      city: p.city,
      state: p.state,
      country: p.country
    }));
  } catch (e) {
    logger.error(`Apollo search error: ${e.response?.status || ''} ${e.message}`);
    return [];
  }
}

module.exports = { searchProspects };
