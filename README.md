# Attendance Tracker (Unraid Docker)

Simple shared attendance board for salaried employees.

## Features
- Add and remove users.
- Manage departments in a dedicated section.
- Assign users to departments via dropdown selection.
- Filter the board by department.
- Click a day cell to toggle an `X` for attendance.
- Shared view for everyone on your network.
- View by **month** or by **pay period** (Sunday-Saturday).
- SQLite persistence via `/data` volume.

---

## Unraid Docker Compose Manager (recommended)

If "Compose Up" failed before, it was likely because the stack used `build.context: .` (local files), but Unraid didn’t have the repo files in that stack folder.

This stack fixes that by using a **GitHub build context URL** so Unraid can fetch source automatically.

### 1) Create a stack in Unraid
In **Docker Compose Manager**, create a new project and paste this stack:

```yaml
services:
  attendance:
    build:
      # Format: https://github.com/<owner>/<repo>.git#<branch-or-tag>
      context: ${GIT_CONTEXT:-https://github.com/REPLACE_WITH_YOUR_USER/attendance.git#main}
      dockerfile: Dockerfile
    image: ${IMAGE_NAME:-attendance-tracker:latest}
    container_name: ${CONTAINER_NAME:-attendance-tracker}
    ports:
      - "${HOST_PORT:-8080}:8080"
    environment:
      ATTENDANCE_DB: ${ATTENDANCE_DB:-/data/attendance.db}
      PORT: 8080
    volumes:
      - ${APPDATA_PATH:-/mnt/user/appdata/attendance-tracker}:/data
    restart: unless-stopped
```

### 2) Add an env file in Unraid for the stack
Use values like this:

```env
GIT_CONTEXT=https://github.com/REPLACE_WITH_YOUR_USER/attendance.git#main
IMAGE_NAME=attendance-tracker:latest
CONTAINER_NAME=attendance-tracker
HOST_PORT=8080
APPDATA_PATH=/mnt/user/appdata/attendance-tracker
ATTENDANCE_DB=/data/attendance.db
```

### 3) Deploy
- Replace `GIT_CONTEXT` with your real GitHub repo URL/ref.
- Click **Compose Up**.
- Open `http://<unraid-ip>:8080` (or your `HOST_PORT`).

### 4) Use
- Add departments first in the **Departments** section.
- Add employees and select department from the dropdown.
- Choose **Month View** or **Pay Period View**.
- Use the department dropdown to filter the board.
- Click a date cell to add/remove an `X`.
- Click **Remove** to delete a user and their attendance history.

---

## Included files
- `compose.yaml` → Unraid-friendly stack using GitHub build context.
- `.env.example` → template env file for Compose Manager.

For local testing outside Unraid:

```bash
cp .env.example .env
docker compose up -d --build
```

Then open `http://localhost:8080`.
