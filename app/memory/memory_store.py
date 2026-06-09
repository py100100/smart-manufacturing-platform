from __future__ import annotations

from datetime import datetime
from pathlib import Path


class MemoryStore:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        if not self.file_path.exists():
            self.file_path.write_text("# MEMORY\n\n", encoding="utf-8")

    def append(self, title: str, lines: list[str]) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content = [f"## {timestamp} | {title}"]
        content.extend(f"- {line}" for line in lines)
        with self.file_path.open("a", encoding="utf-8") as file:
            file.write("\n".join(content) + "\n\n")

    def tail(self, count: int = 3) -> str:
        text = self.file_path.read_text(encoding="utf-8")
        sections = [section.strip() for section in text.split("## ") if section.strip()]
        if not sections:
            return ""
        return "\n\n".join(f"## {section}" for section in sections[-count:])
