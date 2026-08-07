import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timezone/timezone.dart' as tz;

/// A way out of a conversation: arm it discreetly, then the phone rings on its
/// own a few minutes later with a name you chose.
///
/// The whole point is that nothing looks deliberate at the moment it matters,
/// so arming is a hidden gesture that shows no UI, and the delay exists so the
/// call never arrives while you still have your hand on the phone.
class FakeCallService {
  FakeCallService(this._plugin);

  final FlutterLocalNotificationsPlugin _plugin;

  static const _kName = 'fakecall_name';
  static const _kNumber = 'fakecall_number';
  static const _kDelay = 'fakecall_delay_secs';

  /// Fixed id, so arming twice replaces the pending call instead of stacking
  /// two rings a minute apart.
  static const notificationId = 77021;

  /// Marks the notification as ours when the app is opened by tapping it.
  static const payload = 'fake_call';

  String name = 'Mom';
  String number = '+91 98765 43210';
  int delaySecs = 120;

  Future<void> load() async {
    final p = await SharedPreferences.getInstance();
    name = p.getString(_kName) ?? name;
    number = p.getString(_kNumber) ?? number;
    delaySecs = p.getInt(_kDelay) ?? delaySecs;
  }

  Future<void> save({String? name, String? number, int? delaySecs}) async {
    final p = await SharedPreferences.getInstance();
    if (name != null) {
      // An empty caller would render as a blank call screen, which reads as a
      // bug rather than a call. Fall back rather than store nothing.
      this.name = name.trim().isEmpty ? 'Mom' : name.trim();
      await p.setString(_kName, this.name);
    }
    if (number != null) {
      this.number = number.trim();
      await p.setString(_kNumber, this.number);
    }
    if (delaySecs != null) {
      this.delaySecs = delaySecs;
      await p.setInt(_kDelay, delaySecs);
    }
  }

  /// Schedules the ring. Returns when it will land, so the caller can show a
  /// brief confirmation somewhere unobtrusive.
  Future<DateTime> arm({int? inSeconds}) async {
    final wait = inSeconds ?? delaySecs;
    final when = DateTime.now().add(Duration(seconds: wait));

    // A dedicated max-importance channel so this arrives as a heads-up with
    // sound and vibration, rather than sliding silently into the shade with
    // the digest notifications.
    final android = AndroidNotificationDetails(
      'jarvis_fake_call',
      'Incoming call',
      channelDescription: 'The scheduled fake call',
      importance: Importance.max,
      priority: Priority.max,
      category: AndroidNotificationCategory.call,
      playSound: true,
      enableVibration: true,
      // Keeps ringing until it's dealt with, the way a real call would, instead
      // of chiming once and going quiet.
      ongoing: true,
      autoCancel: false,
      fullScreenIntent: true,
      ticker: 'Incoming call',
    );

    await _plugin.zonedSchedule(
      notificationId,
      name,
      number.isEmpty ? 'Incoming call' : number,
      tz.TZDateTime.from(when, tz.local),
      NotificationDetails(android: android),
      androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
      uiLocalNotificationDateInterpretation:
          UILocalNotificationDateInterpretation.absoluteTime,
      payload: payload,
    );
    return when;
  }

  /// Called when the call is answered, declined, or armed by mistake.
  Future<void> cancel() => _plugin.cancel(notificationId);

  String prettyDelay([int? secs]) {
    final s = secs ?? delaySecs;
    if (s < 60) return '${s}s';
    final m = s ~/ 60;
    return s % 60 == 0 ? '${m}m' : '${m}m ${s % 60}s';
  }
}
