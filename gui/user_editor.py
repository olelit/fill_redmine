import tkinter as tk
from tkinter import ttk

from configs.user_config import MANUAL, YOUTRACK, UserConfig
from gui.validation import parse_exclude_date, validate_user_form


class UserEditor(tk.Toplevel):
    def __init__(self, parent: tk.Misc, user: UserConfig | None = None):
        super().__init__(parent)
        self.user = user
        self.result: UserConfig | None = None
        self.exclude_dates = list(user.exclude_dates) if user else []
        self.driver_var = tk.StringVar(value=user.driver if user else MANUAL)
        self.enable_var = tk.BooleanVar(value=user.is_enable if user else True)
        self.show_secrets = tk.BooleanVar(value=False)
        self.fields: dict[str, ttk.Entry] = {}
        self.secret_entries: list[ttk.Entry] = []

        self.title("Изменить юзера" if user else "Добавить юзера")
        self.resizable(False, False)
        self._build_form()
        self._sync_driver()
        self.transient(parent)
        self.grab_set()
        self.focus_set()

    def _add_entry(
        self,
        form: ttk.Frame,
        row: int,
        key: str,
        label: str,
        secret: bool = False,
    ) -> ttk.Entry:
        ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
        entry = ttk.Entry(form, width=44, show="*" if secret else "")
        entry.grid(row=row, column=1, sticky="we", pady=2)
        if self.user is not None:
            entry.insert(0, str(getattr(self.user, key)))
        if secret:
            self.secret_entries.append(entry)
        self.fields[key] = entry
        return entry

    def _build_form(self) -> None:
        form = ttk.Frame(self, padding=10)
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)

        self._add_entry(form, 0, "name", "Имя")

        ttk.Label(form, text="Driver").grid(row=1, column=0, sticky="w", pady=2)
        driver_frame = ttk.Frame(form)
        driver_frame.grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(
            driver_frame,
            text="manual",
            variable=self.driver_var,
            value=MANUAL,
            command=self._sync_driver,
        ).pack(side="left")
        ttk.Radiobutton(
            driver_frame,
            text="youtrack",
            variable=self.driver_var,
            value=YOUTRACK,
            command=self._sync_driver,
        ).pack(side="left")

        self._add_entry(form, 2, "redmine_api_key", "redmine_api_key", secret=True)
        self._add_entry(form, 3, "user_id", "user_id")
        self._add_entry(form, 4, "activity_id", "activity_id")
        self._add_entry(form, 5, "issue_id", "issue_id")
        self._add_entry(form, 6, "comment", "Комментарий")
        self.token_entry = self._add_entry(
            form, 7, "youtrack_access_token", "youtrack_access_token", secret=True
        )

        ttk.Checkbutton(
            form,
            text="показать ключи",
            variable=self.show_secrets,
            command=self._toggle_secrets,
        ).grid(row=8, column=1, sticky="w", pady=(4, 0))
        ttk.Checkbutton(form, text="включён", variable=self.enable_var).grid(
            row=9, column=1, sticky="w"
        )

        dates_frame = ttk.LabelFrame(form, text="Исключённые даты", padding=6)
        dates_frame.grid(row=10, column=0, columnspan=2, sticky="we", pady=(8, 0))
        self.dates_list = tk.Listbox(dates_frame, height=4, width=16)
        self.dates_list.grid(row=0, column=0, rowspan=3, sticky="we")
        for value in self.exclude_dates:
            self.dates_list.insert("end", value)
        self.date_entry = ttk.Entry(dates_frame, width=14)
        self.date_entry.grid(row=0, column=1, padx=6)
        ttk.Button(dates_frame, text="Добавить", command=self._add_date).grid(
            row=1, column=1, padx=6, sticky="we"
        )
        ttk.Button(dates_frame, text="Удалить", command=self._remove_date).grid(
            row=2, column=1, padx=6, sticky="we"
        )

        self.error_label = ttk.Label(form, text="", foreground="red", wraplength=420)
        self.error_label.grid(row=11, column=0, columnspan=2, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(form)
        buttons.grid(row=12, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Сохранить", command=self._save).pack(side="left", padx=4)
        ttk.Button(buttons, text="Отмена", command=self.destroy).pack(side="left")

    def _sync_driver(self) -> None:
        state = "normal" if self.driver_var.get() == YOUTRACK else "disabled"
        self.token_entry.configure(state=state)

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
        form["driver"] = self.driver_var.get()
        user, errors = validate_user_form(
            form,
            is_enable=self.enable_var.get(),
            exclude_dates=self.exclude_dates,
            db_id=self.user.db_id if self.user else None,
        )
        if errors:
            self.error_label.configure(text="\n".join(errors))
            return
        self.result = user
        self.destroy()
