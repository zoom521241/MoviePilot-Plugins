"""
资源名称偏好打分
按「原盘不要、优先 4K、优先中文」的口径给候选资源/文件名打分，
供搜索源排序与文件匹配阶段复用。
"""
import re
from typing import Optional

# 完整蓝光镜像（BDMV 目录 / ISO 碟）：不经重封装、体积极大且无法直接作为视频文件入库，排除。
# 注意：REMUX 是无损重封装后的 mkv，属于正常可播放的视频，**不在此列**。
DISC_IMAGE_RE = re.compile(
    r"(\bBDMV\b|\bBDISO\b|\bBD-?ISO\b|完整原盘|蓝光原盘(?!.*REMUX)|未经压缩|Untouched"
    r"|Blu-?ray\s*Disc|全碟|\bISO\b)",
    re.IGNORECASE,
)
# 明确标注为 REMUX 时一律保留（哪怕描述里带「原盘 REMUX」）
_REMUX_RE = re.compile(r"\bREMUX\b", re.IGNORECASE)

# 4K / 2160p
UHD_RE = re.compile(r"(2160[pP]|(?<![0-9])4[kK](?![0-9])|4KUHD|(?<![A-Za-z])UHD(?![A-Za-z]))", re.IGNORECASE)
# 1080p
FHD_RE = re.compile(r"(1080[pP]|\bFHD\b)", re.IGNORECASE)
# 720p 及以下
LOW_RE = re.compile(r"(720[pP]|480[pP]|\bSD\b)", re.IGNORECASE)

# 中文相关标识（字幕/音轨/国配）
CHINESE_RE = re.compile(
    r"(简繁|简中|繁中|中字|中英|中英双字|国语|国配|粤语|双语|中文|CHS|CHT|chs|cht|内封字幕|字幕组)",
    re.IGNORECASE,
)

# 画质特效
EFFECT_RE = re.compile(r"(\bDV\b|DoVi|杜比视界|Dolby\.?Vision|\bHDR10\+?\b|\bHDR\b)", re.IGNORECASE)
# 片源类型
WEB_RE = re.compile(r"(WEB-?DL|WEBRip|WEB)", re.IGNORECASE)
BLURAY_RE = re.compile(r"(BluRay|Blu-?ray|BDRip|BRRip)", re.IGNORECASE)

# 打分权重：4K 最高，中文其次，特效/片源再次
SCORE_UHD = 1000
SCORE_FHD = 600
SCORE_LOW = 200
SCORE_CHINESE = 300
SCORE_EFFECT = 100
SCORE_WEB = 50
SCORE_BLURAY = 40

# 完全无分辨率信息时的兜底分
SCORE_UNKNOWN = 0


def join_names(*names: Optional[str]) -> str:
    """把多个候选文本拼成一个用于匹配的字符串"""
    return " ".join([n for n in names if n]) if names else ""


def is_disc_image(*names: Optional[str]) -> bool:
    """
    是否完整蓝光镜像（BDMV / BDISO / ISO 碟 / 「原盘」描述）

    REMUX 不算镜像——它是无损重封装出的 mkv，按正常视频入库。
    """
    text = join_names(*names)
    if not text:
        return False
    if _REMUX_RE.search(text):
        return False
    return bool(DISC_IMAGE_RE.search(text))


def is_chinese(*names: Optional[str]) -> bool:
    """是否带中文标识（简繁/中字/国语/双语等）"""
    text = join_names(*names)
    if not text:
        return False
    return bool(CHINESE_RE.search(text))


def resolution_of(*names: Optional[str]) -> str:
    """
    从候选文本里判断分辨率档位：4K / 1080p / 720p / unknown

    有明确的 2160p / 1080p / 720p 标注时以标注为准（避免把「4K修复版 1080P」当成 4K），
    只有在没有明确标注时才用 4K / UHD 关键词兜底。
    """
    text = join_names(*names)
    if not text:
        return "unknown"
    if re.search(r"2160[pP]|4KUHD", text) or re.search(r"(?<![A-Za-z])UHD(?![A-Za-z])", text, re.IGNORECASE):
        return "4K"
    if FHD_RE.search(text):
        return "1080p"
    if LOW_RE.search(text):
        return "720p"
    if re.search(r"(?<![0-9])4[kK](?![0-9])", text):
        return "4K"
    return "unknown"


def preference_score(*names: Optional[str]) -> int:
    """
    偏好分数，越高越优先

    打分口径：
      - 4K / 2160p：+1000
      - 1080p：+600，720p 及以下：+200
      - 中文（简繁/中字/国语/双语）：+300
      - DV / HDR：+100
      - WEB-DL：+50，BluRay：+40
    """
    text = join_names(*names)
    if not text:
        return SCORE_UNKNOWN

    score = 0
    resolution = resolution_of(text)
    if resolution == "4K":
        score += SCORE_UHD
    elif resolution == "1080p":
        score += SCORE_FHD
    elif resolution == "720p":
        score += SCORE_LOW

    if CHINESE_RE.search(text):
        score += SCORE_CHINESE
    if EFFECT_RE.search(text):
        score += SCORE_EFFECT
    if WEB_RE.search(text):
        score += SCORE_WEB
    elif BLURAY_RE.search(text):
        score += SCORE_BLURAY

    return score


def describe(*names: Optional[str]) -> str:
    """生成简短的中文描述，便于日志排查"""
    parts = []
    if is_disc_image(*names):
        parts.append("原盘")
    parts.append(resolution_of(*names))
    if is_chinese(*names):
        parts.append("中文")
    text = join_names(*names)
    if EFFECT_RE.search(text):
        parts.append("DV/HDR")
    return "/".join(parts)
