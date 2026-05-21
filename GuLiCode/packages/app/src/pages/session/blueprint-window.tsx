import { decode64 } from "@/utils/base64"
import { usePlatform } from "@/context/platform"
import { BlueprintSidePanel, type BlueprintPlanningSubmitInput } from "@/pages/session/blueprint-side-panel"
import { useSessionLayout } from "@/pages/session/session-layout"

export default function BlueprintWindowPage() {
  const platform = usePlatform()
  const { params } = useSessionLayout()
  const projectDirectory = () => decode64(params.dir) ?? "global"

  const submitPlanningTask = async (input: BlueprintPlanningSubmitInput) => {
    if (!platform.submitBlueprintWindowPlanning) return false
    const result = await platform
      .submitBlueprintWindowPlanning(projectDirectory(), params.id, input)
      .catch(() => ({ accepted: false }))
    return result.accepted
  }

  return (
    <div data-blueprint-popout-window class="h-dvh w-screen overflow-hidden bg-[#071019]">
      <BlueprintSidePanel
        floating
        onDock={() => {
          void platform.dockBlueprintWindow?.(projectDirectory(), params.id)
        }}
        onBlueprintPlanningSubmit={submitPlanningTask}
      />
    </div>
  )
}
