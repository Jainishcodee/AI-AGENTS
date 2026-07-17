import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:geocoding/geocoding.dart';
import 'package:geolocator/geolocator.dart';

class WeatherService {
  /// Returns a spoken-ready summary for [location], or for the device GPS if
  /// [location] is null/empty.
  Future<String> describe({String? location}) async {
    try {
      double lat, lon;
      String displayName;

      final loc = (location ?? '').trim();
      if (loc.isNotEmpty) {
        final places = await locationFromAddress(loc);
        if (places.isEmpty) return "I couldn't find $loc on the map.";
        lat = places.first.latitude;
        lon = places.first.longitude;
        displayName = loc;
      } else {
        final pos = await _tryDeviceLocation();
        if (pos != null) {
          lat = pos.latitude;
          lon = pos.longitude;
          displayName = await _reverseGeocode(lat, lon) ?? 'your area';
        } else {
          final fallback = (dotenv.env['DEFAULT_CITY'] ?? 'Mumbai').trim();
          final places = await locationFromAddress(fallback);
          if (places.isEmpty) return "Couldn't get a location.";
          lat = places.first.latitude;
          lon = places.first.longitude;
          displayName = fallback;
        }
      }

      final url = Uri.parse(
        'https://api.open-meteo.com/v1/forecast'
        '?latitude=$lat&longitude=$lon'
        '&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m'
        '&daily=temperature_2m_max,temperature_2m_min'
        '&timezone=auto',
      );
      final resp = await http.get(url);
      if (resp.statusCode != 200) {
        return "Weather service is unreachable right now.";
      }
      final data = jsonDecode(resp.body) as Map<String, dynamic>;
      final cur = data['current'] as Map<String, dynamic>;
      final daily = data['daily'] as Map<String, dynamic>;

      final temp = (cur['temperature_2m'] as num).toDouble();
      final feels = (cur['apparent_temperature'] as num).toDouble();
      final hum = (cur['relative_humidity_2m'] as num).toInt();
      final wind = (cur['wind_speed_10m'] as num).toDouble();
      final code = (cur['weather_code'] as num).toInt();
      final hi = (daily['temperature_2m_max'][0] as num).toDouble();
      final lo = (daily['temperature_2m_min'][0] as num).toDouble();

      final desc = _wmoToWords(code);
      return "$desc in $displayName. "
          "It's ${temp.toStringAsFixed(0)} degrees, feels like ${feels.toStringAsFixed(0)}. "
          "Today's range ${lo.toStringAsFixed(0)} to ${hi.toStringAsFixed(0)}. "
          "Humidity $hum percent, wind ${wind.toStringAsFixed(0)} kilometres per hour.";
    } catch (e) {
      return "I had trouble getting the weather: $e";
    }
  }

  Future<Position?> _tryDeviceLocation() async {
    try {
      final enabled = await Geolocator.isLocationServiceEnabled();
      if (!enabled) return null;
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) {
        perm = await Geolocator.requestPermission();
      }
      if (perm == LocationPermission.denied ||
          perm == LocationPermission.deniedForever) return null;
      return await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.low,
          timeLimit: Duration(seconds: 6),
        ),
      );
    } catch (_) {
      return null;
    }
  }

  Future<String?> _reverseGeocode(double lat, double lon) async {
    try {
      final places = await placemarkFromCoordinates(lat, lon);
      if (places.isEmpty) return null;
      final p = places.first;
      return p.locality?.isNotEmpty == true
          ? p.locality
          : (p.subAdministrativeArea ?? p.administrativeArea);
    } catch (_) {
      return null;
    }
  }

  String _wmoToWords(int c) {
    if (c == 0) return "Clear sky";
    if (c <= 2) return "Mostly clear";
    if (c == 3) return "Overcast";
    if (c <= 48) return "Foggy";
    if (c <= 57) return "Drizzling";
    if (c <= 67) return "Rainy";
    if (c <= 77) return "Snowing";
    if (c <= 82) return "Rain showers";
    if (c <= 86) return "Snow showers";
    return "Thunderstorms";
  }
}
