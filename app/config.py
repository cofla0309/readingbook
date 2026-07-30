"""data/config.json 읽기/쓰기.

알라딘 TTB키처럼 남에게 넘기면 안 되는 값만 여기 둔다.
DB(reading.db)와 분리해 두었기 때문에 독서 기록을 백업하거나
CSV로 내보내도 키가 딸려 나가지 않는다.
"""
from __future__ import annotations

import json
from typing import Any

from .paths import CONFIG_PATH

DEFAULTS: dict[str, Any] = {
    "aladin_ttb_key": "",
}


def load() -> dict[str, Any]:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            # 손상된 설정 파일 때문에 앱이 못 뜨는 일은 없어야 한다.
            pass
    return cfg


def get(key: str, default: Any = None) -> Any:
    return load().get(key, default)


def save(updates: dict[str, Any]) -> dict[str, Any]:
    cfg = load()
    cfg.update(updates)
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return cfg
