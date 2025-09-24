import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'
import {resolve} from 'path'

export default defineConfig({
   plugins: [
       tailwindcss(),
   ],
  // Build configuration
  build: {
    // Output directory for built assets
    outDir: resolve('./static/dist'),
    // Generate manifest for Django integration
    manifest: true,
    // Empty outDir before building
    emptyOutDir: true,
    // Configure rollup options
    rollupOptions: {
      // Define entry points
      input: {
        // 'main': resolve('./frontend/css/main.css'),
        // 'base': resolve('./frontend/js/base.js'),
        // 'dashboard': resolve('./frontend/js/dashboard.js')
      }
    }
  },
  // Development server configuration
  server: {
    // Allow external connections (for Docker)
    host: true,
    port: 5173,
    strictPort: true,
    cors: (origin, callback) => {
      if (!origin) // allow non-browser requests
          return callback(null, true)
      const allowed = new RegExp(process.env.VITE_CORS_ORIGIN || "\\.docker\\.test$").test(origin);
      callback(null, allowed)
    },
    // Configure HMR for Docker/Traefik
    allowedHosts: String(process.env.VITE_ALLOWED_HOSTS).split(",") || ['localhost']
  },
  // Base URL for assets - configurable for different environments
    // base:  process.env.VITE_BASE || "/static/"
    base: '/static/',
})