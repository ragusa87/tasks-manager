import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'
import {resolve} from 'path'

export default defineConfig(({ command }) => ({
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
        'base': resolve('./frontend/js/base.js'),
        'batch': resolve('./frontend/js/batch.js'),
        'dashboard': resolve('./frontend/js/dashboard.js'),
        'charts': resolve('./frontend/js/charts.js'),
        'offload': resolve('./frontend/js/offload.js'),
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
  // Base URL for assets. Builds go to static/dist and are served from
  // /static/dist/ — the runtime preload helper for dynamic imports builds
  // asset URLs from this value, so it must include the dist segment or
  // lazily-loaded chunk CSS 404s. The dev server serves from its own root,
  // where django-vite expects /static/<source path>.
    base: command === 'build' ? '/static/dist/' : '/static/',
}))
