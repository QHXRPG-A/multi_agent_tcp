# Blueprint POPO Callback Service Control Drawer

Date: 2026-06-09

## Summary

This archive records the Workbench UI work for managing plugin-level POPO
callback robot routes from the Blueprint window.

The new panel is a callback-service control surface. It is not an editor for the
current Blueprint document's `runtime.popo_entry` and is not the selected
AgentNode Inspector POPO forwarding editor.

## Drawer Placement

The Blueprint Workbench now has a left-side Blueprint Control drawer opened by:

- A toolbar button.
- A left-edge pull handle.

When the drawer is open, the Blueprint collaboration panel moves into the
drawer bottom. The old floating bottom-left collaboration panel is hidden while
the drawer owns that space.

This keeps plugin-level controls in the same visual layer as resident services
instead of attaching them to a selected node.

## POPO Callback Service Panel

The drawer includes a "POPO Callback Service" panel that shows:

- Callback service status.
- Callback URL template:
  `http://127.0.0.1:3100/popo/callback/<robot_app_key>`
- Legacy callback URL:
  `http://127.0.0.1:3100/popo/callback`
- The global callback robot route list.

Each robot row has an enable checkbox. Checked robots are accepted by the POPO
callback service. Unchecked robots remain saved but are rejected by the callback
service before forwarding.

The editor supports:

- Add robot.
- Edit robot app key and display name.
- Edit callback credentials.
- Delete robot.
- Toggle enabled state.

Credential fields use password inputs so app secret, callback token, and AES key
are not spread as plain visible text by default.

## Platform Bridge

The Workbench platform type includes:

- `BlueprintPopoRobot`
- `blueprintPopoServiceStatus`
- `listBlueprintPopoRobots`
- `saveBlueprintPopoRobot`
- `deleteBlueprintPopoRobot`
- `setBlueprintPopoRobotEnabled`

The plugin-served `entry.tsx` implementation maps those methods to singleton
service commands:

- `service.popoStatus`
- `blueprint.popo.robots`
- `blueprint.popo.robot.save`
- `blueprint.popo.robot.delete`
- `blueprint.popo.robot.enabled`

The panel refreshes service status and robot routes together, then normalizes
returned robot data before rendering.

## Interaction Boundary

This UI configures the POPO callback service's global robot allowlist. It does
not automatically create Blueprint sessions or change which Blueprint receives
a message.

Accepted callbacks still route to a Blueprint through the existing
`sourceIdentity.robotAppKey` and Blueprint/AgentNode `popo_entry` binding.

## Main Files

- `GuLiCode/packages/app/src/context/platform.tsx`
- `GuLiCode/packages/app/src/entry.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.tsx`
- `GuLiCode/packages/app/src/pages/session/blueprint-side-panel.test.ts`
- `GuLiCode/packages/app/src/i18n/en.ts`
- `GuLiCode/packages/app/src/i18n/zh.ts`
- `GuLiCode/packages/app/src/i18n/zht.ts`

## Verification

Commands run from `F:\src\Package\Script\Python\multi_agent_tcp\GuLiCode\packages\app`:

```powershell
bun test --preload ./happydom.ts ./src/pages/session/blueprint-side-panel.test.ts
bun run typecheck
```

Results:

- Blueprint side-panel tests passed: `22 pass`.
- Typecheck passed.

Packaged plugin verification from `F:\src\Package\Script\Python\multi_agent_tcp`:

```powershell
python plugins\gulicode-bp\scripts\install_personal_plugin.py --force
```

Results:

- Web assets and runtime wheel rebuilt and installed into
  `C:\Users\qiuhaoxuan\plugins\gulicode-bp`.
- Singleton Workbench service restarted at `http://127.0.0.1:10469`.
- Active Workbench URL after restart:
  `http://127.0.0.1:1474/Rjpcc3JjXFBhY2thZ2VcU2NyaXB0XFB5dGhvblxtdWx0aV9hZ2VudF90Y3A/blueprint-window/default`.

Known verification boundary: browser automation smoke was not repeated in this
final packaging pass. The implementation was covered by frontend tests,
typecheck, plugin rebuild, and service restart.
