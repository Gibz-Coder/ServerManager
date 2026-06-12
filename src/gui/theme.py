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
    background-color: #6366f1;
    border-color: #6366f1;
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
"""
