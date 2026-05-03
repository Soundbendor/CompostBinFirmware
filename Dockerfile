#code/Dockerfile
FROM python:3.9-bookworm

# Copy our code to the firmware directory
WORKDIR /firmware
COPY ./requirements.txt /firmware/requirements.txt
COPY dependencies /firmware/dependencies

# Update apt sources
RUN apt-get update

# Update pip
RUN pip install --upgrade pip --break-system-packages

# Install apt dependencies
RUN apt-get -y install portaudio19-dev
RUN apt-get -y install python3-pyaudio
RUN apt-get -y install ffmpeg
RUN apt-get -y install alsa-utils
RUN apt-get -y install libbluetooth-dev
RUN apt-get -y install network-manager
RUN apt-get -y install wireless-tools

# Install python dependenices
RUN pip install -r requirements.txt --no-cache-dir --break-system-packages

# Pre-download faster-whisper model
RUN python3 -c "from faster_whisper import WhisperModel; WhisperModel('small.en', device='cpu', compute_type='int8')"

RUN mv /firmware/dependencies/librealsense2.so /usr/local/lib/python3.9/site-packages/librealsense2.so
RUN mv /firmware/dependencies/pyrealsense2.cpython-39-aarch64-linux-gnu.so /usr/local/lib/python3.9/site-packages/pyrealsense2.cpython-39-aarch64-linux-gnu.so

COPY media /firmware/media
COPY src /firmware/src

COPY .aws /root/.aws

WORKDIR  /firmware/src
