import os
import re
import shutil
import subprocess
import uuid
import xml.etree.ElementTree as ET
from functools import wraps

from flask import (
    Flask, request, render_template, redirect,
    url_for, session, send_file, flash, abort
)

APP_SECRET = os.environ.get("SECRET_KEY", "change-this-secret-key")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WORK_DIR = os.path.join(BASE_DIR, "work")
os.makedirs(WORK_DIR, exist_ok=True)

APKTOOL_JAR = os.environ.get("APKTOOL_JAR", "/opt/apktool.jar")
SIGNER_JAR = os.environ.get("SIGNER_JAR", "/opt/uber-apk-signer.jar")

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
AUDIO_EXT = (".mp3", ".ogg", ".wav", ".m4a")
ICON_NAME_HINT = "ic_launcher"

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


def job_dir_for(job_id):
    return os.path.join(WORK_DIR, job_id)


def current_job_dir():
    job_id = session.get("job_id")
    if not job_id:
        return None
    d = job_dir_for(job_id)
    if not os.path.isdir(d):
        return None
    return d


def safe_join(base, rel_path):
    """Resolve rel_path under base, refusing to leave the sandbox."""
    base = os.path.realpath(base)
    target = os.path.realpath(os.path.join(base, rel_path))
    if not (target == base or target.startswith(base + os.sep)):
        abort(400, "Invalid path")
    return target


# ---------------------------------------------------------------- apktool

def run_apktool_decode(apk_path, decoded_dir):
    if os.path.isdir(decoded_dir):
        shutil.rmtree(decoded_dir)
    result = subprocess.run(
        ["java", "-jar", APKTOOL_JAR, "d", "-f", "-o", decoded_dir, apk_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:] or "apktool decode failed")


def run_apktool_build(decoded_dir, out_apk_path):
    os.makedirs(os.path.dirname(out_apk_path), exist_ok=True)
    result = subprocess.run(
        ["java", "-jar", APKTOOL_JAR, "b", decoded_dir, "-o", out_apk_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:] or "apktool build failed")


def sign_apk(unsigned_apk_path, signed_out_dir):
    os.makedirs(signed_out_dir, exist_ok=True)
    result = subprocess.run(
        ["java", "-jar", SIGNER_JAR, "-a", unsigned_apk_path, "--out", signed_out_dir],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:] or "signing failed")
    for f in os.listdir(signed_out_dir):
        if f.endswith("-aligned-debugSigned.apk") or f.endswith("-debugSigned.apk"):
            return os.path.join(signed_out_dir, f)
    # fall back to any apk produced
    for f in os.listdir(signed_out_dir):
        if f.endswith(".apk"):
            return os.path.join(signed_out_dir, f)
    raise RuntimeError("Signed APK not found in output")


# ------------------------------------------------------------- asset scan

def scan_assets(decoded_dir):
    icons, images, audio = [], [], []

    for root, _dirs, files in os.walk(decoded_dir):
        rel_root = os.path.relpath(root, decoded_dir)
        # Skip compiled code and build metadata — not editable content
        if rel_root.split(os.sep)[0] in ("smali", "original", "build", "unknown"):
            continue
        for fname in files:
            lower = fname.lower()
            rel_path = os.path.normpath(os.path.join(rel_root, fname))
            if lower.endswith(IMAGE_EXT):
                (icons if ICON_NAME_HINT in lower else images).append(rel_path)
            elif lower.endswith(AUDIO_EXT):
                audio.append(rel_path)

    images.sort()
    audio.sort()
    icons.sort()

    app_name = read_app_name(decoded_dir)
    colors = read_colors(decoded_dir)

    return {
        "icons": icons[:20],
        "images": images[:150],
        "audio": audio[:150],
        "app_name": app_name,
        "colors": colors,
        "truncated_images": len(images) > 150,
        "truncated_audio": len(audio) > 150,
    }


def strings_xml_path(decoded_dir):
    return os.path.join(decoded_dir, "res", "values", "strings.xml")


def colors_xml_path(decoded_dir):
    return os.path.join(decoded_dir, "res", "values", "colors.xml")


def read_app_name(decoded_dir):
    path = strings_xml_path(decoded_dir)
    if not os.path.exists(path):
        return None
    try:
        tree = ET.parse(path)
        for el in tree.getroot().findall("string"):
            if el.get("name") == "app_name":
                return el.text or ""
    except ET.ParseError:
        pass
    return None


def write_app_name(decoded_dir, new_name):
    path = strings_xml_path(decoded_dir)
    if not os.path.exists(path):
        return False
    tree = ET.parse(path)
    for el in tree.getroot().findall("string"):
        if el.get("name") == "app_name":
            el.text = new_name
            tree.write(path, encoding="utf-8", xml_declaration=True)
            return True
    return False


def read_colors(decoded_dir):
    path = colors_xml_path(decoded_dir)
    if not os.path.exists(path):
        return []
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return []
    out = []
    for el in tree.getroot().findall("color"):
        name = el.get("name")
        value = (el.text or "").strip()
        if name and re.match(r"^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$", value):
            out.append({"name": name, "value": value})
    return out


def write_colors(decoded_dir, updates):
    path = colors_xml_path(decoded_dir)
    if not os.path.exists(path):
        return False
    tree = ET.parse(path)
    changed = False
    for el in tree.getroot().findall("color"):
        name = el.get("name")
        if name in updates:
            new_val = updates[name].strip()
            if re.match(r"^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$", new_val):
                el.text = new_val
                changed = True
    if changed:
        tree.write(path, encoding="utf-8", xml_declaration=True)
    return changed


# ----------------------------------------------------------------- routes

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
    job_dir = current_job_dir()
    return render_template("dashboard.html", has_project=bool(job_dir))


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename.lower().endswith(".apk"):
        flash("Please upload a .apk file.")
        return redirect(url_for("dashboard"))

    job_id = uuid.uuid4().hex
    job_dir = job_dir_for(job_id)
    os.makedirs(job_dir, exist_ok=True)
    apk_path = os.path.join(job_dir, "source.apk")
    uploaded.save(apk_path)

    try:
        run_apktool_decode(apk_path, os.path.join(job_dir, "decoded"))
    except RuntimeError as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        flash("Could not open that APK: " + str(exc)[:300])
        return redirect(url_for("dashboard"))

    session["job_id"] = job_id
    return redirect(url_for("project"))


@app.route("/project")
@login_required
def project():
    job_dir = current_job_dir()
    if not job_dir:
        flash("Upload an APK first.")
        return redirect(url_for("dashboard"))
    data = scan_assets(os.path.join(job_dir, "decoded"))
    return render_template("project.html", **data)


@app.route("/project/asset")
@login_required
def asset_preview():
    job_dir = current_job_dir()
    if not job_dir:
        abort(404)
    rel_path = request.args.get("path", "")
    full_path = safe_join(os.path.join(job_dir, "decoded"), rel_path)
    if not os.path.isfile(full_path):
        abort(404)
    return send_file(full_path)


@app.route("/project/rename", methods=["POST"])
@login_required
def rename_app():
    job_dir = current_job_dir()
    if not job_dir:
        return redirect(url_for("dashboard"))
    new_name = request.form.get("app_name", "").strip()
    if new_name:
        write_app_name(os.path.join(job_dir, "decoded"), new_name)
        flash("App name updated.")
    return redirect(url_for("project"))


@app.route("/project/colors", methods=["POST"])
@login_required
def update_colors():
    job_dir = current_job_dir()
    if not job_dir:
        return redirect(url_for("dashboard"))
    updates = {
        key[len("color:"):]: value
        for key, value in request.form.items()
        if key.startswith("color:")
    }
    if write_colors(os.path.join(job_dir, "decoded"), updates):
        flash("Colors updated.")
    return redirect(url_for("project"))


@app.route("/project/replace", methods=["POST"])
@login_required
def replace_asset():
    job_dir = current_job_dir()
    if not job_dir:
        return redirect(url_for("dashboard"))
    rel_path = request.form.get("rel_path", "")
    uploaded = request.files.get("file")
    if not rel_path or not uploaded or uploaded.filename == "":
        flash("Choose a replacement file first.")
        return redirect(url_for("project"))

    target = safe_join(os.path.join(job_dir, "decoded"), rel_path)
    if not os.path.isfile(target):
        abort(404)
    uploaded.save(target)
    flash(os.path.basename(rel_path) + " replaced.")
    return redirect(url_for("project"))


@app.route("/project/build", methods=["POST"])
@login_required
def build_project():
    job_dir = current_job_dir()
    if not job_dir:
        return redirect(url_for("dashboard"))

    decoded_dir = os.path.join(job_dir, "decoded")
    unsigned_apk = os.path.join(job_dir, "build", "unsigned.apk")
    signed_dir = os.path.join(job_dir, "build", "signed")

    try:
        run_apktool_build(decoded_dir, unsigned_apk)
        signed_apk = sign_apk(unsigned_apk, signed_dir)
    except RuntimeError as exc:
        flash("Build failed: " + str(exc)[:300])
        return redirect(url_for("project"))

    app_name = read_app_name(decoded_dir) or "app"
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", app_name) or "app"
    return send_file(signed_apk, as_attachment=True,
                      download_name=safe_name + ".apk")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80)
