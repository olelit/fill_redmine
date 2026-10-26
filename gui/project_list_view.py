from collections.abc import Callable
from tkinter import messagebox, ttk

from configs.project_config import ProjectConfig
from gui.project_editor import ProjectEditor
from storage.project_repository import ProjectRepository
from trackers.registry import configured_trackers


class ProjectListView(ttk.Frame):
    def __init__(
        self,
        parent,
        repo: ProjectRepository,
        on_open: Callable[[ProjectConfig], None],
    ):
        super().__init__(parent, padding=6)
        self.repo = repo
        self.on_open = on_open
        self.projects_by_iid: dict[str, ProjectConfig] = {}
        self._build()
        self.refresh()

    def _build(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="+", width=3, command=self.add_project).pack(
            side="left", padx=2
        )
        for text, command in (
            ("Открыть", self.open_project),
            ("Настройки", self.edit_project),
            ("Удалить", self.delete_project),
        ):
            ttk.Button(toolbar, text=text, command=command).pack(
                side="left", padx=2
            )

        self.tree = ttk.Treeview(
            self,
            columns=("name", "git", "trackers"),
            show="headings",
            height=16,
        )
        for column, (title, width) in {
            "name": ("Проект", 220),
            "git": ("Git-репозиторий", 420),
            "trackers": ("Трекеры", 220),
        }.items():
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=6)
        self.tree.bind("<Double-1>", lambda event: self.open_project())
        self.tree.bind("<Return>", lambda event: self.open_project())

        self.empty_label = ttk.Label(
            self,
            text="Нажмите +, чтобы добавить проект",
            foreground="#777",
        )
        self.empty_label.pack(anchor="w")

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.projects_by_iid.clear()
        projects = self.repo.list_projects()
        for project in projects:
            labels = ", ".join(
                tracker.label for tracker in configured_trackers(project)
            )
            iid = self.tree.insert(
                "",
                "end",
                values=(project.name, project.git_repo_path or "—", labels or "—"),
            )
            self.projects_by_iid[iid] = project
        if projects:
            self.empty_label.pack_forget()
        else:
            self.empty_label.pack(anchor="w")

    def selected_project(self, show_message: bool = True) -> ProjectConfig | None:
        selection = self.tree.selection()
        if not selection:
            if show_message:
                messagebox.showinfo("Work Assistant", "Выберите проект", parent=self)
            return None
        return self.projects_by_iid[selection[0]]

    def add_project(self) -> None:
        editor = ProjectEditor(self, self.repo, None)
        self.wait_window(editor)
        if editor.result is not None:
            self.repo.add_project(editor.result)
            self.refresh()

    def edit_project(self) -> None:
        project = self.selected_project()
        if project is None:
            return
        editor = ProjectEditor(self, self.repo, project)
        self.wait_window(editor)
        if editor.result is not None:
            self.repo.update_project(project.db_id, editor.result)
            self.refresh()

    def delete_project(self) -> None:
        project = self.selected_project()
        if project is None:
            return
        if messagebox.askyesno(
            "Work Assistant",
            f"Удалить проект «{project.name}»?",
            parent=self,
        ):
            self.repo.delete_project(project.db_id)
            self.refresh()

    def open_project(self) -> None:
        project = self.selected_project(show_message=False)
        if project is not None:
            self.on_open(project)
