FROM python:3.11-slim

# Java runs apktool (decode/build) and uber-apk-signer (debug signing).
# curl+jq are only needed at build time to fetch the latest tool jars.
RUN apt-get update && \
    apt-get install -y --no-install-recommends default-jre-headless curl jq unzip && \
    rm -rf /var/lib/apt/lists/*

# --- Apktool: decodes/rebuilds the APK's resources -------------------------
RUN set -eux; \
    APKTOOL_TAG=$(curl -fsSL https://api.github.com/repos/iBotPeaches/Apktool/releases/latest | jq -r .tag_name); \
    APKTOOL_VER=${APKTOOL_TAG#v}; \
    curl -fsSL -o /opt/apktool.jar \
      "https://github.com/iBotPeaches/Apktool/releases/download/${APKTOOL_TAG}/apktool_${APKTOOL_VER}.jar"

# --- uber-apk-signer: zipaligns + debug-signs the rebuilt APK ---------------
RUN set -eux; \
    UAS_TAG=$(curl -fsSL https://api.github.com/repos/patrickfav/uber-apk-signer/releases/latest | jq -r .tag_name); \
    UAS_VER=${UAS_TAG#v}; \
    curl -fsSL -o /opt/uber-apk-signer.jar \
      "https://github.com/patrickfav/uber-apk-signer/releases/download/${UAS_TAG}/uber-apk-signer-${UAS_VER}.jar"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/work

ENV APKTOOL_JAR=/opt/apktool.jar
ENV SIGNER_JAR=/opt/uber-apk-signer.jar

# Default login credentials — override at "docker run" time
ENV ADMIN_USERNAME=admin
ENV ADMIN_PASSWORD=admin123
ENV SECRET_KEY=change-this-secret-key

EXPOSE 80

# Single worker: progress tracking lives in that process's memory, so every
# poll request must land on the same worker as the one running the job.
# Long timeout: decoding/rebuilding a big game APK takes real time.
CMD ["gunicorn", "--bind", "0.0.0.0:80", "--workers", "1", "--threads", "4", "--timeout", "900", "app:app"]
