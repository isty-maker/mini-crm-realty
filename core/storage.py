import os
from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible

try:
    from storages.backends.s3boto3 import S3Boto3Storage
except ImportError:
    S3Boto3Storage = None


def is_yandex_storage_configured() -> bool:
    bucket = (
        os.getenv("YANDEX_STORAGE_BUCKET_NAME")
        or os.getenv("AWS_STORAGE_BUCKET_NAME")
        or getattr(settings, "YANDEX_STORAGE_BUCKET_NAME", "")
    )
    key_id = (
        os.getenv("YANDEX_CLIENT_KEY_ID")
        or os.getenv("AWS_ACCESS_KEY_ID")
        or getattr(settings, "YANDEX_CLIENT_KEY_ID", "")
    )
    return bool(bucket and key_id)


@deconstructible
class YandexMediaStorage(Storage):
    """
    Storage class for media files (photos, etc.).
    If Yandex Object Storage credentials are set, delegates to S3Boto3Storage.
    Otherwise, falls back to local FileSystemStorage.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if is_yandex_storage_configured() and S3Boto3Storage is not None:
            bucket_name = (
                os.getenv("YANDEX_STORAGE_BUCKET_NAME")
                or os.getenv("AWS_STORAGE_BUCKET_NAME")
                or getattr(settings, "YANDEX_STORAGE_BUCKET_NAME", "")
            )
            access_key = (
                os.getenv("YANDEX_CLIENT_KEY_ID")
                or os.getenv("AWS_ACCESS_KEY_ID")
                or getattr(settings, "YANDEX_CLIENT_KEY_ID", "")
            )
            secret_key = (
                os.getenv("YANDEX_CLIENT_SECRET_KEY")
                or os.getenv("AWS_SECRET_ACCESS_KEY")
                or getattr(settings, "YANDEX_CLIENT_SECRET_KEY", "")
            )
            endpoint_url = (
                os.getenv("YANDEX_S3_ENDPOINT_URL")
                or getattr(settings, "YANDEX_S3_ENDPOINT_URL", "https://storage.yandexcloud.net")
            )
            region_name = (
                os.getenv("YANDEX_STORAGE_REGION")
                or getattr(settings, "YANDEX_STORAGE_REGION", "ru-central1")
            )
            custom_domain = (
                os.getenv("YANDEX_STORAGE_CUSTOM_DOMAIN")
                or getattr(settings, "YANDEX_STORAGE_CUSTOM_DOMAIN", None)
            )

            s3_kwargs = {
                "access_key": access_key,
                "secret_key": secret_key,
                "bucket_name": bucket_name,
                "endpoint_url": endpoint_url,
                "region_name": region_name,
                "default_acl": "public-read",
                "querystring_auth": False,
                "file_overwrite": False,
            }
            if custom_domain:
                s3_kwargs["custom_domain"] = custom_domain

            self._backend = S3Boto3Storage(**s3_kwargs)
        else:
            self._backend = FileSystemStorage()

    def _open(self, name, mode="rb"):
        return self._backend._open(name, mode)

    def _save(self, name, content):
        return self._backend._save(name, content)

    def delete(self, name):
        return self._backend.delete(name)

    def exists(self, name):
        return self._backend.exists(name)

    def listdir(self, path):
        return self._backend.listdir(path)

    def size(self, name):
        return self._backend.size(name)

    def url(self, name):
        return self._backend.url(name)

    def get_available_name(self, name, max_length=None):
        return self._backend.get_available_name(name, max_length=max_length)

    def path(self, name):
        if hasattr(self._backend, "path"):
            return self._backend.path(name)
        raise NotImplementedError("This backend doesn't support absolute paths.")


@deconstructible
class YandexFeedStorage(YandexMediaStorage):
    """
    Storage class for feed files with file_overwrite=True.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(self._backend, "file_overwrite"):
            self._backend.file_overwrite = True
