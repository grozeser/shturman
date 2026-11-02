import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const api = process.env.API_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
    plugins: [react()],
    server: {
        host: '127.0.0.1',
        port: 5190,
        proxy: { '/api': api, '/health': api },
    },
});
