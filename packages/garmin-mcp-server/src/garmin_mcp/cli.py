"""Typer CLI generated from the single-source tool registry.

Subcommands are grouped by ``ToolDef.cli_group`` (e.g. ``physiology``) and named
by ``ToolDef.cli_name`` (e.g. ``hr-efficiency``). Each command validates its
arguments via the ToolDef's Pydantic params model, invokes the handler against a
``GarminDBReader``, and prints ``json.dumps(result, default=str)`` to stdout.

Entry point: ``garmin-db`` (see pyproject ``[project.scripts]``).
"""

from __future__ import annotations

import inspect
import json
import types
import typing
from collections.abc import Callable
from typing import Annotated, Any

import typer
from pydantic.fields import FieldInfo

from garmin_mcp.database.connection import get_db_path
from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools import ALL_DEFS
from garmin_mcp.tools.registry import ToolDef

# Scalar types Typer can render directly as CLI parameters. Anything else
# (dict / list, e.g. ``plan`` / ``profile`` / ``activity_ids``) is accepted as a
# JSON string on the CLI and decoded back before Pydantic validation.
_CLI_SCALAR_TYPES = (str, int, float, bool)
_UNION_ORIGINS = (typing.Union, types.UnionType)


def _is_cli_scalar(annotation: Any) -> bool:
    """Return True if ``annotation`` (incl. Optional[...] scalar / Literal) is
    something Typer can render directly as a CLI parameter."""
    if annotation in _CLI_SCALAR_TYPES:
        return True
    origin = typing.get_origin(annotation)
    if origin in _UNION_ORIGINS:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return len(args) == 1 and args[0] in _CLI_SCALAR_TYPES
    # typing.Literal["parquet", "csv"] -> treat as str on the CLI.
    return origin is typing.Literal


app = typer.Typer(
    name="garmin-db",
    help="Garmin DuckDB CLI (single-source registry).",
    no_args_is_help=True,
)


def _run_tool(tool_def: ToolDef, arguments: dict[str, Any]) -> None:
    """Validate args, dispatch via the registry handler, print JSON to stdout."""
    reader = GarminDBReader(str(get_db_path()))
    params_instance = tool_def.params(**arguments)
    result = tool_def.handler(reader, params_instance)
    typer.echo(json.dumps(result, default=str, ensure_ascii=False))


def _make_command(tool_def: ToolDef) -> Callable[..., None]:
    """Build a Typer command callback whose parameters mirror the params model.

    Required fields (no default) become CLI arguments; fields with defaults
    become options. A shared ``--json`` flag is accepted for parity with the
    documented invocation (output is always JSON).
    """
    fields: dict[str, FieldInfo] = tool_def.params.model_fields

    # Fields whose type Typer cannot render are accepted as JSON strings and
    # decoded before validation.
    json_fields = {
        name
        for name, field in fields.items()
        if not _is_cli_scalar(field.annotation if field.annotation is not None else str)
    }

    def command(**kwargs: Any) -> None:
        kwargs.pop("json_output", None)
        for name in json_fields:
            raw = kwargs.get(name)
            if isinstance(raw, str):
                kwargs[name] = json.loads(raw)
        # Drop optional args left at their sentinel ``None`` so Pydantic applies
        # its own defaults (matches MCP behavior where omitted args are absent).
        cleaned = {k: v for k, v in kwargs.items() if v is not None}
        _run_tool(tool_def, cleaned)

    parameters: list[inspect.Parameter] = []
    for field_name, field in fields.items():
        annotation = field.annotation if field.annotation is not None else str
        if field_name in json_fields:
            annotation = str
        if field.is_required():
            param_decl: Any = typer.Argument(help=field.description)
            default: Any = inspect.Parameter.empty
        else:
            param_decl = typer.Option(help=field.description)
            default = field.default
        parameters.append(
            inspect.Parameter(
                name=field_name,
                kind=inspect.Parameter.KEYWORD_ONLY,
                default=default,
                annotation=Annotated[annotation, param_decl],
            )
        )

    # ``--json`` flag (output is always JSON; accepted for invocation parity).
    parameters.append(
        inspect.Parameter(
            name="json_output",
            kind=inspect.Parameter.KEYWORD_ONLY,
            default=False,
            annotation=Annotated[
                bool,
                typer.Option("--json", help="Emit JSON (default; always on)."),
            ],
        )
    )

    command.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
    command.__name__ = tool_def.cli_name.replace("-", "_")
    return command


def _build_groups(defs: list[ToolDef]) -> None:
    """Register a Typer sub-app per ``cli_group`` and attach commands."""
    groups: dict[str, typer.Typer] = {}
    for tool_def in defs:
        group = groups.get(tool_def.cli_group)
        if group is None:
            group = typer.Typer(
                help=f"{tool_def.cli_group} tools.", no_args_is_help=True
            )
            groups[tool_def.cli_group] = group
            app.add_typer(group, name=tool_def.cli_group)
        group.command(name=tool_def.cli_name)(_make_command(tool_def))


_build_groups(ALL_DEFS)


if __name__ == "__main__":  # pragma: no cover
    app()
