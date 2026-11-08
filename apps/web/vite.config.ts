import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev'de /api -> task-api (8000), /api/v1/assistant -> assistant-service (8100).
// TASK_API_PROXY / ASSISTANT_PROXY: ikinci bir kopyayi baska portlarda calistirmak icin.
declare const process: { env: Record<string, string | undefined> } // @types/node yok

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Sira onemli: daha ozel yol once (asistan servisi), sonra genel task-api
      '/api/v1/assistant': process.env.ASSISTANT_PROXY ?? 'http://localhost:8100',
      '/api': process.env.TASK_API_PROXY ?? 'http://localhost:8000',
    },
  },
})
