import { defineConfig } from 'vite';
export default defineConfig(({mode})=>({base:mode==='pages'?'/ASUFC/':'/',server:{proxy:mode==='pages'?{}:{'/api':{target:'http://127.0.0.1:8000',rewrite:p=>p.replace(/^\/api/,'')}}}}));
