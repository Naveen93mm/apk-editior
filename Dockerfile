FROM python:3.11-slim

# Java is needed for keytool/jarsigner, used to debug-sign rebuilt APKs
RUN apt-get update && \
    apt-get install -y --no-install-recommends default-jre-headless && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/work

# Default login credentials — override these at "docker run" time
ENV ADMIN_USERNAME=admin
ENV ADMIN_PASSWORD=admin123
ENV SECRET_KEY=change-this-secret-key

EXPOSE 80

# 1 GB max upload is set in app.py; timeout raised for large APK files
CMD ["gunicorn", "--bind", "0.0.0.0:80", "--workers", "2", "--timeout", "300", "app:app"]
