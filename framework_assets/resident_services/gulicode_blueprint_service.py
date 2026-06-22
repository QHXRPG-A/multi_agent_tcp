"""Public helpers for GuLiCode Blueprint resident services.

Resident service files import these decorators from this local module so
editor navigation stays inside the resident service workspace.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def blueprint_service(
    cls: type[Any] | None = None,
    *,
    name: str | None = None,
    title: str | None = None,
    description: str = "",
) -> Callable[[type[Any]], type[Any]] | type[Any]:
    """Mark a class as a Blueprint resident service."""

    def decorate(target: type[Any]) -> type[Any]:
        target.__blueprint_service__ = {
            "name": name,
            "title": title,
            "description": description,
        }
        return target

    if cls is None:
        return decorate
    return decorate(cls)


def service_method(
    func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str = "",
) -> Callable[..., Any]:
    """Expose a method on a Blueprint resident service."""

    def decorate(target: Callable[..., Any]) -> Callable[..., Any]:
        target.__blueprint_service_method__ = {
            "name": name,
            "description": description,
        }
        return target

    if func is None:
        return decorate
    return decorate(func)
