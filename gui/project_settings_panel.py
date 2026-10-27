import tkinter as tk
from collections.abc import Callable
from tkinter import filedialog, messagebox, ttk

from configs.project_config import ProjectConfig, ProjectUserConfig
from gui.settings_validation import (
    duplicate_user_names,
    validate_project_settings,
    validate_users_for_save,
)
from gui.user_editor import UserEditor
from gui.validation import parse_exclude_date
from storage.project_repository import ProjectRepository
from trackers.registry import all_trackers, build_tracker, get_tracker_class


class ProjectSettingsPanel(ttk.LabelFrame):
    def __init__(
        self,
        parent: tk.Misc,
        project: ProjectConfig,
        repo: ProjectRepository,
        on_saved: Callable[[ProjectConfig], None],
    ) -> None:
        super().__init__(parent, text="Настройки проекта", padding=8)
        self.project = project
        self.repo = repo
        self.on_saved = on_saved
        self.users: list[ProjectUserConfig] = []
        self.selected_vars: dict[str, tk.BooleanVar] = {}
        self.users_by_iid: dict[str, ProjectUserConfig] = {}
        self.iid_by_name: dict[str, str] = {}
        self.fields: dict[str, ttk.Entry] = {}
        self.exclude_dates: list[str] = []
        self.collapsed = False
        self.tracker_kinds: list[str] = [cls.kind for cls in all_trackers()]
        self._build()
        self.reload(project)

    def _build(self) -> None:
        self.toggle_button = ttk.Button(
            self,
            text="Свернуть",
            width=12,
            command=self.toggle_collapsed,
        )
        self.toggle_button.pack(anchor="e")

        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True)

        general = ttk.Frame(self.body)
        general.pack(fill="x")
        general.columnconfigure(1, weight=1)
        self.fields["git_repo_path"] = self._entry(
            general, 0, "Git-репозиторий", width=60
        )
        ttk.Button(general, text="Выбрать…", command=self._browse_repo).grid(
            row=0, column=2, padx=4, pady=3
        )
        self.fields["workday_hours"] = self._entry(
            general, 1, "Рабочий день, ч", width=10
        )
        self.fields["default_comment"] = self._entry(
            general, 2, "Комментарий по умолчанию", width=40
        )

        dates = ttk.LabelFrame(
            self.body, text="Исключённые даты", padding=6
        )
        dates.pack(fill="x", pady=(6, 0))
        self.dates_list = tk.Listbox(
            dates, height=3, width=18, exportselection=False
        )
        self.dates_list.grid(row=0, column=0, rowspan=3, sticky="we")
        self.date_entry = ttk.Entry(dates, width=16)
        self.date_entry.grid(row=0, column=1, padx=6, sticky="we")
        ttk.Button(dates, text="Добавить", command=self._add_date).grid(
            row=1, column=1, padx=6, pady=2, sticky="we"
        )
        ttk.Button(dates, text="Удалить", command=self._remove_date).grid(
            row=2, column=1, padx=6, pady=2, sticky="we"
        )

        users = ttk.LabelFrame(self.body, text="Юзеры", padding=6)
        users.pack(fill="both", expand=True, pady=(6, 0))
        users.columnconfigure(0, weight=1)
        users.rowconfigure(0, weight=1)

        columns = ("track", "name", "email") + tuple(self.tracker_kinds)
        self.users_tree = ttk.Treeview(
            users, columns=columns, show="headings", height=6
        )
        self.users_tree.heading("track", text="☑")
        self.users_tree.column(
            "track", width=36, anchor="center", stretch=False
        )
        self.users_tree.heading("name", text="Имя")
        self.users_tree.column("name", width=180, anchor="w")
        self.users_tree.heading("email", text="git email")
        self.users_tree.column("email", width=200, anchor="w")
        for kind in self.tracker_kinds:
            cls = get_tracker_class(kind)
            self.users_tree.heading(kind, text=cls.label if cls else kind)
            self.users_tree.column(kind, width=110, anchor="center")
        self.users_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(
            users, orient="vertical", command=self.users_tree.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.users_tree.configure(yscrollcommand=scrollbar.set)
        self.users_tree.bind("<Double-1>", self._on_double_click)
        self.users_tree.bind("<Button-1>", self._on_tree_click)
        self.users_tree.bind("<space>", self._on_tree_space)

        buttons = ttk.Frame(users)
        buttons.grid(row=1, column=0, columnspan=2, sticky="we", pady=(6, 0))
        ttk.Button(
            buttons, text="Добавить юзера", command=self.add_user
        ).pack(side="left", padx=2)
        ttk.Button(buttons, text="Изменить", command=self.edit_user).pack(
            side="left", padx=2
        )
        ttk.Button(buttons, text="Удалить", command=self.delete_user).pack(
            side="left", padx=2
        )
        ttk.Button(
            buttons, text="Импорт из проекта", command=self.import_from_project
        ).pack(side="left", padx=2)
        ttk.Button(
            buttons, text="Сохранить настройки", command=self.save
        ).pack(side="right", padx=2)

        self.error_label = ttk.Label(
            self.body, text="", foreground="red", wraplength=800
        )
        self.error_label.pack(fill="x", pady=(4, 0))
        self.status_label = ttk.Label(self.body, text="", foreground="#555")
        self.status_label.pack(fill="x")

    def _entry(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        width: int = 40,
    ) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(parent, width=width)
        entry.grid(row=row, column=1, sticky="we", pady=3)
        return entry

    def toggle_collapsed(self) -> None:
        self.collapsed = not self.collapsed
        if self.collapsed:
            self.body.pack_forget()
            self.toggle_button.configure(text="Развернуть")
        else:
            self.body.pack(fill="both", expand=True)
            self.toggle_button.configure(text="Свернуть")

    def reload(self, project: ProjectConfig) -> None:
        self.project = project
        self.users = list(project.users)
        self.exclude_dates = sorted(project.exclude_dates)
        self._set_entry("git_repo_path", project.git_repo_path)
        self._set_entry("workday_hours", f"{project.workday_hours:g}")
        self._set_entry("default_comment", project.default_comment)
        self._refresh_dates()
        self._refresh_users(preserve_selection=True)
        self.error_label.configure(text="")
        self.status_label.configure(text="")

    def _set_entry(self, key: str, value: str) -> None:
        entry = self.fields[key]
        entry.delete(0, "end")
        entry.insert(0, value)

    def _refresh_dates(self) -> None:
        self.dates_list.delete(0, "end")
        for value in self.exclude_dates:
            self.dates_list.insert("end", value)

    def _refresh_users(self, preserve_selection: bool = True) -> None:
        previous = (
            {name: var.get() for name, var in self.selected_vars.items()}
            if preserve_selection
            else {}
        )
        self.selected_vars = {
            user.name: tk.BooleanVar(value=previous.get(user.name, True))
            for user in self.users
        }
        self.users_tree.delete(*self.users_tree.get_children())
        self.users_by_iid.clear()
        self.iid_by_name.clear()
        for user in self.users:
            iid = self.users_tree.insert("", "end", values=self._user_values(user))
            self.users_by_iid[iid] = user
            self.iid_by_name[user.name] = iid

    def _user_values(self, user: ProjectUserConfig) -> tuple[str, ...]:
        selected = self.selected_vars.get(user.name)
        values = [
            "☑" if selected is not None and selected.get() else "☐",
            user.name,
            user.git_email,
        ]
        for kind in self.tracker_kinds:
            values.append(self._tracker_status(user, kind))
        return tuple(values)

    @staticmethod
    def _tracker_status(user: ProjectUserConfig, kind: str) -> str:
        values = user.trackers.get(kind, {})
        tracker = build_tracker(kind, values)
        if tracker is None:
            return "—"
        if tracker.is_configured():
            return "настроен"
        return "неполный" if values else "—"

    def _toggle_user(self, name: str) -> None:
        var = self.selected_vars.get(name)
        if var is None:
            return
        var.set(not var.get())
        iid = self.iid_by_name.get(name)
        user = self.users_by_iid.get(iid) if iid is not None else None
        if iid is not None and user is not None:
            self.users_tree.item(iid, values=self._user_values(user))

    def _on_tree_click(self, event: tk.Event) -> str | None:
        if self.users_tree.identify_region(event.x, event.y) != "cell":
            return None
        if self.users_tree.identify_column(event.x) != "#1":
            return None
        iid = self.users_tree.identify_row(event.y)
        user = self.users_by_iid.get(iid)
        if user is None:
            return None
        self._toggle_user(user.name)
        return "break"

    def _on_tree_space(self, event: tk.Event) -> str:
        user = self.users_by_iid.get(self.users_tree.focus())
        if user is not None:
            self._toggle_user(user.name)
        return "break"

    def _on_double_click(self, event: tk.Event) -> None:
        if self.users_tree.identify_region(event.x, event.y) != "cell":
            return
        if self.users_tree.identify_column(event.x) == "#1":
            return
        self.edit_user()

    def selected_user_ids(self) -> list[int]:
        result: list[int] = []
        for user in self.users:
            if user.db_id is None:
                continue
            var = self.selected_vars.get(user.name)
            if var is not None and var.get():
                result.append(user.db_id)
        return result

    def _selected_user(self) -> ProjectUserConfig | None:
        selection = self.users_tree.selection()
        if not selection:
            return None
        return self.users_by_iid.get(selection[0])

    def add_user(self) -> None:
        editor = UserEditor(self)
        self.wait_window(editor)
        if editor.result is None:
            return
        if editor.result.name in self.selected_vars:
            messagebox.showerror(
                "Настройки проекта",
                f"Юзер «{editor.result.name}» уже есть в проекте",
                parent=self,
            )
            return
        self.users.append(editor.result)
        self._refresh_users(preserve_selection=True)
        self.error_label.configure(text="")
        self.status_label.configure(text=f"Добавлен юзер: {editor.result.name}")

    def edit_user(self) -> None:
        user = self._selected_user()
        if user is None:
            messagebox.showinfo(
                "Настройки проекта", "Выберите юзера в таблице", parent=self
            )
            return
        selected = self.selected_vars.get(user.name)
        was_selected = selected.get() if selected is not None else True
        index = self.users.index(user)
        editor = UserEditor(self, user)
        self.wait_window(editor)
        if editor.result is None:
            return
        new_name = editor.result.name
        for other in self.users:
            if other is not user and other.name == new_name:
                messagebox.showerror(
                    "Настройки проекта",
                    f"Юзер «{new_name}» уже есть в проекте",
                    parent=self,
                )
                return
        self.users[index] = editor.result
        self._refresh_users(preserve_selection=True)
        var = self.selected_vars.get(new_name)
        if var is not None:
            var.set(was_selected)
        iid = self.iid_by_name.get(new_name)
        if iid is not None:
            self.users_tree.item(iid, values=self._user_values(editor.result))
        self.error_label.configure(text="")
        self.status_label.configure(text=f"Изменён юзер: {new_name}")

    def delete_user(self) -> None:
        user = self._selected_user()
        if user is None:
            messagebox.showinfo(
                "Настройки проекта", "Выберите юзера в таблице", parent=self
            )
            return
        if not messagebox.askyesno(
            "Настройки проекта", f"Удалить юзера «{user.name}»?", parent=self
        ):
            return
        self.users.remove(user)
        self._refresh_users(preserve_selection=True)
        self.error_label.configure(text="")
        self.status_label.configure(text=f"Удалён юзер: {user.name}")

    def import_from_project(self) -> None:
        if self.project.db_id is None:
            return
        donors = [
            project
            for project in self.repo.list_projects()
            if project.db_id != self.project.db_id
        ]
        if not donors:
            messagebox.showinfo(
                "Настройки проекта",
                "Нет других проектов для импорта",
                parent=self,
            )
            return
        chooser = _ProjectChooser(self, donors)
        self.wait_window(chooser)
        donor = chooser.result
        if donor is None or donor.db_id is None:
            return
        if not messagebox.askyesno(
            "Настройки проекта",
            f"Импортировать настройки из «{donor.name}»?\n"
            "Общие настройки будут заменены, юзеры с одинаковыми именами "
            "обновятся.",
            parent=self,
        ):
            return
        try:
            changed = self.repo.merge_users_from(self.project.db_id, donor)
        except Exception as exc:
            messagebox.showerror(
                "Настройки проекта",
                f"Не удалось импортировать настройки: {exc}",
                parent=self,
            )
            return
        refreshed = self.repo.get_project(self.project.db_id)
        if refreshed is None:
            self._show_errors(["Проект не найден после импорта"])
            return
        self.reload(refreshed)
        self.on_saved(refreshed)
        self.status_label.configure(
            text=f"Импорт завершён, затронуто юзеров: {changed}"
        )

    def save(self) -> None:
        if self.project.db_id is None:
            self._show_errors(["Проект не сохранён в базе"])
            return
        project, errors = validate_project_settings(
            self._form_values(), self.exclude_dates
        )
        errors.extend(validate_users_for_save(self.users, self.exclude_dates))
        duplicates = duplicate_user_names(self.users)
        if duplicates:
            errors.append(
                "Имена юзеров не должны повторяться: " + ", ".join(duplicates)
            )
        if project is None or errors:
            self._show_errors(errors)
            return
        project.name = self.project.name
        project.db_id = self.project.db_id
        project.git_author_email = self.project.git_author_email
        project.trackers = dict(self.project.trackers)
        project.ai = dict(self.project.ai)
        try:
            self.repo.update_project(project.db_id, project)
            self.repo.replace_users(project.db_id, self.users)
        except Exception as exc:
            messagebox.showerror(
                "Настройки проекта",
                f"Не удалось сохранить настройки: {exc}",
                parent=self,
            )
            return
        refreshed = self.repo.get_project(project.db_id)
        if refreshed is None:
            self._show_errors(["Проект не найден после сохранения"])
            return
        self.reload(refreshed)
        self.on_saved(refreshed)
        self.status_label.configure(text="Настройки сохранены")

    def _form_values(self) -> dict[str, str]:
        return {key: entry.get() for key, entry in self.fields.items()}

    def _browse_repo(self) -> None:
        path = filedialog.askdirectory(parent=self)
        if path:
            self._set_entry("git_repo_path", path)

    def _add_date(self) -> None:
        parsed, error = parse_exclude_date(
            self.date_entry.get(), self.exclude_dates
        )
        if error:
            self.error_label.configure(text=error)
            return
        self.exclude_dates.append(parsed)
        self.exclude_dates.sort()
        self.date_entry.delete(0, "end")
        self._refresh_dates()
        self.error_label.configure(text="")

    def _remove_date(self) -> None:
        selection = self.dates_list.curselection()
        if not selection:
            return
        del self.exclude_dates[selection[0]]
        self._refresh_dates()

    def _show_errors(self, errors: list[str]) -> None:
        self.error_label.configure(text="\n".join(errors))
        self.status_label.configure(text="")


class _ProjectChooser(tk.Toplevel):
    def __init__(
        self, parent: tk.Misc, projects: list[ProjectConfig]
    ) -> None:
        super().__init__(parent)
        self.projects = projects
        self.result: ProjectConfig | None = None
        self.title("Импорт настроек")
        self.geometry("420x300")
        self.minsize(320, 220)

        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.listbox = tk.Listbox(list_frame, exportselection=False)
        for project in projects:
            self.listbox.insert("end", project.name)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.listbox.yview
        )
        scrollbar.pack(side="right", fill="y")
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.bind("<Double-1>", lambda event: self._ok())
        if projects:
            self.listbox.selection_set(0)
            self.listbox.activate(0)

        footer = ttk.Frame(self, padding=(10, 0, 10, 10))
        footer.pack(fill="x")
        ttk.Button(footer, text="Импортировать", command=self._ok).pack(
            side="right", padx=4
        )
        ttk.Button(footer, text="Отмена", command=self.destroy).pack(side="right")

        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def _ok(self) -> None:
        selection = self.listbox.curselection()
        if not selection:
            return
        self.result = self.projects[selection[0]]
        self.destroy()
