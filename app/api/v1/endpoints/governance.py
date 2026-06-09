from fastapi import APIRouter

from app.core.config import get_settings
from app.core.guardrails import PROTECTED_MODULES
from app.memory.memory_store import MemoryStore

router = APIRouter(prefix="/governance", tags=["governance"])


@router.get("/claude")
async def read_claude_rules() -> dict[str, object]:
    settings = get_settings()
    content = settings.claude_file.read_text(encoding="utf-8")
    return {
        "file": str(settings.claude_file),
        "protected_modules": PROTECTED_MODULES,
        "content": content,
    }


@router.get("/memory")
async def read_memory_tail() -> dict[str, str]:
    settings = get_settings()
    memory = MemoryStore(settings.memory_file)
    return {"content": memory.tail()}
