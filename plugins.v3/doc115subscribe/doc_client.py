"""腾讯文档（docs.qq.com）在线表格读取客户端。

读取原理
--------
腾讯文档的在线表格在浏览器里是 canvas 渲染的，DOM 里拿不到单元格；
但只要**调文档前端自身的 dop-api 接口**，就能取到单元格原始数据块
（`related_sheet` = base64(zlib(protobuf))），从而在**不需要「导出/下载」权限**、
也不需要浏览器的情况下完整读取表格内容。

本模块只依赖 Python 标准库。
"""
from __future__ import annotations

import base64
import re
import struct
import urllib.parse
import urllib.request
import zlib
from typing import Any, Dict, List, Optional, Tuple

API = "https://docs.qq.com/dop-api/opendoc"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
# 单次请求最多拉取的行数（分页粒度）
CHUNK_ROWS = 512
# 数据块里“主数据段”的最小长度，用于在一堆 f5 里挑出真正的主段
POOL_MIN_LEN = 10000


class DocError(RuntimeError):
    """文档读取失败，附带可读原因。"""


# ---------------------------------------------------------------------------
# protobuf 基础：没有 schema，按 wire format 盲扫
# ---------------------------------------------------------------------------
def _pb_varint(buf: bytes, i: int) -> Tuple[Optional[int], int]:
    shift = result = 0
    while i < len(buf):
        byte = buf[i]
        i += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, i
        shift += 7
        if shift > 63:
            return None, i
    return None, i


def pb_fields(buf: bytes) -> List[Tuple[int, str, Any]]:
    """把字节切成 [(field_number, kind, value)]，kind ∈ v/l/f32/f64。"""
    out: List[Tuple[int, str, Any]] = []
    i = 0
    while i < len(buf):
        key, i = _pb_varint(buf, i)
        if key is None:
            return out
        field, wire = key >> 3, key & 7
        if field == 0 or wire not in (0, 1, 2, 5):
            return out
        if wire == 0:
            value, i = _pb_varint(buf, i)
            out.append((field, "v", value))
        elif wire == 2:
            length, i = _pb_varint(buf, i)
            if length is None or i + length > len(buf):
                return out
            out.append((field, "l", buf[i:i + length]))
            i += length
        elif wire == 5:
            if i + 4 > len(buf):
                return out
            out.append((field, "f32", struct.unpack("<f", buf[i:i + 4])[0]))
            i += 4
        else:
            if i + 8 > len(buf):
                return out
            out.append((field, "f64", struct.unpack("<d", buf[i:i + 8])[0]))
            i += 8
    return out


def pb_msg(buf: bytes, field: int, minlen: int = 0) -> Optional[bytes]:
    for num, kind, value in pb_fields(buf):
        if num == field and kind == "l" and len(value) >= minlen:
            return value
    return None


def _utf8(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return ""


# ---------------------------------------------------------------------------
# 值池解析
# ---------------------------------------------------------------------------
def _pool_text(inner: bytes) -> str:
    """纯文本池条目：f1 -> f1 = utf8"""
    for field, kind, value in pb_fields(inner):
        if field == 1 and kind == "l":
            return _utf8(value)
    return ""


def _extract_rich(inner: bytes) -> Tuple[str, Optional[str]]:
    """富文本池条目 -> (显示文本, 超链接 URL)。

    文本在 ``f3 -> f2 -> f3 -> f1``；
    超链接在 ``f3 -> f7 -> f11 -> f1``（剧集表里显示为「点击转存」的单元格就是这个）。
    注意：不能把整段可读字符串拼起来再清洗，否则会把正文首字符一起删掉。
    """
    texts: List[str] = []
    hrefs: List[str] = []
    for field, kind, value in pb_fields(inner):
        if field != 3 or kind != "l":
            continue
        for f2, k2, v2 in pb_fields(value):
            if f2 == 3 and k2 == "l":
                for f3, k3, v3 in pb_fields(v2):
                    if f3 == 1 and k3 == "l":
                        texts.append(_utf8(v3))
            elif f2 == 7 and k2 == "l":
                for f3, k3, v3 in pb_fields(v2):
                    if f3 == 11 and k3 == "l":
                        for f4, k4, v4 in pb_fields(v3):
                            if f4 == 1 and k4 == "l":
                                s = _utf8(v4).strip()
                                if s.lower().startswith(("http://", "https://", "magnet:?", "ed2k://")):
                                    hrefs.append(s)
    return "".join(texts), (hrefs[0] if hrefs else None)


def _decode_block(related_b64: str) -> Tuple[List[Tuple[int, int, int, int]], List[str],
                                             List[Tuple[str, Optional[str]]], List[Any]]:
    """解开一个数据块 -> (cells[(row,col,tp,idx)], texts, rich[(text,href)], nums)"""
    raw = zlib.decompress(base64.b64decode(related_b64))
    top = pb_msg(raw, 1)
    if top is None:
        raise DocError("数据块结构不符预期")
    # f5 里也有图像/样式等大段，不能仅按第一个达到长度阈值的段判断。
    # 逐个验证 f19 + 值池结构，也兼容不足阈值的小表。
    candidates = sorted((value for field, kind, value in pb_fields(top)
                         if field == 5 and kind == "l"), key=len, reverse=True)
    if not candidates:
        raise DocError("数据块里找不到主数据段（空表或接口已变更）")
    node = next((segment for candidate in candidates
                 if (segment := pb_msg(candidate, 19)) is not None and pb_msg(segment, 5) is not None), None)
    if node is None:
        raise DocError("数据块里找不到 f19 段（接口可能已变更）")

    fields = pb_fields(node)
    pool = None
    for field, kind, value in fields:
        if field == 5 and kind == "l":
            pool = value
            break
    if pool is None:
        raise DocError("数据块里找不到值池（接口可能已变更）")

    texts: List[str] = []
    rich: List[Tuple[str, Optional[str]]] = []
    nums: List[Any] = []
    i = 0
    while i < len(pool):
        key, i = _pb_varint(pool, i)
        if key is None:
            break
        field, wire = key >> 3, key & 7
        if field == 0 or wire not in (0, 1, 2, 5):
            break
        if wire == 2:
            length, i = _pb_varint(pool, i)
            if length is None or i + length > len(pool):
                break
            inner = pool[i:i + length]
            i += length
            if field == 1:
                texts.append(_pool_text(inner))
            elif field == 2:
                rich.append(_extract_rich(inner))
            elif field == 3:
                sub = pb_fields(inner)
                nums.append(sub[0][2] if sub else None)
        elif wire == 0:
            _, i = _pb_varint(pool, i)
        elif wire == 5:
            i += 4
        else:
            i += 8

    cells: List[Tuple[int, int, int, int]] = []
    for cell in [v for f, k, v in fields if f == 6 and k == "l"]:
        row = col = 0
        tp = idx = None
        for f2, k2, v2 in pb_fields(cell):
            if f2 == 1 and k2 == "v":
                row = v2
            elif f2 == 2 and k2 == "v":
                col = v2
            elif f2 == 3 and k2 == "l":
                for f3, k3, v3 in pb_fields(v2):
                    if f3 == 1 and k3 == "v":
                        tp = v3
                    elif f3 == 2 and k3 == "l":
                        sub = pb_fields(v3)
                        idx = 0 if not sub else sub[0][2]
        cells.append((row, col, tp, idx))
    return cells, texts, rich, nums


def _cell_value(tp: Optional[int], idx: Optional[int], texts: List[str],
                rich: List[Tuple[str, Optional[str]]], nums: List[Any]) -> Optional[str]:
    """按值类型还原单元格文本；None 表示该格无内容。"""
    if idx is None:
        return None
    if tp == 4:
        return texts[idx] if 0 <= idx < len(texts) else None
    if tp == 6:
        return rich[idx][0] if 0 <= idx < len(rich) else None
    if tp == 2:
        if idx < 129:
            value: Any = idx
        else:
            pos = idx - 129
            if pos >= len(nums) or nums[pos] is None:
                return None
            value = nums[pos]
        if isinstance(value, float) and value == int(value):
            return str(int(value))
        return str(value)
    if tp == 5:
        return str(idx + 1)
    return None


def _cell_href(tp: Optional[int], idx: Optional[int],
               rich: List[Tuple[str, Optional[str]]]) -> Optional[str]:
    if tp == 6 and idx is not None and 0 <= idx < len(rich):
        return rich[idx][1]
    return None


# ---------------------------------------------------------------------------
# 客户端
# ---------------------------------------------------------------------------
class TencentDocsClient:
    """腾讯文档在线表格读取客户端。"""

    def __init__(self, doc_id: str, cookie: str = "", timeout: int = 40):
        self.doc_id = doc_id
        self.cookie = (cookie or "").strip()
        self.timeout = timeout

    # -- 工具 -----------------------------------------------------------------
    @staticmethod
    def parse_doc_id(url_or_id: str) -> Tuple[str, Optional[str]]:
        """从分享链接或裸 ID 解析 (doc_id, tab_id)。"""
        text = (url_or_id or "").strip()
        if "://" in text:
            try:
                parsed = urllib.parse.urlsplit(text)
                valid_host = (parsed.scheme.lower() in ("http", "https")
                              and parsed.hostname == "docs.qq.com"
                              and not parsed.username and not parsed.password
                              and parsed.port in (None, 80, 443))
            except ValueError:
                valid_host = False
            if not valid_host:
                raise DocError("只支持 docs.qq.com/sheet/ 链接")
            m = re.fullmatch(r"/sheet/([A-Za-z0-9]+)/?", parsed.path)
            if not m:
                raise DocError("只支持 docs.qq.com/sheet/ 链接")
            q = urllib.parse.parse_qs(parsed.query)
            return m.group(1), (q.get("tab") or [None])[0]
        if not re.fullmatch(r"[A-Za-z0-9]+", text):
            raise DocError("文档 ID 无效，请填写 docs.qq.com/sheet/ 分享链接或文档 ID")
        return text, None

    def _fetch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{API}?{query}",
            headers={
                "User-Agent": UA,
                "Referer": f"https://docs.qq.com/sheet/{self.doc_id}",
                "Cookie": self.cookie,
            },
        )
        try:
            body = urllib.request.urlopen(req, timeout=self.timeout).read()
        except Exception as exc:  # noqa: BLE001
            raise DocError(f"请求文档失败：{exc}") from exc
        raw = body.decode("utf-8", "replace")
        m = re.match(r"^[^(]*\((.*)\)\s*$", raw, re.S)
        if not m:
            raise DocError("返回不是预期的 JSONP（文档不可访问 / ID 不对 / 接口已变更）")
        import json
        try:
            payload = json.loads(m.group(1))
        except ValueError as exc:
            raise DocError(f"JSONP 解析失败：{exc}") from exc
        cv = payload.get("clientVars", {})
        if not cv.get("isLogin", False) and not cv.get("collab_client_vars", {}).get(
            "initialAttributedText"
        ):
            # 未登录时接口会返回 isLogin=false 且无内容
            pass
        return payload

    def _opendoc_raw(self, tab: Optional[str], start_row: int = 0, end_row: int = 0,
                     end_col: int = 63) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """返回 (collab_client_vars, sheet_info)。

        ``sheet_info`` 即 ``initialAttributedText.text[0]``，数据块
        (``block_datas``) 与行列表头 (``max_row`` / ``max_col``) 都在这里面。
        """
        params = {
            "tab": tab or "",
            "id": self.doc_id,
            "u": "",
            "noEscape": 1,
            "enableSmartsheetSplit": 1,
            "needSheetState": 1,
            "sliceStates": 1,
            "block_start_col": 0,
            "block_start_row": start_row,
            "block_end_col": end_col,
            "block_end_row": end_row,
            "startrow": 0,
            "endrow": 1000,
            "normal": 1,
            "outformat": 1,
            "wb": 1,
            "nowb": 0,
            "callback": "clientVarsCallback",
            "xsrf": "",
        }
        payload = self._fetch(params)
        ccv = payload.get("clientVars", {}).get("collab_client_vars", {}) or {}
        text_list = (ccv.get("initialAttributedText") or {}).get("text") or []
        info = text_list[0] if text_list and isinstance(text_list[0], dict) else {}
        return ccv, info

    def _ccv(self, tab: Optional[str] = None) -> Dict[str, Any]:
        return self._opendoc_raw(tab)[0]

    # -- 对外接口 -------------------------------------------------------------
    def login_ok(self) -> bool:
        """判断 Cookie 是否有效（能读到文档）。"""
        try:
            ccv = self._ccv(None)
        except DocError:
            return False
        return bool(ccv.get("header") or ccv.get("globalPadId"))

    def fetch_sheet_list(self) -> List[Dict[str, Any]]:
        """列出所有工作表 -> [{"id", "name"}]"""
        ccv = self._ccv(None)
        header = ccv.get("header") or []
        if not header:
            raise DocError("返回里没有 header，无法枚举工作表（Cookie 可能已失效）")
        sheets: List[Dict[str, Any]] = []
        for item in header[0].get("d", []) or []:
            sid = item.get("id")
            if sid:
                sheets.append({"id": sid, "name": item.get("name") or sid})
        return sheets

    def fetch_sheet(self, tab_id: str) -> Dict[str, Any]:
        """读取整张工作表 -> {"grid": [[str]], "hrefs": [[str|None]], "meta": {...}}"""
        _, probe = self._opendoc_raw(tab_id, 0, 0)
        max_row = probe.get("max_row")
        max_col = probe.get("max_col")
        if not isinstance(max_row, int) or max_row <= 0:
            raise DocError("没拿到有效行数（表可能为空，或接口已变更）")

        grid: Dict[Tuple[int, int], str] = {}
        hrefs: Dict[Tuple[int, int], str] = {}
        done = set()
        start = 0
        while start < max_row:
            end = min(start + CHUNK_ROWS - 1, max_row - 1)
            _, info = self._opendoc_raw(tab_id, start, end, (max_col or 0) + 1)
            blocks = info.get("block_datas") or []
            for block in blocks:
                rel = block.get("related_sheet")
                if not rel:
                    continue
                cells, texts, rich, nums = _decode_block(rel)
                for row, col, tp, idx in cells:
                    key = (row, col)
                    if key in done:
                        continue
                    done.add(key)
                    value = _cell_value(tp, idx, texts, rich, nums)
                    if value is not None:
                        grid[key] = value
                    href = _cell_href(tp, idx, rich)
                    if href:
                        hrefs[key] = href
            start = end + 1

        if not grid and not hrefs:
            return {"grid": [], "hrefs": [], "meta": {"max_row": max_row, "max_col": max_col}}

        nrow = max(r for r, _ in list(grid) + list(hrefs)) + 1
        ncol = max(c for _, c in list(grid) + list(hrefs)) + 1
        g = [["" for _ in range(ncol)] for _ in range(nrow)]
        h = [[None for _ in range(ncol)] for _ in range(nrow)]
        for (row, col), value in grid.items():
            g[row][col] = value
        for (row, col), value in hrefs.items():
            h[row][col] = value
        return {"grid": g, "hrefs": h,
                "meta": {"max_row": max_row, "max_col": max_col, "cells": len(grid)}}
