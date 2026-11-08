import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev'de /api -> task-api (8000), /api/v1/assistant -> assistant-service (8100).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Sira onemli: daha ozel yol once (asistan servisi), sonra genel task-api
      '/api/v1/assistant': 'http://localhost:8100',
      '/api': 'http://localhost:8000',
    },
  },
})
