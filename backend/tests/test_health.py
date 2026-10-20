from app.db.session import check_database_readiness


def test_database_readiness_uses_one_combined_query(monkeypatch):
    class Result:
        def fetchone(self):
            return (1, True)

    class Connection:
        execute_calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query):
            self.execute_calls += 1
            assert "pg_extension" in str(query)
            return Result()

    connection = Connection()

    class Engine:
        def connect(self):
            return connection

    monkeypatch.setattr("app.db.session.get_engine", lambda: Engine())

    assert check_database_readiness() == (True, True)
    assert connection.execute_calls == 1


def test_database_readiness_reports_database_errors(monkeypatch):
    class Engine:
        def connect(self):
            raise RuntimeError("controlled test failure")

    monkeypatch.setattr("app.db.session.get_engine", lambda: Engine())

    assert check_database_readiness() == (False, False)
