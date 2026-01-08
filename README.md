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

#### Run Detection Loop
```bash
./src/main.py
```

## Acknowledgements & Contact
If you would like to use any part of this program, please cite our publication here: 
```@inproceedings{10.1145/3686215.3686216,
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
