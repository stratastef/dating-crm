"""Every module in `app/`, imported. A module joins the API by defining `router` and the worker by using `@handler`;
no list of modules is kept anywhere, so two tickets never edit the same line to register themselves."""

import importlib
import pkgutil
from collections.abc import Iterator
from types import ModuleType

from fastapi import APIRouter

import app

ENTRY_POINTS = {"main", "worker"}


def modules() -> Iterator[ModuleType]:
    for info in sorted(pkgutil.iter_modules(app.__path__), key=lambda info: info.name):
        if info.name not in ENTRY_POINTS:
            yield importlib.import_module(f"app.{info.name}")


def routers() -> Iterator[APIRouter]:
    for module in modules():
        if router := getattr(module, "router", None):
            yield router
