const path = require('path');
const { defineConfig } = require('@playwright/test');

const PORT = 8766;

module.exports = defineConfig({
  testDir: __dirname,
  outputDir: path.join(__dirname, 'test-results'),
  reporter: 'list',
  workers: 1,
  use: { baseURL: `http://127.0.0.1:${PORT}`, viewport: { width: 1440, height: 900 } },
  webServer: {
    command: `python3 web/server.py --port ${PORT}`,
    cwd: path.dirname(__dirname),
    url: `http://127.0.0.1:${PORT}/web/`,
    reuseExistingServer: true,
  },
  projects: [
    { name: 'checks', testMatch: 'checks.spec.js', timeout: 30000 },
    { name: 'live', testMatch: 'live.spec.js', timeout: 360000 },
    {
      name: 'demo',
      testMatch: 'demo.spec.js',
      timeout: 240000,
      use: { video: { mode: 'on', size: { width: 1440, height: 900 } } },
    },
  ],
});
