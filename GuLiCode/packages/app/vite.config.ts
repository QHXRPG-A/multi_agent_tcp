import { defineConfig } from "vite"
import { VitePWA } from "vite-plugin-pwa"
import desktopPlugin from "./vite"

export default defineConfig({
  plugins: [
    desktopPlugin,
    VitePWA({
      registerType: "autoUpdate",
      manifestFilename: "site.webmanifest",
      includeAssets: [
        "favicon.ico",
        "favicon.svg",
        "favicon-96x96.png",
        "apple-touch-icon.png",
        "apple-touch-icon-v3.png",
      ],
      manifest: {
        id: "/",
        name: "GuLiCode",
        short_name: "GuLiCode",
        description: "GuLiCode mobile collaboration client",
        start_url: "/mobile",
        scope: "/",
        display: "standalone",
        orientation: "portrait-primary",
        theme_color: "#131010",
        background_color: "#f8f7f7",
        icons: [
          {
            src: "/web-app-manifest-192x192.png",
            sizes: "192x192",
            type: "image/png",
            purpose: "any maskable",
          },
          {
            src: "/web-app-manifest-512x512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any maskable",
          },
        ],
      },
      workbox: {
        cleanupOutdatedCaches: true,
        globPatterns: ["**/*.{js,css,html,ico,png,svg,woff,woff2}"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/auth\//, /^\/api\//, /^\/runs\//, /^\/stream(?:\/|\?|$)/],
        runtimeCaching: [
          {
            urlPattern: ({ url }: { url: URL }) =>
              url.pathname.startsWith("/auth/") ||
              url.pathname.startsWith("/api/") ||
              url.pathname.startsWith("/runs/") ||
              url.pathname === "/stream" ||
              url.pathname.startsWith("/stream/"),
            handler: "NetworkOnly",
          },
          {
            urlPattern: ({ request }: { request: Request }) =>
              request.destination === "image" ||
              request.destination === "font" ||
              request.destination === "style" ||
              request.destination === "script",
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "gulicode-static-assets",
              expiration: {
                maxEntries: 128,
                maxAgeSeconds: 7 * 24 * 60 * 60,
              },
            },
          },
        ],
      },
      devOptions: {
        enabled: false,
      },
    }),
  ] as any,
  server: {
    host: "0.0.0.0",
    allowedHosts: true,
    port: 3000,
  },
  build: {
    target: "esnext",
    // sourcemap: true,
  },
})
