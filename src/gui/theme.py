DARK_THEME_STYLE = """
/* Base Window Styles */
QMainWindow {
    background-color: #121214;
    color: #e4e4e7;
}

QWidget {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
    color: #e4e4e7;
}

/* Sidebar Styling */
QFrame#SidebarFrame {
    background-color: #1a1a1e;
    border-right: 1px solid #27272a;
    min-width: 220px;
    max-width: 220px;
}

QLabel#SidebarTitle {
    font-size: 18px;
    font-weight: bold;
    color: #6366f1;
    padding: 15px 10px;
    border-bottom: 1px solid #27272a;
}

QPushButton#SidebarButton {
    background-color: transparent;
    color: #a1a1aa;
    border: none;
    border-radius: 6px;
    padding: 12px 15px;
    text-align: left;
    font-weight: 500;
    margin: 4px 10px;
}

QPushButton#SidebarButton:hover {
    background-color: #27272a;
    color: #f4f4f5;
}

QPushButton#SidebarButton:checked {
    background-color: #6366f1;
    color: #ffffff;
}

/* Header & Pages Content Styling */
QLabel#PageTitle {
    font-size: 24px;
    font-weight: bold;
    color: #f4f4f5;
    margin-bottom: 5px;
}

QLabel#PageSubtitle {
    font-size: 13px;
    color: #a1a1aa;
    margin-bottom: 20px;
}

/* Dashboard Cards */
QFrame#CardFrame {
    background-color: #1a1a1e;
    border: 1px solid #27272a;
    border-radius: 8px;
    padding: 15px;
}

QLabel#CardTitle {
    font-size: 12px;
    font-weight: bold;
    color: #a1a1aa;
    text-transform: uppercase;
}

QLabel#CardValue {
    font-size: 22px;
    font-weight: bold;
    color: #f4f4f5;
    margin: 5px 0px;
}

QLabel#CardDesc {
    font-size: 11px;
    color: #71717a;
}

/* Inputs and Forms */
QLineEdit {
    background-color: #1e1e24;
    border: 1px solid #27272a;
    border-radius: 6px;
    padding: 8px 12px;
    color: #f4f4f5;
}

QLineEdit:focus {
    border: 1px solid #6366f1;
}

QComboBox {
    background-color: #1e1e24;
    border: 1px solid #27272a;
    border-radius: 6px;
    padding: 8px 12px;
    color: #f4f4f5;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #1a1a1e;
    border: 1px solid #27272a;
    selection-background-color: #6366f1;
    selection-color: #ffffff;
}

QSpinBox {
    background-color: #1e1e24;
    border: 1px solid #27272a;
    border-radius: 6px;
    padding: 8px 12px;
    color: #f4f4f5;
}

QSpinBox:focus {
    border: 1px solid #6366f1;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #27272a;
    border-radius: 4px;
    background-color: #1e1e24;
}

QCheckBox::indicator:checked {
    background-color: #1e1e24;
    border-color: #6366f1;
    image: url(src/gui/checkbox_checked_dark.svg);
}

/* Buttons */
QPushButton {
    background-color: #27272a;
    color: #f4f4f5;
    border: 1px solid #3f3f46;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #3f3f46;
}

QPushButton:pressed {
    background-color: #18181b;
}

QPushButton#PrimaryButton {
    background-color: #6366f1;
    color: #ffffff;
    border: none;
}

QPushButton#PrimaryButton:hover {
    background-color: #4f46e5;
}

QPushButton#PrimaryButton:pressed {
    background-color: #3730a3;
}

QPushButton#SuccessButton {
    background-color: #10b981;
    color: #ffffff;
    border: none;
}

QPushButton#SuccessButton:hover {
    background-color: #059669;
}

QPushButton#SuccessButton:pressed {
    background-color: #065f46;
}

QPushButton#DangerButton {
    background-color: #ef4444;
    color: #ffffff;
    border: none;
}

QPushButton#DangerButton:hover {
    background-color: #dc2626;
}

QPushButton#DangerButton:pressed {
    background-color: #991b1b;
}

/* Lists and Tables */
QListWidget {
    background-color: #1a1a1e;
    border: 1px solid #27272a;
    border-radius: 8px;
    padding: 5px;
}

QListWidget::item {
    padding: 10px;
    border-radius: 6px;
    margin-bottom: 2px;
}

QListWidget::item:hover {
    background-color: #27272a;
}

QListWidget::item:selected {
    background-color: #6366f1;
    color: #ffffff;
}

QTableWidget {
    background-color: #1a1a1e;
    border: 1px solid #27272a;
    border-radius: 8px;
    gridline-color: #27272a;
}

QTableWidget::item {
    padding: 8px;
}

QHeaderView::section {
    background-color: #27272a;
    color: #a1a1aa;
    padding: 8px;
    border: none;
    font-weight: bold;
}

/* Scrollbars */
QScrollBar:vertical {
    background-color: #121214;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #27272a;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background-color: #3f3f46;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Terminal Console Log Box */
QTextEdit#LogConsole {
    background-color: #0d0d0f;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    color: #a1a1aa;
    border: 1px solid #27272a;
    border-radius: 6px;
    padding: 10px;
}

/* Tab Widget Styling */
QTabWidget::pane {
    border: 1px solid #27272a;
    background-color: #121214;
    border-radius: 8px;
}
QTabBar::tab {
    background-color: #1a1a1e;
    color: #a1a1aa;
    padding: 10px 20px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid #27272a;
    border-bottom: none;
    margin-right: 2px;
}
QTabBar::tab:hover {
    background-color: #27272a;
    color: #f4f4f5;
}
QTabBar::tab:selected {
    background-color: #6366f1;
    color: #ffffff;
    border-color: #6366f1;
}

/* Database list widget */
QListWidget#DatabaseList {
    background-color: #161619;
    border: 1px solid #27272a;
    border-radius: 6px;
}
QListWidget#DatabaseList::item {
    padding: 8px;
    border-bottom: 1px solid #27272a;
    color: #e4e4e7;
}
QListWidget#DatabaseList::item:last {
    border-bottom: none;
}

/* Disk space progress bar */
QProgressBar#DiskProgressBar {
    border: 1px solid #27272a;
    border-radius: 4px;
    background-color: #161619;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
    height: 20px;
}
QProgressBar#DiskProgressBar::chunk {
    background-color: #3b82f6;
    border-radius: 3px;
}

/* Separator & Footer */
QFrame#PageSeparator {
    background-color: #27272a;
    max-height: 1px;
}
QFrame#ProfileFooter {
    border-top: 1px solid #27272a;
    padding: 15px;
}

/* Labels custom colors */
QLabel#SidebarTitleLabel {
    font-size: 15px;
    font-weight: bold;
    color: #6366f1;
}
QLabel#SidebarSubtitleLabel {
    font-size: 11px;
    color: #71717a;
}
QLabel#FormHeader {
    font-size: 15px;
    font-weight: bold;
    color: #f4f4f5;
}
QLabel#DiskValueLabel {
    font-weight: bold;
    font-size: 13px;
    color: #f4f4f5;
}
QLabel#FolderSizeLabel {
    color: #a1a1aa;
    font-size: 12px;
}
"""

LIGHT_THEME_STYLE = """
/* Base Window Styles */
QMainWindow {
    background-color: #f8fafc;
    color: #0f172a;
}

QWidget {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
    color: #334155;
}

/* Sidebar Styling */
QFrame#SidebarFrame {
    background-color: #f1f5f9;
    border-right: 1px solid #cbd5e1;
    min-width: 220px;
    max-width: 220px;
}

QLabel#SidebarTitle {
    font-size: 18px;
    font-weight: bold;
    color: #2563eb;
    padding: 15px 10px;
    border-bottom: 1px solid #cbd5e1;
}

QPushButton#SidebarButton {
    background-color: transparent;
    color: #475569;
    border: none;
    border-radius: 6px;
    padding: 12px 15px;
    text-align: left;
    font-weight: 500;
    margin: 4px 10px;
}

QPushButton#SidebarButton:hover {
    background-color: #e2e8f0;
    color: #0f172a;
}

QPushButton#SidebarButton:checked {
    background-color: #2563eb;
    color: #ffffff;
}

/* Header & Pages Content Styling */
QLabel#PageTitle {
    font-size: 24px;
    font-weight: bold;
    color: #0f172a;
    margin-bottom: 5px;
}

QLabel#PageSubtitle {
    font-size: 13px;
    color: #64748b;
    margin-bottom: 20px;
}

/* Dashboard Cards */
QFrame#CardFrame {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 15px;
}

QLabel#CardTitle {
    font-size: 12px;
    font-weight: bold;
    color: #64748b;
    text-transform: uppercase;
}

QLabel#CardValue {
    font-size: 22px;
    font-weight: bold;
    color: #0f172a;
    margin: 5px 0px;
}

QLabel#CardDesc {
    font-size: 11px;
    color: #94a3b8;
}

/* Inputs and Forms */
QLineEdit {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 8px 12px;
    color: #0f172a;
}

QLineEdit:focus {
    border: 1px solid #2563eb;
}

QComboBox {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 8px 12px;
    color: #0f172a;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}

QSpinBox {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 8px 12px;
    color: #0f172a;
}

QSpinBox:focus {
    border: 1px solid #2563eb;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    background-color: #ffffff;
}

QCheckBox::indicator:checked {
    background-color: #ffffff;
    border-color: #2563eb;
    image: url(src/gui/checkbox_checked_light.svg);
}

/* Buttons */
QPushButton {
    background-color: #e2e8f0;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #cbd5e1;
}

QPushButton:pressed {
    background-color: #94a3b8;
}

QPushButton#PrimaryButton {
    background-color: #2563eb;
    color: #ffffff;
    border: none;
}

QPushButton#PrimaryButton:hover {
    background-color: #1d4ed8;
}

QPushButton#PrimaryButton:pressed {
    background-color: #1e3a8a;
}

QPushButton#SuccessButton {
    background-color: #10b981;
    color: #ffffff;
    border: none;
}

QPushButton#SuccessButton:hover {
    background-color: #059669;
}

QPushButton#SuccessButton:pressed {
    background-color: #065f46;
}

QPushButton#DangerButton {
    background-color: #ef4444;
    color: #ffffff;
    border: none;
}

QPushButton#DangerButton:hover {
    background-color: #dc2626;
}

QPushButton#DangerButton:pressed {
    background-color: #991b1b;
}

/* Lists and Tables */
QListWidget {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 5px;
}

QListWidget::item {
    padding: 10px;
    border-radius: 6px;
    margin-bottom: 2px;
    color: #334155;
}

QListWidget::item:hover {
    background-color: #e2e8f0;
}

QListWidget::item:selected {
    background-color: #2563eb;
    color: #ffffff;
}

QTableWidget {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    gridline-color: #e2e8f0;
    color: #334155;
}

QTableWidget::item {
    padding: 8px;
}

QHeaderView::section {
    background-color: #e2e8f0;
    color: #475569;
    padding: 8px;
    border: none;
    font-weight: bold;
}

/* Scrollbars */
QScrollBar:vertical {
    background-color: #f1f5f9;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #cbd5e1;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background-color: #94a3b8;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Terminal Console Log Box */
QTextEdit#LogConsole {
    background-color: #0f172a;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    color: #cbd5e1;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 10px;
}

/* Tab Widget Styling */
QTabWidget::pane {
    border: 1px solid #cbd5e1;
    background-color: #f8fafc;
    border-radius: 8px;
}
QTabBar::tab {
    background-color: #e2e8f0;
    color: #475569;
    padding: 10px 20px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid #cbd5e1;
    border-bottom: none;
    margin-right: 2px;
}
QTabBar::tab:hover {
    background-color: #cbd5e1;
    color: #0f172a;
}
QTabBar::tab:selected {
    background-color: #2563eb;
    color: #ffffff;
    border-color: #2563eb;
}

/* Database list widget */
QListWidget#DatabaseList {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
}
QListWidget#DatabaseList::item {
    padding: 8px;
    border-bottom: 1px solid #cbd5e1;
    color: #334155;
}
QListWidget#DatabaseList::item:last {
    border-bottom: none;
}

/* Disk space progress bar */
QProgressBar#DiskProgressBar {
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    background-color: #ffffff;
    text-align: center;
    color: #0f172a;
    font-weight: bold;
    height: 20px;
}
QProgressBar#DiskProgressBar::chunk {
    background-color: #2563eb;
    border-radius: 3px;
}

/* Separator & Footer */
QFrame#PageSeparator {
    background-color: #cbd5e1;
    max-height: 1px;
}
QFrame#ProfileFooter {
    border-top: 1px solid #cbd5e1;
    padding: 15px;
}

/* Labels custom colors */
QLabel#SidebarTitleLabel {
    font-size: 15px;
    font-weight: bold;
    color: #2563eb;
}
QLabel#SidebarSubtitleLabel {
    font-size: 11px;
    color: #64748b;
}
QLabel#FormHeader {
    font-size: 15px;
    font-weight: bold;
    color: #0f172a;
}
QLabel#DiskValueLabel {
    font-weight: bold;
    font-size: 13px;
    color: #0f172a;
}
QLabel#FolderSizeLabel {
    color: #64748b;
    font-size: 12px;
}
"""

MIDNIGHT_THEME_STYLE = """
/* Base Window Styles */
QMainWindow {
    background-color: #0b0f19;
    color: #e2e8f0;
}

QWidget {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
    color: #cbd5e1;
}

/* Sidebar Styling */
QFrame#SidebarFrame {
    background-color: #0f172a;
    border-right: 1px solid #1e293b;
    min-width: 220px;
    max-width: 220px;
}

QLabel#SidebarTitle {
    font-size: 18px;
    font-weight: bold;
    color: #0ea5e9;
    padding: 15px 10px;
    border-bottom: 1px solid #1e293b;
}

QPushButton#SidebarButton {
    background-color: transparent;
    color: #94a3b8;
    border: none;
    border-radius: 6px;
    padding: 12px 15px;
    text-align: left;
    font-weight: 500;
    margin: 4px 10px;
}

QPushButton#SidebarButton:hover {
    background-color: #1e293b;
    color: #f8fafc;
}

QPushButton#SidebarButton:checked {
    background-color: #0ea5e9;
    color: #ffffff;
}

/* Header & Pages Content Styling */
QLabel#PageTitle {
    font-size: 24px;
    font-weight: bold;
    color: #f8fafc;
    margin-bottom: 5px;
}

QLabel#PageSubtitle {
    font-size: 13px;
    color: #64748b;
    margin-bottom: 20px;
}

/* Dashboard Cards */
QFrame#CardFrame {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 15px;
}

QLabel#CardTitle {
    font-size: 12px;
    font-weight: bold;
    color: #64748b;
    text-transform: uppercase;
}

QLabel#CardValue {
    font-size: 22px;
    font-weight: bold;
    color: #f8fafc;
    margin: 5px 0px;
}

QLabel#CardDesc {
    font-size: 11px;
    color: #475569;
}

/* Inputs and Forms */
QLineEdit {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 12px;
    color: #f8fafc;
}

QLineEdit:focus {
    border: 1px solid #0ea5e9;
}

QComboBox {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 12px;
    color: #f8fafc;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox QAbstractItemView {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    selection-background-color: #0ea5e9;
    selection-color: #ffffff;
}

QSpinBox {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 12px;
    color: #f8fafc;
}

QSpinBox:focus {
    border: 1px solid #0ea5e9;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #334155;
    border-radius: 4px;
    background-color: #1e293b;
}

QCheckBox::indicator:checked {
    background-color: #1e293b;
    border-color: #0ea5e9;
    image: url(src/gui/checkbox_checked_midnight.svg);
}

/* Buttons */
QPushButton {
    background-color: #1e293b;
    color: #cbd5e1;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #334155;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #0f172a;
}

QPushButton#PrimaryButton {
    background-color: #0ea5e9;
    color: #ffffff;
    border: none;
}

QPushButton#PrimaryButton:hover {
    background-color: #0284c7;
}

QPushButton#PrimaryButton:pressed {
    background-color: #0369a1;
}

QPushButton#SuccessButton {
    background-color: #10b981;
    color: #ffffff;
    border: none;
}

QPushButton#SuccessButton:hover {
    background-color: #059669;
}

QPushButton#SuccessButton:pressed {
    background-color: #065f46;
}

QPushButton#DangerButton {
    background-color: #ef4444;
    color: #ffffff;
    border: none;
}

QPushButton#DangerButton:hover {
    background-color: #dc2626;
}

QPushButton#DangerButton:pressed {
    background-color: #991b1b;
}

/* Lists and Tables */
QListWidget {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 5px;
}

QListWidget::item {
    padding: 10px;
    border-radius: 6px;
    margin-bottom: 2px;
}

QListWidget::item:hover {
    background-color: #1e293b;
}

QListWidget::item:selected {
    background-color: #0ea5e9;
    color: #ffffff;
}

QTableWidget {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    gridline-color: #1e293b;
}

QTableWidget::item {
    padding: 8px;
}

QHeaderView::section {
    background-color: #1e293b;
    color: #94a3b8;
    padding: 8px;
    border: none;
    font-weight: bold;
}

/* Scrollbars */
QScrollBar:vertical {
    background-color: #0b0f19;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #1e293b;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background-color: #334155;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Terminal Console Log Box */
QTextEdit#LogConsole {
    background-color: #020617;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    color: #38bdf8;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 10px;
}

/* Tab Widget Styling */
QTabWidget::pane {
    border: 1px solid #1e293b;
    background-color: #0f172a;
    border-radius: 8px;
}
QTabBar::tab {
    background-color: #0f172a;
    color: #94a3b8;
    padding: 10px 20px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid #1e293b;
    border-bottom: none;
    margin-right: 2px;
}
QTabBar::tab:hover {
    background-color: #1e293b;
    color: #f8fafc;
}
QTabBar::tab:selected {
    background-color: #0ea5e9;
    color: #ffffff;
    border-color: #0ea5e9;
}

/* Database list widget */
QListWidget#DatabaseList {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 6px;
}
QListWidget#DatabaseList::item {
    padding: 8px;
    border-bottom: 1px solid #1e293b;
    color: #cbd5e1;
}
QListWidget#DatabaseList::item:last {
    border-bottom: none;
}

/* Disk space progress bar */
QProgressBar#DiskProgressBar {
    border: 1px solid #1e293b;
    border-radius: 4px;
    background-color: #1e293b;
    text-align: center;
    color: #f8fafc;
    font-weight: bold;
    height: 20px;
}
QProgressBar#DiskProgressBar::chunk {
    background-color: #0ea5e9;
    border-radius: 3px;
}

/* Separator & Footer */
QFrame#PageSeparator {
    background-color: #1e293b;
    max-height: 1px;
}
QFrame#ProfileFooter {
    border-top: 1px solid #1e293b;
    padding: 15px;
}

/* Labels custom colors */
QLabel#SidebarTitleLabel {
    font-size: 15px;
    font-weight: bold;
    color: #0ea5e9;
}
QLabel#SidebarSubtitleLabel {
    font-size: 11px;
    color: #64748b;
}
QLabel#FormHeader {
    font-size: 15px;
    font-weight: bold;
    color: #f8fafc;
}
QLabel#DiskValueLabel {
    font-weight: bold;
    font-size: 13px;
    color: #f8fafc;
}
QLabel#FolderSizeLabel {
    color: #94a3b8;
    font-size: 12px;
}
"""
