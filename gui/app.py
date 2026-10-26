import tkinter as tk
from tkinter import messagebox, ttk

from configs.project_config import ProjectConfig
from gui.project_list_view import ProjectListView
from gui.project_view import ProjectView
from gui.worker import GuiWorker
from services.import_service import ImportService
from storage.project_repository import ProjectRepository


class MainWindow(tk.Tk):
    def __init__(self, repo: ProjectRepository):
        super().__init__()
        self.repo = repo
        self.current_view: tk.Widget | None = None

        self.title("Work Assistant")
        self.geometry("1100x780")
        self.minsize(900, 620)

        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self.status = tk.StringVar(value="готово")
        ttk.Label(
            self,
            textvariable=self.status,
            relief="sunken",
            anchor="w",
            padding=2,
        ).pack(fill="x", side="bottom")

        self.worker = GuiWorker(self)
        self.worker.register("status", self._set_status)
        self.service = ImportService(
            log=lambda message: self.worker.send("status", message)
        )

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show_project_list()

    def _set_status(self, message: str) -> None:
        self.status.set(message)
        view = self.current_view
        if view is not None and hasattr(view, "log"):
            view.log(message)

    def _set_view(self, view: tk.Widget) -> None:
        if self.current_view is not None:
            self.current_view.destroy()
        self.current_view = view
        view.pack(fill="both", expand=True)

    def show_project_list(self) -> None:
        self.status.set("готово")
        self._set_view(
            ProjectListView(self.container, self.repo, on_open=self.show_project)
        )

    def show_project(self, project: ProjectConfig) -> None:
        self.status.set(project.name)
        self._set_view(
            ProjectView(
                self.container,
                project=project,
                repo=self.repo,
                worker=self.worker,
                service=self.service,
                on_back=self.show_project_list,
                on_project_updated=self.show_project,
            )
        )

    def _on_close(self) -> None:
        busy = bool(getattr(self.current_view, "busy", False))
        if busy and not messagebox.askyesno(
            "Work Assistant", "Работа выполняется. Закрыть окно?", parent=self
        ):
            return
        self.destroy()
