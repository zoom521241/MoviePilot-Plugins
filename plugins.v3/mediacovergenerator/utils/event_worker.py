"""Cancellable, coalescing background work for fast MoviePilot event callbacks."""

import threading
import time


class CoverEventWorker:
    def __init__(self, handler, on_error):
        self._handler = handler
        self._on_error = on_error
        self._condition = threading.Condition()
        self._pending = {}
        self._generation = 0
        self._stopped = False
        self._thread = None

    def submit(self, key, payload, delay=0):
        with self._condition:
            if self._stopped:
                return False
            deadline = time.monotonic() + max(0, delay)
            if key in self._pending:
                # A continuous stream must not postpone this update forever.
                deadline = self._pending[key][0]
            self._pending[key] = (deadline, payload)
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run, name="MediaCoverGenerator-events", daemon=True
                )
                self._thread.start()
            self._condition.notify_all()
            return True

    def cancel_pending(self):
        with self._condition:
            count = len(self._pending)
            self._pending.clear()
            self._generation += 1
            self._condition.notify_all()
            return count

    def stop(self, timeout=5):
        with self._condition:
            self._stopped = True
            self._pending.clear()
            self._generation += 1
            self._condition.notify_all()
            thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout)
        return not thread or not thread.is_alive()

    def _cancelled(self, generation):
        with self._condition:
            return self._stopped or generation != self._generation

    def _run(self):
        while True:
            with self._condition:
                while not self._stopped:
                    if not self._pending:
                        self._condition.wait()
                        continue
                    # Gather events dispatched a few milliseconds apart into one
                    # batch, so episodes in the same library share a cover update.
                    wait = min(entry[0] for entry in self._pending.values()) + 0.1 - time.monotonic()
                    if wait > 0:
                        self._condition.wait(wait)
                        continue
                    now = time.monotonic()
                    keys = [key for key, entry in self._pending.items() if entry[0] <= now]
                    batch = [self._pending.pop(key)[1] for key in keys]
                    generation = self._generation
                    break
                else:
                    return
            try:
                self._handler(batch, lambda: self._cancelled(generation))
            except Exception as error:
                self._on_error(error)
