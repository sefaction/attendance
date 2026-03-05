from __future__ import annotations

import html
import os
import sqlite3
from contextlib import closing
from datetime import date
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

DB_PATH = os.environ.get("ATTENDANCE_DB", "/data/attendance.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    parent = os.path.dirname(DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with closing(get_conn()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS attendance (
                user_id INTEGER NOT NULL,
                attended_on TEXT NOT NULL,
                PRIMARY KEY (user_id, attended_on),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()


def redirect(start_response, location: str):
    start_response("303 See Other", [("Location", location)])
    return [b""]


def get_month(query: dict[str, list[str]]) -> tuple[int, int]:
    month = (query.get("month") or [""])[0]
    today = date.today()
    if month and "-" in month:
        y, m = month.split("-", 1)
        return int(y), int(m)
    return today.year, today.month


def render_index(query: dict[str, list[str]]) -> bytes:
    year, month = get_month(query)
    with closing(get_conn()) as conn:
        users = conn.execute("SELECT id, name FROM users ORDER BY name COLLATE NOCASE").fetchall()
        records = conn.execute(
            "SELECT user_id, attended_on FROM attendance WHERE substr(attended_on, 1, 7) = ?",
            (f"{year:04d}-{month:02d}",),
        ).fetchall()

    days_in_month = 31
    while True:
        try:
            date(year, month, days_in_month)
            break
        except ValueError:
            days_in_month -= 1

    marks = {(r["user_id"], r["attended_on"]) for r in records}
    prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)

    head_cells = "".join(f"<th>{d}</th>" for d in range(1, days_in_month + 1))
    body_rows = []
    month_string = f"{year:04d}-{month:02d}"

    for user in users:
        cells = []
        for d in range(1, days_in_month + 1):
            day_str = f"{year:04d}-{month:02d}-{d:02d}"
            checked = (user["id"], day_str) in marks
            marker = "X" if checked else ""
            cls = "mark checked" if checked else "mark"
            cells.append(
                "<td><form method='post' action='/attendance/toggle'>"
                f"<input type='hidden' name='user_id' value='{user['id']}'/>"
                f"<input type='hidden' name='attended_on' value='{day_str}'/>"
                f"<button type='submit' class='{cls}'>{marker}</button>"
                "</form></td>"
            )

        body_rows.append(
            "<tr>"
            f"<td>{html.escape(user['name'])}</td>"
            + "".join(cells)
            + "<td><form method='post' action='/users/delete'>"
            f"<input type='hidden' name='user_id' value='{user['id']}'/>"
            f"<input type='hidden' name='month' value='{month_string}'/>"
            "<button class='danger' type='submit'>Remove</button>"
            "</form></td></tr>"
        )

    rows_html = "".join(body_rows) if body_rows else "<tr><td colspan='999'>No users added yet.</td></tr>"

    page = f"""<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Attendance Tracker</title><link rel='stylesheet' href='/static/styles.css'></head>
<body><main><h1>Attendance Tracker</h1>
<section class='card'><h2>Users</h2>
<form method='post' action='/users' class='inline-form'>
<input type='hidden' name='month' value='{month_string}' />
<input type='text' name='name' placeholder='Add employee name' required />
<button type='submit'>Add User</button></form></section>
<section class='card'><div class='month-nav'>
<a href='/?month={prev_year:04d}-{prev_month:02d}'>← Previous</a>
<h2>{month_string}</h2>
<a href='/?month={next_year:04d}-{next_month:02d}'>Next →</a></div>
<div class='table-wrap'><table><thead><tr><th>User</th>{head_cells}<th>Actions</th></tr></thead>
<tbody>{rows_html}</tbody></table></div></section></main></body></html>"""
    return page.encode("utf-8")


def read_post(environ) -> dict[str, list[str]]:
    length = int(environ.get("CONTENT_LENGTH") or 0)
    body = environ["wsgi.input"].read(length).decode("utf-8")
    return parse_qs(body)


def serve_static(path: str, start_response):
    if path == "/static/styles.css":
        with open("static/styles.css", "rb") as f:
            data = f.read()
        start_response("200 OK", [("Content-Type", "text/css; charset=utf-8")])
        return [data]
    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"Not found"]


def application(environ, start_response):
    method = environ["REQUEST_METHOD"]
    path = environ.get("PATH_INFO", "/")
    query = parse_qs(environ.get("QUERY_STRING", ""))

    if method == "GET" and path.startswith("/static/"):
        return serve_static(path, start_response)

    if method == "GET" and path == "/":
        data = render_index(query)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [data]

    if method == "POST" and path == "/users":
        form = read_post(environ)
        name = (form.get("name") or [""])[0].strip()
        month = (form.get("month") or [""])[0]
        if name:
            with closing(get_conn()) as conn:
                conn.execute("INSERT OR IGNORE INTO users(name) VALUES (?)", (name,))
                conn.commit()
        return redirect(start_response, f"/?month={month}" if month else "/")

    if method == "POST" and path == "/users/delete":
        form = read_post(environ)
        user_id = int((form.get("user_id") or ["0"])[0])
        month = (form.get("month") or [""])[0]
        with closing(get_conn()) as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
        return redirect(start_response, f"/?month={month}" if month else "/")

    if method == "POST" and path == "/attendance/toggle":
        form = read_post(environ)
        user_id = int((form.get("user_id") or ["0"])[0])
        attended_on = (form.get("attended_on") or [""])[0]
        with closing(get_conn()) as conn:
            exists = conn.execute(
                "SELECT 1 FROM attendance WHERE user_id = ? AND attended_on = ?",
                (user_id, attended_on),
            ).fetchone()
            if exists:
                conn.execute("DELETE FROM attendance WHERE user_id = ? AND attended_on = ?", (user_id, attended_on))
            else:
                conn.execute("INSERT INTO attendance(user_id, attended_on) VALUES (?, ?)", (user_id, attended_on))
            conn.commit()
        return redirect(start_response, f"/?month={attended_on[:7]}")

    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"Not found"]


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "8080"))
    print(f"Attendance Tracker running on 0.0.0.0:{port}")
    with make_server("0.0.0.0", port, application) as server:
        server.serve_forever()
