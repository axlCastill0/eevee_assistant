import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],

  build: {
    // The kiosk is the only consumer and it is on the same box, so a single
    // bundle beats code splitting: no waterfall, no chunk requests.
    target: 'es2022',
    cssCodeSplit: false,
    // Fonts are inlined up to 4 KB by default; these woff2 files are larger,
    // so they stay as separate assets served by nginx with a long cache.
    assetsInlineLimit: 4096,
    sourcemap: false,
  },

  server: {
    host: true,
    port: 5173,
    // Dev-only: proxy to the backend so `npm run dev` behaves like the nginx
    // deployment. The API key is read from .env.local and never reaches the
    // browser bundle, because this rewrite happens in the Vite dev server.
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_API_URL || 'http://127.0.0.1:8000',
        changeOrigin: true,
        // The voice event stream is a WebSocket on this same prefix. Without
        // this the upgrade request is proxied as plain HTTP and the pill never
        // leaves 'unknown' in `npm run dev`.
        ws: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        configure: (proxy) => {
          const key = process.env.VITE_DEV_API_KEY

          proxy.on('proxyReq', (proxyReq) => {
            if (key) proxyReq.setHeader('X-API-Key', key)
          })

          // WebSocket upgrades go through a DIFFERENT event. 'proxyReq' never
          // fires for them, so without this the voice event socket reaches the
          // backend with no key and is closed with 1008 — which the browser
          // reports only as "closed before the connection is established".
          // nginx has no such split; this is a dev-server quirk only.
          proxy.on('proxyReqWs', (proxyReq) => {
            if (key) proxyReq.setHeader('X-API-Key', key)
          })
        },
      },
    },
  },
})
