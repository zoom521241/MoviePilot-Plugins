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
    raw = str(getattr(value, "value", value) or "").strip().lower()
    mapped = {"电影": "movie", "电视剧": "tv", "series": "tv", "mediatype.movie": "movie", "mediatype.tv": "tv"}.get(raw, raw)
    # 「未知」不是一种类型：文档没标类型的批次（type=unknown）不能与 MP 识别出的电影/剧集构成冲突
    return "" if mapped in ("unknown", "未知", "mediatype.unknown", "none") else mapped


_PATH_MEDIA = (("电视剧", "tv"), ("剧集", "tv"), ("电视节目", "tv"), ("电影", "movie"))


def media_type_from_path(value: Any) -> str:
    """从 MP 整理记录的目标路径推断类型（``/…/电影/…`` 或 ``/…/电视剧/…``）。

    「电视剧」先于「电影」判断：不依赖分词，只要求 ``/类型词`` 出现在路径里，
    所以 ``/115-links/电视剧/欧美剧/…`` 不会因为「电影」二字被判成电影。
    """
    raw = unicodedata.normalize("NFKC", str(value or ""))
    for token, kind in _PATH_MEDIA:
        if "/" + token in raw:
            return kind
    return ""


def media_bucket(item: Any) -> str:
    """把一个批次行归一化为 ``'movie'`` / ``'tv'`` / ``''``（空串＝类型待确认）。

    这是全插件**唯一**的媒体类型判定口径：统计条、任务列表筛选、SQLite 派生列
    与身份匹配全部走它，避免同一条规则多处实现后互相打架。回落顺序：

    1. ``mp_media_type``：MoviePilot 整理记录给出的权威类型（最可信）；
    2. ``type`` / ``media_type``：文档索引当时判定出来的类型；
    3. ``target_type``：用户提交时选择的下载目录。

    ⚠️ ``unknown`` / ``未知`` 是**占位符而不是一种类型**：它必须被当作「没有」
    继续往后回落。曾经的实现写成 ``type or target_type``，于是 ``type='unknown'``
    这个真值把后面的 ``target_type='movie'`` 整个挡住，电影/电视剧两边都不统计。
    """
    if not isinstance(item, dict):
        return ""
    for field in ("mp_media_type", "type", "media_type", "target_type"):
        kind = _media_type(item.get(field))
        if kind in ("movie", "tv"):
            return kind
    return ""


def observed_media_type(entries: Iterable[Dict[str, Any]]) -> str:
    """从 MP 整理记录里提取**权威**媒体类型；没有可判定证据时返回空串。

    只认 ``status is True`` 的成功记录——失败记录不能作为类型依据（例如 MP 会把
    附带的推广小文件单独判成「未知」）。优先用记录自带的 ``type``，缺失时退到
    ``dest`` 目标路径。证据互相矛盾（两种类型票数相同）时返回空串，宁可回落到
    文档/目录判断，也不写一个可能错的「权威」值。
    """
    votes: Dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("status") is not True:
            continue
        kind = _media_type(entry.get("type") or entry.get("media_type")) or media_type_from_path(entry.get("dest"))
        if kind in ("movie", "tv"):
            votes[kind] = votes.get(kind, 0) + 1
    if not votes:
        return ""
    if len(votes) == 1:
        return next(iter(votes))
    top = max(votes.values())
    winners = [kind for kind, count in votes.items() if count == top]
    return winners[0] if len(winners) == 1 else ""


def _batch_type(batch: Dict[str, Any]) -> str:
    """批次类型：与 :func:`media_bucket` 同一口径（MP 权威 > 文档 > 用户选的目录）。"""
    return media_bucket(batch)


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


def legacy_title_key(value: Any) -> str:
    """旧记录回退用片名键：去掉所有括号标签、季号、年份与发布标签后再比较。

    文档标题常带「[60帧率版本][高码版][国语配音+中文字幕].Pegasus.2019.2160p…」这类标签，
    直接比较会与 MP 整理记录里的简短片名对不上；而"飞驰人生"与"飞驰人生3"去掉标签后仍不等，避免误配。
    """
    raw = unicodedata.normalize("NFKC", str(value or ""))
    raw = re.sub(r"[\[(（【][^\])）】]*[\])）】]", " ", raw)                      # 括号标签
    raw = re.sub(r"(?<![a-z0-9])s\d{1,2}(?!\d)|\bseason\s*\d+|第[零一二三四五六七八九十两\d]+季", " ", raw, flags=re.I)
    raw = re.split(r"(?:18|19|20|21)\d{2}", raw, maxsplit=1)[0]                    # 年份及其后
    raw = re.split(r"[.\-_]", raw, maxsplit=1)[0]                                  # 点/横线后的发布信息
    return re.sub(r"[\s\-_.·:：!！?？,，/\\|]", "", raw).casefold()


def legacy_identity(batch: Dict[str, Any], entry: Dict[str, Any]) -> bool:
    """旧版本（无本批清单）记录的回退身份匹配：类型/季号不冲突，且去标签片名相等。"""
    a_id, b_id = str(batch.get("tmdbid") or batch.get("tmdb_id") or ""), str(entry.get("tmdbid") or entry.get("tmdb_id") or "")
    if a_id and b_id and a_id != b_id:
        return False
    a_type = _batch_type(batch)
    b_type = _media_type(entry.get("type") or entry.get("media_type"))
    if a_type and b_type and a_type != b_type:
        return False
    a_season, b_season = _season(batch), _season(entry)
    if a_season is not None and b_season is not None and a_season != b_season:
        return False
    a, b = legacy_title_key(batch.get("title")), legacy_title_key(entry.get("title"))
    return bool(a and b and a == b)


def identity_matches(batch: Dict[str, Any], entry: Dict[str, Any]) -> bool:
    """Reject known conflicts and require a complete title or media ID identity."""
    a_id, b_id = str(batch.get("tmdbid") or batch.get("tmdb_id") or ""), str(entry.get("tmdbid") or entry.get("tmdb_id") or "")
    if a_id and b_id and a_id != b_id:
        return False
    a_type, b_type = _batch_type(batch), _media_type(entry.get("type") or entry.get("media_type"))
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
    # 年份只在双方都给出时才要求一致（上面已拒绝冲突年份）；
    # MP 的整理记录经常不带年份，若要求"条目必须有年份"会漏判，这里不再额外要求。
    return True


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
    """MP 的一条整理记录能否证明「本批次 / 本单元」已整理。

    带逐文件单元（manifest）时，**只认逐文件身份**，批次级的标题/年份/类型/季号启发式不能否决它：

    一条 MP 记录对应一个整理动作，文件是否真的被搬走过，只能由「这个文件」本身证明 ——
    115 文件 ID + 存储一致，或 NFKC 归一化后源路径 + 存储一致（`exact_path` / `exact_id`）。
    批次级元数据（整包标题、`extract_year` 取得的年份）在合集类批次上必然对不上：
    例如「…[共3部合集]…2005-2012」整包会被 MP 拆成若干部各自命名的记录，
    批次标题永远不等于任何一条记录标题，批次年份还会被取成区间末位（2012）；
    若先拿这些元数据当硬门槛，整包的必要文件会全部判成「无证据」。
    反过来，批次级身份是「整批一个动作」的粒度，也**不能**摊到每个文件上
    （否则一季 20 集会被同一条记录一次性确认），所以这里不回落批次级启发式。

    不带单元（旧记录 / 无清单）时才用批次级身份：标题、年份、类型、季号、根路径。
    """
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
        # 单元级只认逐文件身份（或该单元自己的历史记录 id）：一条 MP 记录对应一个动作，
        # 批次级标题/年份身份是「整批」粒度，摊到每个文件会把一季的所有集一起误判。
        if not (exact_path or exact_id or unit_linked):
            return False
        # 逐文件身份成立，即证明「这个文件」确实被 MP 搬走过；年份/类型/季号/标题都是批次级
        # 启发式，在合集/整包场景下必然对不上，不能用来否决既成事实。
        # TMDB ID 是标识符而非启发式：双方都给出且冲突时说明不是同一部媒体，仍然拒绝。
        a_id = str(batch.get("tmdbid") or batch.get("tmdb_id") or "")
        b_id = str(entry.get("tmdbid") or entry.get("tmdb_id") or "")
        return not (a_id and b_id and a_id != b_id)
    if not identity_matches(batch, entry):
        return False
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
