import { useParams } from "@solidjs/router"
import { decode64 } from "@/utils/base64"
import { usePlatform } from "@/context/platform"
import { BlueprintSidePanel } from "@/pages/session/blueprint-side-panel"

export default function BlueprintWindowPage() {
  const platform = usePlatform()
  const params = useParams()
  const projectDirectory = () => decode64(params.dir) ?? "global"
  const workbenchInitialBlueprintId = () => (window.__GULICODE_BP__ ? params.id : undefined)

  return (
    <div data-blueprint-popout-window class="h-dvh w-screen overflow-hidden bg-[#071019]">
      <BlueprintSidePanel
        floating
        initialBlueprintId={workbenchInitialBlueprintId()}
        onDock={() => {
          void platform.dockBlueprintWindow?.(projectDirectory(), params.id)
        }}
      />
    </div>
  )
}
