# Food Detection IoT 
Intended to run on in home compost bins for the purpose of collect AI training data.

## Production - Automatically run detections on bootup

SSH or open up a terminal on the Jetson Nano and run the following commands:

#### Setup:
```bash
git clone https://github.com/Soundbendor/food-detection-embedded.git
cd food-detection-embedded
git checkout nano-refactor
./setup.sh
```

<br>

Exit the terminal, unplug the Jetson Nano, wait 10 seconds. <br>
Then, plug the Jetson Nano back in, wait 30 seconds, and the device should automatically light up to detect foods!


### Development

#### Audio transcription on Raspberry Pi

The current Docker image uses faster-whisper on the CPU with INT8 computation.
The image packages `Systran/faster-whisper-small.en` at revision
`d1d751a5f8271d482d14ca55d9e2deeebbae577f`; the model is loaded from disk and
is never downloaded at runtime. The native model is created inside the publisher
process so Python 3.14's `forkserver` startup can serialize the driver safely.

`WHISPER_MODEL_PATH` defaults to `/firmware/models/faster-whisper-small.en`.
For development outside Docker, point it at an existing CTranslate2 model
directory containing the model, configuration, tokenizer, and vocabulary files.
`WHISPER_CPU_THREADS` defaults to `2` to leave CPU capacity for sensor processes.

Transcription failures retain the scan and media, requeue the scan, and wait one
second before trying the next queued item. The worker retries model loading if
startup failed. Media is deleted only after the API acknowledges the upload.
An unreadable recording remains queued until it can be processed; it is not
silently uploaded with a missing or stale transcription.

Dependency versions in `pyproject.toml` and `uv.lock` control the Docker build.
The historical requirements files are retained for existing development setups.
The whisper.cpp source, executable, and GGML model are no longer used or packaged.

Run the hardware-independent transcription tests from `src` in an environment
with the project's `httpx` dependency installed:

```bash
python -m unittest discover -s tests/unit -p test_transcription.py -v
```

The Docker publication workflow runs these tests before building the image.
The image build also decodes a synthetic WAV on the target architecture, without
loading a speech model. PyAV is pinned to `17.0.1` because faster-whisper `1.2.1`
uses an audio-decoder argument removed in PyAV `19`.

Before promoting this image to devices, verify an ARM64 build, startup with
networking disabled, and transcription of representative speech, silence, and
invalid recordings on a Pi. Check latency and memory use while sensors are active.
Rollback uses the previous firmware image; the scan schema and disk cache format
are unchanged, and the packaged model is outside the persistent data volume.

#### Run Detection Loop
```bash
./src/main.py
```

## Acknowledgements & Contact
If you would like to use any part of this program, please cite our publication here: 
```
@inproceedings{10.1145/3686215.3686216,
  author = {Beery, Aidan J. and Eastman, Daniel W. and Enos, Jake and Richards, William and Donnelly, Patrick J.},
  title = {Smart Compost Bin for Measurement of Consumer Food Waste},
  year = {2024},
  isbn = {9798400704635},
  publisher = {Association for Computing Machinery},
  address = {New York, NY, USA},
  url = {https://doi-org.oregonstate.idm.oclc.org/10.1145/3686215.3686216},
  doi = {10.1145/3686215.3686216},
  booktitle = {Companion Proceedings of the 26th International Conference on Multimodal Interaction},
  pages = {100–107},
  numpages = {8},
  keywords = {artificial intelligence, computer vision, consumer compost, food waste, smart technology},
  location = {San Jose, Costa Rica},
  series = {ICMI '24 Companion}
}
```
Lead Developer: Will Richards [(@WL-Richards)](https://github.com/WL-Richards)

Project Lead: Aidan Beery [(@Aidan-B1409)](https://github.com/Aidan-B1409)

Advised By: Dr. Patrick J. Donnelly @ Oregon State University

Website: http://www.soundbendor.org/
