import math
import tkinter as tk
from tkinter import ttk

from dto.tracking_dto import TrackingRow

DEFAULT_COMMENT = "development"


def validate_report_row(
    hours_text: str, comment: str
) -> tuple[float | None, list[str]]:
    try:
        hours = float(hours_text.replace(",", ".").strip())
    except ValueError:
        return None, ["Часы должны быть числом"]
    if not math.isfinite(hours):
        return None, ["Часы должны быть числом"]
    if hours <= 0:
        return None, ["Часы должны быть больше нуля"]
    if hours > 24:
        return None, ["Часы не могут быть больше 24"]
    if abs(hours * 2 - round(hours * 2)) > 1e-9:
        return None, ["Часы должны быть кратны 0.5"]
    return hours, []


class ReportEditor(tk.Toplevel):
    def __init__(self, parent: tk.Misc, row: TrackingRow) -> None:
        super().__init__(parent)
        self.row = row
        self.result = False
        self.title("Редактировать строку")
        self.resizable(False, False)
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"{row.user_name} — {row.date}").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        ttk.Label(frame, text="Часы").grid(row=1, column=0, sticky="w")
        self.hours = ttk.Entry(frame, width=12)
        self.hours.grid(row=1, column=1, sticky="we")
        self.hours.insert(0, f"{row.proposed_hours:g}")
        ttk.Label(frame, text="Комментарий").grid(row=2, column=0, sticky="w")
        self.comment = ttk.Entry(frame, width=40)
        self.comment.grid(row=2, column=1, sticky="we")
        self.comment.insert(0, row.comment)
        self.include = tk.BooleanVar(value=row.include)
        ttk.Checkbutton(
            frame, text="включить в трек", variable=self.include
        ).grid(row=3, column=1, sticky="w", pady=4)
        self.error = ttk.Label(
            frame, text="", foreground="red", wraplength=360
        )
        self.error.grid(row=4, column=0, columnspan=2, sticky="w")
        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Сохранить", command=self._save).pack(
            side="left", padx=4
        )
        ttk.Button(buttons, text="Отмена", command=self.destroy).pack(
            side="left"
        )
        self.bind("<Return>", self._save)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.transient(parent)
        self.grab_set()
        self.hours.focus_set()

    def _save(self, _event: tk.Event | None = None) -> None:
        hours, errors = validate_report_row(
            self.hours.get(), self.comment.get()
        )
        if errors or hours is None:
            self.error.configure(text="\n".join(errors))
            return
        self.row.proposed_hours = hours
        self.row.comment = self.comment.get().strip() or DEFAULT_COMMENT
        self.row.include = self.include.get()
        self.result = True
        self.destroy()
