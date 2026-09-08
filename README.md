# Skin Bench — game APK reskinning tool

Login-protected website for reskinning a 2D game APK: swap its logo, background
images, colors, and music, then rebuild it into an installable APK. Ships as a
single Docker image on port **80**, same pattern as the earlier converter.

## How it works
1. **Upload** — you upload a `.apk`. The server runs `apktool` to decode it into
   its resources: images, audio files (from `assets/` and `res/`), `colors.xml`,
   and the app name from `strings.xml`.
2. **Edit** — the project page lists the launcher icon, all images, all audio
   files, and all named colors, each with a "Replace" control. Replace an image
   or sound by uploading your own file with the same role; edit a color with the
   swatch or its hex value; rename the app in one field.
3. **Build** — `apktool` rebuilds the resources back into an APK, then
   `uber-apk-signer` zipaligns and debug-signs it so it can be installed on a
   device or emulator.

Only two building blocks are used, both well-known open-source Android tools —
no code inside the app (smali) is touched, only resources.

## Build the image
```bash
docker build -t skin-bench .
```
This downloads the latest `apktool` and `uber-apk-signer` jars from GitHub at
build time, so your build machine needs internet access to `github.com` and
`api.github.com`.

## Run it
```bash
docker run -d \
  --name skin-bench \
  -p 80:80 \
  -e ADMIN_USERNAME=yourname \
  -e ADMIN_PASSWORD='a-strong-password' \
  -e SECRET_KEY="$(openssl rand -hex 32)" \
  skin-bench
```
Open `http://<server-ip>/` and log in.

## Notes
- **Debug-signed only.** The rebuilt APK is signed with a debug certificate
  (v1/v2/v3), which installs fine for testing/sideloading. If you plan to
  publish it (e.g. on the Play Store), you'll need to re-sign it with your own
  release keystore before submission.
- **One project at a time per login session.** Uploading a new APK starts a
  fresh project; the previous one's files stay in `/app/work/<job-id>/` inside
  the container until you clean them up.
- **Large games:** raise `MAX_CONTENT_LENGTH` in `app.py` and the gunicorn
  `--timeout` in the `Dockerfile` if your APKs are bigger than 1 GB or take
  longer than 15 minutes to decode/rebuild.
- **Amazon Linux (EC2):** an 8 GB instance is comfortable for this. Install
  Docker (`sudo yum install -y docker && sudo service docker start`), open
  port 80 in the security group, then build and run as above.
- Only touches resources that `apktool` decodes as **plain files** (images,
  audio, XML values) — it doesn't decompile or let you edit app logic (smali
  code), pop-up animation *timing* defined in code, or anything encrypted at
  the app's own level beyond standard APK/ZIP packaging.

## Files
```
app.py                Flask app: login, apktool decode/build, asset scanning
templates/             login.html, dashboard.html, project.html
static/style.css       styling
requirements.txt       Flask, gunicorn
Dockerfile             fetches apktool + uber-apk-signer, runs on port 80
```
