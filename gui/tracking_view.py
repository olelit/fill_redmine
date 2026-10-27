import calendar
import copy
import tkinter as tk
from collections.abc import Callable
from datetime import date
from tkinter import messagebox, ttk
from typing import Any

from configs.project_config import ProjectConfig, ProjectUserConfig
from dto.tracking_dto import TrackingReport, TrackingRow
from gui.project_settings_panel import ProjectSettingsPanel
from gui.tracking_validation import validate_tracking_request
from gui.worker import GuiWorker
from services.tracking_service import TrackingService
from storage.project_repository import ProjectRepository
from storage.settings_repository import SettingsRepository
from trackers.base import BaseTracker
from trackers.registry import all_trackers

SOURCE_LABELS: dict[str, str] = {
    "autofill": "Автозаполнение",
    "tracker": "Из трекера",
    "commits": "Из коммитов",
}
SOURCE_KINDS_BY_LABEL: dict[str, str] = {
    label: kind for kind, label in SOURCE_LABELS.items()
}


def _trackers_for_users(
    users: list[ProjectUserConfig],
) -> list[type[BaseTracker]]:
    kinds = {
        kind
        for user in users
        for kind, config in user.trackers.items()
        if config
    }
    return [
        cls for cls in all_trackers() if cls.kind in kinds and cls.can_read
    ]


def trackers_for_project(project: ProjectConfig) -> list[type[BaseTracker]]:
    return _trackers_for_users(project.users)


class TrackingView(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        project: ProjectConfig,
        repo: ProjectRepository,
        settings_repo: SettingsRepository,
        worker: GuiWorker,
        on_back: Callable[[], None],
    ) -> None:
        super().__init__(parent, padding=6)
        self.project = project
        self.repo = repo
        self.settings_repo = settings_repo
        self.worker = worker
        self.on_back = on_back
        self.report: TrackingReport | None = None
        self._busy = False
        self.destination_by_label: dict[str, str] = {}
        self.source_kind_by_label: dict[str, str] = {}
        self.rows_by_iid: dict[str, TrackingRow] = {}
        self._handlers: dict[str, Callable[[Any], None]] = {}
        self.service = TrackingService(log=self._log_from_worker)

        self.destination_label = tk.StringVar()
        self.source_label = tk.StringVar(value=SOURCE_LABELS["autofill"])
        self.source_tracker_label = tk.StringVar()

        self._build()
        self._register_handlers()
        self.refresh_trackers()
        self._set_busy(False)

    @property
    def busy(self) -> bool:
        return self._busy

    def _build(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Button(
            header, text="← Проект", command=self.on_back
        ).pack(side="left")
        ttk.Label(
            header,
            text=f"Трекинг времени — {self.project.name}",
            font=("TkDefaultFont", 14, "bold"),
        ).pack(side="left", padx=12)

        self.settings_panel = ProjectSettingsPanel(
            self, self.project, self.repo, on_saved=self._on_settings_saved
        )
        self.settings_panel.pack(fill="x", pady=(6, 0))

        self._build_controls()

        report_frame = ttk.LabelFrame(self, text="Отчёт", padding=6)
        report_frame.pack(fill="both", expand=True, pady=(6, 0))

        columns = (
            "include",
            "user",
            "date",
            "existing",
            "proposed",
            "comment",
            "details",
        )
        self.report_tree = ttk.Treeview(
            report_frame, columns=columns, show="headings", height=10
        )
        for column, (title, width, anchor) in {
            "include": ("☑", 36, "center"),
            "user": ("Юзер", 140, "w"),
            "date": ("Дата", 100, "w"),
            "existing": ("Было", 70, "e"),
            "proposed": ("Предложено", 90, "e"),
            "comment": ("Комментарий", 260, "w"),
            "details": ("Источник / статус", 200, "w"),
        }.items():
            self.report_tree.heading(column, text=title)
            self.report_tree.column(
                column, width=width, anchor=anchor, stretch=column != "include"
            )
        self.report_tree.tag_configure("excluded", foreground="#888")
        self.report_tree.tag_configure("error", foreground="#b00020")
        tree_scroll = ttk.Scrollbar(
            report_frame, orient="vertical", command=self.report_tree.yview
        )
        self.report_tree.configure(yscrollcommand=tree_scroll.set)
        self.report_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")

        self.summary_label = ttk.Label(self, text="", foreground="#555")
        self.summary_label.pack(fill="x", pady=(2, 0))

        write_row = ttk.Frame(self)
        write_row.pack(fill="x", pady=4)
        self.write_button = ttk.Button(
            write_row, text="Затрекать", state="disabled"
        )
        self.write_button.pack(side="left")
        ttk.Label(
            write_row,
            text="Запись отчёта появится в следующем шаге.",
            foreground="#777",
        ).pack(side="left", padx=8)

        log_frame = ttk.Frame(self)
        log_frame.pack(fill="x", pady=(4, 0))
        self.log_text = tk.Text(
            log_frame, height=5, state="disabled", wrap="word"
        )
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

    def _build_controls(self) -> None:
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(6, 0))
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(3, weight=1)

        ttk.Label(controls, text="Трекер:").grid(
            row=0, column=0, sticky="w", pady=3
        )
        self.destination_combo = ttk.Combobox(
            controls,
            textvariable=self.destination_label,
            state="readonly",
            width=22,
        )
        self.destination_combo.grid(row=0, column=1, sticky="w", padx=(4, 16))
        self.destination_combo.bind(
            "<<ComboboxSelected>>", self._on_destination_changed
        )

        ttk.Label(controls, text="Источник:").grid(
            row=0, column=2, sticky="w", pady=3
        )
        self.source_combo = ttk.Combobox(
            controls,
            textvariable=self.source_label,
            values=list(SOURCE_LABELS.values()),
            state="readonly",
            width=22,
        )
        self.source_combo.grid(row=0, column=3, sticky="w", padx=4)
        self.source_combo.bind("<<ComboboxSelected>>", self._on_source_changed)

        self.source_tracker_name_label = ttk.Label(
            controls, text="Трекер-источник:"
        )
        self.source_tracker_name_label.grid(
            row=1, column=0, sticky="w", pady=3
        )
        self.source_tracker_combo = ttk.Combobox(
            controls,
            textvariable=self.source_tracker_label,
            state="readonly",
            width=22,
        )
        self.source_tracker_combo.grid(
            row=1, column=1, sticky="w", padx=(4, 16)
        )
        self.source_tracker_combo.bind(
            "<<ComboboxSelected>>", self._on_source_tracker_changed
        )

        period = ttk.Frame(controls)
        period.grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        ttk.Label(period, text="Период:").pack(side="left")
        start, end = self._month_bounds()
        self.start_entry = ttk.Entry(period, width=12)
        self.start_entry.pack(side="left", padx=4)
        self.start_entry.insert(0, start.isoformat())
        self.start_entry.bind("<KeyRelease>", self._on_period_changed)
        ttk.Label(period, text="—").pack(side="left")
        self.end_entry = ttk.Entry(period, width=12)
        self.end_entry.pack(side="left", padx=4)
        self.end_entry.insert(0, end.isoformat())
        self.end_entry.bind("<KeyRelease>", self._on_period_changed)

        self.generate_button = ttk.Button(
            controls, text="Сгенерировать отчёт", command=self._generate
        )
        self.generate_button.grid(
            row=2, column=2, columnspan=2, sticky="e", pady=(6, 0)
        )

    @staticmethod
    def _month_bounds() -> tuple[date, date]:
        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]
        return today.replace(day=1), today.replace(day=last_day)

    def _register_handlers(self) -> None:
        handlers: dict[str, Callable[[Any], None]] = {
            "tracking_report_done": self._on_report_done,
            "tracking_error": self._on_error,
            "tracking_log": self.log,
        }
        for kind, handler in handlers.items():
            self._handlers[kind] = handler
            self.worker.register(kind, handler)

    def destroy(self) -> None:
        for kind, handler in self._handlers.items():
            self.worker.unregister(kind, handler)
        self._handlers.clear()
        super().destroy()

    def _log_from_worker(self, message: str) -> None:
        self.worker.send("tracking_log", message)

    def log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _selected_users(self) -> list[ProjectUserConfig]:
        selected = set(self.settings_panel.selected_user_ids())
        return [
            user for user in self.project.users if user.db_id in selected
        ]

    def _current_source(self) -> str:
        return SOURCE_KINDS_BY_LABEL.get(self.source_label.get(), "autofill")

    def refresh_trackers(self) -> None:
        classes = _trackers_for_users(self._selected_users())
        destinations = [cls for cls in classes if cls.can_write]
        self.destination_by_label = {
            cls.label: cls.kind for cls in destinations
        }
        destination_values = list(self.destination_by_label)
        self.destination_combo.configure(values=destination_values)
        if self.destination_label.get() not in destination_values:
            self.destination_label.set(
                destination_values[0] if destination_values else ""
            )
        self._refresh_source_trackers()
        self._reset_report()

    def _refresh_source_trackers(self) -> None:
        destination = self.destination_by_label.get(
            self.destination_label.get(), ""
        )
        classes = [
            cls
            for cls in _trackers_for_users(self._selected_users())
            if cls.kind != destination
        ]
        self.source_kind_by_label = {
            cls.label: cls.kind for cls in classes
        }
        values = list(self.source_kind_by_label)
        self.source_tracker_combo.configure(values=values)
        if self.source_tracker_label.get() not in values:
            self.source_tracker_label.set("")
        self._sync_source_tracker_visibility()

    def _sync_source_tracker_visibility(self) -> None:
        if self._current_source() == "tracker":
            self.source_tracker_name_label.grid()
            self.source_tracker_combo.grid()
        else:
            self.source_tracker_name_label.grid_remove()
            self.source_tracker_combo.grid_remove()

    def _on_settings_saved(self, project: ProjectConfig) -> None:
        self.project = project
        self.refresh_trackers()
        self.log("Настройки проекта обновлены")

    def _on_destination_changed(self, _event: tk.Event | None = None) -> None:
        self._refresh_source_trackers()
        self._reset_report()

    def _on_source_changed(self, _event: tk.Event | None = None) -> None:
        self._sync_source_tracker_visibility()
        self._reset_report()

    def _on_source_tracker_changed(
        self, _event: tk.Event | None = None
    ) -> None:
        self._reset_report()

    def _on_period_changed(self, _event: tk.Event | None = None) -> None:
        if not self._busy:
            self._reset_report()

    def _reset_report(self) -> None:
        self.report = None
        self.report_tree.delete(*self.report_tree.get_children())
        self.rows_by_iid.clear()
        self.summary_label.configure(text="")
        self.write_button.configure(state="disabled")

    def _generate(self) -> None:
        if self._busy:
            return
        source = self._current_source()
        source_kind = (
            self.source_kind_by_label.get(self.source_tracker_label.get(), "")
            if source == "tracker"
            else ""
        )
        destination = self.destination_by_label.get(
            self.destination_label.get(), ""
        )
        data, errors = validate_tracking_request(
            user_ids=self.settings_panel.selected_user_ids(),
            destination=destination,
            source=source,
            source_kind=source_kind,
            start_text=self.start_entry.get(),
            end_text=self.end_entry.get(),
        )
        if data is None:
            for error in errors:
                self.log(f"Проверка: {error}")
            messagebox.showerror(
                "Трекинг", "\n".join(errors), parent=self
            )
            return
        try:
            ai_settings = self.settings_repo.get_ai_settings()
        except Exception as exc:
            message = str(exc) or exc.__class__.__name__
            self.log(f"Не удалось прочитать настройки AI: {message}")
            messagebox.showerror(
                "Трекинг",
                f"Не удалось прочитать настройки AI: {message}",
                parent=self,
            )
            return

        project = copy.deepcopy(self.project)
        self._reset_report()
        self.log(
            f"Генерирую отчёт за {data['start']} — {data['end']} "
            f"({data['source']})"
        )
        self._set_busy(True)
        self.worker.submit(
            lambda: self.service.generate_report(
                project,
                data["user_ids"],
                data["destination"],
                data["source"],
                data["source_kind"],
                data["start"],
                data["end"],
                ai_settings=ai_settings,
            ),
            done_kind="tracking_report_done",
            error_kind="tracking_error",
        )

    def _on_report_done(self, report: TrackingReport) -> None:
        self.report = report
        self.report_tree.delete(*self.report_tree.get_children())
        self.rows_by_iid.clear()
        for row in report.rows:
            self._insert_row(row)
        included = [
            row
            for row in report.rows
            if row.include and row.proposed_hours > 0
        ]
        hours = sum(row.proposed_hours for row in included)
        self.summary_label.configure(
            text=(
                f"Строк: {len(report.rows)} · к записи: {len(included)}"
                f" · часов: {hours:g}"
            )
        )
        for error in report.errors:
            self.log(f"Ошибка: {error}")
        self.log(f"Отчёт готов: строк {len(report.rows)}")
        self._set_busy(False)

    def _insert_row(self, row: TrackingRow) -> None:
        tags: tuple[str, ...] = ()
        if row.error:
            tags = ("error",)
        elif not row.include:
            tags = ("excluded",)
        self.report_tree.insert(
            "",
            "end",
            iid=row.row_id,
            values=self._row_values(row),
            tags=tags,
        )
        self.rows_by_iid[row.row_id] = row

    @staticmethod
    def _row_values(row: TrackingRow) -> tuple[str, ...]:
        return (
            "☑" if row.include else "☐",
            row.user_name,
            row.date,
            f"{row.existing_hours:g}",
            f"{row.proposed_hours:g}",
            row.comment,
            TrackingView._row_details(row),
        )

    @staticmethod
    def _row_details(row: TrackingRow) -> str:
        if row.error:
            return f"ошибка: {row.error}"
        if row.status:
            return row.status
        return row.source_details

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        readonly = "disabled" if busy else "readonly"
        self.generate_button.configure(state=state)
        self.start_entry.configure(state=state)
        self.end_entry.configure(state=state)
        self.destination_combo.configure(state=readonly)
        self.source_combo.configure(state=readonly)
        self.source_tracker_combo.configure(state=readonly)

    def _on_error(self, exc: object) -> None:
        message = str(exc) if exc is not None else ""
        if not message and isinstance(exc, BaseException):
            message = exc.__class__.__name__
        if not message:
            message = "Неизвестная ошибка"
        self._set_busy(False)
        self.log(f"Ошибка: {message}")
        messagebox.showerror("Трекинг", message, parent=self)
