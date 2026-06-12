import os
import subprocess
import zipfile
from datetime import datetime
import pymysql
from src.utils.logger import logger

class MySQLBackupManager:
    def __init__(self, profile: dict, backup_dir: str, mysqldump_path: str = "", compress: bool = True):
        self.profile = profile
        self.backup_dir = backup_dir
        self.mysqldump_path = mysqldump_path
        self.compress = compress
        os.makedirs(self.backup_dir, exist_ok=True)

    def run_backup(self, database_name: str, tables: list[str] = None) -> tuple[bool, str]:
        """
        Execute the backup process for the specified database and optional tables.
        Tries to use mysqldump first. If that's unavailable or fails, falls back to pure-Python dump.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "partial" if tables else "full"
        sql_filename = f"backup_{database_name}_{suffix}_{timestamp}.sql"
        sql_filepath = os.path.join(self.backup_dir, sql_filename)
        
        logger.info(f"Starting backup for database: '{database_name}' (Tables: {tables or 'All'}).")
        
        success = False
        message = ""
        
        # Try mysqldump
        if self.mysqldump_path and os.path.exists(self.mysqldump_path):
            success, message = self._run_mysqldump(database_name, tables, sql_filepath)
        else:
            logger.info("mysqldump executable path not specified or not found. Using pure-Python backup engine.")
            success, message = self._run_python_dump(database_name, tables, sql_filepath)

        if not success:
            # Clean up raw SQL file if backup failed
            if os.path.exists(sql_filepath):
                try:
                    os.remove(sql_filepath)
                except Exception:
                    pass
            return False, message

        # Compression if requested
        if self.compress:
            zip_filename = f"{sql_filename}.zip"
            zip_filepath = os.path.join(self.backup_dir, zip_filename)
            try:
                logger.info(f"Compressing backup SQL file into {zip_filename}...")
                with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(sql_filepath, arcname=sql_filename)
                
                # Delete original SQL file
                os.remove(sql_filepath)
                logger.info("Backup compression successful.")
                return True, f"Backup completed successfully: {zip_filepath}"
            except Exception as e:
                err_msg = f"Backup succeeded but compression failed: {str(e)}"
                logger.error(err_msg)
                return True, f"Backup completed (uncompressed): {sql_filepath}. Error compressing: {str(e)}"
        
        return True, f"Backup completed successfully: {sql_filepath}"

    def _run_mysqldump(self, database_name: str, tables: list[str], output_path: str) -> tuple[bool, str]:
        """Run mysqldump binary via subprocess securely."""
        cmd = [
            self.mysqldump_path,
            f"--host={self.profile.get('host', 'localhost')}",
            f"--port={self.profile.get('port', 3306)}",
            f"--user={self.profile.get('user', 'root')}",
            "--skip-lock-tables",  # avoid blocking active server transactions
            "--add-drop-table",
            database_name
        ]
        if tables:
            cmd.extend(tables)

        env = os.environ.copy()
        # Set password securely via env variable (hides it from process view list)
        env["MYSQL_PWD"] = self.profile.get("password", "")

        try:
            logger.info(f"Executing: {' '.join(cmd[:-1])} [PASSWORD MASKED]")
            with open(output_path, "w", encoding="utf-8") as out_file:
                process = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=out_file,
                    stderr=subprocess.PIPE,
                    text=True
                )
                _, stderr = process.communicate()

                if process.returncode == 0:
                    logger.info("mysqldump execution completed successfully.")
                    return True, "mysqldump successful"
                else:
                    logger.error(f"mysqldump failed with exit code {process.returncode}: {stderr}")
                    return False, f"mysqldump error: {stderr}"
        except Exception as e:
            logger.error(f"Failed to execute mysqldump: {str(e)}")
            return False, f"Execution exception: {str(e)}"

    def _run_python_dump(self, database_name: str, tables: list[str], output_path: str) -> tuple[bool, str]:
        """Pure Python fallback dumper using PyMySQL server-side cursors to steam records."""
        connection = None
        try:
            # Connect to specific database
            connection = pymysql.connect(
                host=self.profile.get("host", "localhost"),
                port=int(self.profile.get("port", 3306)),
                user=self.profile.get("user", "root"),
                password=self.profile.get("password", ""),
                database=database_name,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )

            # If tables list is empty, fetch all tables
            if not tables:
                with connection.cursor() as cursor:
                    cursor.execute("SHOW TABLES")
                    tables = [list(row.values())[0] for row in cursor.fetchall()]

            with open(output_path, "w", encoding="utf-8") as f:
                # Dumper Header
                f.write(f"-- MySQL Server Manager Backup\n")
                f.write(f"-- Host: {self.profile.get('host')}\n")
                f.write(f"-- Database: {database_name}\n")
                f.write(f"-- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                f.write("SET FOREIGN_KEY_CHECKS=0;\n")
                f.write("SET UNIQUE_CHECKS=0;\n")
                f.write("SET SQL_MODE='NO_AUTO_VALUE_ON_ZERO';\n\n")

                for table in tables:
                    logger.info(f"Dumping table schema and data: {table}")
                    
                    # 1. Write Drop & Show Create Table (DDL)
                    f.write(f"--\n-- Table structure for table `{table}`\n--\n\n")
                    f.write(f"DROP TABLE IF EXISTS `{table}`;\n")
                    
                    with connection.cursor() as cursor:
                        try:
                            cursor.execute(f"SHOW CREATE TABLE `{table}`")
                            create_row = cursor.fetchone()
                            # PyMySQL returns a dict, key is 'Create Table'
                            create_sql = create_row.get('Create Table') or create_row.get('Create View')
                            if create_sql:
                                f.write(f"{create_sql};\n\n")
                        except Exception as table_err:
                            logger.error(f"Error reading structure of {table}: {str(table_err)}")
                            f.write(f"-- Warning: Could not dump structure for `{table}`: {str(table_err)}\n\n")
                            continue

                    # 2. Dump Table Rows (using a separate streaming cursor)
                    f.write(f"--\n-- Dumping data for table `{table}`\n--\n\n")
                    
                    # We use PyMySQL SS (Server Side) cursor to stream huge tables
                    ss_conn = pymysql.connect(
                        host=self.profile.get("host", "localhost"),
                        port=int(self.profile.get("port", 3306)),
                        user=self.profile.get("user", "root"),
                        password=self.profile.get("password", ""),
                        database=database_name,
                        charset='utf8mb4',
                        cursorclass=pymysql.cursors.SSDictCursor
                    )
                    
                    try:
                        with ss_conn.cursor() as ss_cursor:
                            ss_cursor.execute(f"SELECT * FROM `{table}`")
                            
                            batch_size = 500
                            rows_written = 0
                            
                            while True:
                                rows = ss_cursor.fetchmany(batch_size)
                                if not rows:
                                    break
                                
                                # Generate multi-row INSERT statement
                                values_list = []
                                for row in rows:
                                    escaped_vals = []
                                    for val in row.values():
                                        if val is None:
                                            escaped_vals.append("NULL")
                                        elif isinstance(val, (int, float)):
                                            escaped_vals.append(str(val))
                                        elif isinstance(val, (bytes, bytearray)):
                                            # Binary hex representation
                                            escaped_vals.append(f"X'{val.hex()}'")
                                        else:
                                            # String escapes
                                            # Escape backslashes and single quotes
                                            escaped = str(val).replace("\\", "\\\\").replace("'", "\\'")
                                            escaped_vals.append(f"'{escaped}'")
                                    
                                    values_list.append(f"({', '.join(escaped_vals)})")
                                
                                if values_list:
                                    f.write(f"INSERT INTO `{table}` VALUES {', '.join(values_list)};\n")
                                    rows_written += len(values_list)
                            
                            logger.info(f"Dumped {rows_written} rows from table '{table}'.")
                            f.write("\n")
                    except Exception as data_err:
                        logger.error(f"Error dumping data for table {table}: {str(data_err)}")
                        f.write(f"-- Warning: Data dump failed for `{table}`: {str(data_err)}\n\n")
                    finally:
                        ss_conn.close()
                
                f.write("SET FOREIGN_KEY_CHECKS=1;\n")
                f.write("SET UNIQUE_CHECKS=1;\n")
                
            return True, "Python dump successful"
        except Exception as e:
            logger.error(f"Pure Python backup engine failed: {str(e)}")
            return False, f"Python dump error: {str(e)}"
        finally:
            if connection:
                connection.close()
