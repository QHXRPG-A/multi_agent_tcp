# Vendored Ryven components

This directory contains source code copied from the upstream Ryven project for local modification inside `multi_agent_tcp`.

Sources:
- Ryven repository: https://github.com/leon-thomm/Ryven
- Upstream author: Leon Thomm
- Upstream license for copied files: MIT

Vendored subtrees:
- `vendor/ryven/ryven/` copied from `Ryven/ryven-editor/ryven/`
- `vendor/ryvencore_qt/ryvencore_qt/` copied from `Ryven/ryvencore-qt/ryvencore_qt/`

Included license files:
- `vendor/ryven/LICENSE`
- `vendor/ryven/LICENSE.editor`
- `vendor/ryven/LICENSE.ryvencore_qt`

Notes:
- This vendored copy intentionally excludes virtual environments, build metadata, and pip-installed dependencies.
- Upstream `README.md` notes that the repository-level project is MIT, while the separate underlying `ryvencore` library is LGPL-2.1. This vendoring operation did not copy the external `ryvencore` package source into this repository.
- Local modifications may be applied on top of this vendored snapshot.
