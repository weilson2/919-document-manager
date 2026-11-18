import argparse
import logging
import sys
from contextlib import ExitStack
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QStandardPaths, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from document_manager.persistence.database import (
    create_database_engine,
    upgrade_database,
)
from document_manager.services.business import BusinessService
from document_manager.services.settings import SettingsService
from document_manager.ui.main_window import MainWindow

APP_NAME = "919 Document Manager"
logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--data-dir", type=Path, help="Use a separate local data directory.")
    parser.add_argument("--check", action="store_true", help="Initialize and check local storage, then exit.")
    args = parser.parse_args(argv)
    QCoreApplication.setApplicationName(APP_NAME)
    app = None if args.check else QApplication([])
    log_path = None

    with ExitStack() as resources:
        try:
            data_dir = args.data_dir
            if data_dir is None:
                default_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
                if not default_dir:
                    raise RuntimeError("The operating system did not provide a local application data directory.")
                data_dir = Path(default_dir)
            data_dir = data_dir.resolve()
            data_dir.mkdir(parents=True, exist_ok=True)
            log_path = data_dir / "application.log"
            handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
            root = logging.getLogger()
            previous_level = root.level
            root.setLevel(logging.INFO)
            root.addHandler(handler)
            resources.callback(handler.close)
            resources.callback(root.removeHandler, handler)
            resources.callback(root.setLevel, previous_level)

            database = data_dir / "document-manager.sqlite3"
            engine = create_database_engine(database)
            resources.callback(engine.dispose)
            upgrade_database(engine)
            settings = SettingsService(engine)
            company_id = settings.get_default_company_id()
            profile = settings.get_company(company_id)
            logger.info("Local database ready")

            if args.check:
                print(f"Local database ready: {database}")
                return 0

            window = MainWindow(settings, BusinessService(engine), company_id, profile)
            window.show()
        except Exception:
            logger.exception("Application startup failed")
            message = "919 Document Manager could not open its local workspace."
            if log_path is not None:
                message += f"\nSee the application log if available:\n{log_path}"
            else:
                message += "\nCheck that the data folder is accessible."
            if app is None:
                print(message, file=sys.stderr)
            else:
                dialog = QMessageBox(QMessageBox.Icon.Critical, APP_NAME, message)
                dialog.setTextFormat(Qt.TextFormat.PlainText)
                dialog.exec()
            return 1

        return app.exec()
