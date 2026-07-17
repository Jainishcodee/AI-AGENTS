import 'gemini_service.dart';
import 'notes_service.dart';
import 'reminder_service.dart';
import 'spotify_service.dart';
import 'weather_service.dart';

class JarvisReply {
  final String spokenText;
  final String? statusLine; // optional extra line for the chat card
  JarvisReply(this.spokenText, {this.statusLine});
}

class JarvisBrain {
  final GeminiService gemini = GeminiService();
  final WeatherService weather = WeatherService();
  final NotesService notes = NotesService();
  final ReminderService reminders = ReminderService();
  final SpotifyService spotify = SpotifyService();

  Future<void> init() async {
    await reminders.init();
  }

  Future<JarvisReply> handle(String userText) async {
    final t = userText.trim();
    if (t.isEmpty) return JarvisReply("I didn't hear anything.");

    final result = await gemini.ask(t);
    final action = result.action;

    if (action == null) {
      return JarvisReply(result.text);
    }

    final type = (action['type'] as String?)?.toLowerCase() ?? '';

    switch (type) {
      case 'weather':
        final summary = await weather.describe(
          location: action['location'] as String?,
        );
        return JarvisReply('${result.text} $summary', statusLine: 'Weather');

      case 'note':
        final c = (action['content'] as String?) ?? '';
        final ok = await notes.saveNote(c);
        return JarvisReply(
          ok
              ? '${result.text} You can save it in the notes app I just opened.'
              : "I couldn't open a notes app on this phone.",
          statusLine: 'Note → $c',
        );

      case 'reminder':
        final c = (action['content'] as String?) ?? '';
        final whenStr = action['when'] as String?;
        DateTime? when;
        if (whenStr != null) {
          try {
            when = DateTime.parse(whenStr).toLocal();
          } catch (_) {}
        }
        if (c.isEmpty || when == null) {
          return JarvisReply("I didn't catch the time. Try again with a clearer time.");
        }
        final spoken = await reminders.schedule(c, when);
        return JarvisReply(spoken, statusLine: 'Reminder → $c');

      case 'spotify':
        final q = (action['query'] as String?) ?? '';
        if (q.isEmpty) return JarvisReply("What should I play on Spotify?");
        final ok = await spotify.playSearch(q);
        return JarvisReply(
          ok
              ? '${result.text}'
              : "I couldn't open Spotify on this phone.",
          statusLine: 'Spotify → $q',
        );

      case 'stop':
        return JarvisReply("Okay, stopping.");

      default:
        return JarvisReply(result.text);
    }
  }
}
