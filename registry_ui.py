"""Tkinter GUI for managing agents_registry.json.

Usage::

    python -m multi_agent_tcp.registry_ui
    python -m multi_agent_tcp registry-ui
"""
from __future__ import annotations

import copy
import json
import logging
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

_MODULE_DIR = Path(__file__).resolve().parent
_REGISTRY_PATH = _MODULE_DIR / "agents_registry.json"
_MANIFEST_PATH = _MODULE_DIR / "skill_list" / "manifest.json"

_models_cache: Optional[List[str]] = None
_FETCH_TIMEOUT_SEC = 10

# Catppuccin Mocha-inspired dark palette
C = {
    "bg": "#1e1e2e",
    "surface0": "#313244",
    "surface1": "#45475a",
    "surface2": "#585b70",
    "card": "#2a2a3d",
    "card_hover": "#35354d",
    "topbar": "#181825",
    "text": "#cdd6f4",
    "subtext": "#a6adc8",
    "accent": "#89b4fa",
    "green": "#a6e3a1",
    "red": "#f38ba8",
}

CARD_W = 240
CARD_H = 170
CARD_PAD = 14
SKILL_SELECTION_MODES = ("none", "all", "selected", "upstream")


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _load_manifest() -> Dict[str, Dict[str, Any]]:
    if _MANIFEST_PATH.is_file():
        try:
            return json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _load_registry() -> Dict[str, Any]:
    if _REGISTRY_PATH.is_file():
        return json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    return {"$comment": "", "skill_list_dir": "skill_list", "agents": {}}


def _save_registry(data: Dict[str, Any], path: Path) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _fetch_codex_models(*, force: bool = False) -> List[str]:
    """Run ``codex debug models`` and return the list of model names.

    Results are cached after the first successful call.  Pass *force* to
    bypass the cache (e.g. on user retry).
    """
    global _models_cache
    if _models_cache is not None and not force:
        return _models_cache
    try:
        proc = subprocess.run(
            ["codex", "debug", "models"],
            capture_output=True, text=True, timeout=_FETCH_TIMEOUT_SEC,
            encoding="utf-8", errors="replace",
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            raw_models = data.get("models", []) if isinstance(data, dict) else []
            _models_cache = sorted({
                str(model.get("slug", "")).strip()
                for model in raw_models
                if isinstance(model, dict) and str(model.get("slug", "")).strip()
            })
            return _models_cache
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as exc:
        log.warning("codex model listing failed: %s", exc)
    return []


def _collect_models(registry: Dict[str, Any]) -> List[str]:
    """Merge live Codex models with models already used in the registry."""
    live = _fetch_codex_models()
    models = set(live)
    for agent in registry.get("agents", {}).values():
        m = agent.get("model", "")
        if m:
            models.add(m)
    return sorted(models)


def _skill_selection_from_agent(data: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Return ``(mode, selected_skill_names)`` from new or legacy registry data."""
    raw = data.get("skill_selection")
    legacy = [str(s).strip() for s in data.get("skills", []) if str(s).strip()]

    mode = "selected" if legacy else "none"
    selected = legacy
    if isinstance(raw, str):
        mode = raw.strip().lower() or mode
        selected = []
    elif isinstance(raw, dict):
        raw_skills = raw.get("skill_hashes", raw.get("skills", [])) or []
        if isinstance(raw_skills, list):
            selected = [str(s).strip() for s in raw_skills if str(s).strip()]
        mode = str(raw.get("mode", "selected" if selected else "none")).strip().lower()
    elif raw is not None:
        mode = "none"
        selected = []

    if mode not in SKILL_SELECTION_MODES:
        mode = "none"
        selected = []
    if mode == "selected" and not selected:
        selected = legacy
    if mode != "selected":
        selected = []
    return mode, selected


def _skill_selection_payload(mode: str, selected_skills: List[str]) -> Dict[str, Any]:
    mode = mode.strip().lower()
    if mode not in SKILL_SELECTION_MODES:
        mode = "none"
    payload: Dict[str, Any] = {"mode": mode}
    if mode == "selected":
        payload["skill_hashes"] = selected_skills[:]
    return payload


def _skill_selection_summary(data: Dict[str, Any], *, total_skills: int) -> str:
    mode, selected = _skill_selection_from_agent(data)
    if mode == "all":
        return f"all ({total_skills})"
    if mode == "selected":
        return f"selected ({len(selected)})"
    if mode == "upstream":
        return "upstream"
    return "none"



# -------------------------------------------------------------------
# Skill Picker Popup
# -------------------------------------------------------------------

class SkillPickerPopup(tk.Toplevel):
    """Multi-select popup showing all available skills with name + description."""

    def __init__(
        self,
        parent: tk.Widget,
        all_skills: Dict[str, Dict[str, Any]],
        selected: List[str],
    ):
        super().__init__(parent)
        self.title("Select Skills")
        self.configure(bg=C["bg"])
        self.resizable(True, True)
        self.geometry("500x440")
        self.transient(parent)
        self.grab_set()

        self.result: Optional[List[str]] = None
        self._vars: Dict[str, tk.BooleanVar] = {}

        self._build(all_skills, selected)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, px)}+{max(0, py)}")

    def _build(self, all_skills: Dict[str, Dict[str, Any]], selected: List[str]) -> None:
        container = tk.Frame(self, bg=C["bg"])
        container.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        canvas = tk.Canvas(container, bg=C["bg"], highlightthickness=0)
        sb = tk.Scrollbar(
            container, orient="vertical", command=canvas.yview,
            bg=C["surface1"], troughcolor=C["bg"], activebackground=C["surface2"],
        )
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=C["bg"])
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))

        mw = lambda e: canvas.yview_scroll(-e.delta // 120, "units")
        canvas.bind("<MouseWheel>", mw)

        name_font = ("Segoe UI", 11, "bold")
        desc_font = ("Segoe UI", 9)
        items = sorted(all_skills.items())

        for i, (sname, sinfo) in enumerate(items):
            var = tk.BooleanVar(value=(sname in selected))
            self._vars[sname] = var

            row = tk.Frame(inner, bg=C["bg"])
            row.pack(fill="x", padx=4, pady=(6, 0))

            cb = tk.Checkbutton(
                row, variable=var, bg=C["bg"], fg=C["text"],
                selectcolor=C["surface0"], activebackground=C["bg"],
                activeforeground=C["text"], highlightthickness=0,
            )
            cb.pack(side="left", anchor="n", pady=2)

            text_frame = tk.Frame(row, bg=C["bg"])
            text_frame.pack(side="left", fill="x", expand=True)

            name_lbl = tk.Label(
                text_frame, text=sname, font=name_font,
                bg=C["bg"], fg=C["text"], anchor="w",
            )
            name_lbl.pack(fill="x")
            name_lbl.bind("<Button-1>", lambda _, v=var: v.set(not v.get()))

            desc = sinfo.get("description", "")
            if desc:
                desc_lbl = tk.Label(
                    text_frame, text=desc, font=desc_font,
                    bg=C["bg"], fg=C["subtext"], anchor="w", wraplength=400,
                )
                desc_lbl.pack(fill="x")
                desc_lbl.bind("<Button-1>", lambda _, v=var: v.set(not v.get()))

            for w in (row, text_frame, name_lbl):
                w.bind("<MouseWheel>", mw)
            if desc:
                desc_lbl.bind("<MouseWheel>", mw)

            if i < len(items) - 1:
                sep = tk.Frame(inner, bg=C["surface2"], height=1)
                sep.pack(fill="x", padx=8, pady=(6, 0))
                sep.bind("<MouseWheel>", mw)

        btn_frame = tk.Frame(self, bg=C["bg"])
        btn_frame.pack(fill="x", padx=12, pady=10)

        tk.Button(
            btn_frame, text="Select All", command=self._select_all,
            bg=C["surface1"], fg=C["text"], font=("Segoe UI", 10),
            relief="flat", padx=14, pady=4, cursor="hand2",
        ).pack(side="left", padx=4)

        tk.Button(
            btn_frame, text="Clear", command=self._clear_all,
            bg=C["surface1"], fg=C["text"], font=("Segoe UI", 10),
            relief="flat", padx=14, pady=4, cursor="hand2",
        ).pack(side="left", padx=4)

        tk.Button(
            btn_frame, text="OK", command=self._on_ok,
            bg=C["accent"], fg=C["topbar"], font=("Segoe UI", 10, "bold"),
            relief="flat", padx=20, pady=4, cursor="hand2",
        ).pack(side="right", padx=4)

        tk.Button(
            btn_frame, text="Cancel", command=self._on_cancel,
            bg=C["surface1"], fg=C["text"], font=("Segoe UI", 10),
            relief="flat", padx=20, pady=4, cursor="hand2",
        ).pack(side="right", padx=4)

    def _select_all(self) -> None:
        for var in self._vars.values():
            var.set(True)

    def _clear_all(self) -> None:
        for var in self._vars.values():
            var.set(False)

    def _on_ok(self) -> None:
        self.result = sorted(n for n, v in self._vars.items() if v.get())
        self.destroy()

    def _on_cancel(self) -> None:
        self.destroy()


# -------------------------------------------------------------------
# Agent Detail Dialog
# -------------------------------------------------------------------

class AgentDetailDialog(tk.Toplevel):
    """Modal dialog for creating or editing an agent."""

    def __init__(
        self,
        parent: tk.Widget,
        agent_id: str,
        agent_data: Dict[str, Any],
        all_skills: Dict[str, Dict[str, Any]],
        known_models: List[str],
        *,
        is_new: bool = False,
    ):
        super().__init__(parent)
        self.title("New Agent" if is_new else f"Edit: {agent_id}")
        self.configure(bg=C["bg"])
        self.resizable(True, True)
        self.geometry("540x520")
        self.transient(parent)
        self.grab_set()

        self.result: Optional[Tuple[str, Dict[str, Any]]] = None
        self._is_new = is_new
        self._original_data = copy.deepcopy(agent_data)
        self._all_skills = all_skills
        self._known_models = known_models
        skill_mode, selected_skills = _skill_selection_from_agent(agent_data)
        self._skill_mode_var = tk.StringVar(value=skill_mode)
        self._selected_skills: List[str] = selected_skills

        self._build(agent_id, agent_data)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, px)}+{max(0, py)}")

    # -- layout --

    def _field_label(self, parent: tk.Widget, text: str) -> tk.Label:
        lbl = tk.Label(
            parent, text=text, font=("Segoe UI", 10),
            bg=C["bg"], fg=C["subtext"], anchor="w",
        )
        lbl.pack(fill="x", padx=12, pady=(8, 2))
        return lbl

    def _field_entry(self, parent: tk.Widget, var: tk.Variable, **kw) -> tk.Entry:
        e = tk.Entry(
            parent, textvariable=var, font=("Segoe UI", 10),
            bg=C["surface0"], fg=C["text"], insertbackground=C["text"],
            relief="flat", highlightthickness=1, highlightcolor=C["accent"],
            highlightbackground=C["surface2"], **kw,
        )
        e.pack(fill="x", padx=12, pady=2)
        return e

    def _build(self, agent_id: str, data: Dict[str, Any]) -> None:
        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=4, pady=4)

        # Agent ID
        self._field_label(body, "Agent ID")
        self._id_var = tk.StringVar(value=agent_id)
        id_entry = self._field_entry(body, self._id_var)
        if not self._is_new:
            id_entry.configure(state="readonly", readonlybackground=C["surface0"])

        # Display Name
        self._field_label(body, "Display Name")
        self._name_var = tk.StringVar(value=data.get("display_name", ""))
        self._field_entry(body, self._name_var)

        # Model (Combobox — refreshes live on each dropdown open)
        self._field_label(body, "Model")
        self._model_var = tk.StringVar(value=data.get("model", ""))
        self._model_cb = ttk.Combobox(
            body, textvariable=self._model_var, values=self._known_models,
            font=("Segoe UI", 10),
            postcommand=self._refresh_models,
        )
        self._model_cb.pack(fill="x", padx=12, pady=2)

        # Working Directory
        self._field_label(body, "Working Directory")
        cwd_frame = tk.Frame(body, bg=C["bg"])
        cwd_frame.pack(fill="x", padx=12, pady=2)
        self._cwd_var = tk.StringVar(value=data.get("cwd", ""))
        tk.Entry(
            cwd_frame, textvariable=self._cwd_var, font=("Segoe UI", 10),
            bg=C["surface0"], fg=C["text"], insertbackground=C["text"],
            relief="flat", highlightthickness=1, highlightcolor=C["accent"],
            highlightbackground=C["surface2"],
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            cwd_frame, text="Browse", command=self._browse_cwd,
            bg=C["surface1"], fg=C["text"], font=("Segoe UI", 9),
            relief="flat", padx=8, cursor="hand2",
        ).pack(side="right", padx=(6, 0))

        # Timeout
        self._field_label(body, "Timeout (seconds)")
        self._timeout_var = tk.IntVar(value=int(data.get("timeout_sec", 1800)))
        tk.Spinbox(
            body, textvariable=self._timeout_var, from_=60, to=7200, increment=60,
            font=("Segoe UI", 10), bg=C["surface0"], fg=C["text"],
            insertbackground=C["text"], buttonbackground=C["surface1"],
            relief="flat", highlightthickness=1, highlightcolor=C["accent"],
            highlightbackground=C["surface2"],
        ).pack(fill="x", padx=12, pady=2)

        # Enabled
        self._enabled_var = tk.BooleanVar(value=data.get("enabled", True))
        tk.Checkbutton(
            body, text="Enabled", variable=self._enabled_var,
            font=("Segoe UI", 10), bg=C["bg"], fg=C["text"],
            selectcolor=C["surface0"], activebackground=C["bg"],
            activeforeground=C["text"], highlightthickness=0,
        ).pack(anchor="w", padx=12, pady=(8, 2))

        # Skills
        self._field_label(body, "Skills")
        self._skill_mode_cb = ttk.Combobox(
            body, textvariable=self._skill_mode_var,
            values=SKILL_SELECTION_MODES, state="readonly",
            font=("Segoe UI", 10),
        )
        self._skill_mode_cb.pack(fill="x", padx=12, pady=2)
        self._skill_mode_cb.bind(
            "<<ComboboxSelected>>",
            lambda _: self._update_skill_controls(),
        )

        self._skills_btn = tk.Button(
            body, text=self._skills_btn_text(), command=self._pick_skills,
            bg=C["surface0"], fg=C["text"], font=("Segoe UI", 10),
            relief="flat", anchor="w", padx=8, pady=4, cursor="hand2",
            highlightthickness=1, highlightcolor=C["accent"],
            highlightbackground=C["surface2"], disabledforeground=C["subtext"],
        )
        self._skills_btn.pack(fill="x", padx=12, pady=2)
        self._update_skill_controls()

        # Bottom buttons
        btn_frame = tk.Frame(self, bg=C["bg"])
        btn_frame.pack(fill="x", padx=16, pady=(4, 12))

        tk.Button(
            btn_frame, text="OK", command=self._on_ok,
            bg=C["accent"], fg=C["topbar"], font=("Segoe UI", 10, "bold"),
            relief="flat", padx=24, pady=4, cursor="hand2",
        ).pack(side="right", padx=4)

        tk.Button(
            btn_frame, text="Cancel", command=self._on_cancel,
            bg=C["surface1"], fg=C["text"], font=("Segoe UI", 10),
            relief="flat", padx=24, pady=4, cursor="hand2",
        ).pack(side="right", padx=4)

    # -- helpers --

    def _refresh_models(self) -> None:
        """Called by Combobox postcommand each time the dropdown opens.

        Uses cached models (pre-warmed at startup) to avoid blocking the
        UI thread with a subprocess call.
        """
        fresh = _fetch_codex_models()  # cached, no subprocess
        current = self._model_var.get().strip()
        if current and current not in fresh:
            fresh = sorted(set(fresh) | {current})
        self._model_cb["values"] = fresh

    def _skills_btn_text(self) -> str:
        mode = self._skill_mode_var.get().strip().lower()
        if mode == "none":
            return "No skills"
        if mode == "all":
            return f"All skills ({len(self._all_skills)})"
        if mode == "upstream":
            return "Assigned by upstream super agent"
        n = len(self._selected_skills)
        if n == 0:
            return "Click to select skills..."
        names = ", ".join(self._selected_skills)
        if len(names) > 60:
            names = names[:57] + "..."
        return f"{n} skill(s): {names}"

    def _update_skill_controls(self) -> None:
        mode = self._skill_mode_var.get().strip().lower()
        if mode not in SKILL_SELECTION_MODES:
            self._skill_mode_var.set("none")
            mode = "none"
        if mode == "selected":
            self._skills_btn.configure(
                state="normal",
                cursor="hand2",
                text=self._skills_btn_text(),
            )
        else:
            self._skills_btn.configure(
                state="disabled",
                cursor="",
                text=self._skills_btn_text(),
            )

    def _pick_skills(self) -> None:
        if self._skill_mode_var.get().strip().lower() != "selected":
            return
        popup = SkillPickerPopup(self, self._all_skills, self._selected_skills)
        self.wait_window(popup)
        if popup.result is not None:
            self._selected_skills = popup.result
            self._skills_btn.configure(text=self._skills_btn_text())

    def _browse_cwd(self) -> None:
        initial = self._cwd_var.get() or str(_MODULE_DIR.parent)
        d = filedialog.askdirectory(parent=self, initialdir=initial)
        if d:
            self._cwd_var.set(d)

    # -- ok / cancel --

    def _on_ok(self) -> None:
        aid = self._id_var.get().strip()
        if not aid:
            messagebox.showwarning("Validation", "Agent ID cannot be empty.", parent=self)
            return
        if " " in aid:
            messagebox.showwarning("Validation", "Agent ID must not contain spaces.", parent=self)
            return
        skill_mode = self._skill_mode_var.get().strip().lower()
        if skill_mode not in SKILL_SELECTION_MODES:
            messagebox.showwarning("Validation", "Invalid skill mode.", parent=self)
            return
        if skill_mode == "selected" and not self._selected_skills:
            messagebox.showwarning(
                "Validation",
                "Selected skill mode requires at least one skill. Choose none instead.",
                parent=self,
            )
            return
        selected_skills = self._selected_skills[:] if skill_mode == "selected" else []
        updated = copy.deepcopy(self._original_data)
        updated.update({
            "display_name": self._name_var.get().strip(),
            "model": self._model_var.get().strip(),
            "cwd": self._cwd_var.get().strip(),
            "skills": selected_skills,
            "skill_selection": _skill_selection_payload(skill_mode, selected_skills),
            "timeout_sec": self._timeout_var.get(),
            "enabled": self._enabled_var.get(),
        })
        self.result = (aid, updated)
        self.destroy()

    def _on_cancel(self) -> None:
        self.destroy()


# -------------------------------------------------------------------
# Main Window
# -------------------------------------------------------------------

class RegistryUI(tk.Tk):
    """Main application window for agents_registry.json management."""

    def __init__(
        self,
        registry_path: Optional[Path] = None,
        manifest_path: Optional[Path] = None,
    ):
        super().__init__()
        self._reg_path = Path(registry_path) if registry_path else _REGISTRY_PATH
        self._mfst_path = Path(manifest_path) if manifest_path else _MANIFEST_PATH

        self.title("Agents Registry")
        self.configure(bg=C["bg"])
        self.geometry("920x620")
        self.minsize(480, 400)

        self._setup_style()

        self._manifest = _load_manifest()
        _fetch_codex_models()  # pre-warm cache so first dialog open is instant
        self._saved_state = _load_registry()
        self._current_state = copy.deepcopy(self._saved_state)

        self._card_widgets: List[tk.Frame] = []
        self._last_canvas_w = 0
        self._layout_job: Optional[str] = None

        self._build_topbar()
        self._build_scroll_area()
        self._rebuild_cards()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._update_btn_states()

    # -- theming --

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            ".", background=C["bg"], foreground=C["text"],
            fieldbackground=C["surface0"], insertcolor=C["text"],
        )
        style.configure(
            "TCombobox",
            fieldbackground=C["surface0"], background=C["surface1"],
            foreground=C["text"], arrowcolor=C["text"],
            selectbackground=C["accent"], selectforeground=C["topbar"],
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", C["surface0"])],
            background=[("active", C["surface2"])],
        )
        style.configure(
            "TScrollbar",
            background=C["surface1"], troughcolor=C["bg"], arrowcolor=C["text"],
        )
        self.option_add("*TCombobox*Listbox.background", C["surface0"])
        self.option_add("*TCombobox*Listbox.foreground", C["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", C["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", C["topbar"])

    # -- top bar --

    def _build_topbar(self) -> None:
        bar = tk.Frame(self, bg=C["topbar"], height=48)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        self._undo_btn = tk.Button(
            bar, text="Undo", command=self._on_undo,
            bg=C["surface1"], fg=C["text"], font=("Segoe UI", 10),
            relief="flat", padx=14, pady=4, state="disabled",
            disabledforeground=C["surface2"], cursor="hand2",
        )
        self._undo_btn.pack(side="left", padx=12, pady=8)

        title = tk.Label(
            bar, text=f"Agents Registry  \u2014  {self._reg_path.name}",
            font=("Segoe UI", 11), bg=C["topbar"], fg=C["text"], cursor="hand2",
        )
        title.pack(side="left", expand=True)
        title.bind("<Button-1>", lambda _: self._show_info())

        self._save_btn = tk.Button(
            bar, text="Save", command=self._on_save,
            bg=C["accent"], fg=C["topbar"], font=("Segoe UI", 10, "bold"),
            relief="flat", padx=14, pady=4, state="disabled",
            disabledforeground=C["surface2"], cursor="hand2",
        )
        self._save_btn.pack(side="right", padx=12, pady=8)

    # -- scrollable area --

    def _build_scroll_area(self) -> None:
        container = tk.Frame(self, bg=C["bg"])
        container.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(container, bg=C["bg"], highlightthickness=0)
        sb = tk.Scrollbar(
            container, orient="vertical", command=self._canvas.yview,
            bg=C["surface1"], troughcolor=C["bg"], activebackground=C["surface2"],
        )
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._inner = tk.Frame(self._canvas, bg=C["bg"])
        self._cwin = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind(
            "<Configure>",
            lambda _: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas.bind("<Configure>", self._on_canvas_cfg)
        self._canvas.bind(
            "<MouseWheel>",
            lambda e: self._canvas.yview_scroll(-e.delta // 120, "units"),
        )

    def _on_canvas_cfg(self, event: tk.Event) -> None:
        w = event.width
        if w == self._last_canvas_w:
            return
        self._last_canvas_w = w
        if self._layout_job is not None:
            self.after_cancel(self._layout_job)
        self._layout_job = self.after(30, self._do_deferred_layout, w)

    def _do_deferred_layout(self, w: int) -> None:
        self._layout_job = None
        self._canvas.itemconfigure(self._cwin, width=w)
        self._layout_cards()

    # -- card grid --

    def _rebuild_cards(self) -> None:
        for f in self._card_widgets:
            f.destroy()
        self._card_widgets.clear()

        agents = self._current_state.get("agents", {})
        for aid, adata in agents.items():
            self._card_widgets.append(self._make_agent_card(aid, adata))

        self._card_widgets.append(self._make_add_card())
        self._layout_cards()

    def _layout_cards(self) -> None:
        w = self._last_canvas_w or self.winfo_width()
        cols = max(1, (w - CARD_PAD) // (CARD_W + CARD_PAD))
        for i, card in enumerate(self._card_widgets):
            card.grid_forget()
            r, c = divmod(i, cols)
            card.grid(row=r, column=c, padx=CARD_PAD // 2, pady=CARD_PAD // 2)

    # -- single agent card --

    def _make_agent_card(self, agent_id: str, data: Dict[str, Any]) -> tk.Frame:
        card = tk.Frame(
            self._inner, bg=C["card"], width=CARD_W, height=CARD_H,
            highlightthickness=1, highlightbackground=C["surface2"],
        )
        card.grid_propagate(False)
        card.pack_propagate(False)

        enabled = data.get("enabled", True)
        dot_color = C["green"] if enabled else C["red"]

        # header: dot + agent_id + delete btn
        hdr = tk.Frame(card, bg=C["card"])
        hdr.pack(fill="x", padx=10, pady=(10, 2))

        dot_lbl = tk.Label(
            hdr, text="\u25cf", font=("Segoe UI", 10),
            bg=C["card"], fg=dot_color,
        )
        dot_lbl.pack(side="left")

        tk.Label(
            hdr, text=f" {agent_id}", font=("Segoe UI", 11, "bold"),
            bg=C["card"], fg=C["text"], anchor="w",
        ).pack(side="left", fill="x", expand=True)

        del_btn = tk.Label(
            hdr, text="\u2715", font=("Segoe UI", 12),
            bg=C["card"], fg=C["red"], cursor="hand2",
        )
        del_btn.pack(side="right")
        del_btn.bind("<Button-1>", lambda _, a=agent_id: self._delete_agent(a))
        del_btn._skip_propagate = True  # type: ignore[attr-defined]

        # display name
        tk.Label(
            card, text=data.get("display_name", ""),
            font=("Segoe UI", 10), bg=C["card"], fg=C["subtext"], anchor="w",
        ).pack(fill="x", padx=12, pady=1)

        # model
        model = data.get("model", "")
        short = model
        tk.Label(
            card, text=f"Model: {short}",
            font=("Segoe UI", 9), bg=C["card"], fg=C["subtext"], anchor="w",
        ).pack(fill="x", padx=12, pady=1)

        # skills selection
        tk.Label(
            card, text=f"Skills: {_skill_selection_summary(data, total_skills=len(self._manifest))}",
            font=("Segoe UI", 9), bg=C["card"], fg=C["subtext"], anchor="w",
        ).pack(fill="x", padx=12, pady=1)

        # enabled status
        status_text = "Enabled" if enabled else "Disabled"
        tk.Label(
            card, text=f"\u25cf {status_text}",
            font=("Segoe UI", 9), bg=C["card"], fg=dot_color, anchor="w",
        ).pack(fill="x", padx=12, pady=(1, 8))

        # pre-collect flat widget list for O(n) hover, skip delete btn for dblclick
        all_widgets: List[tk.Widget] = []
        dblclick_widgets: List[tk.Widget] = []

        def _collect(w: tk.Widget) -> None:
            all_widgets.append(w)
            if not getattr(w, "_skip_propagate", False):
                dblclick_widgets.append(w)
            for ch in w.winfo_children():
                _collect(ch)

        _collect(card)

        # hover — with pointer bounds check to avoid child-boundary flicker
        orig_bg = C["card"]
        hover_bg = C["card_hover"]
        card._hovered = False  # type: ignore[attr-defined]

        def _enter(_: tk.Event) -> None:
            if not card._hovered:  # type: ignore[attr-defined]
                card._hovered = True  # type: ignore[attr-defined]
                for w in all_widgets:
                    try:
                        w.configure(bg=hover_bg)
                    except tk.TclError:
                        pass

        def _leave(_: tk.Event) -> None:
            if not card._hovered:  # type: ignore[attr-defined]
                return
            px, py = card.winfo_pointerxy()
            cx, cy = card.winfo_rootx(), card.winfo_rooty()
            if cx <= px < cx + card.winfo_width() and cy <= py < cy + card.winfo_height():
                return  # pointer still inside card — ignore child-boundary leave
            card._hovered = False  # type: ignore[attr-defined]
            for w in all_widgets:
                try:
                    w.configure(bg=orig_bg)
                except tk.TclError:
                    pass

        card.bind("<Enter>", _enter)
        card.bind("<Leave>", _leave)

        # double-click → edit
        edit_handler = lambda _, a=agent_id: self._edit_agent(a)
        for w in dblclick_widgets:
            w.bind("<Double-Button-1>", edit_handler)

        # mousewheel → scroll (single handler, shared lambda)
        mw_handler = lambda e: self._canvas.yview_scroll(-e.delta // 120, "units")
        for w in all_widgets:
            w.bind("<MouseWheel>", mw_handler)

        return card

    # -- add card --

    def _make_add_card(self) -> tk.Frame:
        card = tk.Frame(
            self._inner, bg=C["surface0"], width=CARD_W, height=CARD_H,
            highlightthickness=1, highlightbackground=C["surface2"],
        )
        card.grid_propagate(False)
        card.pack_propagate(False)

        plus = tk.Label(
            card, text="+", font=("Segoe UI", 40, "bold"),
            bg=C["surface0"], fg=C["accent"], cursor="hand2",
        )
        plus.pack(expand=True)

        hint = tk.Label(
            card, text="Add Agent",
            font=("Segoe UI", 9), bg=C["surface0"], fg=C["subtext"],
        )
        hint.pack(pady=(0, 14))

        add_widgets = [card, plus, hint]
        for w in add_widgets:
            w.bind("<Button-1>", lambda _: self._add_agent())
            w.bind("<MouseWheel>",
                   lambda e: self._canvas.yview_scroll(-e.delta // 120, "units"))

        card._hovered = False  # type: ignore[attr-defined]
        orig_bg, hover_bg = C["surface0"], C["surface1"]

        def _enter(_: tk.Event) -> None:
            if not card._hovered:  # type: ignore[attr-defined]
                card._hovered = True  # type: ignore[attr-defined]
                for w in add_widgets:
                    w.configure(bg=hover_bg)

        def _leave(_: tk.Event) -> None:
            if not card._hovered:  # type: ignore[attr-defined]
                return
            px, py = card.winfo_pointerxy()
            cx, cy = card.winfo_rootx(), card.winfo_rooty()
            if cx <= px < cx + card.winfo_width() and cy <= py < cy + card.winfo_height():
                return
            card._hovered = False  # type: ignore[attr-defined]
            for w in add_widgets:
                w.configure(bg=orig_bg)

        card.bind("<Enter>", _enter)
        card.bind("<Leave>", _leave)

        return card

    # -- actions --

    def _show_info(self) -> None:
        comment = self._current_state.get("$comment", "(none)")
        skill_dir = self._current_state.get("skill_list_dir", "skill_list")
        n = len(self._current_state.get("agents", {}))
        messagebox.showinfo(
            "Registry Info",
            f"File: {self._reg_path}\n\n"
            f"Comment:\n{comment}\n\n"
            f"Skill list dir: {skill_dir}\n\n"
            f"Agents: {n}",
            parent=self,
        )

    def _add_agent(self) -> None:
        models = _collect_models(self._current_state)
        dlg = AgentDetailDialog(
            self, "", {
                "display_name": "",
                "model": models[0] if models else "",
                "cwd": str(_MODULE_DIR.parent),
                "skills": [],
                "skill_selection": {"mode": "none"},
                "timeout_sec": 1800,
                "enabled": True,
            },
            self._manifest, models, is_new=True,
        )
        self.wait_window(dlg)
        if dlg.result is None:
            return
        aid, adata = dlg.result
        agents = self._current_state.setdefault("agents", {})
        if aid in agents:
            if not messagebox.askyesno(
                "Overwrite",
                f"Agent '{aid}' already exists. Overwrite?",
                parent=self,
            ):
                return
        agents[aid] = adata
        self._rebuild_cards()
        self._update_btn_states()

    def _edit_agent(self, agent_id: str) -> None:
        agents = self._current_state.get("agents", {})
        if agent_id not in agents:
            return
        models = _collect_models(self._current_state)
        dlg = AgentDetailDialog(
            self, agent_id, agents[agent_id],
            self._manifest, models, is_new=False,
        )
        self.wait_window(dlg)
        if dlg.result is None:
            return
        _, adata = dlg.result
        agents[agent_id] = adata
        self._rebuild_cards()
        self._update_btn_states()

    def _delete_agent(self, agent_id: str) -> None:
        if not messagebox.askyesno(
            "Delete Agent",
            f"Delete agent '{agent_id}'?",
            parent=self,
        ):
            return
        self._current_state.get("agents", {}).pop(agent_id, None)
        self._rebuild_cards()
        self._update_btn_states()

    # -- undo / save --

    def _on_undo(self) -> None:
        self._current_state = copy.deepcopy(self._saved_state)
        self._rebuild_cards()
        self._update_btn_states()

    def _on_save(self) -> None:
        _save_registry(self._current_state, self._reg_path)
        self._saved_state = copy.deepcopy(self._current_state)
        self._update_btn_states()

    def _has_unsaved(self) -> bool:
        return self._current_state != self._saved_state

    def _update_btn_states(self) -> None:
        state = "normal" if self._has_unsaved() else "disabled"
        self._undo_btn.configure(state=state)
        self._save_btn.configure(state=state)

    def _on_close(self) -> None:
        if self._has_unsaved():
            if not messagebox.askyesno(
                "Unsaved Changes",
                "You have unsaved changes. Exit anyway?",
                parent=self,
            ):
                return
        self.destroy()


# -------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------

def main() -> None:
    app = RegistryUI()
    app.mainloop()


if __name__ == "__main__":
    main()
