# Attendance Tracker (Unraid Docker)

Simple shared attendance board for salaried employees.

## Features
- Add and remove users.
- Click a day cell to toggle an `X` for attendance.
- Shared view for everyone on your network.
- Monthly navigation.
- SQLite persistence via `/data` volume.

## Run with Docker

```bash
docker build -t attendance-tracker .
docker run -d \
  --name attendance-tracker \
  -p 8080:8080 \
  -v /mnt/user/appdata/attendance-tracker:/data \
  --restart unless-stopped \
  attendance-tracker
```

Then open: `http://<unraid-ip>:8080`

## Unraid Docker template values
Use these when creating a custom container in Unraid:

- **Repository:** image you build/publish for this app
- **Network Type:** bridge
- **Console shell command:** `bash`
- **WebUI:** `http://[IP]:[PORT:8080]/`
- **Port mapping:** container `8080` -> host port of your choice
- **Path mapping:** `/data` -> `/mnt/user/appdata/attendance-tracker`
- **Restart policy:** unless-stopped
- **Optional env var:** `ATTENDANCE_DB=/data/attendance.db`

## Notes
- Clicking a marked `X` removes it.
- Removing a user deletes their attendance history.
