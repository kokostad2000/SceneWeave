import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

/**
 * M00 前端工程配置。
 *
 * - dev server 仅监听本机；`/api` 代理到本机后端，避免前端直连公网（PRD 1.3）。
 * - 需要后端在 http://127.0.0.1:8000 运行；测试不依赖后端（fetch 被 mock）。
 */
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
  },
})
