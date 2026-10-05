from gui.app import MainWindow
from storage.migration import migrate_from_user_list
from storage.user_repository import UserRepository


def main() -> None:
    repository = UserRepository()
    migrate_from_user_list(repository, log=print)
    app = MainWindow(repository)
    app.mainloop()


if __name__ == "__main__":
    main()
