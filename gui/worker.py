import queue
import threading
import traceback
from collections.abc import Callable
from typing import Any


class GuiWorker:
    def __init__(self, root: Any):
        self.root = root
        self.queue: queue.Queue = queue.Queue()
        self.handlers: dict[str, Callable[[Any], None]] = {}
        self.root.after(100, self._poll)

    def register(self, kind: str, handler: Callable[[Any], None]) -> None:
        self.handlers[kind] = handler

    def unregister(self, kind: str, handler: Callable[[Any], None] | None = None) -> None:
        if handler is None:
            self.handlers.pop(kind, None)
        elif self.handlers.get(kind) == handler:
            self.handlers.pop(kind, None)

    def send(self, kind: str, payload: Any = None) -> None:
        self.queue.put((kind, payload))

    def submit(
        self,
        func: Callable[[], Any],
        done_kind: str = "done",
        error_kind: str = "error",
    ) -> None:
        def target() -> None:
            try:
                result = func()
            except Exception as exc:
                self.send(error_kind, exc)
            else:
                self.send(done_kind, result)

        threading.Thread(target=target, daemon=True).start()

    def drain(self) -> None:
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                return
            handler = self.handlers.get(kind)
            if handler is not None:
                handler(payload)

    def _poll(self) -> None:
        try:
            self.drain()
        except Exception:
            traceback.print_exc()
        finally:
            self.root.after(100, self._poll)
