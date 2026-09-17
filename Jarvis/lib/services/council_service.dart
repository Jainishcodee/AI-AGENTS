import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'reminder_service.dart';

/// Decisions from Cognitive OS, the council running on the PC.
///
/// **Only the check-in loop lives here, and that is a deliberate narrowing.**
/// The council can deliberate, but a `standard` full-council run is ~40 calls paced
/// at 5 requests a minute — eight minutes of watching a phone, on a machine that
/// may sleep halfway through. Asking is a desk activity and the web client already
/// does it well.
///
/// What a phone is uniquely good at is the half that was never happening at all.
/// Every Decision Card carries a `check_on` date written at the moment the decision
/// was made, and for a long time nothing ever read it out loud: the CLI nudge only
/// printed if you already ran a command, the web badge only showed if you already
/// opened the app. Both assume you are already there, which is precisely the
/// assumption that fails sixty days later. Until a card is resolved the council
/// learns nothing — calibration, priors and replay are all downstream of it.
///
/// So: due cards surface here, and you answer three questions. That is the whole
/// surface, and it is the one that closes the loop.
///
/// Two delivery paths, for the same reason [StockAlertService] has two:
///
/// **Local alarms** are scheduled from `check_on` as soon as a card is seen. They
/// fire with Jarvis closed, the phone locked and the PC switched off — the schedule
/// lives on the phone once set. This matters more here than anywhere else in the
/// app, because the gap between deciding and reviewing is measured in months.
///
/// **Polling** only refreshes the count while the app is open, and is idle-cheap:
/// one small request, and only when something is actually due does it do more.
class CouncilService {
  CouncilService(this._reminders);

  final ReminderService _reminders;

  static const _kBaseUrl = 'council_base_url';
  static const _kEnabled = 'council_enabled';
  static const _kToken = 'council_token';
  static const _kScheduled = 'council_scheduled_';

  /// The PC running `uvicorn app.main:app`, reachable on the same wifi.
  /// 10.0.2.2 is the host machine as seen from an Android emulator.
  String baseUrl = 'http://192.168.1.5:8787';

  /// Shared secret, matching `COUNCIL_TOKEN` on the server. Empty on a private
  /// network, where the API is reachable but nothing else on it is listening.
  ///
  /// Not optional once this leaves the LAN: every route behind it reads or writes
  /// the decision corpus, which is the most personal thing the project holds.
  String token = '';

  bool enabled = true;
  int pollSeconds = 900;

  Timer? _timer;
  bool _polling = false;

  /// Cards whose check-in date has arrived, newest first. Empty until [refresh].
  List<DueDecision> due = const [];

  /// Called whenever [due] changes, so a screen can rebuild without polling it.
  void Function()? onChanged;

  Map<String, String> get _headers => {
        'accept': 'application/json',
        if (token.isNotEmpty) 'X-Council-Token': token,
      };

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    baseUrl = prefs.getString(_kBaseUrl) ?? baseUrl;
    token = prefs.getString(_kToken) ?? '';
    enabled = prefs.getBool(_kEnabled) ?? true;
  }

  Future<void> save({String? url, String? secret, bool? on}) async {
    final prefs = await SharedPreferences.getInstance();
    if (url != null) {
      baseUrl = url.trim();
      await prefs.setString(_kBaseUrl, baseUrl);
    }
    if (secret != null) {
      token = secret.trim();
      await prefs.setString(_kToken, token);
    }
    if (on != null) {
      enabled = on;
      await prefs.setBool(_kEnabled, on);
    }
  }

  void start() {
    stop();
    if (!enabled) return;
    unawaited(refresh());
    _timer = Timer.periodic(Duration(seconds: pollSeconds), (_) => refresh());
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  /// Is the PC up? `/health` is unauthenticated on purpose, so this answers
  /// without needing the token to be right — which makes "wrong secret" and
  /// "machine asleep" distinguishable instead of one generic failure.
  Future<bool> reachable() async {
    try {
      final res = await http
          .get(Uri.parse('$baseUrl/health'))
          .timeout(const Duration(seconds: 4));
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// Fetch what is due and schedule an alarm for anything not already scheduled.
  ///
  /// Failure is silent by design: the PC being off is the normal overnight state,
  /// not an error worth a banner. Anything already scheduled keeps firing anyway.
  Future<void> refresh() async {
    if (!enabled || _polling) return;
    _polling = true;
    try {
      final res = await http
          .get(Uri.parse('$baseUrl/cards?status=due&limit=50'), headers: _headers)
          .timeout(const Duration(seconds: 8));
      if (res.statusCode != 200) return;

      final raw = jsonDecode(utf8.decode(res.bodyBytes)) as List<dynamic>;
      due = raw
          .map((e) => DueDecision.fromJson(e as Map<String, dynamic>))
          .toList(growable: false);
      onChanged?.call();

      // Open cards are the ones worth an alarm — a due card is already overdue.
      await _scheduleUpcoming();
    } catch (_) {
      // Unreachable PC: keep whatever we last knew rather than blanking the list.
    } finally {
      _polling = false;
    }
  }

  /// Put a local alarm on every open card's check-in date.
  ///
  /// Scheduled once per card and remembered in prefs, because
  /// `flutter_local_notifications` will happily stack duplicates for the same id
  /// and a decision you are reminded about four times is one you start ignoring.
  Future<void> _scheduleUpcoming() async {
    final prefs = await SharedPreferences.getInstance();
    try {
      final res = await http
          .get(Uri.parse('$baseUrl/cards?status=open&limit=50'), headers: _headers)
          .timeout(const Duration(seconds: 8));
      if (res.statusCode != 200) return;

      final raw = jsonDecode(utf8.decode(res.bodyBytes)) as List<dynamic>;
      for (final entry in raw) {
        final card = DueDecision.fromJson(entry as Map<String, dynamic>);
        final when = card.checkOn;
        if (when == null || when.isBefore(DateTime.now())) continue;
        if (prefs.getBool('$_kScheduled${card.id}') == true) continue;

        // Late morning, not midnight: a reminder that arrives while you are asleep
        // is read at a moment when you cannot act on it, and then dismissed.
        final at = DateTime(when.year, when.month, when.day, 10);
        if (at.isBefore(DateTime.now())) continue;

        await _reminders.schedule(
          'Decision due for review: ${card.question}',
          at,
        );
        await prefs.setBool('$_kScheduled${card.id}', true);
      }
    } catch (_) {
      // Scheduling is best-effort; the in-app list still shows what is due.
    }
  }

  /// Record what actually happened, and let the council grade itself against it.
  ///
  /// Returns `null` on success, or a message to show. The server saves the
  /// outcome *before* grading, so a grader failure never costs the answers you
  /// just typed — which is worth surfacing rather than showing a bare failure.
  Future<String?> resolve(
    String cardId, {
    required String chose,
    required String outcome,
    List<String> surprises = const [],
    String notes = '',
  }) async {
    try {
      final res = await http
          .post(
            Uri.parse('$baseUrl/cards/$cardId/resolve'),
            headers: {..._headers, 'content-type': 'application/json'},
            body: jsonEncode({
              'chose': chose,
              'actual_outcome': outcome,
              'happened_at': DateTime.now().toIso8601String().split('T').first,
              'surprises': surprises.where((s) => s.trim().isNotEmpty).toList(),
              'notes': notes,
            }),
          )
          .timeout(const Duration(seconds: 90));

      if (res.statusCode == 200) {
        due = due.where((d) => d.id != cardId).toList(growable: false);
        onChanged?.call();
        return null;
      }
      if (res.statusCode == 401) {
        return 'The council rejected the token. Check the secret in settings.';
      }
      if (res.statusCode == 502) {
        // The resolution landed; only the grading pass failed.
        due = due.where((d) => d.id != cardId).toList(growable: false);
        onChanged?.call();
        return 'Saved, but grading failed. Re-grade from the PC — the outcome is safe.';
      }
      return 'The council answered ${res.statusCode}.';
    } on TimeoutException {
      // Grading calls six modules, so a slow free tier can outlast the timeout
      // without anything being wrong. Saying "probably saved" beats implying loss.
      return 'Timed out while grading. The outcome was probably saved — check on the PC.';
    } catch (e) {
      return 'Could not reach the council: $e';
    }
  }
}

/// A Decision Card as the phone needs it: the question, the bet, and the date.
class DueDecision {
  DueDecision({
    required this.id,
    required this.question,
    required this.createdAt,
    this.checkOn,
    this.prediction = '',
    this.measurableBy = '',
    this.recommendation = '',
  });

  final String id;
  final String question;
  final DateTime createdAt;
  final DateTime? checkOn;

  /// What the council predicted *before it knew* — the reason this screen is a
  /// check rather than a reminiscence.
  final String prediction;
  final String measurableBy;
  final String recommendation;

  static DateTime? _date(dynamic v) =>
      v == null ? null : DateTime.tryParse(v as String);

  factory DueDecision.fromJson(Map<String, dynamic> json) {
    final expected = json['expected_outcome'] as Map<String, dynamic>?;
    final synthesis = json['synthesis'] as Map<String, dynamic>?;
    final recommendation =
        (synthesis?['recommendation'] as Map<String, dynamic>?)?['action'];
    return DueDecision(
      id: json['id'] as String,
      question: (json['question'] as String?) ?? '(no question recorded)',
      createdAt: _date(json['created_at']) ?? DateTime.now(),
      checkOn: _date(expected?['check_on']),
      prediction: (expected?['statement'] as String?) ?? '',
      measurableBy: (expected?['measurable_by'] as String?) ?? '',
      recommendation: (recommendation as String?) ?? '',
    );
  }

  /// How overdue this is, in days. Negative means it is not due yet.
  int get overdueDays {
    final on = checkOn;
    if (on == null) return 0;
    return DateTime.now().difference(on).inDays;
  }
}
