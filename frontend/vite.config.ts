import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

/**
 * M00 前端工程配置。
 *
 * - dev server 仅监听本机；`/api` 代理到本机后端，避免前端直连公网（PRD 1.3）。
 * - 默认连接本机 8000；可用 SCENEWEAVE_DEV_API_PORT 指向另一独立后端。
 * - 测试不依赖后端（fetch 被 mock）。
 */
const apiPort = process.env.SCENEWEAVE_DEV_API_PORT ?? '8000'
if (!/^\d+$/.test(apiPort) || Number(apiPort) < 1 || Number(apiPort) > 65535) {
  throw new Error('SCENEWEAVE_DEV_API_PORT must be a TCP port')
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${apiPort}`,
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
