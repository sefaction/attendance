# Attendance Tracker (Unraid Docker)

Simple shared attendance board for salaried employees.

## Features
- Add and remove users.
- Click a day cell to toggle an `X` for attendance.
- Shared view for everyone on your network.
- Monthly navigation.
- SQLite persistence via `/data` volume.

---

## Unraid Docker Compose Manager (recommended)
This is the easiest setup path for Unraid.

### 1) Add stack files in Unraid
In **Docker Compose Manager**, create a new project and use these two files:

#### Stack file (`compose.yaml`)
```yaml
services:
  attendance:
    build:
      context: .
      dockerfile: Dockerfile
    image: attendance-tracker:latest
    container_name: ${CONTAINER_NAME:-attendance-tracker}
    ports:
      - "${HOST_PORT:-8080}:8080"
    environment:
      ATTENDANCE_DB: ${ATTENDANCE_DB:-/data/attendance.db}
      PORT: 8080
    volumes:
      - ${APPDATA_PATH:-./appdata}:/data
    restart: unless-stopped
```

#### Env file (`.env`)
```env
CONTAINER_NAME=attendance-tracker
HOST_PORT=8080
APPDATA_PATH=/mnt/user/appdata/attendance-tracker
ATTENDANCE_DB=/data/attendance.db
```

### 2) Deploy
- Click **Compose Up** in Docker Compose Manager.
- Open `http://<unraid-ip>:8080` (or your `HOST_PORT`).

### 3) Use
- Add employees in the top form.
- Click a cell to add/remove the `X` for that date.
- Click **Remove** to delete a user and their attendance history.

---

## Repository files for Compose setup
- `compose.yaml` → ready-to-use stack file.
- `.env.example` → template for your Unraid `.env` file.

If you run this repo outside Unraid, copy and customize:

```bash
cp .env.example .env
docker compose up -d --build
```

Then open: `http://localhost:8080`

---

## Alternative: plain Docker CLI
```bash
docker build -t attendance-tracker .
docker run -d \
  --name attendance-tracker \
  -p 8080:8080 \
  -v /mnt/user/appdata/attendance-tracker:/data \
  --restart unless-stopped \
  attendance-tracker
```

## Notes
- Clicking a marked `X` removes it.
- Removing a user deletes their attendance history.
