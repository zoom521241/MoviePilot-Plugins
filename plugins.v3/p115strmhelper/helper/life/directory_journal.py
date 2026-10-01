"""Persist interrupted directory transfers independently of the life-event cursor."""

from threading import RLock
from typing import Any, Callable, Dict, List, Set


_JOURNAL_LOCK = RLock()
_EVENT_FIELDS = (
    "file_category",
    "file_id",
    "parent_id",
    "file_name",
    "pick_code",
    "sha1",
    "file_size",
    "update_time",
    "id",
    "type",
)


def _event_snapshot(event: Dict[str, Any]) -> Dict[str, Any]:
    """Copy only the public scalar fields needed to resume a directory."""
    return {
        key: event[key]
        for key in _EVENT_FIELDS
        if key in event
        and (event[key] is None or isinstance(event[key], (str, int, float, bool)))
    }


class DirectoryTransferJournal:
    """Keep interrupted work and accepted file IDs in the plugin data store.

    A completed scan removes its entry. An exhausted scan remains available for
    inspection as ``needs_review`` and is never retried automatically.
    """

    def __init__(self, load: Callable[[], Any], save: Callable[[Dict], None]):
        self._load = load
        self._save = save

    def _read(self) -> Dict[str, Dict[str, Any]]:
        """Read detached, validated entries without retaining storage aliases."""
        data = self._load()
        if not isinstance(data, dict):
            return {}
        entries = {}
        for folder_id, entry in data.items():
            if not isinstance(entry, dict):
                continue
            if not isinstance(entry.get("event"), dict) or not isinstance(
                entry.get("path"), str
            ):
                continue
            if entry.get("state") not in {"active", "interrupted", "needs_review"}:
                continue
            accepted = entry.get("accepted_ids", [])
            if not isinstance(accepted, (list, tuple, set)):
                accepted = []
            entries[str(folder_id)] = {
                "event": _event_snapshot(entry["event"]),
                "path": entry["path"],
                "state": entry["state"],
                "accepted_ids": sorted(
                    {
                        str(file_id)
                        for file_id in accepted
                        if isinstance(file_id, (str, int))
                    }
                ),
            }
        return entries

    def begin(self, folder_id: Any, event: Dict[str, Any], path: str) -> Set[str]:
        """Record work before scanning, preserving accepted IDs on a resume."""
        folder_id = str(folder_id)
        snapshot = _event_snapshot(event)
        with _JOURNAL_LOCK:
            entries = self._read()
            previous = entries.get(folder_id, {})
            accepted = (
                set(previous.get("accepted_ids", []))
                if previous.get("event") == snapshot and previous.get("path") == path
                else set()
            )
            entries[folder_id] = {
                "event": snapshot,
                "path": path,
                "state": "active",
                "accepted_ids": sorted(accepted),
            }
            self._save(entries)
            return accepted

    def record_accepted(self, folder_id: Any, file_id: Any) -> None:
        """Checkpoint an ID only after its transfer submission is accepted."""
        with _JOURNAL_LOCK:
            entries = self._read()
            entry = entries.get(str(folder_id))
            if entry is None:
                return
            accepted = set(entry["accepted_ids"])
            accepted.add(str(file_id))
            entry["accepted_ids"] = sorted(accepted)
            self._save(entries)

    def pause(self, folder_id: Any) -> None:
        """Keep stopped work eligible for the next monitor startup."""
        with _JOURNAL_LOCK:
            entries = self._read()
            entry = entries.get(str(folder_id))
            if entry is None:
                return
            entry["state"] = "interrupted"
            self._save(entries)

    def finish(self, folder_id: Any, complete: bool) -> None:
        """Remove complete work, or retain exhausted work without automatic retry."""
        with _JOURNAL_LOCK:
            entries = self._read()
            folder_id = str(folder_id)
            if folder_id not in entries:
                return
            if complete:
                del entries[folder_id]
            else:
                entries[folder_id]["state"] = "needs_review"
            self._save(entries)

    def pending(self) -> List[Dict[str, Any]]:
        """Return resumable entries; also recover a process exit during a scan."""
        with _JOURNAL_LOCK:
            return [
                {"folder_id": folder_id, **entry}
                for folder_id, entry in self._read().items()
                if entry["state"] in {"active", "interrupted"}
            ]
