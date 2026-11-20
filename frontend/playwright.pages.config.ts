import { defineConfig } from '@playwright/test';

const previewURL = 'http://127.0.0.1:4173/ASUFC/';
const liveURL = process.env.ASUFC_PAGES_URL;

export default defineConfig({
  testDir: './e2e-pages',
  workers: 1,
  use: { baseURL: liveURL ? new URL(liveURL.replace(/\/?$/, '/')).href : previewURL, browserName: 'chromium', serviceWorkers: 'block' },
  webServer: liveURL ? undefined : {
    command: 'vite preview --host 127.0.0.1 --port 4173 --strictPort --mode pages',
    url: previewURL,
    reuseExistingServer: false,
    timeout: 60000,
  },
});
