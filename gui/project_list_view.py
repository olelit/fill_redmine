from collections.abc import Callable
from tkinter import messagebox, simpledialog, ttk

from configs.project_config import ProjectConfig
from storage.project_repository import ProjectRepository
from storage.settings_repository import SettingsRepository


class ProjectListView(ttk.Frame):
    def __init__(
        self,
        parent,
        repo: ProjectRepository,
        settings_repo: SettingsRepository,
        on_open: Callable[[ProjectConfig], None],
        on_ai_settings: Callable[[], None],
    ) -> None:
        super().__init__(parent, padding=6)
        self.repo = repo
        self.settings_repo = settings_repo
        self.on_open = on_open
        self.on_ai_settings = on_ai_settings
        self.projects_by_iid: dict[str, ProjectConfig] = {}
        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Добавить", command=self.add_project).pack(
            side="left", padx=2
        )
        ttk.Button(toolbar, text="Удалить", command=self.delete_project).pack(
            side="left", padx=2
        )
        ttk.Button(
            toolbar, text="Настройки AI", command=self.on_ai_settings
        ).pack(side="right", padx=2)

        self.tree = ttk.Treeview(
            self, columns=("name",), show="headings", height=16
        )
        self.tree.heading("name", text="Проект")
        self.tree.column("name", width=700, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=6)
        self.tree.bind("<Double-1>", lambda event: self.open_project())
        self.tree.bind("<Return>", lambda event: self.open_project())
        self.empty = ttk.Label(
            self, text="Нажмите «Добавить», чтобы создать проект", foreground="#777"
        )
        self.empty.pack(anchor="w")

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.projects_by_iid.clear()
        projects = self.repo.list_projects()
        for project in projects:
            iid = self.tree.insert("", "end", values=(project.name,))
            self.projects_by_iid[iid] = project
        if projects:
            self.empty.pack_forget()
        else:
            self.empty.pack(anchor="w")

    def selected_project(self, show: bool = True) -> ProjectConfig | None:
        selection = self.tree.selection()
        if not selection:
            if show:
                messagebox.showinfo("Work Assistant", "Выберите проект", parent=self)
            return None
        return self.projects_by_iid[selection[0]]

    def add_project(self) -> None:
        name = simpledialog.askstring("Новый проект", "Имя проекта:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if self.repo.find_by_name(name) is not None:
            messagebox.showerror("Work Assistant", "Проект с таким именем уже есть", parent=self)
            return
        project_id = self.repo.add_project(ProjectConfig(name=name))
        project = self.repo.get_project(project_id)
        self.refresh()
        if project is not None:
            self.on_open(project)

    def delete_project(self) -> None:
        project = self.selected_project()
        if project is None:
            return
        if messagebox.askyesno(
            "Work Assistant", f"Удалить проект «{project.name}»?", parent=self
        ):
            self.repo.delete_project(project.db_id)
            self.refresh()

    def open_project(self) -> None:
        project = self.selected_project(show=False)
        if project is not None:
            self.on_open(project)
