from __future__ import annotations

import html
import os
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from urllib.parse import parse_qs, urlencode
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
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                manager_name TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                department TEXT NOT NULL DEFAULT '',
                department_id INTEGER,
                FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS attendance (
                user_id INTEGER NOT NULL,
                attended_on TEXT NOT NULL,
                PRIMARY KEY (user_id, attended_on),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """
        )

        user_cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "department" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN department TEXT NOT NULL DEFAULT ''")
        if "department_id" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN department_id INTEGER")

        dept_cols = [r[1] for r in conn.execute("PRAGMA table_info(departments)").fetchall()]
        if "manager_name" not in dept_cols:
            conn.execute("ALTER TABLE departments ADD COLUMN manager_name TEXT NOT NULL DEFAULT ''")

        legacy_departments = conn.execute(
            "SELECT DISTINCT trim(department) AS department FROM users WHERE trim(department) <> ''"
        ).fetchall()
        for row in legacy_departments:
            conn.execute("INSERT OR IGNORE INTO departments(name) VALUES (?)", (row["department"],))

        conn.execute(
            """
            UPDATE users
            SET department_id = (
                SELECT d.id FROM departments d WHERE d.name = trim(users.department)
            )
            WHERE department_id IS NULL AND trim(department) <> ''
            """
        )
        conn.commit()


def redirect(start_response, location: str):
    start_response("303 See Other", [("Location", location)])
    return [b""]


def parse_month(query: dict[str, list[str]]) -> tuple[int, int]:
    month = (query.get("month") or [""])[0]
    today = date.today()
    if month and "-" in month:
        y, m = month.split("-", 1)
        return int(y), int(m)
    return today.year, today.month


def sunday_for_day(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def safe_date(value: str, fallback: date) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return fallback


def build_url(params: dict[str, str]) -> str:
    kept = {k: v for k, v in params.items() if v}
    return "/" if not kept else "/?" + urlencode(kept)


def state_from_query(query: dict[str, list[str]]) -> dict[str, str]:
    return {
        "mode": (query.get("mode") or [""])[0],
        "month": (query.get("month") or [""])[0],
        "start": (query.get("start") or [""])[0],
        "department_id": (query.get("department_id") or [""])[0],
    }


def hidden_inputs(state: dict[str, str]) -> str:
    return "".join(
        f"<input type='hidden' name='{html.escape(k)}' value='{html.escape(v)}'/>" for k, v in state.items() if v
    )


def render_departments_page(query: dict[str, list[str]]) -> bytes:
    state = state_from_query(query)
    back_url = build_url(state)
    with closing(get_conn()) as conn:
        departments = conn.execute("SELECT id, name, manager_name FROM departments ORDER BY name COLLATE NOCASE").fetchall()

    rows = "".join(
        f"<tr><td>{html.escape(r['name'])}</td><td>{html.escape(r['manager_name'] or '—')}</td></tr>" for r in departments
    ) or "<tr><td colspan='2'>No departments yet.</td></tr>"

    page = f"""<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Departments - Attendance Tracker</title><link rel='stylesheet' href='/static/styles.css'></head>
<body><main><h1>Departments</h1>
<section class='card'>
<form method='post' action='/departments' class='inline-form'>
{hidden_inputs(state)}
<input type='text' name='name' placeholder='Department name' required />
<input type='text' name='manager_name' placeholder='Department manager name' />
<button type='submit'>Add Department</button>
<a class='pill active' href='{back_url}'>Back to Attendance</a>
</form>
</section>
<section class='card'>
<div class='table-wrap'>
<table><thead><tr><th>Department</th><th>Manager</th></tr></thead><tbody>{rows}</tbody></table>
</div>
</section>
</main></body></html>"""
    return page.encode("utf-8")


def render_index(query: dict[str, list[str]]) -> bytes:
    today = date.today()
    mode = (query.get("mode") or ["month"])[0]
    if mode not in {"month", "period"}:
        mode = "month"

    selected_department_id = (query.get("department_id") or [""])[0].strip()

    if mode == "period":
        current_start = safe_date((query.get("start") or [""])[0], sunday_for_day(today))
        start_day = sunday_for_day(current_start)
        days = [start_day + timedelta(days=i) for i in range(7)]
        prev_start = start_day - timedelta(days=7)
        next_start = start_day + timedelta(days=7)
        title = f"Pay Period {start_day.isoformat()} to {(start_day + timedelta(days=6)).isoformat()}"
        nav_prev = build_url({"mode": "period", "start": prev_start.isoformat(), "department_id": selected_department_id})
        nav_next = build_url({"mode": "period", "start": next_start.isoformat(), "department_id": selected_department_id})
        return_query = {"mode": "period", "start": start_day.isoformat(), "department_id": selected_department_id}
    else:
        year, month = parse_month(query)
        days_in_month = 31
        while True:
            try:
                date(year, month, days_in_month)
                break
            except ValueError:
                days_in_month -= 1
        days = [date(year, month, d) for d in range(1, days_in_month + 1)]
        prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
        month_string = f"{year:04d}-{month:02d}"
        title = f"Month {month_string}"
        nav_prev = build_url({"mode": "month", "month": f"{prev_year:04d}-{prev_month:02d}", "department_id": selected_department_id})
        nav_next = build_url({"mode": "month", "month": f"{next_year:04d}-{next_month:02d}", "department_id": selected_department_id})
        return_query = {"mode": "month", "month": month_string, "department_id": selected_department_id}

    start_iso = days[0].isoformat()
    end_iso = days[-1].isoformat()

    with closing(get_conn()) as conn:
        departments = conn.execute("SELECT id, name, manager_name FROM departments ORDER BY name COLLATE NOCASE").fetchall()

        where = ""
        params: list[str] = []
        if selected_department_id:
            where = "WHERE u.department_id = ?"
            params.append(selected_department_id)

        users = conn.execute(
            f"""
            SELECT u.id, u.name, d.name AS department_name, d.manager_name AS department_manager
            FROM users u
            LEFT JOIN departments d ON d.id = u.department_id
            {where}
            ORDER BY u.name COLLATE NOCASE
            """,
            params,
        ).fetchall()

        records = conn.execute(
            "SELECT user_id, attended_on FROM attendance WHERE attended_on BETWEEN ? AND ?",
            (start_iso, end_iso),
        ).fetchall()

    marks = {(r["user_id"], r["attended_on"]) for r in records}
    head_cells = "".join(f"<th>{d.day}<br><small>{d.strftime('%a')}</small></th>" for d in days)
    return_hidden = hidden_inputs(return_query)

    dept_options = ["<option value=''>No department</option>"]
    filter_options = ["<option value=''>All departments</option>"]
    selected_label = "All departments"

    for dept in departments:
        did = str(dept["id"])
        name = html.escape(dept["name"])
        manager = html.escape(dept["manager_name"] or "—")
        dept_options.append(f"<option value='{did}'>{name} (Mgr: {manager})</option>")
        selected = " selected" if did == selected_department_id else ""
        if selected:
            selected_label = f"{dept['name']} (Mgr: {dept['manager_name'] or '—'})"
        filter_options.append(f"<option value='{did}'{selected}>{name}</option>")

    mon_fri_days = days[1:6] if mode == "period" else []

    body_rows = []
    for user in users:
        cells = []
        for day in days:
            day_str = day.isoformat()
            checked = (user["id"], day_str) in marks
            marker = "X" if checked else ""
            cls = "mark checked" if checked else "mark"
            cells.append(
                "<td><form method='post' action='/attendance/toggle'>"
                f"{return_hidden}"
                f"<input type='hidden' name='user_id' value='{user['id']}'/>"
                f"<input type='hidden' name='attended_on' value='{day_str}'/>"
                f"<button type='submit' class='{cls}'>{marker}</button>"
                "</form></td>"
            )

        is_incomplete_week = mode == "period" and any((user["id"], day.isoformat()) not in marks for day in mon_fri_days)
        dept_label = html.escape(user["department_name"] or "—")
        mgr_label = html.escape(user["department_manager"] or "—")
        row_cls = " class='incomplete-week'" if is_incomplete_week else ""

        bulk_button = ""
        if mode == "period":
            bulk_button = (
                "<form method='post' action='/attendance/fill_weekdays'>"
                f"{return_hidden}"
                f"<input type='hidden' name='user_id' value='{user['id']}'/>"
                "<button class='secondary' type='submit'>Fill Mon–Fri</button>"
                "</form>"
            )

        body_rows.append(
            f"<tr{row_cls}>"
            f"<td><strong>{html.escape(user['name'])}</strong><br><small>{dept_label}</small><br><small>Mgr: {mgr_label}</small></td>"
            + "".join(cells)
            + "<td class='actions-cell'>"
            + bulk_button
            + "<details class='menu'><summary title='Actions'>⋯</summary>"
            + "<div class='menu-panel'><form method='post' action='/users/delete'>"
            + f"{return_hidden}<input type='hidden' name='user_id' value='{user['id']}'/>"
            + "<button class='danger' type='submit'>Remove</button></form></div></details></td></tr>"
        )

    rows_html = "".join(body_rows) if body_rows else "<tr><td colspan='999'>No users for this filter.</td></tr>"

    mode_month_url = build_url({"mode": "month", "department_id": selected_department_id})
    mode_period_url = build_url({"mode": "period", "department_id": selected_department_id})
    dept_page_url = "/departments" + ("?" + urlencode(return_query) if any(return_query.values()) else "")

    page = f"""<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Attendance Tracker</title><link rel='stylesheet' href='/static/styles.css'></head>
<body><main><h1>Attendance Tracker</h1>
<section class='card'><h2>Add Employee</h2>
<form method='post' action='/users' class='inline-form'>
{return_hidden}
<input type='text' name='name' placeholder='Employee name' required />
<select name='department_id'>{''.join(dept_options)}</select>
<button type='submit'>Add User</button>
<a class='pill' href='{dept_page_url}'>Manage Departments</a>
</form></section>
<section class='card controls'>
<form method='get' class='inline-form'>
<input type='hidden' name='mode' value='{mode}' />
<input type='hidden' name='month' value='{return_query.get('month', '')}' />
<input type='hidden' name='start' value='{return_query.get('start', '')}' />
<label>Department:</label><select name='department_id'>{''.join(filter_options)}</select>
<button type='submit'>Apply Filter</button></form>
<div class='view-links'>
<a class='pill {'active' if mode == 'month' else ''}' href='{mode_month_url}'>Month View</a>
<a class='pill {'active' if mode == 'period' else ''}' href='{mode_period_url}'>Pay Period View</a>
</div>
</section>
<section class='card'><div class='month-nav'>
<a href='{nav_prev}'>← Previous</a>
<h2>{title}</h2>
<a href='{nav_next}'>Next →</a></div>
<p class='subtle'>Current filter: <strong>{html.escape(selected_label)}</strong></p>
<p class='subtle'>{'Red rows in pay-period view are missing at least one Monday–Friday attendance mark.' if mode == 'period' else ''}</p>
<div class='table-wrap'><table><thead><tr><th>User / Dept</th>{head_cells}<th>Actions</th></tr></thead>
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


def redirect_from_form(start_response, form: dict[str, list[str]]):
    args = {
        "mode": (form.get("mode") or [""])[0],
        "month": (form.get("month") or [""])[0],
        "start": (form.get("start") or [""])[0],
        "department_id": (form.get("department_id") or [""])[0],
    }
    return redirect(start_response, build_url(args))


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

    if method == "GET" and path == "/departments":
        data = render_departments_page(query)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [data]

    if method == "POST" and path == "/departments":
        form = read_post(environ)
        name = (form.get("name") or [""])[0].strip()
        manager_name = (form.get("manager_name") or [""])[0].strip()
        if name:
            with closing(get_conn()) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO departments(name, manager_name) VALUES (?, ?)",
                    (name, manager_name),
                )
                conn.commit()
        return redirect(start_response, "/departments" + ("?" + urlencode(state_from_query(form)) if any(state_from_query(form).values()) else ""))

    if method == "POST" and path == "/users":
        form = read_post(environ)
        name = (form.get("name") or [""])[0].strip()
        department_id = (form.get("department_id") or [""])[0].strip()
        dept_val = int(department_id) if department_id.isdigit() else None
        if name:
            with closing(get_conn()) as conn:
                conn.execute("INSERT OR IGNORE INTO users(name, department_id) VALUES (?, ?)", (name, dept_val))
                conn.commit()
        return redirect_from_form(start_response, form)

    if method == "POST" and path == "/users/delete":
        form = read_post(environ)
        user_id = int((form.get("user_id") or ["0"])[0])
        with closing(get_conn()) as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
        return redirect_from_form(start_response, form)

    if method == "POST" and path == "/attendance/fill_weekdays":
        form = read_post(environ)
        user_id = int((form.get("user_id") or ["0"])[0])
        start_str = (form.get("start") or [""])[0]
        start_day = safe_date(start_str, sunday_for_day(date.today()))
        sunday = sunday_for_day(start_day)
        weekdays = [(sunday + timedelta(days=i)).isoformat() for i in range(1, 6)]
        with closing(get_conn()) as conn:
            for attended_on in weekdays:
                conn.execute(
                    "INSERT OR IGNORE INTO attendance(user_id, attended_on) VALUES (?, ?)",
                    (user_id, attended_on),
                )
            conn.commit()
        return redirect_from_form(start_response, form)

    if method == "POST" and path == "/attendance/toggle":
        form = read_post(environ)
        user_id = int((form.get("user_id") or ["0"])[0])
        attended_on = (form.get("attended_on") or [""])[0]
        if attended_on:
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
        return redirect_from_form(start_response, form)

    start_response("404 Not Found", [("Content-Type", "text/plain")])
    return [b"Not found"]


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", "8080"))
    print(f"Attendance Tracker running on 0.0.0.0:{port}")
    with make_server("0.0.0.0", port, application) as server:
        server.serve_forever()
