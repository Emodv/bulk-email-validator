const axios = require('axios');
const logger = require('./logger');

// Approximate bounding box for Ontario, Canada.
const ONTARIO_BOUNDS = { minLat: 41.7, maxLat: 56.9, minLng: -95.2, maxLng: -74.3 };

async function verifyLocation(address) {
  if (!address || !address.trim()) return { valid: false, reason: 'No address' };

  const apiKey = process.env.GOOGLE_MAPS_API_KEY;
  if (!apiKey) {
    logger.warn('GOOGLE_MAPS_API_KEY not set — skipping location verification');
    return { valid: true, reason: 'Location check skipped (no API key)' };
  }

  try {
    const url = `https://maps.googleapis.com/maps/api/geocode/json?address=${encodeURIComponent(address)}&key=${apiKey}`;
    const res = await axios.get(url);

    if (res.data.status === 'OK' && res.data.results.length > 0) {
      const loc = res.data.results[0].geometry.location;
      const inOntario =
        loc.lat >= ONTARIO_BOUNDS.minLat && loc.lat <= ONTARIO_BOUNDS.maxLat &&
        loc.lng >= ONTARIO_BOUNDS.minLng && loc.lng <= ONTARIO_BOUNDS.maxLng;

      return inOntario
        ? { valid: true, lat: loc.lat, lng: loc.lng }
        : { valid: false, reason: 'Outside Ontario' };
    }
    return { valid: false, reason: `Geocode API status: ${res.data.status}` };
  } catch (e) {
    logger.error(`Maps error: ${e.message}`);
    return { valid: false, reason: e.message };
  }
}

module.exports = { verifyLocation };
