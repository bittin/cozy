import logging
from threading import Thread
from typing import List

from peewee import SqliteDatabase
from cozy.application_settings import ApplicationSettings
from cozy.architecture.event_sender import EventSender
from cozy.architecture.observable import Observable
from cozy.model.library import Library
from cozy.model.storage import Storage
from cozy.ext import inject
from cozy.media.importer import Importer
from cozy.model.settings import Settings
from cozy.report import reporter
from gi.repository import Gtk



log = logging.getLogger("settings_view_model")

class SettingsViewModel(Observable, EventSender):
    _library: Library = inject.attr(Library)
    _importer: Importer = inject.attr(Importer)
    _model: Settings = inject.attr(Settings)
    _app_settings: ApplicationSettings = inject.attr(ApplicationSettings)
    _db = inject.attr(SqliteDatabase)

    def __init__(self):
        super().__init__()
        super(Observable, self).__init__()

        self._gtk_settings = Gtk.Settings.get_default()

        self._app_settings.add_listener(self._on_app_setting_changed)

        if self._model.first_start:
            self._importer.scan()

    @property
    def storage_locations(self) -> List[Storage]:
        return self._model.storage_locations

    def add_storage_location(self):
        Storage.new(self._db)
        self._model.invalidate()
        self._notify("storage_locations")

    def remove_storage_location(self, model: Storage):
        if model.default:
            log.error("deleting the default storage location {} is not possible".format(model.path))
            reporter.error("settings_view_model", "deleting the default storage location is not possible")
            return
        
        model.delete()
        self._model.invalidate()
        self._notify("storage_locations")
        self.emit_event("storage-removed", model)

    def set_storage_external(self, model: Storage, external: bool):
        model.external = external

        if external:
            self.emit_event("external-storage-added", model)
        else:
            self.emit_event("external-storage-removed", model)

        self._notify("storage_attributes")
    
    def set_default_storage(self, model: Storage):
        if model.default:
            return

        for storage in self._model.storage_locations:
            storage.default = False
        
        model.default = True

        self._notify("storage_attributes")

    def change_storage_location(self, model: Storage, new_path: str):
        old_path = model.path
        model.path = new_path

        if old_path == "":
            self.emit_event("storage-added", model)
            log.info("New audiobook location added. Starting import scan.")
            thread = Thread(target=self._importer.scan, name="ImportThread")
            thread.start()
        else:
            self.emit_event("storage-changed", model)
            log.info("Audio book location changed, rebasing the location in Cozy.")
            thread = Thread(target=self._library.rebase_path, args=(old_path, new_path), name="RebaseStorageLocationThread")
            thread.start()

    def _set_dark_mode(self):
        prefer_dark_mode = self._app_settings.dark_mode
        self._gtk_settings.set_property("gtk-application-prefer-dark-theme", prefer_dark_mode)

    def _on_app_setting_changed(self, event: str, data):
        if event == "dark-mode":
            self._set_dark_mode()
