#!/bin/bash

docker run --rm --privileged \
    -v "$(pwd)"/data:/firmware/data \
    -v /dev/bus/usb:/dev/bus/usb \
    -e FASTAPI_KEY="$FASTAPI_KEY" \
    -e ENDPOINT="$ENDPOINT" \
    -e PORT="$PORT" \
    -v "$(pwd)"/.git:/firmware/.git \
    --mount type=bind,source=/var/run/dbus,target=/var/run/dbus \
    --device-cgroup-rule "c 81:* rmw" \
    --device-cgroup-rule "c 189:* rmw" \
    --device /dev/i2c-1:/dev/i2c-1 \
    --device /dev/spidev0.0:/dev/spidev0.0 \
    --name binsight-firmware \
    --net host \
    -it binsight-firmware \
    bash

