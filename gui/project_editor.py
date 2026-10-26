import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from clients.git_client import GitClient, GitError
from configs.project_config import ProjectConfig
from gui.project_validation import validate_project_form
from gui.validation import parse_exclude_date
from storage.project_repository import ProjectRepository
from trackers.registry import all_trackers


class ProjectEditor(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        repo: ProjectRepository,
        project: ProjectConfig | None = None,
    ):
        super().__init__(parent)
        self.repo = repo
        self.project = project
        self.result: ProjectConfig | None = None
        self.exclude_dates = list(project.exclude_dates) if project else []
        self.fields: dict[str, ttk.Entry] = {}
        self.tracker_entries: dict[str, dict[str, ttk.Entry]] = {}
        self.ai_entries: dict[str, ttk.Entry] = {}
        self.secret_entries: list[ttk.Entry] = []
        self.show_secrets = tk.BooleanVar(value=False)

        self.title("Настройки проекта" if project else "Новый проект")
        self.geometry("720x680")
        self.minsize(640, 560)
        self._build()
        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def _build(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self._build_general(notebook)
        self._build_trackers(notebook)
        self._build_ai(notebook)

        footer = ttk.Frame(self, padding=(8, 0, 8, 8))
        footer.pack(fill="x")
        self.error_label = ttk.Label(footer, text="", foreground="red", wraplength=660)
        self.error_label.pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Сохранить", command=self._save).pack(side="right", padx=4)
        ttk.Button(footer, text="Отмена", command=self.destroy).pack(side="right")

    def _entry(
        self,
        parent: ttk.Frame,
        row: int,
        key: str,
        label: str,
        value: str = "",
        secret: bool = False,
    ) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(parent, width=52, show="*" if secret else "")
        entry.grid(row=row, column=1, sticky="we", pady=3)
        if value:
            entry.insert(0, value)
        if secret:
            self.secret_entries.append(entry)
        return entry

    def _build_general(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text="Общее")
        frame.columnconfigure(1, weight=1)
        project = self.project

        self.fields["name"] = self._entry(
            frame, 0, "name", "Имя", project.name if project else ""
        )
        self.fields["git_repo_path"] = self._entry(
            frame, 1, "git_repo_path", "Git-репозиторий",
            project.git_repo_path if project else "",
        )
        ttk.Button(frame, text="Выбрать…", command=self._browse_repo).grid(
            row=1, column=2, padx=4
        )
        self.fields["git_author_email"] = self._entry(
            frame, 2, "git_author_email", "Email автора",
            project.git_author_email if project else "",
        )
        ttk.Button(frame, text="Из git", command=self._email_from_git).grid(
            row=2, column=2, padx=4
        )
        self.fields["workday_hours"] = self._entry(
            frame, 3, "workday_hours", "Рабочий день, ч",
            str(project.workday_hours) if project else "8",
        )

        dates_frame = ttk.LabelFrame(frame, text="Исключённые даты", padding=6)
        dates_frame.grid(row=4, column=0, columnspan=3, sticky="we", pady=(10, 0))
        self.dates_list = tk.Listbox(dates_frame, height=4, width=18)
        self.dates_list.grid(row=0, column=0, rowspan=3, sticky="we")
        for value in self.exclude_dates:
            self.dates_list.insert("end", value)
        self.date_entry = ttk.Entry(dates_frame, width=16)
        self.date_entry.grid(row=0, column=1, padx=6)
        ttk.Button(dates_frame, text="Добавить", command=self._add_date).grid(
            row=1, column=1, padx=6, sticky="we"
        )
        ttk.Button(dates_frame, text="Удалить", command=self._remove_date).grid(
            row=2, column=1, padx=6, sticky="we"
        )

    def _build_trackers(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text="Трекеры")
        canvas = tk.Canvas(frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        content.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        ttk.Checkbutton(
            content,
            text="показать секреты",
            variable=self.show_secrets,
            command=self._toggle_secrets,
        ).pack(anchor="w", pady=(0, 6))

        for cls in all_trackers():
            section = ttk.LabelFrame(content, text=cls.label, padding=8)
            section.pack(fill="x", pady=4)
            section.columnconfigure(1, weight=1)
            values = (self.project.trackers.get(cls.kind, {}) if self.project else {})
            entries: dict[str, ttk.Entry] = {}
            for row, field in enumerate(cls.fields):
                entries[field.key] = self._entry(
                    section,
                    row,
                    field.key,
                    field.label,
                    str(values.get(field.key, "")),
                    secret=field.kind == "secret",
                )
            self.tracker_entries[cls.kind] = entries

    def _build_ai(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=10)
        notebook.add(frame, text="ИИ")
        frame.columnconfigure(1, weight=1)
        values = self.project.ai if self.project else {}
        self.ai_entries["base_url"] = self._entry(
            frame, 0, "base_url", "Base URL",
            str(values.get("base_url", "")),
        )
        self.ai_entries["model"] = self._entry(
            frame, 1, "model", "Модель", str(values.get("model", ""))
        )
        self.ai_entries["api_key"] = self._entry(
            frame, 2, "api_key", "API key",
            str(values.get("api_key", "")), secret=True,
        )
        ttk.Checkbutton(
            frame,
            text="показать секреты",
            variable=self.show_secrets,
            command=self._toggle_secrets,
        ).grid(row=3, column=1, sticky="w", pady=(10, 0))
        ttk.Label(
            frame,
            text="Пустые поля берутся из OPENAI_BASE_URL, OPENAI_MODEL, OPENAI_API_KEY.",
            wraplength=600,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _browse_repo(self) -> None:
        path = filedialog.askdirectory(parent=self)
        if path:
            self.fields["git_repo_path"].delete(0, "end")
            self.fields["git_repo_path"].insert(0, path)

    def _email_from_git(self) -> None:
        path = self.fields["git_repo_path"].get().strip()
        if not path:
            messagebox.showinfo("Work Assistant", "Сначала выберите репозиторий", parent=self)
            return
        try:
            email = GitClient(path).get_config_email()
        except GitError as exc:
            messagebox.showerror("Work Assistant", str(exc), parent=self)
            return
        self.fields["git_author_email"].delete(0, "end")
        self.fields["git_author_email"].insert(0, email)

    def _toggle_secrets(self) -> None:
        show = "" if self.show_secrets.get() else "*"
        for entry in self.secret_entries:
            entry.configure(show=show)

    def _add_date(self) -> None:
        parsed, error = parse_exclude_date(self.date_entry.get(), self.exclude_dates)
        if error:
            self.error_label.configure(text=error)
            return
        self.exclude_dates.append(parsed)
        self.exclude_dates.sort()
        self.dates_list.delete(0, "end")
        for value in self.exclude_dates:
            self.dates_list.insert("end", value)
        self.date_entry.delete(0, "end")
        self.error_label.configure(text="")

    def _remove_date(self) -> None:
        selection = self.dates_list.curselection()
        if not selection:
            return
        value = self.dates_list.get(selection[0])
        self.dates_list.delete(selection[0])
        self.exclude_dates.remove(value)

    def _save(self) -> None:
        form = {key: entry.get() for key, entry in self.fields.items()}
        tracker_values = {
            kind: {key: entry.get() for key, entry in entries.items()}
            for kind, entries in self.tracker_entries.items()
        }
        ai_values = {
            key: entry.get() for key, entry in self.ai_entries.items()
        }
        project, errors = validate_project_form(
            form,
            exclude_dates=self.exclude_dates,
            tracker_values=tracker_values,
            ai_values=ai_values,
            db_id=self.project.db_id if self.project else None,
        )
        if errors:
            self.error_label.configure(text="\n".join(errors))
            return
        existing = self.repo.find_by_name(project.name)
        if existing is not None and existing.db_id != project.db_id:
            self.error_label.configure(text="Проект с таким именем уже существует")
            return
        if self.project is not None and "selected_trackers" in self.project.ai:
            project.ai["selected_trackers"] = self.project.ai["selected_trackers"]
        self.result = project
        self.destroy()
