import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timezone/timezone.dart' as tz;

import 'reminder_service.dart';

/// Alerts from StockSeer, the market research tool running on the PC.
///
/// Two delivery paths, because the two kinds of alert have very different
/// timing needs and Android treats them differently:
///
/// **IPO calendar alerts** (an issue opens, closes today, lists tomorrow) are
/// known days ahead, so they are scheduled as local exact alarms. Those fire
/// with Jarvis closed, the phone locked, and the PC switched off — the schedule
/// lives on the phone once set.
///
/// **Listing-morning alerts** (it listed, it is holding, stop hit) depend on a
/// live price and cannot be known in advance, so they are polled from the PC
/// every [pollSeconds]. A Dart timer only runs while the app is alive, so this
/// path needs Jarvis open — which is the honest trade. Fifteen-minute
/// WorkManager ticks would be useless for a 90-minute window, and a foreground
/// service is more machinery than one morning a month justifies.
class StockAlertService {
  StockAlertService(this._reminders);

  final ReminderService _reminders;

  static const _kBaseUrl = 'stockseer_base_url';
  static const _kEnabled = 'stockseer_alerts_enabled';
  static const _seenPrefix = 'stockseer_seen_';

  /// The PC running `stockseer ui`, reachable on the same wifi.
  /// 10.0.2.2 is the host machine as seen from an Android emulator.
  String baseUrl = 'http://192.168.1.5:8765';
  bool enabled = true;
  int pollSeconds = 20;

  Timer? _timer;
  bool _polling = false;

  /// Set by the UI so a tapped alert can open the right screen.
  void Function(Map<String, dynamic> alert)? onAlertTapped;

  final _log = <String>[];
  List<String> get log => List.unmodifiable(_log);

  // ---------------------------------------------------------------- setup

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    baseUrl = prefs.getString(_kBaseUrl) ?? baseUrl;
    enabled = prefs.getBool(_kEnabled) ?? true;
    await _reminders.init();
    if (enabled) start();
  }

  Future<void> configure({String? url, bool? on}) async {
    final prefs = await SharedPreferences.getInstance();
    if (url != null && url.trim().isNotEmpty) {
      baseUrl = url.trim().replaceAll(RegExp(r'/+$'), '');
      await prefs.setString(_kBaseUrl, baseUrl);
    }
    if (on != null) {
      enabled = on;
      await prefs.setBool(_kEnabled, on);
    }
    enabled ? start() : stop();
  }

  void start() {
    _timer?.cancel();
    _timer = Timer.periodic(Duration(seconds: pollSeconds), (_) => poll());
    poll();
  }

  void stop() => _timer?.cancel();

  // ---------------------------------------------------------------- polling

  /// Fetch undelivered alerts, notify, then acknowledge.
  ///
  /// Acknowledging only after the notification is shown means a crash or a lost
  /// connection re-delivers rather than silently dropping — for a stop-loss
  /// alert, a duplicate buzz is far cheaper than a missed one.
  Future<void> poll() async {
    if (!enabled || _polling) return;
    _polling = true;
    try {
      final res = await http
          .get(Uri.parse('$baseUrl/api/notify/pending?limit=10'))
          .timeout(const Duration(seconds: 8));
      if (res.statusCode != 200) return;

      final items = (jsonDecode(res.body) as List).cast<Map<String, dynamic>>();
      if (items.isEmpty) return;

      final delivered = <String>[];
      for (final alert in items) {
        try {
          await _show(alert);
          delivered.add(alert['id'] as String);
        } catch (e) {
          debugPrint('stockseer: could not show alert ($e)');
        }
      }
      if (delivered.isNotEmpty) await _ack(delivered);
      _note('delivered ${delivered.length} alert(s)');
    } on TimeoutException {
      // The PC is asleep or off the network. Normal; try again next tick.
    } catch (e) {
      debugPrint('stockseer: poll failed ($e)');
    } finally {
      _polling = false;
    }
  }

  Future<void> _ack(List<String> ids) async {
    try {
      await http
          .post(Uri.parse('$baseUrl/api/notify/ack'),
              headers: {'Content-Type': 'application/json'},
              body: jsonEncode({'ids': ids}))
          .timeout(const Duration(seconds: 8));
    } catch (e) {
      debugPrint('stockseer: ack failed ($e)');
    }
  }

  // ------------------------------------------------------------ notifying

  /// One channel per urgency. Android caches channel settings at creation, so
  /// vibration and importance cannot be changed per-notification afterwards —
  /// separate channels are the only way to make a stop-loss buzz differently
  /// from an FYI, and the user can mute one without losing the other.
  AndroidNotificationDetails _channelFor(String urgency, List<int> pattern) {
    final vib = Int64List.fromList(pattern.isEmpty ? [0, 250] : pattern);
    switch (urgency) {
      case 'critical':
        return AndroidNotificationDetails(
          'stockseer_critical', 'Market: act now',
          channelDescription: 'Entry windows, stops, and profit targets',
          importance: Importance.max,
          priority: Priority.max,
          category: AndroidNotificationCategory.alarm,
          enableVibration: true,
          vibrationPattern: vib,
          fullScreenIntent: true,
          ticker: 'StockSeer',
        );
      case 'act':
        return AndroidNotificationDetails(
          'stockseer_act', 'Market: needs a decision',
          channelDescription: 'IPO deadlines and listing events',
          importance: Importance.high,
          priority: Priority.high,
          enableVibration: true,
          vibrationPattern: vib,
          ticker: 'StockSeer',
        );
      default:
        return AndroidNotificationDetails(
          'stockseer_info', 'Market: for information',
          channelDescription: 'Upcoming IPOs and general updates',
          importance: Importance.defaultImportance,
          priority: Priority.defaultPriority,
          enableVibration: true,
          vibrationPattern: vib,
        );
    }
  }

  Future<void> _show(Map<String, dynamic> alert) async {
    final urgency = (alert['urgency'] as String?) ?? 'info';
    final pattern =
        ((alert['vibration'] as List?) ?? const []).map((e) => e as int).toList();

    await _reminders.plugin.show(
      alert['id'].hashCode & 0x7fffffff,
      (alert['title'] as String?) ?? 'StockSeer',
      (alert['body'] as String?) ?? '',
      NotificationDetails(
        android: _channelFor(urgency, pattern).copyWithStyle(
          (alert['body'] as String?) ?? '',
        ),
      ),
      payload: jsonEncode({'source': 'stockseer', ...alert}),
    );
  }

  // ------------------------------------------------- scheduled IPO calendar

  /// Pull the IPO calendar and schedule local alarms for each dated event.
  ///
  /// Run this once a day while the app is open — after that the phone holds the
  /// schedule, so a "closes today" alert still fires on a morning when Jarvis
  /// was never opened and the PC never turned on.
  Future<int> syncIpoCalendar({int hour = 9, int minute = 30}) async {
    if (!enabled) return 0;
    try {
      final res = await http
          .get(Uri.parse('$baseUrl/api/ipo/calendar'))
          .timeout(const Duration(seconds: 12));
      if (res.statusCode != 200) return 0;

      final events = (jsonDecode(res.body) as List).cast<Map<String, dynamic>>();
      final prefs = await SharedPreferences.getInstance();
      var scheduled = 0;

      for (final ev in events) {
        final ipo = (ev['ipo'] as Map).cast<String, dynamic>();
        final symbol = ipo['symbol'] as String? ?? '?';
        final kind = ev['kind'] as String? ?? 'event';
        final end = ipo['ipo_end'] as String?;
        if (end == null) continue;

        // One alarm per (symbol, kind) — re-syncing must not stack duplicates.
        final key = '$_seenPrefix${symbol}_$kind';
        if (prefs.getBool(key) ?? false) continue;

        final when = _alarmTime(kind, end, ipo['listing_date'] as String?,
            hour, minute);
        if (when == null || when.isBefore(DateTime.now())) continue;

        await _scheduleOne(symbol, kind, ipo, when);
        await prefs.setBool(key, true);
        scheduled++;
      }
      _note('scheduled $scheduled IPO alarm(s)');
      return scheduled;
    } catch (e) {
      debugPrint('stockseer: calendar sync failed ($e)');
      return 0;
    }
  }

  DateTime? _alarmTime(
      String kind, String end, String? listing, int hour, int minute) {
    DateTime? day;
    if (kind == 'closes_today' || kind == 'closes_tomorrow') {
      day = DateTime.tryParse(end);
    } else if (kind == 'lists_tomorrow' && listing != null) {
      day = DateTime.tryParse(listing);
      // Listing morning: nudge before the 10:00 open rather than at 09:30.
      if (day != null) {
        return DateTime(day.year, day.month, day.day, 9, 50);
      }
    } else {
      day = DateTime.tryParse(end);
    }
    if (day == null) return null;
    return DateTime(day.year, day.month, day.day, hour, minute);
  }

  Future<void> _scheduleOne(String symbol, String kind,
      Map<String, dynamic> ipo, DateTime when) async {
    final closing = kind.startsWith('closes');
    final title = closing
        ? 'LAST DAY: $symbol IPO'
        : kind == 'lists_tomorrow'
            ? '$symbol lists at 10:00'
            : '$symbol IPO';
    final band = (ipo['price_range'] as String?)?.isNotEmpty == true
        ? ipo['price_range']
        : 'Rs.${ipo['issue_price']}';
    final body = closing
        ? '${ipo['company']}\n$band\nUPI mandate cut-off is usually 5 PM today.'
        : '${ipo['company']}\n$band';

    await _reminders.plugin.zonedSchedule(
      '$symbol$kind'.hashCode & 0x7fffffff,
      title,
      body,
      tz.TZDateTime.from(when, tz.local),
      NotificationDetails(
        android: _channelFor(closing ? 'critical' : 'act',
            closing ? const [0, 700, 200, 700, 200, 700] : const [0, 420, 180, 420]),
      ),
      androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
      uiLocalNotificationDateInterpretation:
          UILocalNotificationDateInterpretation.absoluteTime,
      payload: jsonEncode({'source': 'stockseer', 'symbol': symbol, 'kind': kind}),
    );
  }

  void _note(String msg) {
    _log.insert(0, '${DateTime.now().toIso8601String().substring(11, 19)}  $msg');
    if (_log.length > 50) _log.removeLast();
  }

  /// Round-trip check for the settings screen.
  Future<String> testConnection() async {
    try {
      final res = await http
          .get(Uri.parse('$baseUrl/api/state'))
          .timeout(const Duration(seconds: 8));
      if (res.statusCode != 200) return 'HTTP ${res.statusCode}';
      final feed = (jsonDecode(res.body) as Map)['feed'];
      return 'Connected — feed: $feed';
    } catch (e) {
      return 'Cannot reach $baseUrl\n$e';
    }
  }

  void dispose() => _timer?.cancel();
}

extension on AndroidNotificationDetails {
  /// Long alerts get truncated to one line without an explicit style, and these
  /// bodies carry the stop price and the base rate — the parts worth reading.
  AndroidNotificationDetails copyWithStyle(String body) =>
      AndroidNotificationDetails(
        channelId,
        channelName,
        channelDescription: channelDescription,
        importance: importance,
        priority: priority,
        category: category,
        enableVibration: enableVibration,
        vibrationPattern: vibrationPattern,
        fullScreenIntent: fullScreenIntent,
        ticker: ticker,
        styleInformation: BigTextStyleInformation(body),
      );
}
