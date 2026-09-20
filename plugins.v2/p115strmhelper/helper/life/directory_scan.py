"""Bounded collection of eventually consistent directory listings.

The caller supplies a fresh iterator of validated, eligible files for every
pass, and is responsible for bounding individual network requests. The elapsed
budget here is a soft limit: it cannot interrupt a blocking iterator operation.
"""

from dataclasses import dataclass
from math import isfinite
from threading import Event
from time import monotonic as _monotonic
from typing import Callable, Iterable, Optional


@dataclass
class DirectorySnapshot:
    """Union of valid observations, with the final collection status.

    ``errors`` counts failed passes, including failures after partial results.
    ``reason`` is ``stable``, ``stopped``, ``max_rounds``, or ``max_elapsed``;
    progress callbacks may also receive ``observing`` between passes.
    """

    items: list[dict]
    stable: bool
    stopped: bool
    rounds: int
    errors: int
    reason: str


def _fingerprint(item: dict) -> tuple:
    """Only downstream-relevant fields affect agreement between passes."""
    return (
        str(item["id"]),
        item["path"],
        str(item["parent_id"]),
        item["size"],
        item["sha1"],
        item["pickcode"],
    )


def collect_directory_snapshot(
    scan: Callable[[], Iterable[dict]],
    *,
    stop_event: Optional[Event] = None,
    interval: float = 10.0,
    min_observation: float = 30.0,
    max_rounds: int = 6,
    max_elapsed: float = 120.0,
    monotonic: Callable[[], float] = _monotonic,
    on_round: Optional[Callable[[DirectorySnapshot], None]] = None,
) -> DirectorySnapshot:
    """Merge bounded scans and wait for two unchanged successful comparisons.

    Stability also requires ``min_observation`` seconds since collection began.
    Empty scans have the same requirements as nonempty scans. A failed pass
    retains its validated files, but clears all stability evidence. File IDs
    are compared as strings and later observations update earlier fields.

    ``on_round`` receives a detached snapshot after each attempted pass. It is
    intended for progress reporting; callback exceptions propagate to callers.
    """
    for name, value in (
        ("interval", interval),
        ("min_observation", min_observation),
        ("max_elapsed", max_elapsed),
    ):
        if not isfinite(value) or value < 0:
            raise ValueError(f"{name} must be finite and nonnegative")
    if not isinstance(max_rounds, int) or max_rounds < 0:
        raise ValueError("max_rounds must be a nonnegative integer")

    event = stop_event if stop_event is not None else Event()
    started = monotonic()
    collected: dict[str, dict] = {}
    previous: Optional[dict[str, tuple]] = None
    unchanged = 0
    rounds = 0
    errors = 0

    def snapshot(reason: str) -> DirectorySnapshot:
        return DirectorySnapshot(
            items=[dict(item) for item in collected.values()],
            stable=reason == "stable",
            stopped=reason == "stopped",
            rounds=rounds,
            errors=errors,
            reason=reason,
        )

    while True:
        if event.is_set():
            return snapshot("stopped")
        if monotonic() - started >= max_elapsed:
            return snapshot("max_elapsed")
        if rounds >= max_rounds:
            return snapshot("max_rounds")

        rounds += 1
        current: dict[str, tuple] = {}
        iterator = None
        complete = False
        failed = False
        try:
            iterator = iter(scan())
            while not event.is_set() and monotonic() - started < max_elapsed:
                try:
                    item = next(iterator)
                except StopIteration:
                    complete = True
                    break
                # Validation is the caller's responsibility. Fingerprinting
                # before merging also prevents incomplete records entering
                # the union if a caller accidentally omits a required field.
                fingerprint = _fingerprint(item)
                file_id = str(item["id"])
                current[file_id] = fingerprint
                collected.setdefault(file_id, {}).update(item)
        except Exception:
            failed = True
        finally:
            close = getattr(iterator, "close", None)
            if close is not None:
                try:
                    close()
                except Exception:
                    failed = True

        if failed:
            errors += 1
        if complete and not failed:
            unchanged = unchanged + 1 if current == previous else 0
            previous = current
        else:
            unchanged = 0
            previous = None

        elapsed = monotonic() - started
        if event.is_set():
            reason = "stopped"
        elif elapsed >= max_elapsed:
            reason = "max_elapsed"
        elif unchanged >= 2 and elapsed >= min_observation:
            reason = "stable"
        elif rounds >= max_rounds:
            reason = "max_rounds"
        else:
            reason = "observing"

        if on_round is not None:
            on_round(snapshot(reason))
        if reason != "observing":
            return snapshot(reason)

        remaining = max_elapsed - (monotonic() - started)
        if remaining > 0:
            event.wait(min(interval, remaining))
