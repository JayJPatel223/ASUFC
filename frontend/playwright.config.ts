import {defineConfig} from '@playwright/test';
export default defineConfig({
 testDir:'./e2e',workers:1,retries:0,
 use:{baseURL:'http://127.0.0.1:5173',browserName:'chromium'},
 webServer:{command:'npm run dev',url:'http://127.0.0.1:5173',reuseExistingServer:false,timeout:60000}
});
