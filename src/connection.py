import pymysql
from src.utils.logger import logger

class MySQLConnectionManager:
    def __init__(self, profile: dict):
        self.host = profile.get("host", "localhost")
        self.port = int(profile.get("port", 3306))
        self.user = profile.get("user", "root")
        self.password = profile.get("password", "")
        self.database = profile.get("database") or None

    def get_connection(self, select_db=True):
        """Establish a PyMySQL connection using the profile credentials."""
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database if select_db else None,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=5
        )

    @staticmethod
    def test_connection(profile: dict) -> tuple[bool, str]:
        """Static method to test connection credentials without persisting state."""
        connection = None
        try:
            connection = pymysql.connect(
                host=profile.get("host", "localhost"),
                port=int(profile.get("port", 3306)),
                user=profile.get("user", "root"),
                password=profile.get("password", ""),
                database=profile.get("database") or None,
                charset='utf8mb4',
                connect_timeout=5
            )
            return True, "Connection successful!"
        except Exception as e:
            logger.error(f"MySQL connection test failed: {str(e)}")
            return False, str(e)
        finally:
            if connection:
                connection.close()

    def get_databases(self) -> list[str]:
        """Fetch list of user databases (excluding MySQL system schemas)."""
        databases = []
        connection = None
        try:
            connection = self.get_connection(select_db=False)
            with connection.cursor() as cursor:
                cursor.execute("SHOW DATABASES")
                results = cursor.fetchall()
                exclude = ['information_schema', 'performance_schema', 'mysql', 'sys']
                for row in results:
                    db_name = list(row.values())[0]
                    if db_name not in exclude:
                        databases.append(db_name)
        except Exception as e:
            logger.error(f"Failed to fetch databases: {str(e)}")
        finally:
            if connection:
                connection.close()
        return databases

    def get_tables(self, database_name: str) -> list[str]:
        """Fetch list of tables inside a specific database."""
        tables = []
        connection = None
        try:
            # Connect directly to the specified database
            connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=database_name,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            with connection.cursor() as cursor:
                cursor.execute("SHOW TABLES")
                results = cursor.fetchall()
                for row in results:
                    tables.append(list(row.values())[0])
        except Exception as e:
            logger.error(f"Failed to fetch tables for db {database_name}: {str(e)}")
        finally:
            if connection:
                connection.close()
        return tables

    def get_columns(self, database_name: str, table_name: str) -> list[dict]:
        """
        Fetch columns for a specific table.
        Each column dict contains: 'name', 'type', 'is_date' (boolean flag)
        """
        columns = []
        connection = None
        try:
            connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=database_name,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            with connection.cursor() as cursor:
                cursor.execute(f"DESCRIBE `{table_name}`")
                results = cursor.fetchall()
                date_types = ['date', 'datetime', 'timestamp', 'time', 'year']
                for row in results:
                    col_name = row['Field']
                    col_type = row['Type'].lower()
                    is_date = any(dt in col_type for dt in date_types)
                    columns.append({
                        "name": col_name,
                        "type": row['Type'],
                        "is_date": is_date
                    })
        except Exception as e:
            logger.error(f"Failed to fetch columns for {database_name}.{table_name}: {str(e)}")
        finally:
            if connection:
                connection.close()
        return columns

    def get_db_stats(self) -> list[dict]:
        """
        Get database statistics (name, total size in MB, table count).
        Returns a list of dicts.
        """
        stats = []
        connection = None
        try:
            connection = self.get_connection(select_db=False)
            with connection.cursor() as cursor:
                # Query sizes
                query_sizes = """
                    SELECT table_schema AS 'database_name',
                           ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'size_mb',
                           COUNT(*) AS 'table_count'
                    FROM information_schema.tables
                    GROUP BY table_schema
                """
                cursor.execute(query_sizes)
                results = cursor.fetchall()
                exclude = ['information_schema', 'performance_schema', 'mysql', 'sys']
                for row in results:
                    db_name = row['database_name']
                    if db_name not in exclude:
                        stats.append({
                            "name": db_name,
                            "size_mb": float(row['size_mb'] or 0.0),
                            "table_count": int(row['table_count'] or 0)
                        })
        except Exception as e:
            logger.error(f"Failed to fetch database stats: {str(e)}")
        finally:
            if connection:
                connection.close()
        return stats

    def get_table_stats(self, database_name: str) -> list[dict]:
        """
        Get details for tables inside a database (name, rows, size in MB).
        """
        stats = []
        connection = None
        try:
            connection = self.get_connection(select_db=False)
            with connection.cursor() as cursor:
                query = """
                    SELECT table_name,
                           table_rows,
                           ROUND((data_length + index_length) / 1024 / 1024, 2) AS size_mb
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    ORDER BY (data_length + index_length) DESC
                """
                cursor.execute(query, (database_name,))
                results = cursor.fetchall()
                for row in results:
                    stats.append({
                        "name": row['table_name'],
                        "rows": int(row['table_rows'] or 0),
                        "size_mb": float(row['size_mb'] or 0.0)
                    })
        except Exception as e:
            logger.error(f"Failed to fetch table stats for {database_name}: {str(e)}")
        finally:
            if connection:
                connection.close()
        return stats
