import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the React dev server forwards /api to Django.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': process.env.VITE_PROXY_TARGET ?? 'http://127.0.0.1:8000',
    },
  },
})
