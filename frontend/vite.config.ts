import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // T46：生产构建不产出 sourcemap；三方库拆包改善缓存粒度
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
