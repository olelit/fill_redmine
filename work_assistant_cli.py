import argparse
import asyncio

from dto.import_action import ImportAction
from services.import_service import ImportService
from services.preview_service import PreviewService
from storage.database import migrate_default_legacy_database
from storage.migration import migrate_from_user_list, migrate_users_to_projects
from storage.project_repository import ProjectRepository
from storage.user_repository import UserRepository


async def main(
    project_id: int | None = None,
    action: ImportAction = ImportAction.REDMINE_FILL,
    override_issue_id: int | None = None,
    repo: ProjectRepository | None = None,
) -> None:
    repository = repo if repo is not None else ProjectRepository()
    if project_id is None:
        projects = repository.list_projects()
        if not projects:
            print("No projects found.")
            return
        for project in projects:
            print(f"{project.db_id}: {project.name}")
        return

    project = repository.get_project(project_id)
    if project is None:
        print(f"Project {project_id} not found.")
        return
    if override_issue_id:
        config = dict(project.trackers.get("redmine", {}))
        config["issue_id"] = override_issue_id
        project.trackers["redmine"] = config

    PreviewService.print_header()
    service = ImportService()
    result = service.prepare(project, action)

    for item in result.items:
        PreviewService.print_preview(item.preview)
    for preview in result.errors:
        PreviewService.print_preview(preview)

    if not result.items:
        print("No time entries to import.")
        return

    proceed = input("Proceed with import? (y/n): ").strip().lower()
    if proceed != "y":
        print("Import cancelled by the user.")
        return

    print("\nStarting import...\n")
    summary = await service.run(result.items)
    success = summary.total - len(summary.errors)
    print(f"Import finished: {success} entries, {len(summary.errors)} errors.")


def cli() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=int, help="Project ID")
    parser.add_argument(
        "--action",
        choices=[action.value for action in ImportAction],
        default=None,
    )
    parser.add_argument("--id", type=int, help="Override Redmine issue ID")
    args = parser.parse_args()

    if args.project is None and (args.id is not None or args.action is not None):
        parser.error("--id/--action требуют --project")

    action = (
        ImportAction(args.action)
        if args.action is not None
        else ImportAction.REDMINE_FILL
    )

    migrate_default_legacy_database()
    user_repo = UserRepository()
    project_repo = ProjectRepository()
    migrate_from_user_list(user_repo)
    migrate_users_to_projects(project_repo, user_repo)
    asyncio.run(
        main(
            project_id=args.project,
            action=action,
            override_issue_id=args.id,
            repo=project_repo,
        )
    )


if __name__ == "__main__":
    cli()
