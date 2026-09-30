import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {readFileSync} from 'node:fs';
const token=readFileSync('.env','utf8').match(/^SERVICE_TOKEN=(.*)$/m)?.[1]?.trim();
export default defineConfig({plugins:[react()],server:{proxy:{'/api':{target:'http://127.0.0.1:8000',headers:{'x-service-token':token||'','x-app-origin':'http://127.0.0.1:5173'}}}}});
