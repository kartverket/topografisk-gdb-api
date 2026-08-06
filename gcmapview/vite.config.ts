import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/geocomponents-api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/geocomponents-api/, '')
      },
      '/gcimport-api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/gcimport-api/, '')
      }
    }
  }
});
