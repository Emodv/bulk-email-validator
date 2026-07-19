const fs = require('fs');
const path = require('path');

const CACHE_FILE = path.join(__dirname, '../cache.json');

let cache = {};
if (fs.existsSync(CACHE_FILE)) {
  try {
    cache = JSON.parse(fs.readFileSync(CACHE_FILE, 'utf8'));
  } catch (e) {
    // Corrupt cache — start fresh rather than crashing the run.
    cache = {};
  }
}

function saveCache() {
  fs.writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 2));
}

function isAlreadyContacted(prospectId) {
  if (!prospectId) return false;
  return !!cache[prospectId];
}

function markContacted(prospectId) {
  if (!prospectId) return;
  cache[prospectId] = Date.now();
  saveCache();
}

module.exports = { isAlreadyContacted, markContacted };
