import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

from clients.ai.factory import create_ai_client
from configs.ai_settings import AiSettings
from gui.ai_settings_validation import PROVIDERS, validate_ai_settings
from gui.worker import GuiWorker
from storage.settings_repository import SettingsRepository

PROVIDER_LABELS: dict[str, str] = {
    "opencode_go": "OpenCode Go",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "custom": "Custom",
}
PROVIDER_IDS: dict[str, str] = {
    label: provider for provider, label in PROVIDER_LABELS.items()
}
FALLBACK_MODELS: dict[str, tuple[str, ...]] = {
    "opencode_go": ("deepseek-v4.1-flash",),
    "openai": (),
    "anthropic": (),
    "custom": (),
}


class AiSettingsDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        settings_repo: SettingsRepository,
        worker: GuiWorker,
    ) -> None:
        super().__init__(parent)
        self.settings_repo = settings_repo
        self.worker = worker
        self.settings = settings_repo.get_ai_settings()
        self.keys: dict[str, str] = dict(self.settings.keys)
        self.saved = False
        self.busy = False
        self._pending: str | None = None
        self._handlers: dict[str, Callable] = {}
        self._active_provider = (
            self.settings.provider
            if self.settings.provider in PROVIDERS
            else "opencode_go"
        )

        self.provider = tk.StringVar(
            value=PROVIDER_LABELS[self._active_provider]
        )
        self.model = tk.StringVar(value=self.settings.model)
        self.api_key = tk.StringVar(
            value=self.keys.get(self._active_provider, "")
        )
        self.base_url = tk.StringVar(value=self.settings.base_url)
        self.log_var = tk.StringVar(value="")

        self.title("Настройки AI")
        self.geometry("580x330")
        self.resizable(False, False)
        self._build()
        self._sync_base_url_row()
        self._register_handlers()

        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.grab_set()
        self.focus_set()

    def _build(self) -> None:
        content = ttk.Frame(self, padding=12)
        content.pack(fill="both", expand=True)
        content.columnconfigure(1, weight=1)

        ttk.Label(content, text="Провайдер").grid(
            row=0, column=0, sticky="w", pady=4
        )
        self.provider_combo = ttk.Combobox(
            content,
            textvariable=self.provider,
            values=list(PROVIDER_LABELS.values()),
            state="readonly",
            width=28,
        )
        self.provider_combo.grid(row=0, column=1, sticky="we", pady=4)
        self.provider_combo.bind("<<ComboboxSelected>>", self._on_provider_changed)

        ttk.Label(content, text="Модель").grid(row=1, column=0, sticky="w", pady=4)
        self.model_combo = ttk.Combobox(
            content,
            textvariable=self.model,
            values=[self.settings.model] if self.settings.model else [],
            width=40,
        )
        self.model_combo.grid(row=1, column=1, sticky="we", pady=4)
        self.refresh_button = ttk.Button(
            content, text="Обновить модели", command=self.refresh_models
        )
        self.refresh_button.grid(row=1, column=2, padx=(6, 0), pady=4)

        ttk.Label(content, text="API key").grid(
            row=2, column=0, sticky="w", pady=4
        )
        self.api_key_entry = ttk.Entry(
            content, textvariable=self.api_key, show="*", width=40
        )
        self.api_key_entry.grid(
            row=2, column=1, columnspan=2, sticky="we", pady=4
        )

        self.base_url_label = ttk.Label(content, text="Base URL")
        self.base_url_label.grid(row=3, column=0, sticky="w", pady=4)
        self.base_url_entry = ttk.Entry(
            content, textvariable=self.base_url, width=40
        )
        self.base_url_entry.grid(
            row=3, column=1, columnspan=2, sticky="we", pady=4
        )

        footer = ttk.Frame(content)
        footer.grid(row=4, column=0, columnspan=3, sticky="we", pady=(14, 4))
        self.check_button = ttk.Button(
            footer, text="Проверить подключение", command=self.check_connection
        )
        self.check_button.pack(side="left")
        self.save_button = ttk.Button(
            footer, text="Сохранить", command=self.save
        )
        self.save_button.pack(side="right", padx=4)
        self.cancel_button = ttk.Button(
            footer, text="Отмена", command=self.destroy
        )
        self.cancel_button.pack(side="right")

        ttk.Label(
            content, textvariable=self.log_var, foreground="#555", wraplength=540
        ).grid(row=5, column=0, columnspan=3, sticky="we", pady=(8, 0))

    def _register_handlers(self) -> None:
        self._register_handler("ai_models_done", self._on_models_done)
        self._register_handler("ai_check_done", self._on_check_done)
        self._register_handler("ai_error", self._on_worker_error)

    def _register_handler(self, kind: str, handler: Callable) -> None:
        self._handlers[kind] = handler
        self.worker.register(kind, handler)

    def destroy(self) -> None:
        for kind, handler in self._handlers.items():
            self.worker.unregister(kind, handler)
        self._handlers.clear()
        super().destroy()

    def log(self, message: str) -> None:
        self.log_var.set(message)

    def _provider_id(self) -> str:
        return PROVIDER_IDS.get(self.provider.get(), "opencode_go")

    def _on_provider_changed(self, event: tk.Event | None = None) -> None:
        provider = self._provider_id()
        if provider == self._active_provider:
            return
        self.keys[self._active_provider] = self.api_key.get()
        self._active_provider = provider
        self.api_key.set(self.keys.get(provider, ""))
        current = self.model.get().strip()
        self.model_combo.configure(values=[current] if current else [])
        self._sync_base_url_row()
        self.log(f"Провайдер: {PROVIDER_LABELS[provider]}")

    def _sync_base_url_row(self) -> None:
        if self._provider_id() == "custom":
            self.base_url_label.grid()
            self.base_url_entry.grid()
        else:
            self.base_url_label.grid_remove()
            self.base_url_entry.grid_remove()

    def _collect(self) -> tuple[AiSettings | None, list[str]]:
        provider = self._provider_id()
        keys = dict(self.keys)
        keys[provider] = self.api_key.get()
        return validate_ai_settings(
            provider=provider,
            model=self.model.get(),
            base_url=self.base_url.get(),
            keys=keys,
        )

    def _show_errors(self, errors: list[str]) -> None:
        message = "\n".join(errors)
        self.log(message)
        messagebox.showerror("Настройки AI", message, parent=self)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.refresh_button.configure(state=state)
        self.check_button.configure(state=state)
        self.save_button.configure(state=state)

    def refresh_models(self) -> None:
        settings, errors = self._collect()
        if settings is None:
            self._show_errors(errors)
            return
        self._pending = "models"
        self._set_busy(True)
        self.log("Загружаю модели…")
        self.worker.submit(
            lambda: create_ai_client(settings).list_models(),
            done_kind="ai_models_done",
            error_kind="ai_error",
        )

    def check_connection(self) -> None:
        settings, errors = self._collect()
        if settings is None:
            self._show_errors(errors)
            return
        self._pending = "check"
        self._set_busy(True)
        self.log("Проверяю подключение…")
        self.worker.submit(
            lambda: create_ai_client(settings).check_connection(),
            done_kind="ai_check_done",
            error_kind="ai_error",
        )

    def save(self) -> None:
        settings, errors = self._collect()
        if settings is None:
            self._show_errors(errors)
            return
        self.settings_repo.save_ai_settings(settings)
        self.saved = True
        self.destroy()

    def _apply_models(self, models: list[str]) -> None:
        current = self.model.get().strip()
        values: list[str] = []
        for value in ([current] if current else []) + list(models):
            if value and value not in values:
                values.append(value)
        self.model_combo.configure(values=values)

    def _fallback_models(self) -> list[str]:
        provider = self._provider_id()
        return list(FALLBACK_MODELS.get(provider, ()))

    def _on_models_done(self, models: list[str]) -> None:
        self._pending = None
        self._apply_models(models)
        if models:
            self.log(f"Моделей получено: {len(models)}")
        else:
            self.log("Список моделей пуст — введите модель вручную")
        self._set_busy(False)

    def _on_check_done(self, result: object = None) -> None:
        self._pending = None
        self._set_busy(False)
        self.log("Подключение работает")
        messagebox.showinfo(
            "Настройки AI", "Подключение работает", parent=self
        )

    def _on_worker_error(self, exc: Exception) -> None:
        pending = self._pending
        self._pending = None
        if pending == "models":
            self._apply_models(self._fallback_models())
        self._set_busy(False)
        message = str(exc) or exc.__class__.__name__
        self.log(f"Ошибка: {message}")
        messagebox.showerror("Настройки AI", message, parent=self)
