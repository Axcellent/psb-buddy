from urllib.parse import quote
import httpx

from ..config import settings


class StorageError(RuntimeError):
    pass

class SeaweedFSStorage:
    def __init__(self) -> None:
        self.base_url = settings.seaweedfs_url.rstrip("/")
        self.timeout = settings.seaweedfs_timeout_seconds
        self.directory = settings.seaweedfs_directory.strip("/")

    def path_for(self, document_id: str) -> str:
        return f"/{self.directory}/{document_id}.txt"

    def _url(self, storage_path: str) -> str:
        safe_path = "/".join(quote(part, safe="") for part in storage_path.strip("/").split("/"))
        return f"{self.base_url}/{safe_path}"

    def upload(self, storage_path: str, content: bytes) -> None:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.put(
                    self._url(storage_path),
                    content=content,
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise StorageError("Не удалось сохранить файл в SeaweedFS.") from exc

    def download(self, storage_path: str) -> bytes:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(self._url(storage_path))
                response.raise_for_status()
                return response.content
        except httpx.HTTPError as exc:
            raise StorageError("Не удалось получить файл из SeaweedFS.") from exc

    def delete(self, storage_path: str) -> None:
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.delete(self._url(storage_path))
                if response.status_code not in (200, 202, 204, 404):
                    response.raise_for_status()
        except httpx.HTTPError as exc:
            raise StorageError("Не удалось удалить файл из SeaweedFS.") from exc

    def healthcheck(self) -> bool:
        try:
            with httpx.Client(timeout=min(self.timeout, 3.0)) as client:
                response = client.get(f"{self.base_url}/healthz")
                return response.status_code == 200
        except httpx.HTTPError:
            return False


storage = SeaweedFSStorage()
