import os
import shutil
import subprocess
import uuid
import zipfile
from functools import wraps

from flask import (
    Flask, request, render_template, redirect,
    url_for, session, send_file, flash
)

APP_SECRET = os.environ.get("SECRET_KEY", "change-this-secret-key")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(BASE_DIR, "work")
os.makedirs(WORK_DIR, exist_ok=True)

KEYSTORE_PATH = os.path.join(BASE_DIR, "debug.keystore")
KEYSTORE_PASS = "android"
KEY_ALIAS = "androiddebugkey"

app = Flask(__name__)
app.secret_key = APP_SECRET
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1 GB uploads


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapped


def new_job_dir():
    job_id = uuid.uuid4().hex
    job_dir = os.path.join(WORK_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    return job_dir


def ensure_debug_keystore():
    """Create a debug keystore once, so converted APKs can be signed."""
    if os.path.exists(KEYSTORE_PATH):
        return
    try:
        subprocess.run(
            [
                "keytool", "-genkeypair", "-v",
                "-keystore", KEYSTORE_PATH,
                "-alias", KEY_ALIAS,
                "-storepass", KEYSTORE_PASS,
                "-keypass", KEYSTORE_PASS,
                "-keyalg", "RSA", "-keysize", "2048",
                "-validity", "10000",
                "-dname", "CN=Android Debug,O=Android,C=US",
            ],
            check=True, capture_output=True,
        )
    except Exception:
        # Signing is a best-effort convenience; conversion still works without it.
        pass


def sign_apk(apk_path):
    """Best-effort debug signing so the rebuilt APK can be installed."""
    if not os.path.exists(KEYSTORE_PATH):
        return False
    try:
        subprocess.run(
            [
                "jarsigner",
                "-keystore", KEYSTORE_PATH,
                "-storepass", KEYSTORE_PASS,
                "-keypass", KEYSTORE_PASS,
                "-sigalg", "SHA256withRSA",
                "-digestalg", "SHA-256",
                apk_path, KEY_ALIAS,
            ],
            check=True, capture_output=True,
        )
        return True
    except Exception:
        return False


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        flash("Wrong username or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/convert/apk-to-zip", methods=["POST"])
@login_required
def apk_to_zip():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename.lower().endswith(".apk"):
        flash("Please upload a .apk file.")
        return redirect(url_for("dashboard"))

    job_dir = new_job_dir()
    apk_path = os.path.join(job_dir, "input.apk")
    uploaded.save(apk_path)

    base_name = os.path.splitext(os.path.basename(uploaded.filename))[0]
    zip_path = os.path.join(job_dir, base_name + ".zip")

    # An APK is itself a ZIP archive, so the safest "conversion" is a
    # direct byte copy with a renamed extension (no re-compression that
    # could disturb the archive's internal structure).
    shutil.copyfile(apk_path, zip_path)

    return send_file(zip_path, as_attachment=True,
                      download_name=base_name + ".zip")


@app.route("/convert/zip-to-apk", methods=["POST"])
@login_required
def zip_to_apk():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename.lower().endswith(".zip"):
        flash("Please upload a .zip file.")
        return redirect(url_for("dashboard"))

    job_dir = new_job_dir()
    zip_path = os.path.join(job_dir, "input.zip")
    uploaded.save(zip_path)

    if not zipfile.is_zipfile(zip_path):
        flash("That file is not a valid zip archive.")
        return redirect(url_for("dashboard"))

    base_name = os.path.splitext(os.path.basename(uploaded.filename))[0]
    apk_path = os.path.join(job_dir, base_name + ".apk")
    shutil.copyfile(zip_path, apk_path)

    ensure_debug_keystore()
    sign_apk(apk_path)

    return send_file(apk_path, as_attachment=True,
                      download_name=base_name + ".apk")


if __name__ == "__main__":
    ensure_debug_keystore()
    app.run(host="0.0.0.0", port=80)
