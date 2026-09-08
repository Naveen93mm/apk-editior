# Package Bench — APK ⇄ ZIP converter

A small login-protected website with exactly two actions:

1. **APK → ZIP** — upload a `.apk`, get back a `.zip` with the same contents.
2. **ZIP → APK** — upload the (edited) `.zip`, get back a debug-signed `.apk`.

Ships as a single Docker image, listening on port **80**.

## Why this works
An `.apk` file *is* a ZIP archive internally, so "conversion" is a safe byte-copy
with the extension changed — no re-compression that could break the archive. When
rebuilding the APK, the app also debug-signs it (via `keytool`/`jarsigner`, bundled
in the image) so the resulting file can actually be installed on a device. Debug
signing only covers the classic v1 scheme — if your target device/tooling insists
on v2/v3 signing or `zipalign`, run those extra steps yourself after downloading it.

## Build the image
```bash
docker build -t package-bench .
```

## Run it (port 80, your own login credentials)
```bash
docker run -d \
  --name package-bench \
  -p 80:80 \
  -e ADMIN_USERNAME=yourname \
  -e ADMIN_PASSWORD='a-strong-password' \
  -e SECRET_KEY="$(openssl rand -hex 32)" \
  package-bench
```

Then open `http://<your-server-ip>/` and log in.

## Amazon Linux (EC2) notes
- Any small instance handles this fine; an 8 GB RAM box is comfortably enough.
- Install Docker first if it isn't already there:
  ```bash
  sudo yum update -y
  sudo yum install -y docker
  sudo service docker start
  sudo usermod -aG docker ec2-user   # log out/in after this
  ```
- Open port 80 (and 443 if you later add TLS) in the instance's security group.
- Uploads default to a 1 GB limit and a 300-second request timeout — both are
  adjustable in `app.py` (`MAX_CONTENT_LENGTH`) and `Dockerfile` (`--timeout`).

## Files
```
app.py              Flask app: login + the two conversion routes
templates/           login.html, dashboard.html
static/style.css     styling
requirements.txt     Flask, gunicorn
Dockerfile           builds the image, runs gunicorn on port 80
```
