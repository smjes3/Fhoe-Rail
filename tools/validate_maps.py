"""校验地图 JSON —— 独立脚本，按路径运行。

    python tools/validate_maps.py              # 校验全部地图版本
    python tools/validate_maps.py default      # 只校验某个版本
    python tools/validate_maps.py --errors-only

退出码：有 error 则 1，只有 warning 或全通过则 0。可以直接接进 CI。
"""

import json
import sys
from pathlib import Path

MAP_DIR = "map"


def load_schema():
    """import 校验器。

    直接按路径运行时 sys.path[0] 是 tools/ 而不是仓库根，所以要显式补上。
    放在函数里而不是模块级 —— 模块级副作用会被 tests/test_architecture.py
    的棘轮拦下（那是给独立脚本定的规则）。
    """
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    from utils.core import schema

    return schema


def iter_map_files(version=None):
    root = Path(MAP_DIR)
    if not root.is_dir():
        print(f"找不到地图目录：{root.resolve()}")
        return
    versions = (
        [version] if version else sorted(p.name for p in root.iterdir() if p.is_dir())
    )
    for name in versions:
        folder = root / name
        if not folder.is_dir():
            print(f"找不到地图版本：{name}")
            continue
        for path in sorted(folder.glob("*.json")):
            yield name, path


def main(argv) -> int:
    schema = load_schema()

    only_errors = "--errors-only" in argv
    args = [a for a in argv if not a.startswith("--")]
    version = args[0] if args else None

    total = 0
    failed = 0
    reported = []

    for _, path in iter_map_files(version):
        total += 1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            reported.append((path, [schema.Issue("error", path.name, f"JSON 解析失败: {e}")]))
            failed += 1
            continue

        issues = schema.validate_map(data, filename=path.name)
        if only_errors:
            issues = [i for i in issues if i.level == "error"]
        if issues:
            if any(i.level == "error" for i in issues):
                failed += 1
            reported.append((path, issues))

    for path, issues in reported:
        print(f"\n{path.relative_to(Path(MAP_DIR).parent)}")
        for issue in issues:
            print(f"    {issue}")

    print()
    print("=" * 60)
    print(f"校验 {total} 个地图文件，{failed} 个有错误")
    if total:
        print(f"通过率 {(total - failed) / total * 100:.1f}%")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
