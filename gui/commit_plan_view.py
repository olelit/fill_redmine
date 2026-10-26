import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk

from clients.ai_client import AiClient, resolve_ai_config
from clients.git_client import GitClient
from configs.project_config import ProjectConfig
from dto.commit_plan_dto import CommitPlanDTO
from gui.project_validation import parse_period
from gui.worker import GuiWorker
from services.commit_plan_service import CommitPlanService
from storage.project_repository import ProjectRepository
from trackers.registry import configured_trackers


def format_plan_text(plan: CommitPlanDTO) -> str:
    lines: list[str] = []
    if plan.summary:
        lines.append(plan.summary)
        lines.append("")
    for day in plan.days:
        if day.planned_hours <= 0:
            continue
        lines.append(
            f"{day.date} — {day.planned_hours:g}h — {day.comment}"
        )
        if day.commit_hashes:
            lines.append(f"  commits: {', '.join(day.commit_hashes)}")
    if not lines:
        return "Нет предложений по часам."
    return "\n".join(lines)


class CommitPlanView(ttk.Frame):
    def __init__(
        self,
        parent,
        project: ProjectConfig,
        repo: ProjectRepository,
        worker: GuiWorker,
    ):
        super().__init__(parent, padding=6)
        self.project = project
        self.repo = repo
        self.worker = worker
        self.commits = []
        self.plan: CommitPlanDTO | None = None
        self.busy = False
        self.tracker_vars: dict[str, tk.BooleanVar] = {}
        self._build()
        self._register_handlers()

    def _kind(self, suffix: str) -> str:
        return f"plan_{suffix}"

    def _register_handlers(self) -> None:
        self.worker.register(self._kind("commits_done"), self._on_commits_done)
        self.worker.register(self._kind("plan_done"), self._on_plan_done)
        self.worker.register(self._kind("error"), self._on_error)

    def _build(self) -> None:
        period = ttk.Frame(self)
        period.pack(fill="x")
        ttk.Label(period, text="С").pack(side="left")
        self.start_var = ttk.Entry(period, width=12)
        self.start_var.pack(side="left", padx=4)
        self.start_var.insert(0, date.today().replace(day=1).isoformat())
        ttk.Label(period, text="По").pack(side="left")
        self.end_var = ttk.Entry(period, width=12)
        self.end_var.pack(side="left", padx=4)
        self.end_var.insert(0, date.today().isoformat())
        self.load_button = ttk.Button(
            period, text="Загрузить коммиты", command=self.load_commits
        )
        self.load_button.pack(side="left", padx=8)

        self.commit_tree = ttk.Treeview(
            self,
            columns=("date", "hash", "subject"),
            show="headings",
            height=8,
        )
        for column, (title, width) in {
            "date": ("Дата", 130),
            "hash": ("Хеш", 90),
            "subject": ("Тема", 600),
        }.items():
            self.commit_tree.heading(column, text=title)
            self.commit_tree.column(column, width=width, anchor="w")
        self.commit_tree.pack(fill="both", expand=True, pady=6)

        trackers_frame = ttk.LabelFrame(
            self, text="Учитывать уже затреканные часы", padding=6
        )
        trackers_frame.pack(fill="x", pady=4)
        configured = configured_trackers(self.project)
        selected = self.project.ai.get("selected_trackers", [])
        if not isinstance(selected, list):
            selected = []
        default_kind = (
            "youtrack"
            if any(tracker.kind == "youtrack" for tracker in configured)
            else (configured[0].kind if configured else "")
        )
        for tracker in configured:
            variable = tk.BooleanVar(
                value=(
                    tracker.kind in selected
                    if selected
                    else tracker.kind == default_kind
                )
            )
            self.tracker_vars[tracker.kind] = variable
            ttk.Checkbutton(
                trackers_frame,
                text=tracker.label,
                variable=variable,
            ).pack(side="left", padx=6)
        if not configured:
            ttk.Label(
                trackers_frame,
                text="Настройте хотя бы один трекер в настройках проекта",
            ).pack(anchor="w")

        self.generate_button = ttk.Button(
            self,
            text="Сгенерировать план",
            command=self.generate_plan,
            state="disabled",
        )
        self.generate_button.pack(anchor="w", pady=4)

        ttk.Label(
            self,
            text="В YouTrack ничего не записывается — план нужно вставить вручную.",
            foreground="#777",
        ).pack(anchor="w")

        self.plan_tree = ttk.Treeview(
            self,
            columns=("date", "existing", "deficit", "planned", "comment", "commits"),
            show="headings",
            height=10,
        )
        for column, (title, width) in {
            "date": ("Дата", 100),
            "existing": ("Было", 70),
            "deficit": ("Дефицит", 80),
            "planned": ("Предложено", 90),
            "comment": ("Комментарий", 360),
            "commits": ("Коммиты", 160),
        }.items():
            self.plan_tree.heading(column, text=title)
            self.plan_tree.column(column, width=width, anchor="w")
        self.plan_tree.pack(fill="both", expand=True, pady=6)

        self.summary_text = ttk.Label(self, text="", wraplength=900)
        self.summary_text.pack(anchor="w")
        self.copy_button = ttk.Button(
            self, text="Копировать план", command=self.copy_plan, state="disabled"
        )
        self.copy_button.pack(anchor="w", pady=4)

        log_frame = ttk.Frame(self)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, height=5, state="disabled", wrap="word")
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
        self.load_button.configure(state="disabled" if busy else "normal")
        can_generate = (
            not busy
            and bool(self.commits)
            and any(variable.get() for variable in self.tracker_vars.values())
        )
        self.generate_button.configure(
            state="normal" if can_generate else "disabled"
        )

    def load_commits(self) -> None:
        try:
            start, end = parse_period(self.start_var.get(), self.end_var.get())
        except ValueError as exc:
            messagebox.showerror("Work Assistant", str(exc), parent=self)
            return
        self.log(f"Загружаю коммиты за {start.isoformat()} — {end.isoformat()}")
        self._set_busy(True)
        client = GitClient(self.project.git_repo_path)
        self.worker.submit(
            lambda: client.list_commits(
                self.project.git_author_email, start, end
            ),
            done_kind=self._kind("commits_done"),
            error_kind=self._kind("error"),
        )

    def _on_commits_done(self, commits) -> None:
        self.commits = list(commits)
        self.commit_tree.delete(*self.commit_tree.get_children())
        for commit in self.commits:
            self.commit_tree.insert(
                "",
                "end",
                values=(
                    commit.date[:10],
                    commit.hash[:7],
                    commit.subject,
                ),
            )
        self.log(f"Загружено коммитов: {len(self.commits)}")
        self._set_busy(False)

    def generate_plan(self) -> None:
        try:
            start, end = parse_period(self.start_var.get(), self.end_var.get())
        except ValueError as exc:
            messagebox.showerror("Work Assistant", str(exc), parent=self)
            return
        selected = [
            kind for kind, variable in self.tracker_vars.items() if variable.get()
        ]
        if not selected:
            messagebox.showinfo(
                "Work Assistant", "Выберите хотя бы один трекер", parent=self
            )
            return

        self.project.ai["selected_trackers"] = selected
        if self.project.db_id is not None:
            self.repo.update_project(self.project.db_id, self.project)

        try:
            ai_client = AiClient(resolve_ai_config(self.project))
        except Exception as exc:
            messagebox.showerror("Work Assistant", str(exc), parent=self)
            return

        service = CommitPlanService(ai_client=ai_client, log=self.log)
        commits = list(self.commits)
        self.log(f"Генерирую план через {ai_client.config.model}...")
        self._set_busy(True)
        self.worker.submit(
            lambda: service.generate(
                self.project, start, end, selected, commits
            ),
            done_kind=self._kind("plan_done"),
            error_kind=self._kind("error"),
        )

    def _on_plan_done(self, plan: CommitPlanDTO) -> None:
        self.plan = plan
        self.plan_tree.delete(*self.plan_tree.get_children())
        for day in plan.days:
            self.plan_tree.insert(
                "",
                "end",
                values=(
                    day.date,
                    f"{day.existing_hours:g}",
                    f"{day.deficit_hours:g}",
                    f"{day.planned_hours:g}",
                    day.comment,
                    ", ".join(hash[:7] for hash in day.commit_hashes),
                ),
            )
        self.summary_text.configure(text=plan.summary)
        self.copy_button.configure(
            state="normal" if any(day.planned_hours for day in plan.days) else "disabled"
        )
        self.log(f"План готов: дней с предложениями {sum(1 for d in plan.days if d.planned_hours)}")
        self._set_busy(False)

    def copy_plan(self) -> None:
        if self.plan is None:
            return
        text = format_plan_text(self.plan)
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Work Assistant", "План скопирован", parent=self)

    def _on_error(self, exc: Exception) -> None:
        self._set_busy(False)
        self.log(f"Ошибка: {exc}")
        messagebox.showerror("Work Assistant", str(exc), parent=self)
