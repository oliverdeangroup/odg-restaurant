"""File storage that follows the active demo copy (see core.demo)."""
import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class OdgStorage(FileSystemStorage):
    @property
    def base_location(self):
        from . import demo

        root = demo.media_root()
        if root is not None:
            return os.fspath(root)
        return self._value_or_setting(self._location, settings.MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)
