import os
import sys
import unittest
from unittest.mock import MagicMock, patch, mock_open

# Bootstrap path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.cleanup import MySQLCleanupManager
from src.backup import MySQLBackupManager

class TestServerManagerLogic(unittest.TestCase):
    def setUp(self):
        self.mock_profile = {
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "secure_password_123",
            "database": "sales_db"
        }

    @patch('pymysql.connect')
    def test_cleanup_chunked_deletion(self, mock_connect):
        """Test that the cleanup manager runs DELETE queries in a chunked loop."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Configure cursor rowcount to return 5000 rows twice, then 0
        # This simulates deleting 10,000 rows in batches of 5000
        mock_cursor.rowcount = 5000
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        # Instaniate manager
        manager = MySQLCleanupManager(self.mock_profile)
        
        # We override time.sleep to speed up tests
        with patch('time.sleep') as mock_sleep:
            # We simulate rowcount changes inside the loop
            # First call: returns 5000. Second call: returns 5000. Third call: returns 0.
            # We can use side_effect on rowcount property, but mock properties can be tricky.
            # An easier way is to set rowcount as a property with side effects or simulate it by patching execute.
            rowcount_values = [5000, 5000, 0]
            type(mock_cursor).rowcount = unittest.mock.PropertyMock(side_effect=rowcount_values)
            
            success, deleted, msg = manager.run_cleanup("sales_db", "orders", "created_at", 6, chunk_size=5000)
            
            self.assertTrue(success)
            self.assertEqual(deleted, 10000)
            self.assertEqual(mock_cursor.execute.call_count, 3)
            mock_sleep.assert_called_with(0.1)

    @patch('pymysql.connect')
    def test_backup_pure_python_engine(self, mock_connect):
        """Test that the pure Python backup engine correctly queries structure and streams data."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        
        # Mock SHOW TABLES and SHOW CREATE TABLE
        mock_cursor.fetchall.return_value = [{"Tables_in_sales_db": "customers"}]
        mock_cursor.fetchone.return_value = {"Create Table": "CREATE TABLE `customers` (\n  `id` int(11) NOT NULL\n) ENGINE=InnoDB"}
        
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock Server-Side connection and streaming cursor
        mock_ss_conn = MagicMock()
        mock_ss_cursor = MagicMock()
        
        # SSDictCursor fetchmany returns a batch of rows once, then None/empty list
        mock_ss_cursor.fetchmany.side_effect = [
            [{"id": 1, "name": "John Doe"}, {"id": 2, "name": "Jane Smith"}],
            [] # End of streaming
        ]
        mock_ss_conn.cursor.return_value.__enter__.return_value = mock_ss_cursor
        
        # Return standard connection for schema query, and SS connection for data stream
        mock_connect.side_effect = [mock_conn, mock_ss_conn]
        
        manager = MySQLBackupManager(self.mock_profile, backup_dir="dummy_backups", compress=False)
        
        # Mock file writing to avoid creating physical backup files
        m_open = mock_open()
        with patch('builtins.open', m_open):
            success, msg = manager._run_python_dump("sales_db", tables=["customers"], output_path="dummy.sql")
            
            self.assertTrue(success)
            
            # Verify file write operations were called
            handle = m_open()
            # Check that structural SQL drop and create and insert statements are written
            written_data = "".join([call[0][0] for call in handle.write.call_args_list])
            self.assertIn("DROP TABLE IF EXISTS `customers`;", written_data)
            self.assertIn("CREATE TABLE `customers`", written_data)
            self.assertIn("INSERT INTO `customers` VALUES", written_data)
            self.assertIn("(1, 'John Doe')", written_data)
            self.assertIn("(2, 'Jane Smith')", written_data)

if __name__ == '__main__':
    unittest.main()
