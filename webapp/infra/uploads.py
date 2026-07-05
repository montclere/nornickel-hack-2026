from __future__ import annotations


class UploadError(ValueError):
    pass

def _safe_rel(name: str) -> str:
    name = (name or "").replace("\\", "/")
    parts = [p for p in name.split("/") if p not in ("", ".", "..")]
    return "/".join(parts) or "file"

_ROLE_DIRS = {"data": "data", "knowledge": "knowledge"}

async def save_group(run_id: str, files, role: str) -> list:
    if role not in _ROLE_DIRS:
        raise UploadError(f"неизвестная роль загрузки: {role}")
    from webapp.infra import storage
    storage.ensure_run(run_id)
    base = storage.run_dir(run_id) / "sources" / _ROLE_DIRS[role]
    saved = []
    for f in files or []:
        if not getattr(f, "filename", ""):
            continue
        rel = _safe_rel(f.filename)
        data = await f.read()
        if not data:
            continue
        dest = base / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        saved.append(f"{_ROLE_DIRS[role]}/{rel}")
    return saved
