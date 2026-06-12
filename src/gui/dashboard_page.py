from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, 
                               QLabel, QPushButton, QTableWidget, QTableWidgetItem, 
                               QHeaderView, QAbstractItemView)
from PySide6.QtCore import Qt, QSize
from src.connection import MySQLConnectionManager
from src.utils.logger import logger

class DashboardPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        
        # Header
        header_layout = QVBoxLayout()
        header_layout.setSpacing(5)
        
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        header_layout.addWidget(title)
        
        subtitle = QLabel("Overview of your MySQL server database size, table records, and schema health.")
        subtitle.setObjectName("PageSubtitle")
        header_layout.addWidget(subtitle)
        
        layout.addLayout(header_layout)
        
        # Cards Layout
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(15)
        
        # Card 1: Connection Info
        self.card_conn = QFrame()
        self.card_conn.setObjectName("CardFrame")
        cc_layout = QVBoxLayout(self.card_conn)
        
        cc_title = QLabel("Server Status")
        cc_title.setObjectName("CardTitle")
        cc_layout.addWidget(cc_title)
        
        self.lbl_conn_status = QLabel("Disconnected")
        self.lbl_conn_status.setObjectName("CardValue")
        self.lbl_conn_status.setStyleSheet("color: #ef4444;")
        cc_layout.addWidget(self.lbl_conn_status)
        
        self.lbl_conn_details = QLabel("No active connection profile.")
        self.lbl_conn_details.setObjectName("CardDesc")
        cc_layout.addWidget(self.lbl_conn_details)
        cards_layout.addWidget(self.card_conn)
        
        # Card 2: Database Size
        self.card_size = QFrame()
        self.card_size.setObjectName("CardFrame")
        cs_layout = QVBoxLayout(self.card_size)
        
        cs_title = QLabel("Selected Database Size")
        cs_title.setObjectName("CardTitle")
        cs_layout.addWidget(cs_title)
        
        self.lbl_db_size = QLabel("0.00 MB")
        self.lbl_db_size.setObjectName("CardValue")
        cs_layout.addWidget(self.lbl_db_size)
        
        self.lbl_db_details = QLabel("0 Tables | 0 Databases")
        self.lbl_db_details.setObjectName("CardDesc")
        cs_layout.addWidget(self.lbl_db_details)
        cards_layout.addWidget(self.card_size)
        
        # Card 3: Quick Stats
        self.card_rules = QFrame()
        self.card_rules.setObjectName("CardFrame")
        cr_layout = QVBoxLayout(self.card_rules)
        
        cr_title = QLabel("Rules & Schedules")
        cr_title.setObjectName("CardTitle")
        cr_layout.addWidget(cr_title)
        
        self.lbl_rules_count = QLabel("0 Active Rules")
        self.lbl_rules_count.setObjectName("CardValue")
        cr_layout.addWidget(self.lbl_rules_count)
        
        self.lbl_rules_details = QLabel("Backup Schedule: Disabled")
        self.lbl_rules_details.setObjectName("CardDesc")
        cr_layout.addWidget(self.lbl_rules_details)
        cards_layout.addWidget(self.card_rules)
        
        layout.addLayout(cards_layout)
        
        # Table Header/Controls
        table_controls_layout = QHBoxLayout()
        table_label = QLabel("Database Table Metrics")
        table_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #f4f4f5;")
        table_controls_layout.addWidget(table_label)
        
        table_controls_layout.addStretch()
        
        btn_refresh = QPushButton("Refresh Stats")
        btn_refresh.setObjectName("PrimaryButton")
        btn_refresh.clicked.connect(self.refresh_page)
        table_controls_layout.addWidget(btn_refresh)
        
        layout.addLayout(table_controls_layout)
        
        # Table Widgets
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(3)
        self.table_widget.setHorizontalHeaderLabels(["Table Name", "Total Rows", "Size (MB)"])
        self.table_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table_widget.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_widget.setSelectionMode(QAbstractItemView.NoSelection)
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.setStyleSheet("""
            QTableWidget {
                alternate-background-color: #1a1a1e;
                background-color: #131316;
            }
        """)
        
        layout.addWidget(self.table_widget)

    def refresh_page(self):
        """Loads server statistics using the active connection profile."""
        profile = self.main_window.active_profile
        config = self.main_window.config
        
        # Reset labels
        self.lbl_conn_status.setText("Disconnected")
        self.lbl_conn_status.setStyleSheet("color: #ef4444;")
        self.lbl_conn_details.setText("No active connection profile.")
        self.lbl_db_size.setText("0.00 MB")
        self.lbl_db_details.setText("0 Tables | 0 Databases")
        self.table_widget.setRowCount(0)
        
        # Read schedule configs
        b_sched = config.get("backup_settings", {})
        c_sched = config.get("retention_schedule", {})
        b_status = "Enabled" if b_sched.get("schedule_enabled") else "Disabled"
        c_status = "Enabled" if c_sched.get("schedule_enabled") else "Disabled"
        rules_cnt = len([r for r in config.get("retention_rules", []) if r.get("enabled", True)])
        
        self.lbl_rules_count.setText(f"{rules_cnt} Active Rules")
        self.lbl_rules_details.setText(f"Backups: {b_status} | Cleanup: {c_status}")
        
        if not profile:
            return
            
        host = profile.get("host")
        port = profile.get("port")
        db = profile.get("database")
        
        self.lbl_conn_details.setText(f"Host: {host}:{port}")
        
        # Test connection & load stats
        success, message = MySQLConnectionManager.test_connection(profile)
        if not success:
            self.lbl_conn_status.setText("Error")
            self.lbl_conn_status.setStyleSheet("color: #ef4444;")
            self.lbl_conn_details.setText(f"Failed to connect: {message}")
            return
            
        self.lbl_conn_status.setText("Connected")
        self.lbl_conn_status.setStyleSheet("color: #10b981;")
        
        mgr = MySQLConnectionManager(profile)
        
        # Fetch databases list to count them
        dbs = mgr.get_databases()
        db_count = len(dbs)
        
        if not db:
            self.lbl_db_size.setText("N/A")
            self.lbl_db_details.setText(f"No database selected | {db_count} Databases")
            return
            
        # Get active db stats
        db_stats = mgr.get_db_stats()
        active_db_size = 0.0
        table_count = 0
        
        for dbs_row in db_stats:
            if dbs_row['name'].lower() == db.lower():
                active_db_size = dbs_row['size_mb']
                table_count = dbs_row['table_count']
                break
                
        self.lbl_db_size.setText(f"{active_db_size:.2f} MB")
        self.lbl_db_details.setText(f"{table_count} Tables | {db_count} Databases")
        
        # Load tables data
        try:
            tables_stats = mgr.get_table_stats(db)
            self.table_widget.setRowCount(len(tables_stats))
            for row_idx, stat in enumerate(tables_stats):
                name_item = QTableWidgetItem(stat['name'])
                
                rows_item = QTableWidgetItem(f"{stat['rows']:,}")
                rows_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                
                size_item = QTableWidgetItem(f"{stat['size_mb']:.2f}")
                size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                
                self.table_widget.setItem(row_idx, 0, name_item)
                self.table_widget.setItem(row_idx, 1, rows_item)
                self.table_widget.setItem(row_idx, 2, size_item)
        except Exception as e:
            logger.error(f"Dashboard failed to populate tables table: {str(e)}")
