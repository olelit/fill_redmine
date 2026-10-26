import time

from gui.worker import GuiWorker


class FakeRoot:
    def after(self, delay, callback):
        return None


def wait_until(worker, predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        worker.drain()
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestGuiWorker:
    def test_drain_dispatches_registered_handlers(self):
        worker = GuiWorker(FakeRoot())
        received = []
        worker.register("log", received.append)

        worker.send("log", "привет")
        worker.send("unknown", "ignored")
        worker.drain()

        assert received == ["привет"]

    def test_submit_reports_function_result(self):
        worker = GuiWorker(FakeRoot())
        done = []
        worker.register("done", done.append)

        worker.submit(lambda: 42)

        assert wait_until(worker, lambda: done == [42])

    def test_submit_reports_exception(self):
        worker = GuiWorker(FakeRoot())
        errors = []
        worker.register("error", errors.append)

        def boom():
            raise ValueError("bad")

        worker.submit(boom)

        assert wait_until(worker, lambda: len(errors) == 1)
        assert isinstance(errors[0], ValueError)

    def test_raising_handler_does_not_stop_poll(self):
        worker = GuiWorker(FakeRoot())
        received = []
        worker.register("boom", lambda payload: 1 / 0)
        worker.register("ok", received.append)

        worker.send("boom", None)
        worker._poll()

        worker.send("ok", "после")
        worker._poll()

        assert received == ["после"]

    def test_unregister_removes_handler(self):
        worker = GuiWorker(FakeRoot())
        received = []
        worker.register("log", received.append)
        worker.unregister("log")

        worker.send("log", "x")
        worker.drain()

        assert received == []

    def test_unregister_specific_handler(self):
        worker = GuiWorker(FakeRoot())
        received = []
        worker.register("log", received.append)
        worker.unregister("log", received.append)

        worker.send("log", "x")
        worker.drain()

        assert received == []
