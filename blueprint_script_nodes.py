"""User-authored Python function nodes for GuLiCode blueprints."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import inspect
import json
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence


SCRIPT_NODE_WORKSPACE_DIR = Path(".multi_agent_workspace") / "scripts"
SUPPORTED_PORT_TYPES = {"int", "float", "str", "bool", "dict", "list", "Any"}
PYRIGHT_CONFIG_FILENAME = "pyrightconfig.json"
VSCODE_SETTINGS_DIR = ".vscode"
VSCODE_SETTINGS_FILENAME = "settings.json"
SCRIPT_WORKSPACE_FILENAME = "blueprint-scripts.code-workspace"


@dataclass
class ScriptNodePort:
    name: str
    type: str = "Any"
    required: bool = True

    def __post_init__(self) -> None:
        self.name = str(self.name).strip()
        if not self.name:
            raise ValueError("script node port name must be non-empty")
        self.type = _normalize_port_type(self.type)
        self.required = bool(self.required)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "type": self.type, "required": self.required}

    @classmethod
    def from_value(cls, value: Any, *, default_name: str = "result") -> "ScriptNodePort":
        if isinstance(value, ScriptNodePort):
            return cls(value.name, value.type, value.required)
        if isinstance(value, str):
            return cls(default_name, value, True)
        if isinstance(value, Mapping):
            return cls(
                str(value.get("name") or default_name),
                str(value.get("type") or value.get("annotation") or "Any"),
                bool(value.get("required", True)),
            )
        return cls(default_name, "Any", True)


@dataclass
class ScriptNodeCatalogItem:
    script_id: str
    module_path: str
    function_name: str
    title: str
    description: str = ""
    inputs: List[ScriptNodePort] = field(default_factory=list)
    outputs: List[ScriptNodePort] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "script_id": self.script_id,
            "module_path": self.module_path,
            "function_name": self.function_name,
            "title": self.title,
            "description": self.description,
            "inputs": [port.to_dict() for port in self.inputs],
            "outputs": [port.to_dict() for port in self.outputs],
        }


@dataclass
class ScriptNodeDiagnostic:
    path: str
    message: str
    line: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"path": self.path, "message": self.message}
        if self.line is not None:
            data["line"] = self.line
        return data


def blueprint_node(
    func: Optional[Callable[..., Any]] = None,
    *,
    name: Optional[str] = None,
    description: str = "",
    inputs: Optional[Mapping[str, Any]] = None,
    outputs: Optional[Mapping[str, Any]] = None,
) -> Callable[..., Any]:
    """Mark a Python function as a GuLiCode blueprint function node."""

    def decorate(target: Callable[..., Any]) -> Callable[..., Any]:
        setattr(
            target,
            "__blueprint_node__",
            {
                "name": name,
                "description": description,
                "inputs": dict(inputs or {}),
                "outputs": dict(outputs or {}),
            },
        )
        return target

    if func is None:
        return decorate
    return decorate(func)


def script_nodes_dir(project_dir: Path) -> Path:
    return Path(project_dir).expanduser().resolve() / SCRIPT_NODE_WORKSPACE_DIR


def ensure_script_nodes_dir(project_dir: Path) -> Path:
    root = script_nodes_dir(project_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_script_nodes_dev_environment(project_dir: Path) -> Dict[str, str]:
    """Write editor metadata that lets IDEs resolve the local framework source."""

    root = ensure_script_nodes_dir(project_dir)
    source_dir = _framework_source_dir()
    import_root = _framework_import_root(source_dir)
    pyright_path = root / PYRIGHT_CONFIG_FILENAME
    vscode_dir = root / VSCODE_SETTINGS_DIR
    vscode_settings_path = vscode_dir / VSCODE_SETTINGS_FILENAME
    workspace_path = root / SCRIPT_WORKSPACE_FILENAME

    _write_json_if_changed(
        pyright_path,
        _merged_pyright_config(_read_json_object(pyright_path), import_root),
    )
    vscode_dir.mkdir(parents=True, exist_ok=True)
    _write_json_if_changed(
        vscode_settings_path,
        _merged_vscode_settings(_read_json_object(vscode_settings_path), import_root),
    )
    _write_json_if_changed(
        workspace_path,
        {
            "folders": [
                {"name": "Blueprint Scripts", "path": "."},
                {"name": "multi_agent_tcp source", "path": str(source_dir)},
            ],
            "settings": {
                "python.analysis.extraPaths": [str(import_root)],
                "python.defaultInterpreterPath": sys.executable,
            },
        },
    )
    return {
        "script_dir": str(root.resolve()),
        "pyright_config": str(pyright_path.resolve()),
        "vscode_settings": str(vscode_settings_path.resolve()),
        "workspace_file": str(workspace_path.resolve()),
        "framework_source_dir": str(source_dir),
        "framework_import_root": str(import_root),
        "python": sys.executable,
    }


def discover_script_nodes(project_dir: Path) -> Dict[str, Any]:
    """Scan user scripts without importing them."""

    root = ensure_script_nodes_dir(project_dir)
    dev_environment = ensure_script_nodes_dev_environment(project_dir)
    items: List[ScriptNodeCatalogItem] = []
    diagnostics: List[ScriptNodeDiagnostic] = []
    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue
        rel_path = _relative_module_path(root, path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            diagnostics.append(ScriptNodeDiagnostic(rel_path, exc.msg, exc.lineno))
            continue
        except UnicodeDecodeError as exc:
            diagnostics.append(ScriptNodeDiagnostic(rel_path, str(exc)))
            continue
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                item, node_diagnostics = _catalog_item_from_function(root, rel_path, node)
                diagnostics.extend(node_diagnostics)
                if item is not None:
                    items.append(item)
    return {
        "script_dir": str(root),
        "dev_environment": dev_environment,
        "nodes": [item.to_dict() for item in items],
        "diagnostics": [diag.to_dict() for diag in diagnostics],
    }


def create_script_node(project_dir: Path, name: str, description: str = "") -> Dict[str, Any]:
    """Create a new user script file and return its discovered catalog node."""

    display_name = str(name or "").strip()
    if not display_name:
        raise ValueError("script node name must be non-empty")
    display_description = str(description or "").strip()

    root = ensure_script_nodes_dir(project_dir)
    function_name = _script_function_name(display_name)
    module_path = _unique_script_module_path(root, function_name)
    path = root / module_path
    template = "\n".join(
        [
            "from multi_agent_tcp.blueprint_script_nodes import blueprint_node",
            "",
            f"@blueprint_node(name={json.dumps(display_name)}, description={json.dumps(display_description)})",
            f"def {function_name}(payload: dict) -> dict:",
            "    return payload",
            "",
        ]
    )
    path.write_text(template, encoding="utf-8")

    discovered = discover_script_nodes(project_dir)
    node = next(
        (
            item
            for item in discovered["nodes"]
            if item.get("module_path") == module_path and item.get("function_name") == function_name
        ),
        None,
    )
    return {
        "script_dir": discovered["script_dir"],
        "dev_environment": discovered.get("dev_environment"),
        "file_path": str(path.resolve()),
        "module_path": module_path,
        "function_name": function_name,
        "node": node,
        "diagnostics": discovered["diagnostics"],
    }


async def execute_script_node(
    script_root: Path,
    node: Any,
    payload: Any,
    *,
    input_port: Optional[str] = None,
) -> Dict[str, Any]:
    module_path = _node_field(node, "module_path")
    function_name = _node_field(node, "function_name")
    if not module_path:
        raise ValueError("ScriptNode.module_path must be non-empty")
    if not function_name:
        raise ValueError("ScriptNode.function_name must be non-empty")

    script_path = _resolve_script_path(Path(script_root), str(module_path))
    module = _load_script_module(script_path, Path(script_root))
    func = getattr(module, str(function_name), None)
    if not callable(func):
        raise ValueError(f"script function not found: {module_path}:{function_name}")

    inputs = _ports_from_node(node, "inputs")
    outputs = _ports_from_node(node, "outputs") or [ScriptNodePort("result", "Any")]
    args, kwargs = _call_args_for_payload(func, inputs, payload, input_port=input_port)
    value = func(*args, **kwargs)
    if inspect.isawaitable(value):
        value = await value
    output_payload = _normalize_script_output(outputs, value)
    return {
        "script_id": _node_field(node, "script_id"),
        "module_path": str(module_path),
        "function_name": str(function_name),
        "outputs": output_payload,
        "result": output_payload.get("result", value),
    }


def validate_script_node_references(project_dir: Path, nodes: Iterable[Any]) -> None:
    discovered = discover_script_nodes(project_dir)
    available = {
        (str(item.get("module_path")), str(item.get("function_name")))
        for item in discovered["nodes"]
        if isinstance(item, dict)
    }
    missing: List[str] = []
    for node in nodes:
        key = (str(_node_field(node, "module_path") or ""), str(_node_field(node, "function_name") or ""))
        if key not in available:
            node_id = _node_field(node, "node_id") or key[1] or "<unknown>"
            missing.append(f"{node_id} ({key[0]}:{key[1]})")
    if missing:
        raise ValueError("missing script node function(s): " + ", ".join(missing))


def _catalog_item_from_function(
    root: Path,
    rel_path: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[Optional[ScriptNodeCatalogItem], List[ScriptNodeDiagnostic]]:
    decorator = _blueprint_decorator(node)
    if decorator is None:
        return None, []

    diagnostics: List[ScriptNodeDiagnostic] = []
    title = _decorator_string_kw(decorator, "name") or node.name
    description = _decorator_string_kw(decorator, "description") or ast.get_docstring(node) or ""
    explicit_inputs = _decorator_ports_kw(decorator, "inputs")
    explicit_outputs = _decorator_ports_kw(decorator, "outputs")

    if explicit_inputs is not None:
        inputs = explicit_inputs
        diagnostics.extend(_decorator_port_diagnostics(decorator, "inputs", rel_path, node.name, getattr(node, "lineno", None)))
    else:
        inputs = _inputs_from_signature(node)
        diagnostics.extend(_signature_input_diagnostics(rel_path, node))
    if explicit_outputs is not None:
        outputs = explicit_outputs
        diagnostics.extend(_decorator_port_diagnostics(decorator, "outputs", rel_path, node.name, getattr(node, "lineno", None)))
    else:
        outputs = [_return_port_from_signature(node)]
        diagnostics.extend(_return_annotation_diagnostics(rel_path, node))
    for port in [*inputs, *outputs]:
        if port.type not in SUPPORTED_PORT_TYPES:
            diagnostics.append(
                ScriptNodeDiagnostic(
                    rel_path,
                    f"unsupported port type {port.type!r} on {node.name}.{port.name}; using Any",
                    getattr(node, "lineno", None),
                )
            )
            port.type = "Any"

    return (
        ScriptNodeCatalogItem(
            script_id=f"{rel_path}:{node.name}",
            module_path=rel_path,
            function_name=node.name,
            title=title,
            description=description,
            inputs=inputs,
            outputs=outputs,
        ),
        diagnostics,
    )


def _blueprint_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Optional[ast.AST]:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == "blueprint_node":
            return decorator
        if isinstance(target, ast.Attribute) and target.attr == "blueprint_node":
            return decorator
    return None


def _decorator_string_kw(decorator: ast.AST, name: str) -> str:
    if not isinstance(decorator, ast.Call):
        return ""
    for keyword in decorator.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant):
            return str(keyword.value.value or "").strip()
    return ""


def _decorator_ports_kw(decorator: ast.AST, name: str) -> Optional[List[ScriptNodePort]]:
    if not isinstance(decorator, ast.Call):
        return None
    for keyword in decorator.keywords:
        if keyword.arg != name:
            continue
        if not isinstance(keyword.value, ast.Dict):
            return []
        ports: List[ScriptNodePort] = []
        for raw_key, raw_value in zip(keyword.value.keys, keyword.value.values):
            if not isinstance(raw_key, ast.Constant):
                continue
            port_name = str(raw_key.value or "").strip()
            if not port_name:
                continue
            ports.append(ScriptNodePort(port_name, _annotation_name(raw_value), True))
        return ports
    return None


def _decorator_port_diagnostics(
    decorator: ast.AST,
    name: str,
    rel_path: str,
    function_name: str,
    line: Optional[int],
) -> List[ScriptNodeDiagnostic]:
    if not isinstance(decorator, ast.Call):
        return []
    diagnostics: List[ScriptNodeDiagnostic] = []
    for keyword in decorator.keywords:
        if keyword.arg != name:
            continue
        if not isinstance(keyword.value, ast.Dict):
            return [
                ScriptNodeDiagnostic(
                    rel_path,
                    f"blueprint_node {name} for {function_name} must be a dict; using no ports",
                    line,
                )
            ]
        for raw_key, raw_value in zip(keyword.value.keys, keyword.value.values):
            if not isinstance(raw_key, ast.Constant):
                continue
            port_name = str(raw_key.value or "").strip()
            if not port_name:
                continue
            diagnostics.extend(_annotation_diagnostics(rel_path, function_name, port_name, raw_value, line))
    return diagnostics


def _inputs_from_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> List[ScriptNodePort]:
    positional = list(node.args.posonlyargs) + list(node.args.args)
    defaults = list(node.args.defaults)
    required_cutoff = len(positional) - len(defaults)
    ports: List[ScriptNodePort] = []
    for index, arg in enumerate(positional):
        ports.append(
            ScriptNodePort(
                arg.arg,
                _annotation_name(arg.annotation),
                required=index < required_cutoff,
            )
        )
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        ports.append(ScriptNodePort(arg.arg, _annotation_name(arg.annotation), required=default is None))
    return ports


def _return_port_from_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ScriptNodePort:
    return ScriptNodePort("result", _annotation_name(node.returns), True)


def _signature_input_diagnostics(rel_path: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> List[ScriptNodeDiagnostic]:
    diagnostics: List[ScriptNodeDiagnostic] = []
    for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
        diagnostics.extend(_annotation_diagnostics(rel_path, node.name, arg.arg, arg.annotation, getattr(arg, "lineno", None)))
    return diagnostics


def _return_annotation_diagnostics(rel_path: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> List[ScriptNodeDiagnostic]:
    return _annotation_diagnostics(rel_path, node.name, "result", node.returns, getattr(node, "lineno", None), return_port=True)


def _annotation_diagnostics(
    rel_path: str,
    function_name: str,
    port_name: str,
    annotation: ast.AST | None,
    line: Optional[int],
    *,
    return_port: bool = False,
) -> List[ScriptNodeDiagnostic]:
    if annotation is None:
        target = "return value" if return_port else f"parameter {port_name!r}"
        return [
            ScriptNodeDiagnostic(
                rel_path,
                f"missing type annotation for {function_name} {target}; using Any",
                line,
            )
        ]
    raw = _raw_annotation_name(annotation)
    normalized = _normalize_port_type(raw)
    if normalized == "Any" and raw not in {"Any", "typing.Any", "any"}:
        return [
            ScriptNodeDiagnostic(
                rel_path,
                f"unsupported type annotation {raw!r} for {function_name}.{port_name}; using Any",
                line,
            )
        ]
    return []


def _annotation_name(value: ast.AST | None) -> str:
    if value is None:
        return "Any"
    if isinstance(value, ast.Name):
        return _normalize_port_type(value.id)
    if isinstance(value, ast.Attribute):
        return _normalize_port_type(value.attr)
    if isinstance(value, ast.Subscript):
        return _annotation_name(value.value)
    if isinstance(value, ast.Constant):
        return _normalize_port_type(str(value.value))
    return "Any"


def _raw_annotation_name(value: ast.AST | None) -> str:
    if value is None:
        return ""
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        if isinstance(value.value, ast.Name):
            return f"{value.value.id}.{value.attr}"
        return value.attr
    if isinstance(value, ast.Subscript):
        return _raw_annotation_name(value.value)
    if isinstance(value, ast.Constant):
        return str(value.value)
    try:
        return ast.unparse(value)
    except Exception:
        return "Any"


def _normalize_port_type(value: Any) -> str:
    raw = getattr(value, "__name__", value)
    text = str(raw or "Any").strip()
    aliases = {
        "integer": "int",
        "number": "float",
        "string": "str",
        "boolean": "bool",
        "object": "dict",
        "array": "list",
        "typing.Any": "Any",
        "any": "Any",
    }
    return aliases.get(text, text if text in SUPPORTED_PORT_TYPES else "Any")


def _relative_module_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _script_function_name(name: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", name.strip().lower()).strip("_")
    if not normalized:
        normalized = "function_node"
    if normalized[0].isdigit():
        normalized = f"node_{normalized}"
    return normalized


def _unique_script_module_path(root: Path, function_name: str) -> str:
    for index in range(1, 10_000):
        suffix = "" if index == 1 else f"_{index}"
        candidate = f"{function_name}{suffix}.py"
        if not (root / candidate).exists():
            return candidate
    return f"{function_name}_{uuid.uuid4().hex}.py"


def _framework_source_dir() -> Path:
    return Path(__file__).resolve().parent


def _framework_import_root(source_dir: Path) -> Path:
    if source_dir.name == "multi_agent_tcp":
        return source_dir.parent.resolve()
    return source_dir.resolve()


def _read_json_object(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _write_json_if_changed(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    try:
        if path.read_text(encoding="utf-8") == text:
            return
    except OSError:
        pass
    path.write_text(text, encoding="utf-8")


def _merged_pyright_config(current: Mapping[str, Any], import_root: Path) -> Dict[str, Any]:
    config = dict(current)
    config.setdefault("include", ["."])
    config["extraPaths"] = _json_string_list_with(config.get("extraPaths"), str(import_root))
    config["pythonVersion"] = f"{sys.version_info.major}.{sys.version_info.minor}"
    return config


def _merged_vscode_settings(current: Mapping[str, Any], import_root: Path) -> Dict[str, Any]:
    settings = dict(current)
    settings["python.analysis.extraPaths"] = _json_string_list_with(
        settings.get("python.analysis.extraPaths"),
        str(import_root),
    )
    settings.setdefault("python.defaultInterpreterPath", sys.executable)
    return settings


def _json_string_list_with(value: Any, item: str) -> List[str]:
    items = [entry for entry in value if isinstance(entry, str)] if isinstance(value, list) else []
    normalized = {entry.casefold() for entry in items}
    if item.casefold() not in normalized:
        items.append(item)
    return items


def _resolve_script_path(script_root: Path, module_path: str) -> Path:
    root = script_root.expanduser().resolve()
    raw = Path(str(module_path).replace("\\", "/"))
    if raw.is_absolute() or any(part == ".." for part in raw.parts):
        raise ValueError("ScriptNode.module_path must stay inside the script directory")
    path = (root / raw).resolve()
    if root not in path.parents and path != root:
        raise ValueError("ScriptNode.module_path escapes the script directory")
    if path.suffix != ".py":
        raise ValueError("ScriptNode.module_path must point to a .py file")
    if not path.is_file():
        raise FileNotFoundError(f"script file not found: {module_path}")
    return path


def _load_script_module(path: Path, script_root: Path) -> Any:
    module_name = f"_gulicode_blueprint_script_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load script module: {path}")
    module = importlib.util.module_from_spec(spec)
    root_text = str(script_root.resolve())
    inserted = False
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
        inserted = True
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted:
            try:
                sys.path.remove(root_text)
            except ValueError:
                pass
    return module


def _ports_from_node(node: Any, field_name: str) -> List[ScriptNodePort]:
    raw = _node_field(node, field_name) or []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    ports = []
    for index, item in enumerate(raw):
        default_name = "result" if field_name == "outputs" and index == 0 else f"port{index + 1}"
        ports.append(ScriptNodePort.from_value(item, default_name=default_name))
    return ports


def _node_field(node: Any, field_name: str) -> Any:
    if isinstance(node, Mapping):
        return node.get(field_name)
    return getattr(node, field_name, None)


def _call_args_for_payload(
    func: Callable[..., Any],
    inputs: Sequence[ScriptNodePort],
    payload: Any,
    *,
    input_port: Optional[str] = None,
) -> tuple[List[Any], Dict[str, Any]]:
    if not inputs:
        return [], {}
    if len(inputs) == 1 and (not isinstance(payload, Mapping) or input_port):
        return [], {inputs[0].name: payload}
    payload_map = payload if isinstance(payload, Mapping) else {"result": payload, "value": payload}
    kwargs: Dict[str, Any] = {}
    for port in inputs:
        if port.name in payload_map:
            kwargs[port.name] = payload_map[port.name]
        elif port.required:
            raise ValueError(f"missing required script input: {port.name}")
    signature = inspect.signature(func)
    accepted = {
        name
        for name, param in signature.parameters.items()
        if param.kind
        in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    }
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return [], kwargs
    return [], {key: value for key, value in kwargs.items() if key in accepted}


def _normalize_script_output(outputs: Sequence[ScriptNodePort], value: Any) -> Dict[str, Any]:
    if len(outputs) <= 1:
        return {outputs[0].name if outputs else "result": value}
    if not isinstance(value, Mapping):
        raise ValueError("script node with multiple outputs must return a dict")
    missing = [port.name for port in outputs if port.name not in value]
    if missing:
        raise ValueError("script node result missing output key(s): " + ", ".join(missing))
    return {port.name: value[port.name] for port in outputs}


def run_script_node(script_root: Path, node: Any, payload: Any, *, input_port: Optional[str] = None) -> Dict[str, Any]:
    return asyncio.run(execute_script_node(script_root, node, payload, input_port=input_port))
