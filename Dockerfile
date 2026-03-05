FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY app.py ./
COPY static ./static

VOLUME ["/data"]
EXPOSE 8080

CMD ["python", "app.py"]
