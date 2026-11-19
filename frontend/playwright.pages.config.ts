import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e-pages',workers:1,use:{baseURL:'http://127.0.0.1:4173/ASUFC/',browserName:'chromium'},webServer:{command:'vite preview --host 127.0.0.1 --port 4173 --strictPort --mode pages',url:'http://127.0.0.1:4173/ASUFC/',reuseExistingServer:false,timeout:60000}});
