import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In dev (npm run dev) the API runs on :8000; in Docker nginx proxies /api to the backend.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://localhost:8000' } },
  test: { environment: 'node' },
})
