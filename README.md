# Desk Matrix 64x64

A Raspberry Pi + Adafruit RGB Matrix Bonnet project that recreates two `desk_display`-style screens on a single 64x64 HUB75 RGB LED matrix:

- `date` — large time, day, and date
- `Weather1` — current temperature, high/low, condition, and compact weather icon

The project uses the `rgbmatrix` Python bindings from `rpi-rgb-led-matrix` and draws each frame with Pillow.

## Hardware

- Raspberry Pi with 40-pin GPIO header
- Adafruit RGB Matrix Bonnet
- 64x64 HUB75 RGB LED matrix
- Proper 5V power supply for the matrix

For many 64x64 panels on the Bonnet, Adafruit notes that the address jumper should be bridged to `8`; some panels may need `16`, depending on the panel.

## Install the RGB matrix library first

Follow Adafruit's current Bonnet installer flow first:

```bash
curl https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/main/rgb-matrix.sh > rgb-matrix.sh
sudo bash rgb-matrix.sh
```

Test the matrix:

```bash
cd ~/rpi-rgb-led-matrix/examples-api-use/
sudo ./demo --led-rows=64 --led-cols=64 --led-gpio-mapping=adafruit-hat -D 0
```

If you used the quality/PWM install option, change `adafruit-hat` to `adafruit-hat-pwm` in `config.json`.

## Install this project

```bash
cd ~
git clone <your-repo-or-copy-folder> desk_matrix_64x64
cd desk_matrix_64x64
./install.sh
cp config.example.json config.json
nano config.json
```

Run it:

```bash
sudo -E env PATH=$PWD/venv/bin:$PATH ./venv/bin/python main.py
```

## Service install

```bash
sudo cp desk-matrix.service /etc/systemd/system/desk-matrix.service
sudo systemctl daemon-reload
sudo systemctl enable --now desk-matrix.service
journalctl -u desk-matrix.service -f
```

## Weather source

This version uses Open-Meteo, which does not require an API key. Edit latitude, longitude, timezone, and location name in `config.json`.
