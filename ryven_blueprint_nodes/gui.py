from __future__ import annotations

from qtpy.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLineEdit,
    QPlainTextEdit,
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
        self.cli_kind_combo = QComboBox()
        self.cli_kind_combo.addItems(["codemaker", "codex"])
        self.model_edit = QLineEdit()
        self.cwd_edit = QLineEdit()
        self.execution_mode_combo = QComboBox()
        self.execution_mode_combo.addItems(["blocking", "nonblocking"])
        self.skill_mode_combo = QComboBox()
        self.skill_mode_combo.addItems(["none", "all", "selected", "upstream"])
        self.skill_hashes_edit = QPlainTextEdit()
        self.skill_hashes_edit.setFixedHeight(56)

        layout = QFormLayout()
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)
        layout.addRow("agent_id", self.agent_id_edit)
        layout.addRow("cli_kind", self.cli_kind_combo)
        layout.addRow("model", self.model_edit)
        layout.addRow("cwd", self.cwd_edit)
        layout.addRow("mode", self.execution_mode_combo)
        layout.addRow("skills", self.skill_mode_combo)
        layout.addRow("hashes", self.skill_hashes_edit)
        self.setLayout(layout)
        self.setFixedWidth(260)

        for edit in (self.agent_id_edit, self.model_edit, self.cwd_edit):
            edit.editingFinished.connect(self.apply_changes)
        self.cli_kind_combo.currentTextChanged.connect(self.apply_changes)
        self.execution_mode_combo.currentTextChanged.connect(self.apply_changes)
        self.skill_mode_combo.currentTextChanged.connect(self.apply_changes)
        self.skill_hashes_edit.textChanged.connect(self.apply_changes)

        self.reload_from_node()

    def reload_from_node(self):
        self._loading = True
        cfg = self.node.agent_config
        self.agent_id_edit.setText(str(cfg.get("agent_id", "")))
        self.cli_kind_combo.setCurrentText(str(cfg.get("cli_kind", "codemaker")))
        self.model_edit.setText(str(cfg.get("model", "")))
        self.cwd_edit.setText(str(cfg.get("cwd", ".")))
        self.execution_mode_combo.setCurrentText(str(cfg.get("execution_mode", "blocking")))
        selection = cfg.get("skill_selection", {})
        self.skill_mode_combo.setCurrentText(str(selection.get("mode", "none")))
        self.skill_hashes_edit.setPlainText("\n".join(selection.get("skill_hashes", [])))
        self._loading = False

    def apply_changes(self):
        if self._loading:
            return

        cfg = dict(self.node.agent_config)
        agent_id = self.agent_id_edit.text().strip()
        if agent_id:
            cfg["agent_id"] = agent_id
        else:
            cfg.pop("agent_id", None)
        cfg["cli_kind"] = self.cli_kind_combo.currentText().strip() or "codemaker"
        cfg["model"] = self.model_edit.text().strip()
        cfg["cwd"] = self.cwd_edit.text().strip() or "."
        cfg["execution_mode"] = self.execution_mode_combo.currentText().strip() or "blocking"

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
