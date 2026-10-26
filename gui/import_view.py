import asyncio
import tkinter as tk
from tkinter import messagebox, ttk

from configs.project_config import ProjectConfig
from dto.import_action import ImportAction
from gui.formatting import format_hours, format_range
from gui.worker import GuiWorker
from services.import_service import (
    ImportService,
    ImportSummary,
    PrepareResult,
    PreparedImport,
)


class ImportView(ttk.LabelFrame):
    def __init__(
        self,
        parent,
        project: ProjectConfig,
        service: ImportService,
        worker: GuiWorker,
        action: ImportAction,
        event_prefix: str,
    ):
        super().__init__(parent, text=action.label, padding=4)
        self.project = project
        self.service = service
        self.worker = worker
        self.action = action
        self.event_prefix = event_prefix
        self.prepared: list[PreparedImport] = []
        self.busy = False
        self._build()
        self._register_handlers()

    def _kind(self, suffix: str) -> str:
        return f"{self.event_prefix}_{suffix}"

    def _register_handlers(self) -> None:
        self.worker.register(self._kind("log"), self.log)
        self.worker.register(self._kind("preview_done"), self._on_preview_done)
        self.worker.register(self._kind("import_done"), self._on_import_done)
        self.worker.register(self._kind("error"), self._on_worker_error)
        self.worker.register(self._kind("progress"), self._on_progress)

    def destroy(self) -> None:
        for suffix in ("log", "preview_done", "import_done", "error", "progress"):
            self.worker.unregister(self._kind(suffix))
        super().destroy()

    def _build(self) -> None:
        buttons = ttk.Frame(self)
        buttons.pack(fill="x")
        self.preview_button = ttk.Button(
            buttons, text="Построить превью", command=self.build_preview
        )
        self.preview_button.pack(side="left", padx=2)
        self.import_button = ttk.Button(
            buttons,
            text="Запустить импорт",
            command=self.run_import,
            state="disabled",
        )
        self.import_button.pack(side="left", padx=2)

        columns = ("issue", "subject", "periods", "total")
        headings = {
            "issue": ("Issue", 90),
            "subject": ("Тема", 300),
            "periods": ("Периоды", 360),
            "total": ("Всего", 80),
        }
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=8)
        for column, (title, width) in headings.items():
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="w")
        self.tree.tag_configure("error", foreground="#c0392b")
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
        self.log_text = tk.Text(log_frame, height=10, state="disabled", wrap="word")
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
        self.preview_button.configure(state="disabled" if busy else "normal")
        can_import = not busy and bool(self.prepared)
        self.import_button.configure(
            state="normal" if can_import else "disabled"
        )

    def build_preview(self) -> None:
        self.prepared = []
        self.import_button.configure(state="disabled")
        self.tree.delete(*self.tree.get_children())
        self.log("Строю превью...")
        self._set_busy(True)
        self.worker.submit(
            lambda: self.service.prepare(self.project, self.action),
            done_kind=self._kind("preview_done"),
            error_kind=self._kind("error"),
        )

    def _on_preview_done(self, result: PrepareResult) -> None:
        try:
            self.prepared = result.items
            for item in result.items:
                preview = item.preview
                parent = self.tree.insert(
                    "",
                    "end",
                    values=(
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
                            format_range(date_range),
                            format_hours(date_range.hours),
                        ),
                    )
            for preview in result.errors:
                self.tree.insert(
                    "",
                    "end",
                    tags=("error",),
                    values=(
                        preview.issue_id,
                        f"Ошибка: {preview.error}",
                        "",
                        "",
                    ),
                )
            self.log(
                f"Превью готово: записей {sum(len(i.records) for i in result.items)}, "
                f"ошибок {len(result.errors)}"
            )
            if not result.items:
                messagebox.showinfo(
                    "Work Assistant", "Нет записей для импорта", parent=self
                )
        finally:
            self._set_busy(False)

    def run_import(self) -> None:
        if not self.prepared:
            messagebox.showinfo(
                "Work Assistant", "Сначала постройте превью", parent=self
            )
            return
        total = sum(len(item.records) for item in self.prepared)
        if not messagebox.askyesno(
            "Work Assistant",
            f"Импортировать {total} записей в Redmine?",
            parent=self,
        ):
            return
        items = self.prepared
        self.progress_bar.configure(maximum=max(total, 1), value=0)
        self.progress_label.set("")
        self._set_busy(True)

        def progress_cb(completed: int, global_total: int, name: str) -> None:
            self.worker.send(
                self._kind("progress"), (completed, global_total, name)
            )

        self.worker.submit(
            lambda: asyncio.run(
                self.service.run(items, progress_cb=progress_cb)
            ),
            done_kind=self._kind("import_done"),
            error_kind=self._kind("error"),
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
            message = (
                f"Импорт завершён: успешно {success}, "
                f"ошибок {len(summary.errors)}"
            )
            self.log(message)
            for project_name, spent_on, error in summary.errors:
                self.log(f"  {project_name} {spent_on}: {error}")
            messagebox.showinfo("Work Assistant", message, parent=self)
        finally:
            self._set_busy(False)

    def _on_worker_error(self, exc: Exception) -> None:
        self._set_busy(False)
        self.log(f"Ошибка: {exc}")
        messagebox.showerror("Work Assistant", str(exc), parent=self)
