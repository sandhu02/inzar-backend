import hashlib
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import settings


class BaseCloudinaryService(ABC):
    @abstractmethod
    def generate_upload_signature(self, incident_id: uuid.UUID) -> dict[str, Any]:
        """Generate signed upload parameters for direct client upload."""
        pass

    @abstractmethod
    async def verify_asset(self, public_id: str) -> dict[str, Any] | None:
        """Verify asset exists in Cloudinary and return its metadata."""
        pass

    @abstractmethod
    async def delete_asset(self, public_id: str) -> bool:
        """Delete an asset from Cloudinary."""
        pass


class CloudinaryService(BaseCloudinaryService):
    def __init__(
        self,
        cloud_name: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        upload_folder: str | None = None,
    ) -> None:
        self.cloud_name = cloud_name or settings.CLOUDINARY_CLOUD_NAME
        self.api_key = api_key or settings.CLOUDINARY_API_KEY
        self.api_secret = api_secret or settings.CLOUDINARY_API_SECRET
        self.upload_folder = upload_folder or settings.CLOUDINARY_UPLOAD_FOLDER

    def _sign_parameters(self, params: dict[str, Any]) -> str:
        # Cloudinary signature: sort keys, join key=val with &, append api_secret, sha1
        sorted_items = sorted(params.items())
        to_sign = "&".join(f"{k}={v}" for k, v in sorted_items if v is not None and v != "")
        to_sign += self.api_secret
        return hashlib.sha1(to_sign.encode("utf-8")).hexdigest()

    def generate_upload_signature(self, incident_id: uuid.UUID) -> dict[str, Any]:
        timestamp = int(time.time())
        folder = f"{self.upload_folder}/{incident_id}"
        public_id = f"photo_{uuid.uuid4().hex[:12]}"

        params_to_sign = {
            "folder": folder,
            "public_id": public_id,
            "timestamp": timestamp,
        }
        signature = self._sign_parameters(params_to_sign)

        return {
            "upload_url": f"https://api.cloudinary.com/v1_1/{self.cloud_name}/image/upload",
            "api_key": self.api_key,
            "cloud_name": self.cloud_name,
            "timestamp": timestamp,
            "folder": folder,
            "public_id": public_id,
            "signature": signature,
        }

    async def verify_asset(self, public_id: str) -> dict[str, Any] | None:
        # Check against Cloudinary Admin API
        url = (
            f"https://api.cloudinary.com/v1_1/{self.cloud_name}/resources/image/upload/{public_id}"
        )
        auth = (self.api_key, self.api_secret)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url, auth=auth)
                if res.status_code == 200:
                    data = res.json()
                    return {
                        "public_id": data.get("public_id", public_id),
                        "secure_url": data.get(
                            "secure_url",
                            f"https://res.cloudinary.com/{self.cloud_name}/image/upload/{public_id}",
                        ),
                        "width": data.get("width"),
                        "height": data.get("height"),
                        "bytes": data.get("bytes"),
                        "format": data.get("format"),
                    }
                elif res.status_code == 404:
                    return None
        except Exception:
            pass

        # If running in development with demo or unreachable credentials, simulate verified asset
        if settings.APP_ENV != "production":
            return {
                "public_id": public_id,
                "secure_url": f"https://res.cloudinary.com/{self.cloud_name}/image/upload/{public_id}.jpg",
                "width": 1920,
                "height": 1080,
                "bytes": 524288,
                "format": "jpg",
            }
        return None

    async def delete_asset(self, public_id: str) -> bool:
        url = f"https://api.cloudinary.com/v1_1/{self.cloud_name}/image/destroy"
        timestamp = int(time.time())
        params_to_sign = {
            "public_id": public_id,
            "timestamp": timestamp,
        }
        signature = self._sign_parameters(params_to_sign)
        data = {
            "public_id": public_id,
            "timestamp": str(timestamp),
            "api_key": self.api_key,
            "signature": signature,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, data=data)
                return res.status_code == 200
        except Exception:
            return False


class FakeCloudinaryService(BaseCloudinaryService):
    def __init__(self) -> None:
        self.verified_assets: dict[str, dict[str, Any]] = {}
        self.deleted_assets: list[str] = []

    def generate_upload_signature(self, incident_id: uuid.UUID) -> dict[str, Any]:
        public_id = f"inzar/incidents/{incident_id}/photo_{uuid.uuid4().hex[:12]}"
        return {
            "upload_url": "https://api.cloudinary.com/v1_1/fake/image/upload",
            "api_key": "fake_key",
            "cloud_name": "fake",
            "timestamp": int(time.time()),
            "folder": f"inzar/incidents/{incident_id}",
            "public_id": public_id,
            "signature": "fake_signature",
        }

    async def verify_asset(self, public_id: str) -> dict[str, Any] | None:
        if public_id in self.verified_assets:
            return self.verified_assets[public_id]
        return {
            "public_id": public_id,
            "secure_url": f"https://res.cloudinary.com/fake/image/upload/{public_id}.jpg",
            "width": 1280,
            "height": 720,
            "bytes": 250000,
            "format": "jpg",
        }

    async def delete_asset(self, public_id: str) -> bool:
        self.deleted_assets.append(public_id)
        return True


def get_cloudinary_service() -> BaseCloudinaryService:
    if settings.APP_ENV == "test":
        return FakeCloudinaryService()
    return CloudinaryService()
