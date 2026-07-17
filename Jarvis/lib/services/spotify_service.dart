import 'package:android_intent_plus/android_intent.dart';
import 'package:android_intent_plus/flag.dart';
import 'package:url_launcher/url_launcher.dart';

class SpotifyService {
  /// Tries to open the Spotify app with a search for [query]; falls back to
  /// the Spotify web player if the app isn't installed.
  Future<bool> playSearch(String query) async {
    final q = query.trim();
    if (q.isEmpty) return false;

    // 1) Spotify app via custom scheme
    final scheme = Uri.parse('spotify:search:${Uri.encodeComponent(q)}');
    try {
      if (await canLaunchUrl(scheme)) {
        return launchUrl(scheme, mode: LaunchMode.externalApplication);
      }
    } catch (_) {}

    // 2) Spotify app via explicit intent (most reliable on modern Android)
    final intent = AndroidIntent(
      action: 'android.intent.action.VIEW',
      data: 'https://open.spotify.com/search/${Uri.encodeComponent(q)}',
      package: 'com.spotify.music',
      flags: <int>[Flag.FLAG_ACTIVITY_NEW_TASK],
    );
    try {
      await intent.launch();
      return true;
    } catch (_) {}

    // 3) Browser fallback
    final web = Uri.parse('https://open.spotify.com/search/${Uri.encodeComponent(q)}');
    return launchUrl(web, mode: LaunchMode.externalApplication);
  }
}
