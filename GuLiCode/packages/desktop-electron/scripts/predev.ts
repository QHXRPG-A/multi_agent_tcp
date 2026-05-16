import { $ } from "bun"

await $`bun ./scripts/copy-icons.ts ${process.env.OPENCODE_CHANNEL ?? "dev"}`

await $`bun ./scripts/build-opencode-node.ts`
