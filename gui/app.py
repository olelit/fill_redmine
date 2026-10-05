import tkinter as tk
from tkinter import messagebox, ttk

from gui.import_view import ImportView
from gui.user_list_view import UserListView
from gui.worker import GuiWorker
from services.import_service import ImportService
from storage.user_repository import UserRepository


class MainWindow(tk.Tk):
    def __init__(self, repo: UserRepository):
        super().__init__()
        self.repo = repo
        self.worker = GuiWorker(self)
        self.service = ImportService(log=lambda message: self.worker.send("log", message))

        self.title("Fill Redmine")
        self.geometry("1000x760")
        self.minsize(900, 600)

        self.user_list_view = UserListView(self, repo)
        self.user_list_view.pack(fill="both", expand=False, padx=6, pady=6)

        self.import_view = ImportView(
            self,
            service=self.service,
            worker=self.worker,
            get_users=self.user_list_view.users_for_action,
        )
        self.import_view.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self.status = tk.StringVar(value="готово")
        ttk.Label(
            self,
            textvariable=self.status,
            relief="sunken",
            anchor="w",
            padding=2,
        ).pack(fill="x", side="bottom")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        if self.import_view.busy:
            question = "Импорт выполняется. Закрыть окно?"
            if not messagebox.askyesno("Fill Redmine", question, parent=self):
                return
        self.destroy()
