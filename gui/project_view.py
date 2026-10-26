import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from configs.project_config import ProjectConfig
from gui.project_editor import ProjectEditor
from gui.worker import GuiWorker
from services.import_service import ImportService
from storage.project_repository import ProjectRepository


class ProjectView(ttk.Frame):
    def __init__(
        self,
        parent,
        project: ProjectConfig,
        repo: ProjectRepository,
        worker: GuiWorker,
        service: ImportService,
        on_back: Callable[[], None],
        on_project_updated: Callable[[ProjectConfig], None],
    ):
        super().__init__(parent, padding=6)
        self.project = project
        self.repo = repo
        self.worker = worker
        self.service = service
        self.on_back = on_back
        self.on_project_updated = on_project_updated

        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Button(header, text="← Проекты", command=self._back).pack(side="left")
        ttk.Label(
            header,
            text=project.name,
            font=("TkDefaultFont", 14, "bold"),
        ).pack(side="left", padx=12)
        ttk.Button(header, text="Настройки", command=self._settings).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, pady=6)
        self._build_placeholders()

    def _build_placeholders(self) -> None:
        for title in ("Redmine", "YouTrack → Redmine", "Коммиты и план"):
            frame = ttk.Frame(self.notebook, padding=12)
            ttk.Label(frame, text="Вкладка будет добавлена следующим шагом").pack()
            self.notebook.add(frame, text=title)

    @property
    def busy(self) -> bool:
        return False

    def _back(self) -> None:
        if self.busy and not messagebox.askyesno(
            "Work Assistant", "Идёт работа. Вернуться к списку проектов?", parent=self
        ):
            return
        self.on_back()

    def _settings(self) -> None:
        if self.busy:
            messagebox.showinfo("Work Assistant", "Дождитесь завершения работы", parent=self)
            return
        editor = ProjectEditor(self, self.repo, self.project)
        self.wait_window(editor)
        if editor.result is not None:
            self.repo.update_project(self.project.db_id, editor.result)
            self.on_project_updated(editor.result)
