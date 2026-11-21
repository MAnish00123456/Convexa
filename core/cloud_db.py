"""Small sqlite3-compatible adapter around the official libSQL driver.

Uses a remote primary, never an ephemeral embedded replica. A local libSQL
file can be used by tests to exercise the identical SQL and row adapter.
"""
import sqlite3


class Row(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class Cursor:
    def __init__(self, cursor):
        self.lastrowid = cursor.lastrowid
        self.rowcount = cursor.rowcount
        columns = [d[0] for d in (cursor.description or ())]
        # Fully consume before another statement uses the connection.
        self.rows = iter([Row(zip(columns, row)) for row in (cursor.fetchall() or [])])

    def fetchone(self):
        return next(self.rows, None)

    def fetchall(self):
        return list(self.rows)

    def __iter__(self):
        return self.rows


class Connection:
    def __init__(self, database, auth_token=''):
        import libsql
        self.raw = libsql.connect(database, auth_token=auth_token, timeout=20)

    def execute(self, sql, args=()):
        return Cursor(self.raw.execute(sql, tuple(args)))

    def executescript(self, script):
        statement = ''
        for line in script.splitlines(True):
            # Schema statements can share a line; use SQLite's parser to split.
            for char in line:
                statement += char
                if char == ';' and sqlite3.complete_statement(statement):
                    if 'PRAGMA journal_mode' not in statement:
                        self.execute(statement)
                    statement = ''
        if statement.strip():
            self.execute(statement)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()
