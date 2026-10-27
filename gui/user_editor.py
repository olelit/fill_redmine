import tkinter as tk
from tkinter import ttk

from configs.project_config import ProjectUserConfig
from gui.settings_validation import validate_user_settings
from trackers.registry import all_trackers


class UserEditor(tk.Toplevel):
    def __init__(
        self, parent: tk.Misc, user: ProjectUserConfig | None = None
    ) -> None:
        super().__init__(parent)
        self.user = user
        self.result: ProjectUserConfig | None = None
        self.name_var = tk.StringVar(value=user.name if user is not None else "")
        self.git_email_var = tk.StringVar(
            value=user.git_email if user is not None else ""
        )
        self.show_secrets = tk.BooleanVar(value=False)
        self.tracker_entries: dict[str, dict[str, ttk.Entry]] = {}
        self.secret_entries: list[ttk.Entry] = []

        self.title("Изменить юзера" if user is not None else "Новый юзер")
        self.geometry("640x560")
        self.minsize(520, 420)
        self._build()
        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def _build(self) -> None:
        content = ttk.Frame(self, padding=10)
        content.pack(fill="both", expand=True)
        content.columnconfigure(1, weight=1)

        ttk.Label(content, text="Имя").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(content, textvariable=self.name_var, width=48).grid(
            row=0, column=1, sticky="we", pady=4
        )
        ttk.Label(content, text="git email").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(content, textvariable=self.git_email_var, width=48).grid(
            row=1, column=1, sticky="we", pady=4
        )
        ttk.Label(
            content,
            text="git email нужен для источника «Из коммитов»; можно оставить пустым.",
            foreground="#555",
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 6))

        ttk.Checkbutton(
            content,
            text="показать секреты",
            variable=self.show_secrets,
            command=self._toggle_secrets,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 4))

        notebook = ttk.Notebook(content)
        notebook.grid(row=4, column=0, columnspan=2, sticky="nsew", pady=4)
        content.rowconfigure(4, weight=1)

        for cls in all_trackers():
            tab = ttk.Frame(notebook, padding=10)
            notebook.add(tab, text=cls.label)
            tab.columnconfigure(1, weight=1)
            user_values = (
                self.user.trackers.get(cls.kind, {}) if self.user else {}
            )
            entries: dict[str, ttk.Entry] = {}
            for row, field in enumerate(cls.fields):
                ttk.Label(tab, text=field.label).grid(
                    row=row, column=0, sticky="w", pady=4
                )
                entry = ttk.Entry(
                    tab,
                    width=40,
                    show="*" if field.kind == "secret" else "",
                )
                entry.grid(row=row, column=1, sticky="we", pady=4)
                raw = user_values.get(field.key, "")
                if raw not in (None, ""):
                    entry.insert(0, str(raw))
                if field.kind == "secret":
                    self.secret_entries.append(entry)
                entries[field.key] = entry
            self.tracker_entries[cls.kind] = entries
            ttk.Label(
                tab,
                text="Пустая секция — трекер не настроен.",
                foreground="#555",
            ).grid(
                row=len(cls.fields),
                column=0,
                columnspan=2,
                sticky="w",
                pady=(10, 0),
            )

        footer = ttk.Frame(content)
        footer.grid(row=5, column=0, columnspan=2, sticky="we", pady=(8, 0))
        self.error_label = ttk.Label(
            footer, text="", foreground="red", wraplength=430
        )
        self.error_label.pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Сохранить", command=self.save).pack(
            side="right", padx=4
        )
        ttk.Button(footer, text="Отмена", command=self.destroy).pack(side="right")

    def _toggle_secrets(self) -> None:
        show = "" if self.show_secrets.get() else "*"
        for entry in self.secret_entries:
            entry.configure(show=show)

    def tracker_values(self) -> dict[str, dict[str, str]]:
        return {
            kind: {key: entry.get() for key, entry in entries.items()}
            for kind, entries in self.tracker_entries.items()
        }

    def save(self) -> None:
        user, errors = validate_user_settings(
            self.name_var.get(),
            self.git_email_var.get(),
            self.tracker_values(),
        )
        if errors or user is None:
            self.error_label.configure(text="\n".join(errors) or "Проверьте поля")
            return
        if self.user is not None:
            user.db_id = self.user.db_id
            user.project_id = self.user.project_id
        self.result = user
        self.destroy()
