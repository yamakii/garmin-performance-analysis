#!/usr/bin/env python3
"""Create GitHub Issues for all projects in docs/project/."""

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


def create_issue(project_dir: Path, is_completed: bool, repo_info: dict) -> None:
    """Create GitHub Issue for a project.

    Args:
        project_dir: Path to project directory
        is_completed: Whether project is completed
        repo_info: Repository info dict with 'owner' and 'name'
    """
    planning_path = project_dir / "planning.md"

    if not planning_path.exists():
        print(f"⚠️  Skipping {project_dir.name}: No planning.md")
        return

    info = extract_project_info(planning_path)

    # Build GitHub URLs
    owner = repo_info["owner"]["login"]
    repo_name = repo_info["name"]
    base_url = f"https://github.com/{owner}/{repo_name}/blob/main"

    planning_rel_path = planning_path.relative_to(Path.cwd())
    planning_url = f"{base_url}/{planning_rel_path}"

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

    # Create issue using gh CLI
    cmd = ["gh", "issue", "create", "--title", info["title"], "--body", body]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        issue_url = result.stdout.strip()

        # If completed, close the issue immediately
        if is_completed:
            issue_number = issue_url.split("/")[-1]
            subprocess.run(
                ["gh", "issue", "close", issue_number, "--reason", "completed"],
                check=True,
            )
            print(f"✅ Created & closed: {info['title']} ({issue_url})")
        else:
            print(f"✅ Created: {info['title']} ({issue_url})")

    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create issue for {project_dir.name}: {e.stderr}")


def main():
    """Main function."""
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

    # Active projects (open issues)
    print("\n🔵 Creating issues for active projects...\n")
    active_dirs = sorted(project_root.glob("2025-*"))
    for project_dir in active_dirs:
        if project_dir.is_dir():
            create_issue(project_dir, is_completed=False, repo_info=repo_info)

    # Archived projects (closed issues)
    print("\n✅ Creating issues for archived projects...\n")
    archived_dirs = sorted((project_root / "_archived").glob("2025-*"))
    for project_dir in archived_dirs:
        if project_dir.is_dir():
            create_issue(project_dir, is_completed=True, repo_info=repo_info)

    print("\n🎉 Done!")


if __name__ == "__main__":
    main()
