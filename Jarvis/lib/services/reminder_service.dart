import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:timezone/data/latest_all.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

class ReminderService {
  final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  bool _initialized = false;

  /// Called with a notification's payload when the user taps it. Set this
  /// before [init] -- the fake call uses it to open its screen, since tapping
  /// the ring is how you "answer".
  void Function(String payload)? onTapped;

  /// The plugin instance, shared so other features schedule on the same
  /// initialised channel set rather than standing up a second one.
  FlutterLocalNotificationsPlugin get plugin => _plugin;

  Future<void> init() async {
    if (_initialized) return;
    tzdata.initializeTimeZones();

    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const settings = InitializationSettings(android: android);

    await _plugin.initialize(
      settings,
      onDidReceiveNotificationResponse: (r) {
        final p = r.payload;
        if (p != null && p.isNotEmpty) onTapped?.call(p);
      },
    );

    // Marked ready before the permission prompts: those can be denied or throw,
    // and callers still need a usable plugin. Without this a refusal left every
    // later call re-running init and re-prompting.
    _initialized = true;

    // Runtime permissions on Android 13+
    try {
      await Permission.notification.request();
      await _android?.requestExactAlarmsPermission();
    } catch (e) {
      debugPrint('reminders: permission request failed ($e)');
    }
  }

  AndroidFlutterLocalNotificationsPlugin? get _android =>
      _plugin.resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>();

  /// Whether exact alarms are currently allowed. The grant can be refused or
  /// revoked later, and scheduling an exact alarm without it throws.
  Future<bool> canScheduleExact() async {
    try {
      return await _android?.canScheduleExactNotifications() ?? true;
    } catch (_) {
      return false;
    }
  }

  /// Schedules a one-shot reminder at [when] (local time). Returns the
  /// human-friendly string Jarvis should speak.
  Future<String> schedule(String content, DateTime when) async {
    await init();
    if (when.isBefore(DateTime.now())) {
      return "That time is already in the past.";
    }

    final tzTime = tz.TZDateTime.from(when, tz.local);
    final id = DateTime.now().millisecondsSinceEpoch.remainder(0x7fffffff);

    const android = AndroidNotificationDetails(
      'jarvis_reminders',
      'Jarvis Reminders',
      channelDescription: 'One-shot reminders set via Jarvis',
      importance: Importance.max,
      priority: Priority.high,
      playSound: true,
      enableVibration: true,
    );

    await _plugin.zonedSchedule(
      id,
      'Jarvis',
      content,
      tzTime,
      const NotificationDetails(android: android),
      androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
      uiLocalNotificationDateInterpretation:
          UILocalNotificationDateInterpretation.absoluteTime,
      payload: content,
    );

    final pretty = TimeOfDay.fromDateTime(when).format24();
    final dayWord = _dayWord(when);
    return "Reminder set: $content, $dayWord at $pretty.";
  }

  /// Fixed id so rescheduling replaces the digest rather than stacking copies.
  static const _digestId = 90210;

  /// A once-a-day nudge that today's list and fact are waiting.
  ///
  /// The text is composed now and repeats verbatim — without a background
  /// isolate there's no way to recount tasks at fire time, so callers should
  /// re-schedule on app open to keep it roughly current.
  Future<void> scheduleDailyDigest({
    required int hour,
    required int minute,
    required String body,
  }) async {
    await init();

    // Built from a device-local DateTime, then converted. `initializeTimeZones`
    // alone leaves `tz.local` as UTC — composing the time from parts in that
    // zone scheduled 08:30 UTC, i.e. 14:00 in India. Converting an instant is
    // correct whatever `tz.local` happens to be.
    final nowLocal = DateTime.now();
    var firstLocal =
        DateTime(nowLocal.year, nowLocal.month, nowLocal.day, hour, minute);
    if (!firstLocal.isAfter(nowLocal)) {
      firstLocal = firstLocal.add(const Duration(days: 1));
    }
    final first = tz.TZDateTime.from(firstLocal, tz.local);

    const android = AndroidNotificationDetails(
      'jarvis_digest',
      'Daily digest',
      channelDescription: 'Your tasks and fact of the day',
      importance: Importance.defaultImportance,
      priority: Priority.defaultPriority,
    );

    await _plugin.zonedSchedule(
      _digestId,
      'Today',
      body,
      first,
      const NotificationDetails(android: android),
      androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      uiLocalNotificationDateInterpretation:
          UILocalNotificationDateInterpretation.absoluteTime,
      matchDateTimeComponents: DateTimeComponents.time, // repeat daily
    );
  }

  Future<void> cancelDailyDigest() async {
    await init();
    await _plugin.cancel(_digestId);
  }

  String _dayWord(DateTime t) {
    final now = DateTime.now();
    final isToday = t.year == now.year && t.month == now.month && t.day == now.day;
    final tomorrow = now.add(const Duration(days: 1));
    final isTomorrow = t.year == tomorrow.year &&
        t.month == tomorrow.month &&
        t.day == tomorrow.day;
    if (isToday) return "today";
    if (isTomorrow) return "tomorrow";
    return "on ${t.year}-${t.month.toString().padLeft(2, '0')}-${t.day.toString().padLeft(2, '0')}";
  }
}

extension on TimeOfDay {
  String format24() =>
      '${hour.toString().padLeft(2, '0')}:${minute.toString().padLeft(2, '0')}';
}
