"""Entry point: start the QApplication and the tray."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

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

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None, "eter", "No system tray is available on this system."
        )
        return 1

    repository = CatalogRepository()
    catalog = repository.load()
    tray = TrayApp(app, catalog, repository)
    app._eter_tray = tray  # keep a strong reference alive for the app lifetime
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
