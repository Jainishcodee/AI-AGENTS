import '../models/reel_card.dart';
import 'deck_db.dart';
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
  JarvisBrain({this.deck, ReminderService? reminders})
      : reminders = reminders ?? ReminderService();

  final GeminiService gemini = GeminiService();
  final WeatherService weather = WeatherService();
  final NotesService notes = NotesService();
  final SpotifyService spotify = SpotifyService();

  /// Shared with the daily digest so notification permission is asked once.
  final ReminderService reminders;

  /// Null when the deck failed to open, so the reel intents degrade to a
  /// spoken apology instead of throwing mid-conversation.
  final DeckDb? deck;

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

      case 'today_tasks':
        return _todayTasks();

      case 'daily_fact':
        return _dailyFact();

      case 'complete_task':
        return _completeTask((action['query'] as String?) ?? '');

      case 'find_saved':
        return _findSaved((action['query'] as String?) ?? '');

      case 'stop':
        return JarvisReply("Okay, stopping.");

      default:
        return JarvisReply(result.text);
    }
  }

  // ------------------------------------------------- saved-reel intents
  //
  // These are spoken aloud, so they stay short: a count, then the titles.
  // Detail lives in the Today / Facts / Library tabs.

  JarvisReply get _noDeck =>
      JarvisReply("I couldn't open your saved reels just now.");

  Future<JarvisReply> _todayTasks() async {
    final d = deck;
    if (d == null) return _noDeck;

    final tasks = await d.todayTasks();
    if (tasks.isEmpty) {
      return JarvisReply(
        "Nothing queued today. Your list is clear.",
        statusLine: 'Today · 0 tasks',
      );
    }
    final done = await d.doneToday();
    final left = tasks.where((t) => !done.contains(t.id)).toList();
    if (left.isEmpty) {
      return JarvisReply(
        "All ${tasks.length} done for today. Nicely handled.",
        statusLine: 'Today · all clear',
      );
    }

    final spoken = StringBuffer(
      left.length == 1 ? "One thing left: " : "${left.length} things left. ",
    );
    spoken.write(left.map((t) => t.title).join('. '));
    return JarvisReply(
      spoken.toString(),
      statusLine: 'Today · ${left.length} of ${tasks.length} left',
    );
  }

  Future<JarvisReply> _dailyFact() async {
    final d = deck;
    if (d == null) return _noDeck;

    final fact = await d.dailyFact();
    if (fact == null) {
      return JarvisReply("No facts saved yet.", statusLine: 'Facts · empty');
    }
    final claim = fact.claim.isNotEmpty ? fact.claim : fact.title;
    final extra = fact.applicability.isNotEmpty
        ? " Worth recalling when ${_lowerFirst(fact.applicability)}"
        : '';
    return JarvisReply('$claim$extra', statusLine: 'Fact · ${fact.domain}');
  }

  Future<JarvisReply> _completeTask(String query) async {
    final d = deck;
    if (d == null) return _noDeck;
    if (query.trim().isEmpty) {
      return JarvisReply("Which one did you finish?");
    }

    final match = await d.matchTodayTask(query);
    if (match == null) {
      return JarvisReply(
        "I couldn't find that on today's list.",
        statusLine: 'No match for "$query"',
      );
    }
    if (match.tracksProgress) {
      // Long-term work is nudged, never ticked -- same rule as the Today tab.
      final next = (match.progress + 10).clamp(0, 100);
      await d.setProgress(match.id, next);
      return JarvisReply(
        "Moved ${match.title} to $next percent.",
        statusLine: 'Progress · $next%',
      );
    }
    await d.setDone(match.id, true);
    return JarvisReply(
      "Done: ${match.title}.",
      statusLine: 'Completed · ${match.title}',
    );
  }

  Future<JarvisReply> _findSaved(String query) async {
    final d = deck;
    if (d == null) return _noDeck;
    if (query.trim().isEmpty) {
      return JarvisReply("What should I look for?");
    }

    final hits = await d.search(query);
    if (hits.isEmpty) {
      return JarvisReply(
        "Nothing saved about $query.",
        statusLine: 'No results for "$query"',
      );
    }

    final top = hits.take(3).toList();
    final lead = hits.length == 1
        ? "One thing: "
        : "${hits.length} things. The top ${top.length}: ";
    final body = top
        .map((c) => c.kind == CardKind.fact && c.claim.isNotEmpty
            ? c.claim
            : c.title)
        .join('. ');
    return JarvisReply(
      '$lead$body',
      statusLine: 'Found ${hits.length} for "$query"',
    );
  }

  String _lowerFirst(String s) =>
      s.isEmpty ? s : s[0].toLowerCase() + s.substring(1);
}
