ARG BUILD_FROM
FROM ${BUILD_FROM}

# Alpine's Python is externally managed; the image is single-purpose so we
# install straight into the system interpreter.
ENV PIP_BREAK_SYSTEM_PACKAGES=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/usr/src/app

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN \
    apk add --no-cache \
        git \
        openssh-client \
        python3 \
    && apk add --no-cache --virtual .build-deps \
        build-base \
        py3-pip \
        python3-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del --no-cache .build-deps \
    && find /usr/lib/python3*/site-packages \
        \( -type d -a \( -name test -o -name tests -o -name '__pycache__' \) \) \
        -exec rm -rf '{}' + \
    && rm -rf /root/.cache

COPY src/ /usr/src/app/
COPY rootfs /

HEALTHCHECK --start-period=30s \
    CMD wget --spider -q http://127.0.0.1:8099/_app/health || exit 1

LABEL \
    io.hass.name="Domácí manuál" \
    io.hass.description="Household Markdown documentation rendered with MkDocs Material" \
    io.hass.type="addon"
