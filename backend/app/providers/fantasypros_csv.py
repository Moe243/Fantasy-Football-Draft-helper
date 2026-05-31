"""Parse FantasyPros rankings CSV uploads for the stdlib HTTP server."""

from __future__ import annotations

import csv
import io
import re
import sqlite3
from typing import Any

from .rankings_csv import import_ranking_rows

FANTASYPROS_CSV_SOURCE = "fantasypros_csv"

HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "player_name": ("PLAYER NAME", "PLAYER", "NAME", "FULL NAME"),
    "overall_rank": ("RK", "RANK", "OVERALL RANK", "OVERALL", "ECR"),
    "team": ("TEAM",),
    "position": ("POS", "POSITION"),
    "tier": ("TIERS", "TIER"),
    "bye_week": ("BYE WEEK", "BYE"),
    "rank_min": ("BEST", "RANK MIN", "MIN", "RANK_MIN"),
    "rank_max": ("WORST", "RANK MAX", "MAX", "RANK_MAX"),
    "rank_ave": ("AVG.", "AVG", "RANK AVE", "RANK_AVE", "AVERAGE", "AVE"),
    "rank_std": ("STD.DEV", "STD DEV", "STD", "RANK STD", "RANK_STD"),
    "position_rank": ("POS RANK",),
    "adp": ("ADP", "AVG ADP"),
    "ecr_vs_adp": ("ECR VS. ADP", "ECR VS ADP"),
}


def import_fantasypros_csv_upload(
    conn: sqlite3.Connection,
    body: bytes,
    content_type: str,
) -> dict[str, Any]:
    """Parse multipart upload and import rows as fantasypros_csv rankings."""
    file_bytes, filename = extract_uploaded_file(body, content_type)
    if not file_bytes:
        raise ValueError("No file uploaded")
    if not str(filename or "").lower().endswith(".csv"):
        raise ValueError("Uploaded file must be a .csv file")
    text = file_bytes.decode("utf-8-sig", errors="replace")
    rows = parse_fantasypros_csv_text(text)
    if not rows:
        raise ValueError("CSV file is empty or has no importable player rows")
    imported = import_ranking_rows(conn, FANTASYPROS_CSV_SOURCE, rows)
    return {
        "ok": True,
        "imported": imported["imported_count"],
        "source_name": FANTASYPROS_CSV_SOURCE,
        "imported_count": imported["imported_count"],
        "matched_players": imported["matched_players"],
        "created_players": imported["created_players"],
        "skipped_count": imported["skipped_count"],
    }


def extract_uploaded_file(body: bytes, content_type: str) -> tuple[bytes | None, str | None]:
    lowered = str(content_type or "").lower()
    if "multipart/form-data" not in lowered:
        raise ValueError("Content-Type must be multipart/form-data")
    match = re.search(r"boundary=([^;\s]+)", content_type, re.I)
    if not match:
        raise ValueError("Invalid multipart form data")
    boundary = match.group(1).strip().strip('"')
    delimiter = f"--{boundary}".encode()
    for part in body.split(delimiter):
        chunk = part.strip(b"\r\n")
        if not chunk or chunk == b"--":
            continue
        header_bytes, _, content = chunk.partition(b"\r\n\r\n")
        if not content:
            continue
        header_text = header_bytes.decode("utf-8", errors="replace")
        if "filename=" not in header_text.lower():
            continue
        filename_match = re.search(r'filename="([^"]+)"', header_text, re.I)
        filename = filename_match.group(1) if filename_match else "upload.csv"
        file_body = content.rstrip(b"\r\n")
        return file_body, filename
    return None, None


def parse_fantasypros_csv_text(text: str) -> list[dict[str, Any]]:
    if not str(text or "").strip():
        raise ValueError("CSV file is empty")
    delimiter = "\t" if text.count("\t") > text.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        raw_headers = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV file is empty") from exc
    headers = [normalize_header_label(cell) for cell in raw_headers]
    if not headers or all(not header for header in headers):
        raise ValueError("Invalid CSV format: missing header row")
    column_map = build_column_map(headers)
    if column_map.get("player_name") is None:
        raise ValueError("Missing required player name column (e.g. PLAYER NAME)")

    rows: list[dict[str, Any]] = []
    for raw_row in reader:
        if not any(str(cell or "").strip() for cell in raw_row):
            continue
        row = row_from_csv_record(headers, raw_row, column_map)
        if row:
            rows.append(row)
    return rows


def normalize_header_label(label: str) -> str:
    cleaned = str(label or "").strip().replace("\ufeff", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.upper()


def canonical_header_key(label: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", normalize_header_label(label)).strip()


def build_column_map(headers: list[str]) -> dict[str, int | None]:
    canonical_to_index = {canonical_header_key(header): index for index, header in enumerate(headers)}
    column_map: dict[str, int | None] = {}
    for field, aliases in HEADER_ALIASES.items():
        column_map[field] = None
        for alias in aliases:
            key = canonical_header_key(alias)
            if key in canonical_to_index:
                column_map[field] = canonical_to_index[key]
                break
    return column_map


def row_from_csv_record(
    headers: list[str],
    values: list[str],
    column_map: dict[str, int | None],
) -> dict[str, Any] | None:
    def cell(field: str) -> str:
        index = column_map.get(field)
        if index is None or index >= len(values):
            return ""
        return str(values[index] or "").strip()

    player_name = cell("player_name")
    if not player_name:
        return None

    pos_raw = cell("position")
    position, position_rank = split_position_value(pos_raw)
    row: dict[str, Any] = {
        "player_name": player_name,
        "team": cell("team") or None,
        "position": position or None,
        "overall_rank": parse_optional_number(cell("overall_rank"), as_int=True),
        "tier": parse_optional_number(cell("tier"), as_int=True),
        "bye_week": parse_optional_number(cell("bye_week"), as_int=True),
        "adp": parse_optional_number(cell("adp")),
        "rank_min": cell("rank_min") or None,
        "rank_max": cell("rank_max") or None,
        "rank_ave": cell("rank_ave") or None,
        "rank_std": cell("rank_std") or None,
        "ecr_vs_adp": parse_optional_number(cell("ecr_vs_adp")),
    }
    if position_rank:
        row["position_rank"] = position_rank
    elif pos_raw:
        row["position_rank"] = pos_raw

    for index, header in enumerate(headers):
        if index < len(values):
            extra_key = re.sub(r"[^a-z0-9]+", "_", header.lower()).strip("_")
            if extra_key and extra_key not in row:
                row[extra_key] = str(values[index] or "").strip()
    return row


def split_position_value(pos_value: str) -> tuple[str, str]:
    raw = str(pos_value or "").strip().upper()
    if not raw:
        return "", ""
    if raw == "DST" or raw.startswith("DST"):
        return "DEF", raw
    letters = re.match(r"^[A-Z]+", raw)
    return (letters.group(0) if letters else raw, raw)


def parse_optional_number(value: str, as_int: bool = False) -> int | float | None:
    text = str(value or "").strip()
    if not text or text == "-":
        return None
    try:
        if as_int:
            return int(float(text))
        return float(text)
    except ValueError:
        return None
