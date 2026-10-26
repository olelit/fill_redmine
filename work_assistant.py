from gui.app import MainWindow
from storage.database import migrate_default_legacy_database
from storage.migration import migrate_from_user_list, migrate_users_to_projects
from storage.project_repository import ProjectRepository
from storage.user_repository import UserRepository


def main() -> None:
    migrate_default_legacy_database(log=print)
    user_repo = UserRepository()
    project_repo = ProjectRepository()
    migrate_from_user_list(user_repo, log=print)
    migrate_users_to_projects(project_repo, user_repo, log=print)
    app = MainWindow(project_repo)
    app.mainloop()


if __name__ == "__main__":
    main()
