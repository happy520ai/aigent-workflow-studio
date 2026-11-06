/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // T50：vitest（jsdom 环境）；T46：生产构建不产出 sourcemap + 三方拆包
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.{ts,tsx}'],
  },
  build: {
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          react_vendor: ['react', 'react-dom'],
          lucide: ['lucide-react'],
        },
      },
    },
  },
})
