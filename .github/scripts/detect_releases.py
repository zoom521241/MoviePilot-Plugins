#!/usr/bin/env python3
"""
检测需要在 GitHub Releases 发布的插件。

规则（确定性、无需 diff 分析）：
  - 扫描 package.v2.json / package.v3.json 中所有 release=true 的插件；
  - 插件 ID 与源码目录按「小写同名」约定映射（Doc911Subscribe -> doc911subscribe）；
  - 以 <PluginId>_v<Version> 作为 tag；
  - 仓库里 tag 不存在的插件 = 需要发布（版本号已变更自然会产生新 tag）。
    因此「只改源码不改版本号」不会产生重复发布，而是等你显式升版本号。

输出：写入 GITHUB_OUTPUT 的 matrix=<json array>
"""
import json
import os
import subprocess
import sys

MANIFESTS = [
    ("package.v2.json", "plugins.v2"),
    ("package.v3.json", "plugins.v3"),
]


def log(msg):
    """日志走 stderr，stdout 只留给矩阵 JSON。"""
    print(msg, file=sys.stderr)


def existing_tags():
    """列出远端已有 tag。"""
    try:
        out = subprocess.run(
            ["git", "ls-remote", "--tags", "origin"],
            capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        log(f"[warn] 无法读取远端 tag：{exc}")
        return set()
    tags = set()
    for line in out.splitlines():
        if "refs/tags/" in line:
            ref = line.split("refs/tags/", 1)[1]
            # ^{} 解引用后的同名 object 记录
            tags.add(ref.rstrip("^{}").strip())
    return tags


def history_notes(plugin: dict, version: str) -> str:
    """取该版本对应的更新说明。"""
    history = plugin.get("history") or {}
    if isinstance(history, dict):
        for key in (f"v{version}", version, version.lstrip("v")):
            if key in history:
                value = history[key]
                return value if isinstance(value, str) else json.dumps(
                    value, ensure_ascii=False, indent=2
                )
    return ""


def main():
    tags = existing_tags()
    log(f"[info] 远端已有 {len(tags)} 个 tag")

    pending = []
    for manifest_file, source_root in MANIFESTS:
        if not os.path.isfile(manifest_file):
            log(f"[skip] 缺少清单 {manifest_file}")
            continue
        with open(manifest_file, encoding="utf-8") as fh:
            manifest = json.load(fh)

        for plugin_id, plugin in manifest.items():
            if not plugin.get("release"):
                log(f"[skip] {plugin_id}: release 未开启")
                continue

            version = str(plugin.get("version", "")).strip()
            if not version:
                log(f"[skip] {plugin_id}: 缺少 version")
                continue

            source_dir = os.path.join(source_root, plugin_id.lower())
            if not os.path.isdir(source_dir):
                log(f"[skip] {plugin_id}: 源码目录不存在 {source_dir}")
                continue

            tag_name = f"{plugin_id}_v{version}"
            if tag_name in tags:
                log(f"[skip] {plugin_id} {version}: tag 已存在 {tag_name}")
                continue

            log(f"[pub ] {plugin_id} {version} -> {tag_name}")
            pending.append({
                "id": plugin_id,
                "name": plugin.get("name", plugin_id),
                "version": version,
                "tag_name": tag_name,
                "source_root": source_root,
                "source_dir": plugin_id.lower(),
                "archive_base": f"{plugin_id.lower()}_v{version}",
                "notes": history_notes(plugin, version),
            })

    ids = [p["id"] for p in pending]
    log(f"[info] 待发布插件：{ids if ids else '（无）'}")

    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
        fh.write("matrix=" + json.dumps(pending, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
