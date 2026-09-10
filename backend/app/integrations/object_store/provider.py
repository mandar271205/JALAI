from abc import ABC, abstractmethod
from pathlib import Path

from minio import Minio

from app.core.config import get_settings


class ObjectStoreProvider(ABC):
    @abstractmethod
    async def upload_bytes(
        self, object_name: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        """Upload byte payload and return public or presigned access URL."""
        pass

    @abstractmethod
    async def get_presigned_url(self, object_name: str, expires_seconds: int = 3600) -> str:
        """Generate presigned download URL."""
        pass

    @abstractmethod
    async def ensure_bucket(self) -> bool:
        """Ensure default storage bucket exists."""
        pass


class MinIOObjectStoreProvider(ObjectStoreProvider):
    def __init__(self):
        settings = get_settings()
        self.bucket_name = settings.MINIO_BUCKET
        self.endpoint = settings.MINIO_ENDPOINT
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )

    async def ensure_bucket(self) -> bool:
        import socket
        try:
            # Fast socket probe: don't hang startup if MinIO service is not running locally
            parts = self.endpoint.split(":")
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 9000
            with socket.create_connection((host, port), timeout=0.2):
                pass
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
            return True
        except Exception:
            return False

    async def upload_bytes(
        self, object_name: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        import io

        stream = io.BytesIO(data)
        self.client.put_object(
            self.bucket_name, object_name, stream, length=len(data), content_type=content_type
        )
        return f"http://{self.endpoint}/{self.bucket_name}/{object_name}"

    async def get_presigned_url(self, object_name: str, expires_seconds: int = 3600) -> str:
        from datetime import timedelta

        return self.client.presigned_get_object(
            self.bucket_name, object_name, expires=timedelta(seconds=expires_seconds)
        )


class LocalObjectStoreProvider(ObjectStoreProvider):
    """
    Local filesystem fallback provider when MinIO daemon is not reachable in local dev/tests.
    """

    def __init__(self, base_dir: str = "/tmp/jalrakshak_storage"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def ensure_bucket(self) -> bool:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        return True

    async def upload_bytes(
        self, object_name: str, data: bytes, content_type: str = "application/octet-stream"
    ) -> str:
        target = self.base_dir / object_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return f"file://{target.absolute()}"

    async def get_presigned_url(self, object_name: str, expires_seconds: int = 3600) -> str:
        target = self.base_dir / object_name
        return f"file://{target.absolute()}"


def get_object_store_provider() -> ObjectStoreProvider:
    settings = get_settings()
    if settings.APP_ENV == "test" or not getattr(settings, "OBJECT_STORAGE_ENABLED", True):
        return LocalObjectStoreProvider()
    try:
        provider = MinIOObjectStoreProvider()
        return provider
    except Exception:
        return LocalObjectStoreProvider()
