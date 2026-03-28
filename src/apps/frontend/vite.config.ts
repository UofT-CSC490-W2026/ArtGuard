/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import path from 'path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  assetsInclude: ['**/*.svg', '**/*.csv'],
  build: {
    sourcemap: false,
    minify: 'esbuild',
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router'],
          ui: ['lucide-react', 'sonner'],
        },
      },
    },
    chunkSizeWarningLimit: 600,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.{test,spec}.{ts,tsx}'],
    /** Avoid cross-file localStorage races in Auth tests */
    fileParallelism: false,
    coverage: {
      provider: 'v8',
      /** json-summary: badge step; lcov: orgoro/coverage PR comments in CI */
      reporter: ['text', 'html', 'json-summary', 'lcov'],
      include: ['src/app/**/*.{ts,tsx}'],
      exclude: ['src/app/components/ui/**'],
      thresholds: {
        lines: 100,
        statements: 100,
        branches: 86,
        functions: 93,
      },
    },
  },
})
