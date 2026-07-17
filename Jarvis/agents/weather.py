"""Weather agent — uses OpenWeatherMap (free tier).

Looks up the location with their geocoding API, then asks for current
conditions. Key lives in `.env` as OPENWEATHER_API_KEY.
"""
import json
import urllib.parse
import urllib.request

import config
from .base import Agent

_GEO_URL = (
    "https://api.openweathermap.org/geo/1.0/direct?q={}&limit=1&appid={}"
)
_CURRENT_URL = (
    "https://api.openweathermap.org/data/2.5/weather"
    "?lat={}&lon={}&units=metric&appid={}"
)


def _http_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


class WeatherAgent(Agent):
    name = "Weather"
    description = "Reports the current weather for a place via OpenWeatherMap."

    def start(self, args: str = "") -> str:
        if not config.OPENWEATHER_API_KEY:
            return "OpenWeather API key isn't set, sir. Add OPENWEATHER_API_KEY to .env."
        location = args.strip() or config.WEATHER_LOCATION
        self._set_status("running")
        try:
            geo = _http_json(_GEO_URL.format(
                urllib.parse.quote(location), config.OPENWEATHER_API_KEY))
            if not geo:
                return f"I couldn't find a place called {location}, sir."
            lat, lon = geo[0]["lat"], geo[0]["lon"]
            place = geo[0].get("name", location)
            country = geo[0].get("country", "")

            cur = _http_json(_CURRENT_URL.format(
                lat, lon, config.OPENWEATHER_API_KEY))
            temp = cur["main"]["temp"]
            feels = cur["main"]["feels_like"]
            humidity = cur["main"]["humidity"]
            wind_kmh = cur["wind"]["speed"] * 3.6  # OWM gives m/s with metric units
            desc = cur["weather"][0]["description"]

            where = f"{place}, {country}" if country else place
            return (
                f"In {where} it's {temp:.0f} degrees, feels like {feels:.0f}, "
                f"with {desc}. Humidity {humidity} percent, wind {wind_kmh:.0f} "
                f"kilometres per hour."
            )
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return "OpenWeather rejected the key, sir. Check OPENWEATHER_API_KEY in .env."
            return f"Weather service returned {e.code}, sir."
        except Exception as e:  # noqa: BLE001
            return f"Couldn't fetch the weather, sir: {e}"
        finally:
            self._set_status("idle")
