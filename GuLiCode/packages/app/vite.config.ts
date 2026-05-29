import { defineConfig } from "vite"
import { VitePWA } from "vite-plugin-pwa"
import desktopPlugin from "./vite"

const DEFAULT_DEV_PORT = 3040
const DEFAULT_COLLABORATION_PROXY_TARGET = "http://127.0.0.1:8787"

function readCollaborationProxyTarget() {
  return (
    process.env.GULICODE_COLLABORATION_API_URL ??
    process.env.VITE_COLLABORATION_API_URL ??
    DEFAULT_COLLABORATION_PROXY_TARGET
  ).replace(/\/+$/, "")
}

function readDevPort() {
  const raw = process.env.GULICODE_APP_PORT ?? process.env.PORT
  if (!raw) return DEFAULT_DEV_PORT

  const port = Number(raw)
  if (Number.isInteger(port) && port > 0 && port < 65536) return port
  return DEFAULT_DEV_PORT
}

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
        description: "GuLiCode 移动协作客户端",
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
    port: readDevPort(),
    proxy: {
      "/api": {
        target: readCollaborationProxyTarget(),
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    target: "esnext",
    // sourcemap: true,
  },
})
