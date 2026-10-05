import asyncio
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from gui.formatting import format_hours, format_range
from gui.worker import GuiWorker
from services.import_service import ImportService, ImportSummary, PreparedImport


class ImportView(ttk.LabelFrame):
    def __init__(
        self,
        parent,
        service: ImportService,
        worker: GuiWorker,
        get_users: Callable[[bool], list],
    ):
        super().__init__(parent, text="Превью и импорт", padding=4)
        self.service = service
        self.worker = worker
        self.get_users = get_users
        self.prepared: list[PreparedImport] = []
        self.busy = False
        self._build()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.worker.register("log", self.log)
        self.worker.register("preview_done", self._on_preview_done)
        self.worker.register("import_done", self._on_import_done)
        self.worker.register("error", self._on_worker_error)
        self.worker.register("progress", self._on_progress)

    def _build(self) -> None:
        buttons = ttk.Frame(self)
        buttons.pack(fill="x")
        self.preview_button = ttk.Button(
            buttons, text="Построить превью", command=self.build_preview
        )
        self.preview_button.pack(side="left", padx=2)
        self.import_button = ttk.Button(
            buttons, text="Запустить импорт", command=self.run_import, state="disabled"
        )
        self.import_button.pack(side="left", padx=2)
        self.only_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            buttons,
            text="только включённые",
            variable=self.only_enabled,
        ).pack(side="left", padx=8)

        columns = ("user", "driver", "issue", "subject", "periods", "total")
        headings = {
            "user": ("Имя", 130),
            "driver": ("Driver", 80),
            "issue": ("Issue", 70),
            "subject": ("Тема", 220),
            "periods": ("Периоды", 260),
            "total": ("Всего", 70),
        }
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=6)
        for column, (title, width) in headings.items():
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=4)

        progress_frame = ttk.Frame(self)
        progress_frame.pack(fill="x", pady=4)
        self.progress_bar = ttk.Progressbar(progress_frame, mode="determinate")
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.progress_label = tk.StringVar(value="")
        ttk.Label(progress_frame, textvariable=self.progress_label, width=28).pack(
            side="left", padx=6
        )

        log_frame = ttk.Frame(self)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, height=9, state="disabled", wrap="word")
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.preview_button.configure(state=state)
        can_import = not busy and bool(self.prepared)
        self.import_button.configure(state="normal" if can_import else "disabled")

    def build_preview(self) -> None:
        users = self.get_users(self.only_enabled.get())
        if not users:
            messagebox.showinfo("Fill Redmine", "Нет юзеров для превью", parent=self)
            return
        self.prepared = []
        self.import_button.configure(state="disabled")
        self.tree.delete(*self.tree.get_children())
        self.log("Строю превью...")
        self._set_busy(True)
        self.worker.submit(
            lambda: self.service.prepare(users),
            done_kind="preview_done",
            error_kind="error",
        )

    def _on_preview_done(self, items: list[PreparedImport]) -> None:
        try:
            self.prepared = items
            for item in items:
                preview = item.preview
                parent = self.tree.insert(
                    "",
                    "end",
                    values=(
                        preview.user_name,
                        preview.driver,
                        preview.issue_id,
                        preview.issue_subject or "—",
                        "",
                        format_hours(preview.total_hours),
                    ),
                )
                for date_range in preview.ranges:
                    self.tree.insert(
                        parent,
                        "end",
                        values=(
                            "",
                            "",
                            "",
                            "",
                            format_range(date_range),
                            format_hours(date_range.hours),
                        ),
                    )
            self.log(f"Превью готово: юзеров {len(items)}")
            if not items:
                messagebox.showinfo("Fill Redmine", "Нет записей для импорта", parent=self)
        finally:
            self._set_busy(False)

    def run_import(self) -> None:
        if not self.prepared:
            messagebox.showinfo("Fill Redmine", "Сначала постройте превью", parent=self)
            return
        total = sum(len(item.records) for item in self.prepared)
        question = f"Импортировать {total} записей для {len(self.prepared)} юзеров?"
        if not messagebox.askyesno("Fill Redmine", question, parent=self):
            return
        items = self.prepared
        self.progress_bar.configure(maximum=max(total, 1), value=0)
        self.progress_label.set("")
        self._set_busy(True)

        def progress_cb(completed: int, global_total: int, name: str) -> None:
            self.worker.send("progress", (completed, global_total, name))

        self.worker.submit(
            lambda: asyncio.run(self.service.run(items, progress_cb=progress_cb)),
            done_kind="import_done",
            error_kind="error",
        )

    def _on_progress(self, payload: tuple[int, int, str]) -> None:
        completed, total, name = payload
        self.progress_bar.configure(value=completed)
        self.progress_label.set(f"{name} {completed}/{total}")

    def _on_import_done(self, summary: ImportSummary) -> None:
        try:
            self.prepared = []
            self.progress_label.set("")
            success = summary.total - len(summary.errors)
            message = f"Импорт завершён: успешно {success}, ошибок {len(summary.errors)}"
            self.log(message)
            for user_name, spent_on, error in summary.errors:
                self.log(f"  {user_name} {spent_on}: {error}")
            messagebox.showinfo("Fill Redmine", message, parent=self)
        finally:
            self._set_busy(False)

    def _on_worker_error(self, exc: Exception) -> None:
        self._set_busy(False)
        self.log(f"Ошибка: {exc}")
        messagebox.showerror("Fill Redmine", str(exc), parent=self)
