import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';

export default defineConfig({
  plugins: [tailwindcss(), react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'index.html'),
        editor: path.resolve(__dirname, 'editor.html'),
        me: path.resolve(__dirname, 'me.html'),
        'target-language': path.resolve(__dirname, 'target-language.html'),
        'web-console': path.resolve(__dirname, 'web-console.html'),
        login: path.resolve(__dirname, 'login.html'),
        'self-service': path.resolve(__dirname, 'self-service.html'),
        pat: path.resolve(__dirname, 'pat.html'),
      },
    },
  },
});
