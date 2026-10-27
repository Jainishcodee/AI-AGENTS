import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'reminder_service.dart';

/// Decisions from Cognitive OS, the reasoning council running on the PC.
///
/// Features:
/// 1. **Deliberation:** Consult the 6 thinking engines (Analyst, Tactician,
///    Strategist, Psychologist, Optimizer, Ethicist) on complex life and work decisions.
/// 2. **Decision Ledger:** Open, due, and resolved Decision Cards with falsifiable
///    predictions.
/// 3. **The Check-in Loop:** Local alarms scheduled for review dates, closing the loop
///    by recording what actually happened and grading the engines.
/// 4. **Calibration & Track Record:** Brier scores and priors learned over time.
class CouncilService {
  CouncilService(this._reminders);

  final ReminderService _reminders;

  static const _kBaseUrl = 'council_base_url';
  static const _kEnabled = 'council_enabled';
  static const _kToken = 'council_token';
  static const _kScheduled = 'council_scheduled_';

  /// The PC running `uvicorn app.main:app`.
  /// Defaults to 127.0.0.1:8787 for desktop or 10.0.2.2:8787 for Android emulator.
  String baseUrl = 'http://127.0.0.1:8787';

  /// Shared secret, matching `COUNCIL_TOKEN` on the server. Empty on a private
  /// network, where the API is reachable but nothing else on it is listening.
  String token = '';

  bool enabled = true;
  int pollSeconds = 900;

  Timer? _timer;
  bool _polling = false;

  /// Cards whose check-in date has arrived, newest first. Empty until [refresh].
  List<DueDecision> due = const [];

  /// All known cards cached from last fetch.
  List<DueDecision> cachedCards = const [];

  /// Called whenever [due] or [cachedCards] changes.
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
    onChanged?.call();
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

  /// Is the PC up? `/health` is unauthenticated on purpose.
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

  /// Test connection and return status info.
  Future<Map<String, dynamic>> testConnection() async {
    try {
      final res = await http
          .get(Uri.parse('$baseUrl/health'))
          .timeout(const Duration(seconds: 5));
      if (res.statusCode == 200) {
        final data = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
        final modules = (data['modules'] as List<dynamic>?)?.cast<String>() ?? [];
        final presets = (data['presets'] as List<dynamic>?)?.cast<String>() ?? [];
        return {
          'ok': true,
          'message': 'Connected! ${modules.length} engines available.',
          'modules': modules,
          'presets': presets,
        };
      }
      return {
        'ok': false,
        'message': 'Server responded with HTTP ${res.statusCode}',
      };
    } catch (e) {
      return {
        'ok': false,
        'message': 'Could not reach $baseUrl: $e',
      };
    }
  }

  /// Fetch what is due and schedule an alarm for anything not already scheduled.
  Future<void> refresh() async {
    if (!enabled || _polling) return;
    _polling = true;
    try {
      final res = await http
          .get(Uri.parse('$baseUrl/cards?status=due&limit=50'), headers: _headers)
          .timeout(const Duration(seconds: 8));
      if (res.statusCode == 200) {
        final raw = jsonDecode(utf8.decode(res.bodyBytes)) as List<dynamic>;
        due = raw
            .map((e) => DueDecision.fromJson(e as Map<String, dynamic>))
            .toList(growable: false);
        onChanged?.call();
      }

      // Schedule alarms for upcoming open cards
      await _scheduleUpcoming();
    } catch (_) {
      // Unreachable PC: keep whatever we last knew
    } finally {
      _polling = false;
    }
  }

  /// Put a local alarm on every open card's check-in date.
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

        final at = DateTime(when.year, when.month, when.day, 10);
        if (at.isBefore(DateTime.now())) continue;

        await _reminders.schedule(
          'Decision due for review: ${card.question}',
          at,
        );
        await prefs.setBool('$_kScheduled${card.id}', true);
      }
    } catch (_) {
      // Scheduling is best-effort
    }
  }

  /// Run a live deliberation through the 6 thinking engines.
  Future<DeliberationResult> deliberate({
    required String question,
    String? preset,
    String depth = 'quick',
    String contextNotes = '',
  }) async {
    final body = jsonEncode({
      'question': question.trim(),
      if (preset != null && preset.isNotEmpty) 'preset': preset,
      'depth': depth,
      'context_notes': contextNotes.trim(),
    });

    final res = await http
        .post(
          Uri.parse('$baseUrl/council/deliberate/sync'),
          headers: {..._headers, 'content-type': 'application/json'},
          body: body,
        )
        .timeout(const Duration(seconds: 180));

    if (res.statusCode == 200) {
      final data = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
      final result = DeliberationResult.fromJson(data);
      unawaited(refresh());
      return result;
    } else {
      String detail = 'Server returned HTTP ${res.statusCode}';
      try {
        final err = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
        if (err['detail'] != null) detail = err['detail'].toString();
      } catch (_) {}
      throw Exception(detail);
    }
  }

  /// List decision cards with optional status filter ('open', 'due', 'resolved').
  Future<List<DueDecision>> listCards({String? status, int limit = 50}) async {
    try {
      final uri = Uri.parse('$baseUrl/cards').replace(
        queryParameters: {
          if (status != null && status.isNotEmpty) 'status': status,
          'limit': '$limit',
        },
      );
      final res = await http.get(uri, headers: _headers).timeout(const Duration(seconds: 10));
      if (res.statusCode != 200) return const [];

      final raw = jsonDecode(utf8.decode(res.bodyBytes)) as List<dynamic>;
      final cards = raw
          .map((e) => DueDecision.fromJson(e as Map<String, dynamic>))
          .toList(growable: false);
      cachedCards = cards;
      return cards;
    } catch (_) {
      return cachedCards;
    }
  }

  /// Record what actually happened, and let the council grade itself against it.
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
        due = due.where((d) => d.id != cardId).toList(growable: false);
        onChanged?.call();
        return 'Saved, but grading failed. Re-grade from the PC — the outcome is safe.';
      }
      return 'The council answered ${res.statusCode}.';
    } on TimeoutException {
      return 'Timed out while grading. The outcome was probably saved — check on the PC.';
    } catch (e) {
      return 'Could not reach the council: $e';
    }
  }

  /// Fetch calibration scores across the thinking engines.
  Future<List<Map<String, dynamic>>> getScores() async {
    try {
      final res = await http
          .get(Uri.parse('$baseUrl/scores?all=true'), headers: _headers)
          .timeout(const Duration(seconds: 6));
      if (res.statusCode != 200) return const [];
      final data = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
      final scores = data['scores'] as List<dynamic>?;
      return scores?.map((e) => Map<String, dynamic>.from(e as Map)).toList() ?? const [];
    } catch (_) {
      return const [];
    }
  }

  /// Fetch learned priors for the user.
  Future<Map<String, List<String>>> getPriors() async {
    try {
      final res = await http
          .get(Uri.parse('$baseUrl/priors'), headers: _headers)
          .timeout(const Duration(seconds: 6));
      if (res.statusCode != 200) return const {};
      final data = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>;
      final out = <String, List<String>>{};
      data.forEach((module, priorsList) {
        if (priorsList is List) {
          out[module] = priorsList.map((p) {
            if (p is Map && p['text'] != null) return p['text'].toString();
            return p.toString();
          }).toList();
        }
      });
      return out;
    } catch (_) {
      return const {};
    }
  }
}

/// A Decision Card representing an open, due, or resolved decision.
class DueDecision {
  DueDecision({
    required this.id,
    required this.question,
    required this.createdAt,
    this.checkOn,
    this.prediction = '',
    this.measurableBy = '',
    this.recommendation = '',
    this.status = 'open',
    this.chose,
    this.actualOutcome,
    this.notes,
    this.surprises = const [],
    this.preset,
  });

  final String id;
  final String question;
  final DateTime createdAt;
  final DateTime? checkOn;
  final String prediction;
  final String measurableBy;
  final String recommendation;
  final String status; // 'open', 'due', 'resolved'
  final String? chose;
  final String? actualOutcome;
  final String? notes;
  final List<String> surprises;
  final String? preset;

  static DateTime? _date(dynamic v) =>
      v == null ? null : DateTime.tryParse(v as String);

  factory DueDecision.fromJson(Map<String, dynamic> json) {
    final expected = json['expected_outcome'] as Map<String, dynamic>?;
    final synthesis = json['synthesis'] as Map<String, dynamic>?;
    final recommendation =
        (synthesis?['recommendation'] as Map<String, dynamic>?)?['action'];
    final resolution = json['resolution'] as Map<String, dynamic>?;
    final surprisesRaw = resolution?['surprises'] as List<dynamic>?;

    String s = 'open';
    if (resolution != null && (resolution['chose'] != null || resolution['actual_outcome'] != null)) {
      s = 'resolved';
    } else {
      final checkOn = _date(expected?['check_on']);
      if (checkOn != null && (checkOn.isBefore(DateTime.now()) || DateTime.now().difference(checkOn).inDays >= 0)) {
        s = 'due';
      }
    }

    return DueDecision(
      id: json['id'] as String,
      question: (json['question'] as String?) ?? '(no question recorded)',
      createdAt: _date(json['created_at']) ?? DateTime.now(),
      checkOn: _date(expected?['check_on']),
      prediction: (expected?['statement'] as String?) ?? '',
      measurableBy: (expected?['measurable_by'] as String?) ?? '',
      recommendation: (recommendation as String?) ?? '',
      status: (json['status'] as String?) ?? s,
      chose: resolution?['chose'] as String?,
      actualOutcome: resolution?['actual_outcome'] as String?,
      notes: resolution?['notes'] as String?,
      surprises: surprisesRaw?.map((e) => e.toString()).toList() ?? const [],
      preset: json['preset'] as String?,
    );
  }

  /// How overdue this is, in days. Negative means it is not due yet.
  int get overdueDays {
    final on = checkOn;
    if (on == null) return 0;
    return DateTime.now().difference(on).inDays;
  }

  /// Days until due. Negative if overdue.
  int get daysRemaining {
    final on = checkOn;
    if (on == null) return 0;
    return on.difference(DateTime.now()).inDays;
  }
}

/// Structured outcome of a council deliberation.
class DeliberationResult {
  DeliberationResult({
    required this.id,
    required this.question,
    this.preset = 'full',
    this.depth = 'quick',
    required this.action,
    this.firstAction = '',
    this.timeline = '',
    this.debateSummary = '',
    this.confidence = '',
    this.blindSpot = '',
    this.doNot = const [],
    this.conditions = const [],
    this.minorityOpinions = const [],
    this.prediction = '',
    this.checkInDays = 60,
    this.checkOnDate,
    this.moduleConclusions = const {},
  });

  final String id;
  final String question;
  final String preset;
  final String depth;
  final String action;
  final String firstAction;
  final String timeline;
  final String debateSummary;
  final String confidence;
  final String blindSpot;
  final List<String> doNot;
  final List<String> conditions;
  final List<MinorityOpinion> minorityOpinions;
  final String prediction;
  final int checkInDays;
  final String? checkOnDate;
  final Map<String, String> moduleConclusions;

  factory DeliberationResult.fromJson(Map<String, dynamic> json) {
    final syn = json['synthesis'] as Map<String, dynamic>? ?? {};
    final rec = syn['recommendation'] as Map<String, dynamic>? ?? {};
    final exp = syn['expected_outcome'] as Map<String, dynamic>? ?? {};
    final conf = syn['confidence'] as Map<String, dynamic>?;

    final doNotList = (rec['do_not'] as List<dynamic>?)?.cast<String>() ?? const [];
    final condList = (rec['conditions'] as List<dynamic>?)?.cast<String>() ?? const [];

    final minoritiesRaw = syn['minority_opinions'] as List<dynamic>? ?? const [];
    final minorities = minoritiesRaw
        .map((m) => MinorityOpinion.fromJson(m as Map<String, dynamic>))
        .toList();

    // Module conclusions if available
    final conclusions = <String, String>{};
    final runs = json['runs'] as List<dynamic>? ?? const [];
    for (final r in runs) {
      if (r is Map) {
        final mod = r['module'] as String?;
        final stages = r['stages'] as List<dynamic>? ?? const [];
        for (final st in stages) {
          if (st is Map && st['produces'] == 'Conclusion' && st['artifact'] != null) {
            final art = st['artifact'] as Map;
            final stance = art['stance'] ?? art['position'] ?? '';
            if (mod != null && stance.isNotEmpty) {
              conclusions[mod] = stance.toString();
            }
          }
        }
      }
    }

    return DeliberationResult(
      id: (json['id'] as String?) ?? '',
      question: (json['question'] as String?) ?? '',
      preset: (json['preset'] as String?) ?? 'full',
      depth: (json['depth'] as String?) ?? 'quick',
      action: (rec['action'] as String?) ?? 'No specific action determined.',
      firstAction: (rec['first_action'] as String?) ?? '',
      timeline: (rec['timeline'] as String?) ?? '',
      debateSummary: (syn['debate_summary'] as String?) ?? '',
      confidence: conf != null ? '${conf['level']} (${(conf['score'] ?? 0.0) * 100}%)' : '',
      blindSpot: (syn['council_blind_spot'] as String?) ?? '',
      doNot: doNotList,
      conditions: condList,
      minorityOpinions: minorities,
      prediction: (exp['statement'] as String?) ?? '',
      checkInDays: (exp['check_in_days'] as int?) ?? 60,
      checkOnDate: exp['check_on'] as String?,
      moduleConclusions: conclusions,
    );
  }
}

/// A dissenting opinion from one of the engines.
class MinorityOpinion {
  MinorityOpinion({
    required this.module,
    required this.position,
    required this.whenRight,
  });

  final String module;
  final String position;
  final String whenRight;

  factory MinorityOpinion.fromJson(Map<String, dynamic> json) {
    return MinorityOpinion(
      module: (json['module'] as String?) ?? '',
      position: (json['position'] as String?) ?? '',
      whenRight: (json['when_it_would_be_right'] as String?) ?? '',
    );
  }
}
