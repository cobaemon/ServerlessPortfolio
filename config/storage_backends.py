import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from storages.backends.s3 import S3ManifestStaticStorage


def _normalize_manifest_paths(manifest):
    """Return a new manifest with normalized path separators."""
    if not manifest:
        return {}
    return {k.replace("\\", "/"): v.replace("\\", "/") for k, v in manifest.items()}


class LocalManifestS3Storage(S3ManifestStaticStorage):
    """S3 storage that reads the manifest from the packaged staticfiles directory."""

    def __init__(self, *args, **kwargs):
        manifest_location = os.path.join(settings.BASE_DIR, 'staticfiles')
        kwargs.setdefault('manifest_storage', FileSystemStorage(location=manifest_location))
        super().__init__(*args, **kwargs)

    def load_manifest(self):
        files, manifest_hash = super().load_manifest()
        return _normalize_manifest_paths(files), manifest_hash
