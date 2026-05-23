import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Electron 生产模式需要相对路径
  base: './',
  build: {
    outDir: 'dist',
  },
})
