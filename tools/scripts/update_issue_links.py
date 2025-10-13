#!/usr/bin/env python3
"""Update GitHub Issue links to use absolute GitHub URLs."""

import json
import re
import subprocess
from pathlib import Path


def extract_project_info(planning_path: Path) -> dict:
    """Extract title and overview from planning.md."""
    content = planning_path.read_text(encoding="utf-8")

    # Extract title (first # heading)
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1) if title_match else planning_path.parent.name

    # Extract overview section
    overview_match = re.search(
        r"##\s+Overview\s*\n+(.*?)(?=\n##|\Z)", content, re.DOTALL
    )
    overview = overview_match.group(1).strip() if overview_match else ""

    # Truncate overview if too long
    if len(overview) > 500:
        overview = overview[:500] + "..."

    return {"title": title, "overview": overview}


def get_issue_number_by_title(title: str) -> str | None:
    """Get issue number by title."""
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--state", "all", "--json", "number,title"],
            capture_output=True,
            text=True,
            check=True,
        )
        issues = json.loads(result.stdout)
        for issue in issues:
            if issue["title"] == title:
                return str(issue["number"])
        return None
    except subprocess.CalledProcessError:
        return None


def update_issue(project_dir: Path, repo_info: dict, dry_run: bool = False) -> None:
    """Update GitHub Issue body with correct links.

    Args:
        project_dir: Path to project directory
        repo_info: Repository info dict with 'owner' and 'name'
        dry_run: If True, only print what would be updated
    """
    planning_path = project_dir / "planning.md"

    if not planning_path.exists():
        print(f"⚠️  Skipping {project_dir.name}: No planning.md")
        return

    info = extract_project_info(planning_path)
    issue_number = get_issue_number_by_title(info["title"])

    if not issue_number:
        print(f"⚠️  Skipping {project_dir.name}: Issue not found")
        return

    # Build GitHub URLs
    owner = repo_info["owner"]["login"]
    repo_name = repo_info["name"]
    base_url = f"https://github.com/{owner}/{repo_name}/blob/main"

    planning_rel_path = planning_path.relative_to(Path.cwd())
    planning_url = f"{base_url}/{planning_rel_path}"

    # Check if project is completed
    is_completed = "_archived" in str(project_dir)

    # Create issue body
    body = f"""{info['overview']}

**Project Directory**: `{project_dir.relative_to(Path.cwd())}`

**Planning Document**: [{project_dir.name}/planning.md]({planning_url})
"""

    if is_completed:
        completion_path = project_dir / "completion_report.md"
        if completion_path.exists():
            completion_rel_path = completion_path.relative_to(Path.cwd())
            completion_url = f"{base_url}/{completion_rel_path}"
            body += f"\n**Completion Report**: [{project_dir.name}/completion_report.md]({completion_url})\n"

    if dry_run:
        print(f"🔍 Would update Issue #{issue_number}: {info['title']}")
        print(f"   Planning URL: {planning_url}")
        if is_completed and (project_dir / "completion_report.md").exists():
            completion_rel_path = (project_dir / "completion_report.md").relative_to(
                Path.cwd()
            )
            completion_url = f"{base_url}/{completion_rel_path}"
            print(f"   Completion URL: {completion_url}")
        return

    # Update issue using gh CLI
    cmd = ["gh", "issue", "edit", issue_number, "--body", body]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print(f"✅ Updated Issue #{issue_number}: {info['title']}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to update issue #{issue_number}: {e.stderr}")


def main():
    """Main function."""
    import sys

    dry_run = "--dry-run" in sys.argv

    if dry_run:
        print("\n🔍 DRY RUN MODE - No changes will be made\n")

    # Get repository info
    try:
        result = subprocess.run(
            ["gh", "repo", "view", "--json", "owner,name"],
            capture_output=True,
            text=True,
            check=True,
        )
        repo_info = json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to get repository info: {e.stderr}")
        return

    project_root = Path.cwd() / "docs" / "project"

    # Active projects
    print("\n🔵 Updating active project issues...\n")
    active_dirs = sorted(project_root.glob("2025-*"))
    for project_dir in active_dirs:
        if project_dir.is_dir():
            update_issue(project_dir, repo_info, dry_run=dry_run)

    # Archived projects
    print("\n✅ Updating archived project issues...\n")
    archived_dirs = sorted((project_root / "_archived").glob("2025-*"))
    for project_dir in archived_dirs:
        if project_dir.is_dir():
            update_issue(project_dir, repo_info, dry_run=dry_run)

    if dry_run:
        print("\n🔍 Dry run complete. Run without --dry-run to apply changes.")
    else:
        print("\n🎉 Done!")


if __name__ == "__main__":
    main()
