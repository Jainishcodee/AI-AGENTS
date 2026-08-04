import 'package:shared_preferences/shared_preferences.dart';

import 'deck_db.dart';
import 'reminder_service.dart';

/// When (and whether) the daily nudge fires.
///
/// Kept in shared_preferences rather than the deck database because it's a
/// user preference, not deck content — re-importing a deck shouldn't touch it.
class DigestSettings {
  static const _kOn = 'digest_on';
  static const _kHour = 'digest_hour';
  static const _kMinute = 'digest_minute';

  final ReminderService reminders;
  DigestSettings(this.reminders);

  bool enabled = false;
  int hour = 8;
  int minute = 30;

  String get pretty =>
      '${hour.toString().padLeft(2, '0')}:${minute.toString().padLeft(2, '0')}';

  Future<void> load() async {
    final p = await SharedPreferences.getInstance();
    enabled = p.getBool(_kOn) ?? false;
    hour = p.getInt(_kHour) ?? 8;
    minute = p.getInt(_kMinute) ?? 30;
  }

  Future<void> save({bool? on, int? h, int? m}) async {
    enabled = on ?? enabled;
    hour = h ?? hour;
    minute = m ?? minute;
    final p = await SharedPreferences.getInstance();
    await p.setBool(_kOn, enabled);
    await p.setInt(_kHour, hour);
    await p.setInt(_kMinute, minute);
  }

  /// Re-arms the notification with today's real numbers. Safe to call on every
  /// app open; that's what keeps the repeating text from going stale.
  Future<void> apply(DeckDb? deck) async {
    if (!enabled) {
      await reminders.cancelDailyDigest();
      return;
    }
    await reminders.scheduleDailyDigest(
      hour: hour,
      minute: minute,
      body: await _body(deck),
    );
  }

  Future<String> _body(DeckDb? deck) async {
    if (deck == null) return 'Your tasks and fact of the day are ready.';
    try {
      final tasks = await deck.todayTasks();
      final done = await deck.doneToday();
      final left = tasks.where((t) => !done.contains(t.id)).length;
      if (tasks.isEmpty) return 'Your fact of the day is ready.';
      final noun = left == 1 ? 'task' : 'tasks';
      return '$left $noun waiting, plus your fact of the day.';
    } catch (_) {
      return 'Your tasks and fact of the day are ready.';
    }
  }
}
