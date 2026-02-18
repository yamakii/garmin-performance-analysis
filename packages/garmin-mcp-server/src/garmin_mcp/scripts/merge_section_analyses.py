"""Merge section analysis JSON files into DuckDB.

Reads all .json files from a temp directory and inserts them into DuckDB
using GarminDBWriter. Replaces the manual LLM read-and-insert loop.

Usage:
    uv run python -m garmin_mcp.scripts.merge_section_analyses /tmp/analysis_21884133706
    uv run python -m garmin_mcp.scripts.merge_section_analyses /tmp/analysis_21884133706 --keep
"""

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

from garmin_mcp.database.db_writer import GarminDBWriter

logger = logging.getLogger(__name__)


def merge_section_analyses(temp_dir: Path, *, keep: bool = False) -> dict:
    """Merge all section analysis JSON files from temp_dir into DuckDB.

    Args:
        temp_dir: Directory containing section analysis .json files.
        keep: If True, do not delete temp_dir after successful merge.

    Returns:
        Dict with "succeeded", "failed", and "errors" keys.
    """
    json_files = sorted(temp_dir.glob("*.json"))
    if not json_files:
        return {"succeeded": [], "failed": [], "errors": ["No .json files found"]}

    writer = GarminDBWriter()
    succeeded: list[str] = []
    failed: list[str] = []
    errors: list[str] = []

    for json_file in json_files:
        section_type = json_file.stem
        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)

            activity_id = data["activity_id"]
            activity_date = str(data["activity_date"])
            analysis_data = data["analysis_data"]

            success = writer.insert_section_analysis(
                activity_id=activity_id,
                activity_date=activity_date,
                section_type=section_type,
                analysis_data=analysis_data,
            )

            if success:
                succeeded.append(section_type)
            else:
                failed.append(section_type)
                errors.append(f"{section_type}: insert returned False")

        except Exception as e:
            failed.append(section_type)
            errors.append(f"{section_type}: {e}")

    if not failed and not keep:
        shutil.rmtree(temp_dir)

    return {"succeeded": succeeded, "failed": failed, "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge section analysis JSON files into DuckDB"
    )
    parser.add_argument("temp_dir", type=Path, help="Directory containing .json files")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep temp directory after successful merge",
    )
    args = parser.parse_args()

    if not args.temp_dir.is_dir():
        print(
            json.dumps(
                {"succeeded": [], "failed": [], "errors": ["Directory not found"]}
            )
        )
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)
    result = merge_section_analyses(args.temp_dir, keep=args.keep)
    print(json.dumps(result))

    if result["failed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
