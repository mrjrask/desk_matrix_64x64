#!/usr/bin/env python3
"""
Desk Matrix 64x64

Raspberry Pi + Adafruit RGB Matrix Bonnet + 64x64 HUB75 panel display
for two desk_display-style screens:
  - date
  - Weather1

Requires the hzeller/rpi-rgb-led-matrix Python bindings installed for the
Python environment used to run this script.
"""

from __future__ import annotations

import json
import logging
import math
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import requests
from PIL import Image, ImageDraw, ImageFont

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
except ImportError as exc:
    raise SystemExit(
        "Could not import rgbmatrix. Install the rpi-rgb-led-matrix Python "
        "bindings first, then run this script with sudo using the same Python."
    ) from exc

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
ICON_DIR = BASE_DIR / "images" / "WeatherKit"

Color = Tuple[int, int, int]


def clamp(value: int, low: int = 0, high: int = 255) -> int:
    return max(low, min(high, int(value)))


def rgb(value: Any, fallback: Color) -> Color:
    if isinstance(value, list) and len(value) == 3:
        return (clamp(value[0]), clamp(value[1]), clamp(value[2]))
    return fallback


def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        example = BASE_DIR / "config.example.json"
        raise SystemExit(f"Missing {CONFIG_PATH}. Copy {example.name} to config.json first.")
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_font(path: str, size: int, fallback_bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [Path(path)] if path else []
    if fallback_bold:
        candidates += [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        ]
    else:
        candidates += [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        ]

    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def center_text(
    draw: ImageDraw.ImageDraw,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: Color,
    width: int = 64,
) -> None:
    w, _ = text_size(draw, text, font)
    draw.text(((width - w) // 2, y), text, font=font, fill=fill)


def draw_text_fit(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    font_path: str,
    max_width: int,
    start_size: int,
    min_size: int,
    fill: Color,
    bold: bool = False,
) -> None:
    size = start_size
    while size >= min_size:
        font = load_font(font_path, size, fallback_bold=bold)
        w, _ = text_size(draw, text, font)
        if w <= max_width:
            draw.text(xy, text, font=font, fill=fill)
            return
        size -= 1
    font = load_font(font_path, min_size, fallback_bold=bold)
    draw.text(xy, text[:8], font=font, fill=fill)


@dataclass
class WeatherData:
    temp: Optional[int] = None
    high: Optional[int] = None
    low: Optional[int] = None
    code: Optional[int] = None
    wind_mph: Optional[int] = None
    fetched_at: Optional[datetime] = None
    error: Optional[str] = None

    @property
    def condition(self) -> str:
        if self.code is None:
            return "Weather"
        code_map = {
            0: "Clear",
            1: "Mostly Clear",
            2: "Partly Cloudy",
            3: "Cloudy",
            45: "Fog",
            48: "Fog",
            51: "Drizzle",
            53: "Drizzle",
            55: "Drizzle",
            56: "Freezing Drizzle",
            57: "Freezing Drizzle",
            61: "Rain",
            63: "Rain",
            65: "Heavy Rain",
            66: "Freezing Rain",
            67: "Freezing Rain",
            71: "Snow",
            73: "Snow",
            75: "Heavy Snow",
            77: "Snow",
            80: "Showers",
            81: "Showers",
            82: "Heavy Showers",
            85: "Snow Showers",
            86: "Snow Showers",
            95: "Thunderstorms",
            96: "Thunderstorms",
            99: "Thunderstorms",
        }
        return code_map.get(self.code, "Weather")


def fetch_weather(config: Dict[str, Any], timeout: int = 8) -> WeatherData:
    loc = config["location"]
    units = config.get("weather", {}).get("units", "fahrenheit")
    temp_unit = "fahrenheit" if units == "fahrenheit" else "celsius"
    wind_unit = "mph" if units == "fahrenheit" else "kmh"

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": loc["latitude"],
        "longitude": loc["longitude"],
        "timezone": loc.get("timezone", "auto"),
        "temperature_unit": temp_unit,
        "wind_speed_unit": wind_unit,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code",
        "forecast_days": 1,
    }

    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        current = payload.get("current", {})
        daily = payload.get("daily", {})
        return WeatherData(
            temp=round(current.get("temperature_2m")) if current.get("temperature_2m") is not None else None,
            high=round(daily.get("temperature_2m_max", [None])[0])
            if daily.get("temperature_2m_max")
            else None,
            low=round(daily.get("temperature_2m_min", [None])[0])
            if daily.get("temperature_2m_min")
            else None,
            code=current.get("weather_code"),
            wind_mph=round(current.get("wind_speed_10m")) if current.get("wind_speed_10m") is not None else None,
            fetched_at=datetime.now(tz=ZoneInfo(loc.get("timezone", "UTC"))),
        )
    except Exception as exc:
        logging.warning("Weather refresh failed: %s", exc)
        return WeatherData(error=str(exc), fetched_at=datetime.now())


def draw_sun(draw: ImageDraw.ImageDraw, cx: int, cy: int, color: Color) -> None:
    for angle in range(0, 360, 45):
        radians = math.radians(angle)
        x1 = cx + int(math.cos(radians) * 8)
        y1 = cy + int(math.sin(radians) * 8)
        x2 = cx + int(math.cos(radians) * 12)
        y2 = cy + int(math.sin(radians) * 12)
        draw.line((x1, y1, x2, y2), fill=color, width=1)
    draw.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=color)


def draw_cloud(draw: ImageDraw.ImageDraw, x: int, y: int, fill: Color, outline: Optional[Color] = None) -> None:
    draw.ellipse((x + 2, y + 6, x + 17, y + 21), fill=fill, outline=outline)
    draw.ellipse((x + 12, y + 1, x + 29, y + 20), fill=fill, outline=outline)
    draw.ellipse((x + 24, y + 7, x + 39, y + 21), fill=fill, outline=outline)
    draw.rectangle((x + 8, y + 13, x + 34, y + 23), fill=fill)
    if outline:
        draw.arc((x + 2, y + 6, x + 17, y + 21), 180, 360, fill=outline)
        draw.arc((x + 12, y + 1, x + 29, y + 20), 180, 360, fill=outline)
        draw.arc((x + 24, y + 7, x + 39, y + 21), 180, 360, fill=outline)
        draw.line((x + 8, y + 23, x + 34, y + 23), fill=outline)


def draw_weather_icon(draw: ImageDraw.ImageDraw, code: Optional[int], colors: Dict[str, Color]) -> None:
    yellow = colors["yellow"]
    muted = colors["muted"]
    blue = colors["blue"]
    white = colors["white"]
    red = colors["red"]

    if code in (0, 1, None):
        draw_sun(draw, 47, 16, yellow)
    elif code == 2:
        draw_sun(draw, 43, 14, yellow)
        draw_cloud(draw, 25, 20, muted, white)
    elif code in (3, 45, 48):
        draw_cloud(draw, 21, 15, muted, white)
        if code in (45, 48):
            draw.line((22, 43, 55, 43), fill=muted)
            draw.line((26, 48, 51, 48), fill=muted)
    elif code in (51, 53, 55, 61, 63, 65, 80, 81, 82):
        draw_cloud(draw, 21, 12, muted, white)
        for x in (29, 38, 47):
            draw.line((x, 39, x - 3, 48), fill=blue, width=2)
    elif code in (71, 73, 75, 77, 85, 86):
        draw_cloud(draw, 21, 12, muted, white)
        for x, y in ((30, 42), (40, 47), (50, 42)):
            draw.text((x, y), "*", fill=white, font=ImageFont.load_default())
    elif code in (95, 96, 99):
        draw_cloud(draw, 21, 11, muted, white)
        draw.polygon([(40, 34), (33, 48), (42, 46), (35, 58), (51, 39), (42, 41)], fill=yellow)
        draw.line((48, 38, 54, 45), fill=red, width=1)
    else:
        draw_cloud(draw, 21, 15, muted, white)


def weather_icon_name(code: Optional[int], is_night: bool) -> str:
    suffix = "_night" if is_night else ""
    if code in (0,):
        return f"clear{suffix}"
    if code in (1,):
        return f"mostlyClear{suffix}"
    if code in (2,):
        return f"partlyCloudy{suffix}"
    if code in (3,):
        return f"cloudy{suffix}"
    if code in (45, 48):
        return f"foggy{suffix}"
    if code in (51, 53, 55):
        return f"drizzle{suffix}"
    if code in (56, 57):
        return f"freezingDrizzle{suffix}"
    if code in (61, 63):
        return f"rain{suffix}"
    if code in (65, 82):
        return f"heavyRain{suffix}"
    if code in (66, 67):
        return f"freezingRain{suffix}"
    if code in (71, 73, 77):
        return f"snow{suffix}"
    if code in (75,):
        return f"heavySnow{suffix}"
    if code in (80, 81):
        return f"sunShowers{suffix}"
    if code in (85, 86):
        return f"sunFlurries{suffix}"
    if code in (95, 96, 99):
        return f"thunderstorms{suffix}"
    return f"cloudy{suffix}"


def paste_weather_icon(image: Image.Image, code: Optional[int], tz_name: str) -> bool:
    try:
        now = datetime.now(tz=ZoneInfo(tz_name))
    except Exception:
        now = datetime.now(tz=ZoneInfo("UTC"))
    is_night = now.hour < 6 or now.hour >= 18
    icon_name = weather_icon_name(code, is_night)
    icon_path = ICON_DIR / f"{icon_name}.png"
    if not icon_path.exists():
        fallback = ICON_DIR / "cloudy.png"
        if not fallback.exists():
            return False
        icon_path = fallback
    with Image.open(icon_path) as source:
        icon = source.convert("RGBA").resize((32, 32), Image.Resampling.LANCZOS)
    image.alpha_composite(icon, dest=(16, 13))
    return True


def render_date_screen(config: Dict[str, Any]) -> Image.Image:
    style = config["style"]
    loc = config["location"]
    tz = ZoneInfo(loc.get("timezone", "America/Chicago"))
    now = datetime.now(tz)

    colors = {
        "background": rgb(style.get("background"), (0, 0, 0)),
        "white": rgb(style.get("white"), (235, 235, 235)),
        "muted": rgb(style.get("muted"), (130, 130, 130)),
        "blue": rgb(style.get("blue"), (60, 150, 255)),
        "yellow": rgb(style.get("yellow"), (255, 205, 55)),
    }
    font_regular = style.get("font_regular", "")
    font_bold = style.get("font_bold", "")

    image = Image.new("RGB", (64, 64), colors["background"])
    draw = ImageDraw.Draw(image)

    time_font = load_font(font_bold, 18, fallback_bold=True)
    day_font = load_font(font_bold, 11, fallback_bold=True)
    date_font = load_font(font_regular, 10)
    small_font = load_font(font_regular, 8)

    center_text(draw, 1, now.strftime("%-I:%M"), time_font, colors["white"])
    center_text(draw, 23, now.strftime("%A").upper(), day_font, colors["blue"])
    center_text(draw, 39, now.strftime("%b %-d, %Y"), date_font, colors["yellow"])
    center_text(draw, 54, loc.get("name", ""), small_font, colors["muted"])

    return image


def render_weather_screen(config: Dict[str, Any], weather: WeatherData) -> Image.Image:
    style = config["style"]
    loc = config["location"]
    unit_symbol = "F" if config.get("weather", {}).get("units", "fahrenheit") == "fahrenheit" else "C"

    colors = {
        "background": rgb(style.get("background"), (0, 0, 0)),
        "white": rgb(style.get("white"), (235, 235, 235)),
        "muted": rgb(style.get("muted"), (130, 130, 130)),
        "blue": rgb(style.get("blue"), (60, 150, 255)),
        "yellow": rgb(style.get("yellow"), (255, 205, 55)),
        "orange": rgb(style.get("orange"), (255, 145, 45)),
        "red": rgb(style.get("red"), (255, 70, 70)),
    }
    font_regular = style.get("font_regular", "")
    font_bold = style.get("font_bold", "")

    image = Image.new("RGA", (64, 64), colors["background"] + (255,))
    draw = ImageDraw.Draw(image)

    temp_font = load_font(font_bold, 23, fallback_bold=True)
    degree_font = load_font(font_regular, 8)
    label_font = load_font(font_regular, 8)
    small_font = load_font(font_regular, 7)

    if weather.temp is None:
        if not paste_weather_icon(image, None, loc.get("timezone", "UTC")):
          draw_weather_icon(draw, None, colors)
        center_text(draw, 2, "WEATHER", load_font(font_bold, 9, True), colors["blue"])
        center_text(draw, 48, "No data", label_font, colors["muted"])
        return image.convert("RGB")

    if not paste_weather_icon(image, weather.code, loc.get("timezone", "UTC")):
        draw_weather_icon(draw, weather.code, colors)

    temp_text = str(weather.temp)
    draw.text((2, 8), temp_text, font=temp_font, fill=colors["white"])
    temp_w, _ = text_size(draw, temp_text, temp_font)
    draw.text((4 + temp_w, 10), f"°{unit_symbol}", font=degree_font, fill=colors["muted"])

    hi_lo = ""
    if weather.high is not None and weather.low is not None:
        hi_lo = f"H{weather.high} L{weather.low}"
    elif weather.high is not None:
        hi_lo = f"H{weather.high}"
    elif weather.low is not None:
        hi_lo = f"L{weather.low}"
    draw.text((3, 34), hi_lo, font=label_font, fill=colors["orange"])

    condition = weather.condition.upper()
    draw_text_fit(draw, (2, 48), condition, font_bold, 60, 9, 6, colors["blue"], bold=True)

    fetched = weather.fetched_at
    if fetched:
        age = fetched.strftime("%-I:%M")
        draw.text((43, 56), age, font=small_font, fill=colors["muted"])

    return image


class MatrixApp:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.running = True
        self.weather = WeatherData()
        self.next_weather_refresh = datetime.min
        self.matrix = self._build_matrix()

    def _build_matrix(self) -> RGBMatrix:
        matrix_config = self.config["matrix"]
        options = RGBMatrixOptions()
        options.rows = int(matrix_config.get("rows", 64))
        options.cols = int(matrix_config.get("cols", 64))
        options.chain_length = int(matrix_config.get("chain_length", 1))
        options.parallel = int(matrix_config.get("parallel", 1))
        options.hardware_mapping = matrix_config.get("hardware_mapping", "adafruit-hat")
        options.gpio_slowdown = int(matrix_config.get("gpio_slowdown", 4))
        options.brightness = int(matrix_config.get("brightness", 65))
        options.pwm_bits = int(matrix_config.get("pwm_bits", 11))
        options.limit_refresh_rate_hz = int(matrix_config.get("limit_refresh_rate_hz", 120))
        options.led_rgb_sequence = matrix_config.get("rgb_sequence", "RGB")
        return RGBMatrix(options=options)

    def stop(self, *_: Any) -> None:
        self.running = False

    def refresh_weather_if_needed(self) -> None:
        now = datetime.now()
        if now >= self.next_weather_refresh:
            refreshed = fetch_weather(self.config)
            if refreshed.temp is not None:
                self.weather = refreshed
            elif self.weather.temp is None:
                self.weather = refreshed
            minutes = int(self.config.get("weather", {}).get("refresh_minutes", 15))
            self.next_weather_refresh = now + timedelta(minutes=max(1, minutes))

    def show_image(self, image: Image.Image, seconds: int) -> None:
        canvas = self.matrix.CreateFrameCanvas()
        canvas.SetImage(image.convert("RGB"), 0, 0)
        self.matrix.SwapOnVSync(canvas)

        end_time = time.monotonic() + seconds
        while self.running and time.monotonic() < end_time:
            time.sleep(0.1)

    def run(self) -> None:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        screen_config = self.config.get("screens", {})
        date_seconds = int(screen_config.get("date_seconds", 10))
        weather_seconds = int(screen_config.get("weather_seconds", 12))

        while self.running:
            self.refresh_weather_if_needed()
            self.show_image(render_date_screen(self.config), date_seconds)
            if not self.running:
                break
            self.refresh_weather_if_needed()
            self.show_image(render_weather_screen(self.config, self.weather), weather_seconds)

        self.matrix.Clear()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    config = load_config()
    app = MatrixApp(config)
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
