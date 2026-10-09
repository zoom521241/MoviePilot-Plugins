"""Conservative, local-only association of MP evidence with one resource batch.

Searching a title only discovers candidates. A candidate is evidence only when
its source belongs to this batch, its time is credible and media identity does
not conflict. This module never reads the cloud or MoviePilot itself.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, List, Optional

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".ts", ".m2ts", ".mpg", ".mpeg", ".webm", ".iso"}
ARCHIVE_EXTENSIONS = {".rar", ".zip", ".7z", ".001"}
_EXTRA = re.compile(r"(?:^|[ /._-])(?:sample|trailer|extras?|featurettes?)(?:$|[ /._-])|预告|样片|花絮", re.I)
_EPISODE = re.compile(r"(?<![a-z0-9])s(\d{1,2})e(\d{1,3})(?:(?:[-_]e?|\s+e|e)(\d{1,3}))?", re.I)


def classify_optional_media(items: Iterable[Dict[str, Any]], min_media_size_mb: int) -> List[Dict[str, Any]]:
    """按批次固定阈值标记附带小视频；未知大小不忽略，不删除任何文件。"""
    threshold = max(0, int(min_media_size_mb)) * 1024 * 1024
    result = []
    for incoming in items:
        item = dict(incoming)
        name = str(item.get("name") or PurePosixPath(item.get("source_path") or item.get("relative_path") or item.get("path") or "").name)
        size = item.get("size")
        known = not isinstance(size, bool) and (isinstance(size, int) or isinstance(size, str) and bool(re.fullmatch(r"[0-9]+", size.strip())))
        try:
            size = int(size) if known else None
        except (ValueError, OverflowError):
            size = None
        video = PurePosixPath(name).suffix.lower() in VIDEO_EXTENSIONS - {".iso", ".m2ts"}
        if threshold and video and not item.get("is_dir") and size is not None and 0 <= size < threshold:
            item.update(required=False, role="small_video", ignored_reason=f"小于 {min_media_size_mb} MB，作为附带视频", size=size)
        result.append(item)
    return result


def timestamp(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return number if math.isfinite(number) else None
    if not value:
        return None
    raw = str(value).strip()
    try:
        number = float(raw)
        return number if math.isfinite(number) else None
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except (ValueError, OverflowError):
        return None


def normalize_path(value: Any) -> str:
    raw = unicodedata.normalize("NFKC", str(value or "")).replace("\\", "/").strip()
    if not raw or "\x00" in raw:
        return ""
    parts = raw.split("/")
    if ".." in parts:
        return ""
    return "/".join(p for p in parts if p and p != ".") if not raw.startswith("/") else "/" + "/".join(p for p in parts if p and p != ".")


def path_is_within(path: Any, root: Any) -> bool:
    path, root = normalize_path(path), normalize_path(root)
    return bool(path and root and (path == root or path.startswith(root.rstrip("/") + "/")))


def storage_identity(value: Any) -> str:
    raw = str(getattr(value, "value", value) or "").strip().lower()
    return {"115网盘": "115", "p115": "115", "p115disk": "115", "u115": "115", "115网盘plus": "115"}.get(raw, raw)


def _media_type(value: Any) -> str:
    raw = str(getattr(value, "value", value) or "").lower()
    return {"电影": "movie", "电视剧": "tv", "series": "tv", "mediatype.movie": "movie", "mediatype.tv": "tv"}.get(raw, raw)


def _season(value: Dict[str, Any]) -> Optional[int]:
    raw = value.get("season") or value.get("seasons")
    if raw is not None:
        match = re.search(r"\d+", str(raw))
        if match:
            return int(match.group())
    title = str(value.get("title") or "")
    match = re.search(r"(?<![a-z0-9])s(\d{1,2})(?!\d)|season\s*(\d{1,2})|第(\d+)季", title, re.I)
    if match:
        return int(next(g for g in match.groups() if g))
    match = re.search(r"第([零一二三四五六七八九十两]+)季", title)
    if match:
        chars = match.group(1).replace("两", "二")
        digits = "零一二三四五六七八九"
        if "十" in chars:
            left, right = chars.split("十", 1)
            return (digits.index(left) if left else 1) * 10 + (digits.index(right) if right else 0)
        if len(chars) == 1 and chars in digits:
            return digits.index(chars)
    return None


def core_title(value: Any) -> str:
    """Full identity title, never the shortened search keyword."""
    raw = unicodedata.normalize("NFKC", str(value or "")).strip()
    raw = re.split(r"第[零一二三四五六七八九十两\d]+季|(?<![a-z0-9])s\d{1,2}(?!\d)|\bseason\s*\d+", raw, maxsplit=1, flags=re.I)[0]
    raw = re.sub(r"\s*[\[(](?:(?:18|19|20|21)\d{2}|[^\])]*(?:2160p|1080p|720p|4k|中字|字幕|国语|bluray|web-?dl|hevc|h264|h265)[^\])]*)[\])].*$", "", raw, flags=re.I)
    raw = re.sub(r"\s*\(?((?:18|19|20|21)\d{2})\)?\s*$", "", raw)
    return re.sub(r"[\s\-_.·:：!！?？,，/\\|\[\]【】（）()]", "", raw).casefold()


def _year(value: Dict[str, Any]) -> str:
    if value.get("year"):
        return str(value["year"])[:4]
    match = re.search(r"[\[(]((?:18|19|20|21)\d{2})[\])]|\s((?:18|19|20|21)\d{2})$", str(value.get("title") or ""))
    return next((group for group in match.groups() if group), "") if match else ""


def identity_matches(batch: Dict[str, Any], entry: Dict[str, Any]) -> bool:
    """Reject known conflicts and require a complete title or media ID identity."""
    a_id, b_id = str(batch.get("tmdbid") or batch.get("tmdb_id") or ""), str(entry.get("tmdbid") or entry.get("tmdb_id") or "")
    if a_id and b_id and a_id != b_id:
        return False
    a_type, b_type = _media_type(batch.get("type") or batch.get("media_type")), _media_type(entry.get("type") or entry.get("media_type"))
    if a_type and b_type and a_type != b_type:
        return False
    a_year, b_year = _year(batch), _year(entry)
    if a_year and b_year and a_year != b_year:
        return False
    a_season, b_season = _season(batch), _season(entry)
    if a_season is not None and b_season is not None and a_season != b_season:
        return False
    if a_id and b_id:
        return True
    titles = [batch.get("media_title") or batch.get("title"), *(batch.get("aliases") or [])]
    normalized = {core_title(t) for t in titles if core_title(t)}
    if not core_title(entry.get("title")) or core_title(entry.get("title")) not in normalized:
        return False
    # When title is the identity, a supplied year must also be established.
    return not a_year or a_year == b_year


def prepare_manifest(items: Iterable[Dict[str, Any]], complete: bool = False,
                     expected_episodes: Optional[Iterable[int]] = None) -> Dict[str, Any]:
    """Retain required units; ambiguous containers never prove completeness."""
    units, reasons, seen = [], [], set()
    for incoming in items:
        item = dict(incoming)
        path = normalize_path(item.get("source_path") or item.get("path") or item.get("src"))
        name = str(item.get("name") or PurePosixPath(path).name)
        role = str(item.get("role") or "")
        extension = PurePosixPath(name).suffix.lower()
        is_dir = item.get("type") == "dir" or item.get("is_dir") is True or role == "directory"
        if is_dir:
            reasons.append("directory_not_enumerated")
            continue
        if extension in ARCHIVE_EXTENSIONS or extension == ".iso" or "/bdmv/" in path.lower() or (extension == ".m2ts" and not role):
            reasons.append("ambiguous_media_container")
        if not path:
            reasons.append("missing_source_path")
            continue
        required = item.get("required")
        if required is None:
            required = extension in VIDEO_EXTENSIONS and not _EXTRA.search(path)
        if not role:
            role = "extra" if _EXTRA.search(path) else "media" if required else "attachment"
        match = _EPISODE.search(name)
        if match:
            item.setdefault("season", int(match.group(1)))
            first, last = int(match.group(2)), int(match.group(3) or match.group(2))
            if last < first or last - first > 10:
                reasons.append("ambiguous_episode_range")
            else:
                item.setdefault("episodes", list(range(first, last + 1)))
                if required:
                    role = "episode"
        file_id = str(item.get("file_id") or item.get("fileid") or "")
        storage = storage_identity(item.get("storage") or item.get("source_storage"))
        key = str(item.get("unit_key") or hashlib.sha256(f"{storage}|{path}|{file_id}".encode()).hexdigest())
        if key in seen:
            continue
        seen.add(key)
        item.update(source_path=path, storage=storage, file_id=file_id, unit_key=key, role=role, required=bool(required))
        units.append(item)
    required_units = [u for u in units if u["required"]]
    if not required_units:
        reasons.append("empty_required_manifest")
    if expected_episodes is not None:
        expected = {int(e) for e in expected_episodes}
        actual = {int(e) for u in required_units for e in (u.get("episodes") or [])}
        if not expected.issubset(actual):
            reasons.append("expected_episode_missing")
    return {"items": units, "complete": bool(complete and not reasons), "reason": ",".join(dict.fromkeys(reasons))}


def _source(entry: Dict[str, Any]) -> Dict[str, str]:
    source = entry.get("src_fileitem") or entry.get("fileitem") or {}
    if not isinstance(source, dict):
        source = vars(source) if hasattr(source, "__dict__") else {}
    return {"path": normalize_path(source.get("path") or entry.get("src") or entry.get("source_path")),
            "storage": storage_identity(source.get("storage") or entry.get("src_storage") or entry.get("storage")),
            "file_id": str(source.get("fileid") or source.get("file_id") or entry.get("source_file_id") or "")}


def _entry_time(entry: Dict[str, Any]) -> Optional[float]:
    for key in ("completed_at", "updated_at", "date", "created_at", "timestamp", "time"):
        stamp = timestamp(entry.get(key))
        if stamp is not None:
            return stamp
    return None


def history_matches(batch: Dict[str, Any], entry: Dict[str, Any], unit: Optional[Dict[str, Any]] = None) -> bool:
    if not identity_matches(batch, entry):
        return False
    history_id = str(entry.get("id") or entry.get("history_id") or "")
    linked = history_id and history_id in {str(h) for h in batch.get("mp_history_ids", [])}
    source = _source(entry)
    started = timestamp(batch.get("evidence_started_at") or batch.get("created_ts") or batch.get("created_at") or batch.get("submitted_at"))
    observed = _entry_time(entry)
    if started is not None and observed is not None and observed < started:
        return False
    if not linked and (started is None or observed is None):
        return False
    wanted_storage = storage_identity((unit or {}).get("storage") or batch.get("source_storage") or batch.get("final_storage") or batch.get("storage"))
    if wanted_storage and source["storage"] and wanted_storage != source["storage"]:
        return False
    if not linked and (not wanted_storage or not source["storage"]):
        return False
    if unit:
        path = normalize_path(unit.get("source_path") or unit.get("path"))
        fid = str(unit.get("file_id") or unit.get("fileid") or "")
        if fid and source["file_id"] and fid != source["file_id"]:
            return False
        # An unchanged exact ID is useful, but never licenses a different path.
        if path and source["path"] and path != source["path"]:
            return False
        exact_path = bool(path and source["path"] == path)
        exact_id = bool(fid and source["file_id"] == fid and wanted_storage and wanted_storage == source["storage"])
        unit_linked = history_id and history_id in {str(h) for h in [*(unit.get("mp_history_ids") or []), unit.get("history_id")] if h}
        # A batch-level history ID identifies one history action, never every
        # file in a season. Without file identity it cannot fan out to all units.
        return bool(exact_path or exact_id or unit_linked)
    roots = list(batch.get("source_roots") or [])
    final = normalize_path(batch.get("final_path"))
    names = batch.get("item_names") or ([batch["item_name"]] if batch.get("item_name") else [])
    roots.extend(final.rstrip("/") + "/" + str(name) for name in names if final and name)
    return bool(linked or any(path_is_within(source["path"], root) for root in roots))


def match_history(batch: Dict[str, Any], entries: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    matched, seen = [], set()
    manifest = batch.get("manifest") or batch.get("manifest_items") or []
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        entry = dict(raw)
        units = [unit for unit in manifest if unit.get("required", True) and history_matches(batch, entry, unit)]
        if manifest and not units:
            continue
        if not manifest and not history_matches(batch, entry):
            continue
        key = str(entry.get("id") or entry.get("history_id") or hashlib.sha256(json.dumps(entry, sort_keys=True, default=str).encode()).hexdigest())
        if key in seen:
            continue
        seen.add(key)
        entry["evidence_key"] = key
        entry["unit_keys"] = [unit["unit_key"] for unit in units]
        entry["evidence_at"] = _entry_time(entry)
        matched.append(entry)
    return matched


def summarize(manifest: Iterable[Dict[str, Any]], evidence: Iterable[Dict[str, Any]],
              complete: bool = False, pagination_complete: bool = False) -> Dict[str, Any]:
    required = {str(u["unit_key"]): u for u in manifest if u.get("required", True)}
    latest: Dict[str, Dict[str, Any]] = {}
    for entry in evidence:
        if not isinstance(entry.get("status"), bool):
            continue
        for key in entry.get("unit_keys") or []:
            if key not in required:
                continue
            previous = latest.get(key)
            if previous and previous.get("status") is True and entry.get("status") is False and entry.get("time_is_observed"):
                continue
            if previous and previous.get("status") is False and previous.get("time_is_observed") and entry.get("status") is True:
                latest[key] = entry
                continue
            # Exact same time prefers success: duplicated/late failure cannot
            # erase a known completed action. A newer real failure is retained.
            rank = (timestamp(entry.get("evidence_at")) or 0, bool(entry["status"]))
            previous_rank = (timestamp(previous.get("evidence_at")) or 0, bool(previous["status"])) if previous else (-1, False)
            if rank >= previous_rank:
                latest[key] = entry
    successful = sum(e["status"] is True for e in latest.values())
    failed = sum(e["status"] is False for e in latest.values())
    missing = len(required) - len(latest)
    proven_complete = bool(complete and required)
    if proven_complete and successful == len(required):
        state = "success"
    elif successful:
        state = "partial"
    elif failed and proven_complete and not missing:
        state = "failed"
    else:
        state = "unknown"
    return {"organization_status": state, "organization_confirmed": state == "success",
            "organized_count": successful, "organized_failed": failed,
            "organized_missing": missing if proven_complete else None,
            "organized_total": len(required) if proven_complete else None,
            "manifest_complete": proven_complete, "history_complete": bool(pagination_complete),
            "organization_evidence": list(latest.values())}
