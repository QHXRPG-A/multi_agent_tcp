from __future__ import annotations

from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QWidget,
)

from ryven.gui_env import *

from .nodes import AgentNode, BlueprintEnd, BlueprintStart


class AgentNodeMainWidget(NodeMainWidget, QWidget):
    def __init__(self, params):
        NodeMainWidget.__init__(self, params)
        QWidget.__init__(self)

        self._loading = False

        self.agent_id_edit = QLineEdit()
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setFixedHeight(64)
        self.cli_kind_combo = QComboBox()
        self.cli_kind_combo.addItems(["codex"])
        self.model_edit = QLineEdit()
        self.cwd_edit = QLineEdit()
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 24 * 60 * 60)
        self.timeout_spin.setSingleStep(30)
        self.command_edit = QLineEdit()
        self.prompt_via_file_combo = QComboBox()
        self.prompt_via_file_combo.addItems(["auto", "always", "never"])
        self.external_check = QCheckBox()
        self.execution_mode_combo = QComboBox()
        self.execution_mode_combo.addItems(["blocking", "nonblocking"])
        self.write_scope_edit = QPlainTextEdit()
        self.write_scope_edit.setFixedHeight(44)
        self.artifact_scope_edit = QPlainTextEdit()
        self.artifact_scope_edit.setFixedHeight(44)
        self.extra_env_edit = QPlainTextEdit()
        self.extra_env_edit.setFixedHeight(52)
        self.adapter_options_edit = QPlainTextEdit()
        self.adapter_options_edit.setFixedHeight(52)
        self.skill_mode_combo = QComboBox()
        self.skill_mode_combo.addItems(["none", "all", "selected", "upstream"])
        self.skill_hashes_edit = QPlainTextEdit()
        self.skill_hashes_edit.setFixedHeight(56)
        self.status_label = QLabel("idle")
        self.result_view = QPlainTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setFixedHeight(72)

        layout = QFormLayout()
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        layout.addRow("agent_id", self.agent_id_edit)
        layout.addRow("prompt", self.prompt_edit)
        layout.addRow("cli_kind", self.cli_kind_combo)
        layout.addRow("model", self.model_edit)
        layout.addRow("workdir", self.cwd_edit)
        layout.addRow("timeout", self.timeout_spin)
        layout.addRow("command", self.command_edit)
        layout.addRow("prompt_file", self.prompt_via_file_combo)
        layout.addRow("external", self.external_check)
        layout.addRow("mode", self.execution_mode_combo)
        layout.addRow("write_scope", self.write_scope_edit)
        layout.addRow("artifact_scope", self.artifact_scope_edit)
        layout.addRow("env", self.extra_env_edit)
        layout.addRow("adapter_json", self.adapter_options_edit)
        layout.addRow("skills", self.skill_mode_combo)
        layout.addRow("hashes", self.skill_hashes_edit)
        layout.addRow("status", self.status_label)
        layout.addRow("result", self.result_view)
        self.setLayout(layout)
        self.setFixedWidth(320)

        for edit in (self.agent_id_edit, self.model_edit, self.cwd_edit):
            edit.editingFinished.connect(self.apply_changes)
        self.prompt_edit.textChanged.connect(self.apply_changes)
        self.cli_kind_combo.currentTextChanged.connect(self.apply_changes)
        self.timeout_spin.valueChanged.connect(self.apply_changes)
        self.command_edit.editingFinished.connect(self.apply_changes)
        self.prompt_via_file_combo.currentTextChanged.connect(self.apply_changes)
        self.external_check.stateChanged.connect(self.apply_changes)
        self.execution_mode_combo.currentTextChanged.connect(self.apply_changes)
        self.write_scope_edit.textChanged.connect(self.apply_changes)
        self.artifact_scope_edit.textChanged.connect(self.apply_changes)
        self.extra_env_edit.textChanged.connect(self.apply_changes)
        self.adapter_options_edit.textChanged.connect(self.apply_changes)
        self.skill_mode_combo.currentTextChanged.connect(self.apply_changes)
        self.skill_hashes_edit.textChanged.connect(self.apply_changes)

        self.reload_from_node()
        self.reload_runtime_state()

    def reload_from_node(self):
        self._loading = True
        cfg = self.node.agent_config
        self.agent_id_edit.setText(str(cfg.get("agent_id", "")))
        self.prompt_edit.setPlainText(str(cfg.get("prompt", "")))
        self.cli_kind_combo.setCurrentText(str(cfg.get("cli_kind", "codex")))
        self.model_edit.setText(str(cfg.get("model", "")))
        self.cwd_edit.setText(str(cfg.get("cwd", ".")))
        self.timeout_spin.setValue(int(float(cfg.get("timeout_sec", 1800))))
        self.command_edit.setText(str(cfg.get("command", "")))
        self.prompt_via_file_combo.setCurrentText(str(cfg.get("prompt_via_file", "auto")))
        self.external_check.setChecked(bool(cfg.get("external", False)))
        self.execution_mode_combo.setCurrentText(str(cfg.get("execution_mode", "blocking")))
        self.write_scope_edit.setPlainText("\n".join(cfg.get("write_scope", [])))
        self.artifact_scope_edit.setPlainText("\n".join(cfg.get("artifact_scope", [])))
        self.extra_env_edit.setPlainText(self._dict_to_lines(cfg.get("extra_env", {})))
        self.adapter_options_edit.setPlainText(self._dict_to_json(cfg.get("adapter_options", {})))
        selection = cfg.get("skill_selection", {})
        self.skill_mode_combo.setCurrentText(str(selection.get("mode", "none")))
        self.skill_hashes_edit.setPlainText("\n".join(selection.get("skill_hashes", [])))
        self._loading = False

    def reload_runtime_state(self):
        status = getattr(self.node, "runtime_status", "idle")
        payload = getattr(self.node, "runtime_payload", {})
        self.status_label.setText(str(status))
        text = ""
        if isinstance(payload, dict):
            text = str(payload.get("text") or "")
            if not text and payload:
                import json

                text = json.dumps(payload, ensure_ascii=False, indent=2)
        self.result_view.setPlainText(text)

    @staticmethod
    def _split_lines(text: str) -> list[str]:
        return [line.strip() for line in text.replace(",", "\n").splitlines() if line.strip()]

    @staticmethod
    def _dict_to_lines(value):
        if not isinstance(value, dict):
            return ""
        return "\n".join(f"{key}={val}" for key, val in value.items())

    @staticmethod
    def _dict_to_json(value):
        if not isinstance(value, dict) or not value:
            return ""
        import json

        return json.dumps(value, ensure_ascii=False, indent=2)

    @staticmethod
    def _parse_env(text: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key:
                out[key] = value.strip()
        return out

    @staticmethod
    def _parse_json_object(text: str) -> dict:
        text = text.strip()
        if not text:
            return {}
        import json

        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("adapter options must be a JSON object")
        return value

    def apply_changes(self):
        if self._loading:
            return

        cfg = dict(self.node.agent_config)
        agent_id = self.agent_id_edit.text().strip()
        if agent_id:
            cfg["agent_id"] = agent_id
        else:
            cfg.pop("agent_id", None)
        cfg["cli_kind"] = self.cli_kind_combo.currentText().strip() or "codex"
        cfg["prompt"] = self.prompt_edit.toPlainText().strip()
        cfg["model"] = self.model_edit.text().strip()
        cfg["cwd"] = self.cwd_edit.text().strip() or "."
        cfg["timeout_sec"] = float(self.timeout_spin.value())
        command = self.command_edit.text().strip()
        if command:
            cfg["command"] = command
        else:
            cfg["command"] = "codex"
        cfg["prompt_via_file"] = self.prompt_via_file_combo.currentText().strip() or "auto"
        cfg["external"] = self.external_check.isChecked()
        cfg["execution_mode"] = self.execution_mode_combo.currentText().strip() or "blocking"
        cfg["write_scope"] = self._split_lines(self.write_scope_edit.toPlainText())
        cfg["artifact_scope"] = self._split_lines(self.artifact_scope_edit.toPlainText())
        cfg["extra_env"] = self._parse_env(self.extra_env_edit.toPlainText())
        try:
            cfg["adapter_options"] = self._parse_json_object(
                self.adapter_options_edit.toPlainText()
            )
        except ValueError:
            return

        hashes = [
            part.strip()
            for line in self.skill_hashes_edit.toPlainText().splitlines()
            for part in line.split(",")
            if part.strip()
        ]
        skill_mode = self.skill_mode_combo.currentText().strip() or "none"
        if skill_mode == "selected" and hashes:
            cfg["skill_selection"] = {"mode": "selected", "skill_hashes": hashes}
        elif skill_mode == "selected":
            cfg["skill_selection"] = {"mode": "none"}
        else:
            cfg["skill_selection"] = {"mode": skill_mode}

        try:
            self.node.set_agent_config(cfg)
        except ValueError:
            return

    def get_state(self):
        return {}

    def set_state(self, data):
        self.reload_from_node()


@node_gui(AgentNode)
class AgentNodeGui(NodeGUI):
    main_widget_class = AgentNodeMainWidget
    main_widget_pos = "below ports"
    color = "#3b82f6"

    def initialized(self):
        if self.main_widget() is not None:
            self.main_widget().reload_from_node()


@node_gui(BlueprintStart)
class BlueprintStartGui(NodeGUI):
    color = "#16a34a"
    style = "small"


@node_gui(BlueprintEnd)
class BlueprintEndGui(NodeGUI):
    color = "#dc2626"
    style = "small"
