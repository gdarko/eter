"""Entry point: start the QApplication and the app."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import config
from .app import TrayApp
from .catalog_repository import CatalogRepository
from .platform_mac import hide_dock_icon


def main() -> int:
    QApplication.setApplicationName(config.APP_NAME)
    QApplication.setOrganizationName(config.ORG_NAME)
    QApplication.setOrganizationDomain(config.ORG_DOMAIN)
    QApplication.setApplicationDisplayName(config.DISPLAY_NAME)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    hide_dock_icon()

    # No system-tray requirement: TrayApp picks a presenter (tray or window),
    # so the app still runs on desktops without a working tray.
    repository = CatalogRepository()
    catalog = repository.load()
    controller = TrayApp(app, catalog, repository)
    app._eter_controller = controller  # keep a strong reference for the app lifetime
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
