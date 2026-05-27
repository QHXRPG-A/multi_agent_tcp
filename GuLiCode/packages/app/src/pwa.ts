const PWA_UPDATE_EVENT = "gulicode:pwa-update"
const PWA_OFFLINE_READY_EVENT = "gulicode:pwa-offline-ready"

export type PwaUpdateDetail = {
  update: () => Promise<void>
}

export function registerPwa() {
  if (import.meta.env.DEV) return
  if (typeof window === "undefined" || typeof navigator === "undefined") return
  if (!("serviceWorker" in navigator)) return

  let updateSW: ((reloadPage?: boolean) => Promise<void>) | undefined

  void import("virtual:pwa-register").then(({ registerSW }) => {
    updateSW = registerSW({
      immediate: true,
      onNeedRefresh() {
        window.dispatchEvent(
          new CustomEvent<PwaUpdateDetail>(PWA_UPDATE_EVENT, {
            detail: {
              update: () => updateSW?.(true) ?? Promise.resolve(),
            },
          }),
        )
      },
      onOfflineReady() {
        window.dispatchEvent(new CustomEvent(PWA_OFFLINE_READY_EVENT))
      },
    })
  })
}

export const pwaEvents = {
  update: PWA_UPDATE_EVENT,
  offlineReady: PWA_OFFLINE_READY_EVENT,
} as const
