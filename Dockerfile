#code/Dockerfile
FROM ghcr.io/astral-sh/uv:python3.14-bookworm

# Copy our code to the firmware directory
WORKDIR /firmware
COPY ./requirements_new.txt /firmware/requirements.txt
COPY dependencies /firmware/dependencies

# Update apt sources
RUN apt-get update

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

# Omit development dependencies
ENV UV_NO_DEV=1

# Ensure installed tools can be executed out of the box
ENV UV_TOOL_BIN_DIR=/usr/local/bin

# Install apt dependencies
RUN apt-get -y install portaudio19-dev \
                       python3-pyaudio \
                       ffmpeg \
                       alsa-utils \
                       libbluetooth-dev \
                       network-manager \
                       wireless-tools \
                       swig \
                       unzip \
                       wget

# Download, compile, and install the lgpio C library from source
RUN wget https://github.com/joan2937/lg/archive/master.zip \
    && unzip master.zip \
    && cd lg-master \
    && make \
    && make install \
    && ldconfig \
    && cd .. \
    && rm -rf master.zip lg-master

# Install python dependenices
# RUN pip install -r requirements.txt --no-cache-dir --break-system-packages

# Ensure installed tools can be executed out of the box
ENV UV_TOOL_BIN_DIR=/usr/local/bin

# Install the project's dependencies using the lockfile and settings
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# hotfix patch - keep lgpio 
RUN uv pip install rpi-lgpio 

# Compile BSEC library
COPY bme68x-python-library-bsec2.6.1.0 /firmware/bme68x-python-library-bsec2.6.1.0
WORKDIR /firmware/bme68x-python-library-bsec2.6.1.0
RUN BSEC2=64; export BSEC2; /firmware/.venv/bin/python3 setup.py install
WORKDIR /firmware

# Compile whisper
COPY whisper.cpp /firmware/whisper.cpp
WORKDIR /firmware/whisper.cpp
RUN UNAME_M=arm64 UNAME_p=arm make
RUN ./models/download-ggml-model.sh small.en
WORKDIR /firmware

# RUN mv /firmware/dependencies/librealsense2.so /usr/local/lib/python3.14/site-packages/librealsense2.so
# RUN mv /firmware/dependencies/pyrealsense2.cpython-314-aarch64-linux-gnu.so /usr/local/lib/python3.14/site-packages/pyrealsense2.cpython-314-aarch64-linux-gnu.so

COPY media /firmware/media
COPY src /firmware/src

COPY .aws /root/.aws

# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

ENV PATH="/firmware/.venv/bin:$PATH"

LABEL io.balena.contract.requires="[]"

WORKDIR  /firmware/src
