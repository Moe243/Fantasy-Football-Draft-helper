import io
import sqlite3
import unittest

from backend.app import db
from backend.app.providers.fantasypros_csv import (
    FANTASYPROS_CSV_SOURCE,
    import_fantasypros_csv_upload,
    parse_fantasypros_csv_text,
)
from backend.app.providers.rankings_csv import import_ranking_rows, resolve_rankings_source_name


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


def build_multipart(filename: str, content: str, field_name: str = "file") -> tuple[bytes, str]:
    boundary = "----FantasyBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        "Content-Type: text/csv\r\n"
        "\r\n"
        f"{content}\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")
    content_type = f"multipart/form-data; boundary={boundary}"
    return body, content_type


class RankingsImportTests(unittest.TestCase):
    def test_resolve_rankings_source_name_defaults_to_manual(self):
        self.assertEqual(resolve_rankings_source_name(None), "manual_rankings")
        self.assertEqual(resolve_rankings_source_name(""), "manual_rankings")
        self.assertEqual(resolve_rankings_source_name("fantasypros"), "fantasypros")

    def test_manual_rankings_import_without_source_name(self):
        conn = memory_db()
        result = import_ranking_rows(
            conn,
            resolve_rankings_source_name(None),
            [
                {
                    "player_name": "Ja'Marr Chase",
                    "team": "CIN",
                    "position": "WR",
                    "overall_rank": 2,
                }
            ],
        )
        self.assertEqual(result["source_name"], "manual_rankings")
        self.assertEqual(result["imported_count"], 1)

    def test_parse_fantasypros_csv_with_common_columns(self):
        csv_text = (
            "RK,TIERS,PLAYER NAME,TEAM,POS,BYE WEEK,BEST,WORST,AVG.,STD.DEV,ECR\n"
            "1,1,Bijan Robinson,ATL,RB1,11,1,3,1.95,0.97,1\n"
        )
        rows = parse_fantasypros_csv_text(csv_text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["player_name"], "Bijan Robinson")
        self.assertEqual(rows[0]["position"], "RB")
        self.assertEqual(rows[0]["position_rank"], "RB1")
        self.assertEqual(rows[0]["overall_rank"], 1)

    def test_parse_fantasypros_csv_requires_player_name_column(self):
        with self.assertRaises(ValueError) as ctx:
            parse_fantasypros_csv_text("RK,TEAM\n1,ATL\n")
        self.assertIn("player name", str(ctx.exception).lower())

    def test_import_fantasypros_csv_upload(self):
        conn = memory_db()
        csv_text = (
            "RK,PLAYER NAME,TEAM,POS,BYE\n"
            "1,Ja'Marr Chase,CIN,WR1,10\n"
        )
        body, content_type = build_multipart("fantasypros.csv", csv_text)
        result = import_fantasypros_csv_upload(conn, body, content_type)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source_name"], FANTASYPROS_CSV_SOURCE)
        self.assertEqual(result["imported"], 1)

    def test_import_fantasypros_csv_upload_no_file(self):
        conn = memory_db()
        with self.assertRaises(ValueError) as ctx:
            import_fantasypros_csv_upload(conn, b"", "multipart/form-data; boundary=x")
        self.assertIn("no file", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
