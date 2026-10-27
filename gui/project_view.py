from collections.abc import Callable
from tkinter import ttk

from configs.project_config import ProjectConfig
from gui.worker import GuiWorker
from storage.project_repository import ProjectRepository
from storage.settings_repository import SettingsRepository


class ProjectView(ttk.Frame):
    def __init__(
        self,
        parent,
        project: ProjectConfig,
        repo: ProjectRepository,
        settings_repo: SettingsRepository,
        worker: GuiWorker,
        on_back: Callable[[], None],
        on_tracking: Callable[[ProjectConfig], None],
    ) -> None:
        super().__init__(parent, padding=6)
        self.project = project
        self.repo = repo
        self.settings_repo = settings_repo
        self.worker = worker
        self.on_back = on_back
        self.on_tracking = on_tracking

        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Button(header, text="← Проекты", command=self.on_back).pack(side="left")
        ttk.Label(
            header, text=project.name, font=("TkDefaultFont", 14, "bold")
        ).pack(side="left", padx=12)

        menu = ttk.LabelFrame(self, text="Меню", padding=8)
        menu.pack(fill="x", pady=12)
        ttk.Button(
            menu,
            text="Трекинг времени",
            command=lambda: self.on_tracking(self.project),
        ).pack(anchor="w")

    @property
    def busy(self) -> bool:
        return False
