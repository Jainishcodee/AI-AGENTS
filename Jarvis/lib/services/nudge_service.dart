import 'package:flutter/services.dart';

/// The two things Jarvis interrupts you for.
enum NudgeKind { water, eyes }

extension NudgeKindX on NudgeKind {
  String get key => name;

  String get label => switch (this) {
        NudgeKind.water => 'Water',
        NudgeKind.eyes => 'Eyes',
      };

  String get blurb => switch (this) {
        NudgeKind.water =>
          'Jarvis slides in over whatever you\'re doing and drinks, so you '
              'remember to as well.',
        NudgeKind.eyes =>
          'Every 20 minutes, look at something 20 feet away for 20 seconds. '
              'Jarvis takes his glasses off and waits it out with you.',
      };

  /// Intervals offered in the picker, and which one is the recommendation.
  List<int> get intervalChoices => switch (this) {
        NudgeKind.water => const [30, 45, 60, 90],
        NudgeKind.eyes => const [20, 30, 45, 60],
      };

  int get suggestedInterval => switch (this) {
        NudgeKind.water => 45,
        NudgeKind.eyes => 20,
      };

  /// Water: millilitres per day. Eyes: seconds to hold the look.
  List<int> get amountChoices => switch (this) {
        NudgeKind.water => const [2200, 2600, 3000, 3500],
        NudgeKind.eyes => const [20, 30, 60, 120],
      };

  String amountLabel(int v) => switch (this) {
        NudgeKind.water => '${(v / 1000).toStringAsFixed(1)} L',
        NudgeKind.eyes => '$v s',
      };

  String? amountNote(int v) => switch (this) {
        NudgeKind.water => switch (v) { 2200 => 'women', 3000 => 'men', _ => null },
        NudgeKind.eyes => switch (v) { 20 => 'the rule', 60 => 'better evidence', _ => null },
      };

  String get amountTitle => switch (this) {
        NudgeKind.water => 'DAILY TARGET',
        NudgeKind.eyes => 'LOOK AWAY FOR',
      };
}

/// Settings for one nudge, as the native side reports them.
class NudgeSettings {
  final NudgeKind kind;
  final bool enabled;
  final int intervalMin;
  final int startMin;
  final int endMin;
  final int amount;

  /// Derived natively so the overlay and this screen can't disagree.
  final int perNudge;
  final int nudgesPerDay;
  final int countToday;
  final DateTime nextFireAt;

  const NudgeSettings({
    required this.kind,
    required this.enabled,
    required this.intervalMin,
    required this.startMin,
    required this.endMin,
    required this.amount,
    required this.perNudge,
    required this.nudgesPerDay,
    required this.countToday,
    required this.nextFireAt,
  });

  factory NudgeSettings.fromMap(NudgeKind kind, Map<dynamic, dynamic> m) {
    final defaults = NudgeSettings.defaultsFor(kind);
    return NudgeSettings(
      kind: kind,
      enabled: (m['enabled'] as bool?) ?? false,
      intervalMin: (m['intervalMin'] as int?) ?? defaults.intervalMin,
      startMin: (m['startMin'] as int?) ?? defaults.startMin,
      endMin: (m['endMin'] as int?) ?? defaults.endMin,
      amount: (m['amount'] as int?) ?? defaults.amount,
      perNudge: (m['perNudge'] as int?) ?? defaults.perNudge,
      nudgesPerDay: (m['nudgesPerDay'] as int?) ?? defaults.nudgesPerDay,
      countToday: (m['countToday'] as int?) ?? 0,
      nextFireAt: DateTime.fromMillisecondsSinceEpoch(
        (m['nextFireAt'] as int?) ?? 0,
      ),
    );
  }

  /// Mirrors the native defaults, for the first paint before the channel answers.
  static NudgeSettings defaultsFor(NudgeKind kind) => switch (kind) {
        NudgeKind.water => NudgeSettings(
            kind: kind,
            enabled: false,
            intervalMin: 45,
            startMin: 7 * 60,
            endMin: 22 * 60,
            amount: 3000,
            perNudge: 150,
            nudgesPerDay: 20,
            countToday: 0,
            nextFireAt: DateTime.fromMillisecondsSinceEpoch(0),
          ),
        NudgeKind.eyes => NudgeSettings(
            kind: kind,
            enabled: false,
            intervalMin: 20,
            startMin: 9 * 60,
            endMin: 23 * 60,
            amount: 20,
            perNudge: 20,
            nudgesPerDay: 42,
            countToday: 0,
            nextFireAt: DateTime.fromMillisecondsSinceEpoch(0),
          ),
      };

  NudgeSettings copyWith({
    bool? enabled,
    int? intervalMin,
    int? startMin,
    int? endMin,
    int? amount,
  }) =>
      NudgeSettings(
        kind: kind,
        enabled: enabled ?? this.enabled,
        intervalMin: intervalMin ?? this.intervalMin,
        startMin: startMin ?? this.startMin,
        endMin: endMin ?? this.endMin,
        amount: amount ?? this.amount,
        perNudge: perNudge,
        nudgesPerDay: nudgesPerDay,
        countToday: countToday,
        nextFireAt: nextFireAt,
      );

  String get windowLabel => '${_hhmm(startMin)} – ${_hhmm(endMin)}';

  /// One line summarising the schedule, for the card on the Today screen.
  String get summary => switch (kind) {
        NudgeKind.water => 'every $intervalMin min · ${perNudge}ml',
        NudgeKind.eyes => 'every $intervalMin min · ${perNudge}s look away',
      };

  static String _hhmm(int minutes) =>
      '${(minutes ~/ 60).toString().padLeft(2, '0')}:'
      '${(minutes % 60).toString().padLeft(2, '0')}';
}

/// Talks to the native alarm + overlay. Android only; every call degrades to a
/// no-op elsewhere rather than throwing.
class NudgeService {
  static const _ch = MethodChannel('com.larossatech.jarvis/water');

  Future<bool> canDrawOverlays() async =>
      await _try<bool>('canDrawOverlays') ?? false;

  Future<void> requestOverlayPermission() =>
      _try<void>('requestOverlayPermission');

  Future<bool> canScheduleExactAlarms() async =>
      await _try<bool>('canScheduleExactAlarms') ?? true;

  Future<void> requestExactAlarmPermission() =>
      _try<void>('requestExactAlarmPermission');

  Future<NudgeSettings?> getSettings(NudgeKind kind) async {
    final m = await _try<Map<dynamic, dynamic>>('getSettings', {'kind': kind.key});
    return m == null ? null : NudgeSettings.fromMap(kind, m);
  }

  Future<NudgeSettings?> save(NudgeSettings s) async {
    final m = await _try<Map<dynamic, dynamic>>('saveSettings', {
      'kind': s.kind.key,
      'enabled': s.enabled,
      'intervalMin': s.intervalMin,
      'startMin': s.startMin,
      'endMin': s.endMin,
      'amount': s.amount,
    });
    return m == null ? null : NudgeSettings.fromMap(s.kind, m);
  }

  /// Shows the overlay now, so the setting can be proved without waiting.
  Future<bool> preview(NudgeKind kind) async =>
      await _try<bool>('preview', {'kind': kind.key}) ?? false;

  Future<T?> _try<T>(String method, [Map<String, dynamic>? args]) async {
    try {
      return await _ch.invokeMethod<T>(method, args);
    } on MissingPluginException {
      return null; // not Android, or the engine isn't attached yet
    } on PlatformException {
      return null;
    }
  }
}
