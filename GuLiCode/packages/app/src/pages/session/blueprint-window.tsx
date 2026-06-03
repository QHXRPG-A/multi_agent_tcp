import { useParams } from "@solidjs/router"
import { BlueprintSidePanel } from "@/pages/session/blueprint-side-panel"

export default function BlueprintWindowPage() {
  const params = useParams()
  const workbenchInitialBlueprintId = () => (window.__GULICODE_BP__ ? params.id : undefined)

  return (
    <div data-blueprint-popout-window class="h-dvh w-screen overflow-hidden bg-[#071019]">
      <BlueprintSidePanel
        floating
        initialBlueprintId={workbenchInitialBlueprintId()}
      />
    </div>
  )
}
