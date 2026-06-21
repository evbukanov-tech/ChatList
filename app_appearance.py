"""Тема оформления и размер шрифта интерфейса."""

from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication

import db

THEME_LIGHT = "light"
THEME_DARK = "dark"
DEFAULT_THEME = THEME_LIGHT
DEFAULT_FONT_SIZE = 10
MIN_FONT_SIZE = 9
MAX_FONT_SIZE = 16

SETTING_THEME = "ui_theme"
SETTING_FONT_SIZE = "ui_font_size"

FONT_SIZE_OPTIONS = [9, 10, 11, 12, 13, 14, 16]


def normalize_theme(value: str) -> str:
    theme = value.strip().lower()
    if theme in (THEME_LIGHT, THEME_DARK):
        return theme
    return DEFAULT_THEME


def normalize_font_size(value: str | int) -> int:
    try:
        size = int(str(value).strip())
    except (TypeError, ValueError):
        return DEFAULT_FONT_SIZE
    return max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, size))


def get_theme() -> str:
    return normalize_theme(db.get_setting(SETTING_THEME, DEFAULT_THEME))


def get_font_size() -> int:
    return normalize_font_size(db.get_setting(SETTING_FONT_SIZE, str(DEFAULT_FONT_SIZE)))


def _base_stylesheet(font_size: int) -> str:
    return f"""
        QWidget {{
            font-size: {font_size}pt;
        }}
        QGroupBox {{
            font-weight: bold;
            margin-top: 8px;
            padding-top: 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
        }}
        QTableWidget {{
            gridline-color: palette(mid);
        }}
    """


def _light_stylesheet(font_size: int) -> str:
    return _base_stylesheet(font_size)


def _dark_stylesheet(font_size: int) -> str:
    return (
        _base_stylesheet(font_size)
        + """
        QWidget {
            background-color: #2b2b2b;
            color: #e0e0e0;
        }
        QMainWindow, QDialog, QTabWidget::pane {
            background-color: #2b2b2b;
        }
        QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {
            background-color: #3c3c3c;
            color: #e0e0e0;
            border: 1px solid #555555;
            border-radius: 3px;
            padding: 2px 4px;
        }
        QComboBox::drop-down {
            border: none;
        }
        QComboBox QAbstractItemView {
            background-color: #3c3c3c;
            color: #e0e0e0;
            selection-background-color: #4a6fa5;
        }
        QTableWidget, QTableView {
            background-color: #323232;
            alternate-background-color: #383838;
            color: #e0e0e0;
            gridline-color: #555555;
        }
        QHeaderView::section {
            background-color: #3a3a3a;
            color: #e0e0e0;
            border: 1px solid #555555;
            padding: 4px;
        }
        QPushButton {
            background-color: #404040;
            color: #e0e0e0;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 4px 12px;
        }
        QPushButton:hover {
            background-color: #4a4a4a;
        }
        QPushButton:pressed {
            background-color: #353535;
        }
        QPushButton:disabled {
            color: #888888;
            background-color: #333333;
        }
        QGroupBox {
            border: 1px solid #555555;
            border-radius: 4px;
            margin-top: 10px;
        }
        QTabBar::tab {
            background-color: #353535;
            color: #c0c0c0;
            border: 1px solid #555555;
            padding: 6px 14px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background-color: #2b2b2b;
            color: #ffffff;
        }
        QMenuBar {
            background-color: #2b2b2b;
            color: #e0e0e0;
        }
        QMenuBar::item:selected {
            background-color: #404040;
        }
        QMenu {
            background-color: #3c3c3c;
            color: #e0e0e0;
            border: 1px solid #555555;
        }
        QMenu::item:selected {
            background-color: #4a6fa5;
        }
        QScrollBar:vertical {
            background: #2b2b2b;
            width: 12px;
        }
        QScrollBar::handle:vertical {
            background: #555555;
            min-height: 24px;
            border-radius: 4px;
        }
        QProgressBar {
            border: 1px solid #555555;
            background-color: #3c3c3c;
            text-align: center;
        }
        QProgressBar::chunk {
            background-color: #4a6fa5;
        }
        QTextBrowser {
            background-color: #323232;
            color: #e0e0e0;
            border: 1px solid #555555;
        }
        """
    )


def _apply_palette(app: QApplication, theme: str) -> None:
    palette = QPalette()
    if theme == THEME_DARK:
        palette.setColor(QPalette.ColorRole.Window, QColor("#2b2b2b"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#e0e0e0"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#3c3c3c"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#383838"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#e0e0e0"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#404040"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e0e0e0"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#4a6fa5"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#3c3c3c"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#e0e0e0"))
    else:
        palette = app.style().standardPalette()
    app.setPalette(palette)


def apply_appearance(app: QApplication | None = None) -> None:
    """Применить тему и размер шрифта из таблицы settings."""
    application = app or QApplication.instance()
    if application is None:
        return

    theme = get_theme()
    font_size = get_font_size()

    application.setStyle("Fusion")
    base_font = application.font()
    application.setFont(QFont(base_font.family(), font_size))
    _apply_palette(application, theme)

    if theme == THEME_DARK:
        application.setStyleSheet(_dark_stylesheet(font_size))
    else:
        application.setStyleSheet(_light_stylesheet(font_size))
