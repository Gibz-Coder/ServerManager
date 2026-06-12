import time
import pymysql
from src.utils.logger import logger

class MySQLCleanupManager:
    def __init__(self, profile: dict):
        self.profile = profile

    def run_dry_run(self, database: str, table: str, column: str, months: int) -> tuple[bool, int, str]:
        """
        Count how many rows would be deleted by the retention policy.
        Returns (success, affected_rows_count, message).
        """
        connection = None
        try:
            # Connect specifically to target database
            connection = pymysql.connect(
                host=self.profile.get("host", "localhost"),
                port=int(self.profile.get("port", 3306)),
                user=self.profile.get("user", "root"),
                password=self.profile.get("password", ""),
                database=database,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            
            with connection.cursor() as cursor:
                # Query to count matching rows
                query = f"""
                    SELECT COUNT(*) AS row_count
                    FROM `{table}`
                    WHERE `{column}` < DATE_SUB(NOW(), INTERVAL %s MONTH)
                """
                logger.info(f"Dry run query on {database}.{table}.{column} older than {months} months.")
                cursor.execute(query, (months,))
                result = cursor.fetchone()
                count = result.get('row_count', 0) if result else 0
                return True, count, f"Found {count} rows older than {months} months."
        except Exception as e:
            err_msg = f"Failed dry run for {database}.{table}: {str(e)}"
            logger.error(err_msg)
            return False, 0, err_msg
        finally:
            if connection:
                connection.close()

    def run_cleanup(self, database: str, table: str, column: str, months: int, chunk_size: int = 5000) -> tuple[bool, int, str]:
        """
        Perform chunked deletion of records older than the retention threshold.
        Deletes in increments of `chunk_size` to prevent row locks and server lag.
        Returns (success, total_deleted_rows, message).
        """
        connection = None
        total_deleted = 0
        
        logger.info(f"Starting database cleanup: {database}.{table}.{column} older than {months} months (chunks of {chunk_size}).")
        
        try:
            connection = pymysql.connect(
                host=self.profile.get("host", "localhost"),
                port=int(self.profile.get("port", 3306)),
                user=self.profile.get("user", "root"),
                password=self.profile.get("password", ""),
                database=database,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True  # Important: commit deletes immediately
            )
            
            # Sub-query for chunked deletion (MySQL requires LIMIT in DELETE)
            # Query format: DELETE FROM `table` WHERE `column` < DATE_SUB(NOW(), INTERVAL %s MONTH) LIMIT %s
            delete_query = f"""
                DELETE FROM `{table}`
                WHERE `{column}` < DATE_SUB(NOW(), INTERVAL %s MONTH)
                LIMIT %s
            """
            
            with connection.cursor() as cursor:
                chunk_index = 1
                while True:
                    start_time = time.time()
                    cursor.execute(delete_query, (months, chunk_size))
                    rows_affected = cursor.rowcount
                    
                    if rows_affected == 0:
                        break
                        
                    total_deleted += rows_affected
                    elapsed = time.time() - start_time
                    logger.info(f"Chunk {chunk_index}: Deleted {rows_affected} rows in {elapsed:.3f}s. (Total: {total_deleted})")
                    
                    chunk_index += 1
                    # Give the server a tiny breath (100ms) to process other transactions
                    time.sleep(0.1)
            
            success_msg = f"Cleanup complete. Total rows deleted: {total_deleted}."
            logger.info(success_msg)
            return True, total_deleted, success_msg
            
        except Exception as e:
            err_msg = f"Cleanup execution failed: {str(e)}"
            logger.error(err_msg)
            return False, total_deleted, err_msg
        finally:
            if connection:
                connection.close()
