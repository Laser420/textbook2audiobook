from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

SESSIONS_DIR = Path.cwd() / "sessions"


@dataclass
class Session:
    session_id: str
    title: str
    created_at: str

    # ── factories ────────────────────────────────────────────────────────────

    @classmethod
    def create(cls, title: str) -> Session:
        return cls(
            session_id=uuid.uuid4().hex[:8],
            title=title,
            created_at=datetime.now().isoformat(),
        )

    # ── persistence ──────────────────────────────────────────────────────────

    def save(self) -> None:
        self._dir().mkdir(parents=True, exist_ok=True)
        self.screenshots_dir().mkdir(exist_ok=True)
        (self._dir() / "session.json").write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, session_id: str) -> Session:
        path = SESSIONS_DIR / session_id / "session.json"
        data = json.loads(path.read_text())
        data.pop("region", None)  # legacy field, no longer used
        return cls(**data)

    @classmethod
    def list_all(cls) -> list[Session]:
        if not SESSIONS_DIR.exists():
            return []
        sessions = []
        for d in SESSIONS_DIR.iterdir():
            if d.is_dir():
                try:
                    sessions.append(cls.load(d.name))
                except Exception:
                    pass
        return sorted(sessions, key=lambda s: s.created_at)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _dir(self) -> Path:
        return SESSIONS_DIR / self.session_id

    def screenshots_dir(self) -> Path:
        return self._dir() / "screenshots"

    @property
    def page_count(self) -> int:
        d = self.screenshots_dir()
        return len(list(d.glob("*.png"))) if d.exists() else 0

    def next_filename(self) -> str:
        return f"{self.page_count + 1:04d}.png"

    def title_slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "_", self.title.lower()).strip("_")
