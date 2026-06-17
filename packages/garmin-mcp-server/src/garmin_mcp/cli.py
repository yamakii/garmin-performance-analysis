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
from collections.abc import Callable
from typing import Annotated, Any

import typer
from pydantic.fields import FieldInfo

from garmin_mcp.database.connection import get_db_path
from garmin_mcp.database.db_reader import GarminDBReader
from garmin_mcp.tools.physiology import PHYSIOLOGY_TOOLS
from garmin_mcp.tools.registry import ToolDef

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

    def command(**kwargs: Any) -> None:
        kwargs.pop("json_output", None)
        _run_tool(tool_def, kwargs)

    parameters: list[inspect.Parameter] = []
    for field_name, field in fields.items():
        annotation = field.annotation if field.annotation is not None else str
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


_build_groups(PHYSIOLOGY_TOOLS)


if __name__ == "__main__":  # pragma: no cover
    app()
