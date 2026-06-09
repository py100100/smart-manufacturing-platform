from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 确保从项目根目录直接运行 python hooks/check_claude.py 也能找到 app 模块
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.guardrails import protected_module_hint, scan_text_for_guardrails  # noqa: E402

DEFAULT_TARGETS = [ROOT / "app", ROOT / "hooks", ROOT / "tests"]
IGNORE_PATTERN_FILES = {
    (ROOT / "app/core/guardrails.py").resolve(),
    (ROOT / "tests/test_guardrails.py").resolve(),
}


def iter_python_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            files.append(path)
            continue
        if path.is_dir():
            files.extend(sorted(path.rglob("*.py")))
    return files


def check_file(file_path: Path) -> list[str]:
    content = file_path.read_text(encoding="utf-8")
    errors: list[str] = []
    if file_path.resolve() not in IGNORE_PATTERN_FILES:
        errors.extend(
            f"{issue.file_path}: {issue.message}"
            for issue in scan_text_for_guardrails(content, file_path.as_posix())
        )
    hint = protected_module_hint(file_path.as_posix().replace("\\", "/").split(f"{ROOT.name}/")[-1])
    if hint:
        print(f"敏感模块提醒: {file_path.as_posix()} -> {hint}")
    normalized_path = file_path.as_posix().replace("\\", "/")
    if "print(" in content and "tests/" not in normalized_path and "hooks/" not in normalized_path:
        errors.append(f"{file_path.as_posix()}: 禁止在业务代码中使用 print。")
    return errors


def main() -> int:
    args = [Path(arg).resolve() for arg in sys.argv[1:]] or DEFAULT_TARGETS
    errors: list[str] = []
    for file_path in iter_python_files(args):
        errors.extend(check_file(file_path))

    if errors:
        print("CLAUDE Hook 扫描结果：")
        for item in errors:
            print(f"- {item}")
        return 1

    print("CLAUDE Hook 校验通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
