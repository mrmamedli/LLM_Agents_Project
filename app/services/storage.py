import uuid
from pathlib import Path

from fastapi import UploadFile

CHUNK_SIZE = 1024 * 1024


async def save_upload(upload: UploadFile, root: Path) -> str:
    root.mkdir(parents=True, exist_ok=True)
    key = f"{uuid.uuid4()}.pdf"
    target = root / key
    try:
        with target.open("wb") as destination:
            while chunk := await upload.read(CHUNK_SIZE):
                destination.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    return key


def delete_file(root: Path, key: str) -> None:
    (root / key).unlink(missing_ok=True)
