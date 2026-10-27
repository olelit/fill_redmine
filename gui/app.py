import tkinter as tk
from tkinter import messagebox, ttk

from configs.project_config import ProjectConfig
from gui.ai_settings_dialog import AiSettingsDialog
from gui.project_list_view import ProjectListView
from gui.project_view import ProjectView
from gui.tracking_view import TrackingView
from gui.worker import GuiWorker
from storage.project_repository import ProjectRepository
from storage.settings_repository import SettingsRepository


class MainWindow(tk.Tk):
    def __init__(
        self, repo: ProjectRepository, settings_repo: SettingsRepository
    ) -> None:
        super().__init__()
        self.repo = repo
        self.settings_repo = settings_repo
        self.worker = GuiWorker(self)
        self.current_view: tk.Widget | None = None

        self.title("Work Assistant")
        self.geometry("1100x780")
        self.minsize(900, 620)

        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self.status = tk.StringVar(value="готово")
        ttk.Label(
            self, textvariable=self.status, relief="sunken", anchor="w", padding=2
        ).pack(fill="x", side="bottom")
        self.worker.register("status", self._set_status)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.show_project_list()

    def _set_status(self, message: str) -> None:
        self.status.set(message)

    def _drop_view(self) -> None:
        if self.current_view is not None:
            self.current_view.destroy()
            self.current_view = None

    def _set_view(self, view: tk.Widget) -> None:
        self._drop_view()
        self.current_view = view
        view.pack(fill="both", expand=True)

    def show_project_list(self) -> None:
        self._drop_view()
        self.status.set("готово")
        self._set_view(
            ProjectListView(
                self.container,
                self.repo,
                self.settings_repo,
                on_open=self.show_project,
                on_ai_settings=self.show_ai_settings,
            )
        )

    def show_project(self, project: ProjectConfig) -> None:
        self._drop_view()
        self._set_view(
            ProjectView(
                self.container,
                project=project,
                repo=self.repo,
                settings_repo=self.settings_repo,
                worker=self.worker,
                on_back=self.show_project_list,
                on_tracking=self.show_tracking,
            )
        )

    def show_tracking(self, project: ProjectConfig) -> None:
        self._drop_view()
        self._set_view(
            TrackingView(
                self.container,
                project,
                self.repo,
                self.settings_repo,
                self.worker,
                on_back=lambda: self.show_project(project),
            )
        )

    def show_ai_settings(self) -> None:
        dialog = AiSettingsDialog(self, self.settings_repo, self.worker)
        self.wait_window(dialog)
        if dialog.saved:
            self.status.set("настройки AI сохранены")

    def _on_close(self) -> None:
        busy = bool(getattr(self.current_view, "busy", False))
        if busy and not messagebox.askyesno(
            "Work Assistant", "Работа выполняется. Закрыть окно?", parent=self
        ):
            return
        self.destroy()
