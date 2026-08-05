import 'package:flutter/services.dart';

/// Settings for the water nudge, as the native side reports them.
class WaterSettings {
  final bool enabled;
  final int intervalMin;
  final int startMin;
  final int endMin;
  final int targetMl;

  /// Derived on the native side so the overlay and this screen can't disagree.
  final int perNudgeMl;
  final int nudgesPerDay;
  final int countToday;
  final DateTime nextFireAt;

  const WaterSettings({
    required this.enabled,
    required this.intervalMin,
    required this.startMin,
    required this.endMin,
    required this.targetMl,
    required this.perNudgeMl,
    required this.nudgesPerDay,
    required this.countToday,
    required this.nextFireAt,
  });

  factory WaterSettings.fromMap(Map<dynamic, dynamic> m) => WaterSettings(
        enabled: (m['enabled'] as bool?) ?? false,
        intervalMin: (m['intervalMin'] as int?) ?? 45,
        startMin: (m['startMin'] as int?) ?? 7 * 60,
        endMin: (m['endMin'] as int?) ?? 22 * 60,
        targetMl: (m['targetMl'] as int?) ?? 3000,
        perNudgeMl: (m['perNudgeMl'] as int?) ?? 150,
        nudgesPerDay: (m['nudgesPerDay'] as int?) ?? 20,
        countToday: (m['countToday'] as int?) ?? 0,
        nextFireAt: DateTime.fromMillisecondsSinceEpoch(
          (m['nextFireAt'] as int?) ?? DateTime.now().millisecondsSinceEpoch,
        ),
      );

  /// Defaults for the first paint, before the native side has answered.
  static final empty = WaterSettings(
    enabled: false,
    intervalMin: 45,
    startMin: 7 * 60,
    endMin: 22 * 60,
    targetMl: 3000,
    perNudgeMl: 150,
    nudgesPerDay: 20,
    countToday: 0,
    nextFireAt: DateTime.fromMillisecondsSinceEpoch(0),
  );

  WaterSettings copyWith({
    bool? enabled,
    int? intervalMin,
    int? startMin,
    int? endMin,
    int? targetMl,
  }) =>
      WaterSettings(
        enabled: enabled ?? this.enabled,
        intervalMin: intervalMin ?? this.intervalMin,
        startMin: startMin ?? this.startMin,
        endMin: endMin ?? this.endMin,
        targetMl: targetMl ?? this.targetMl,
        perNudgeMl: perNudgeMl,
        nudgesPerDay: nudgesPerDay,
        countToday: countToday,
        nextFireAt: nextFireAt,
      );

  String get windowLabel => '${_hhmm(startMin)} – ${_hhmm(endMin)}';

  static String _hhmm(int minutes) =>
      '${(minutes ~/ 60).toString().padLeft(2, '0')}:'
      '${(minutes % 60).toString().padLeft(2, '0')}';
}

/// Talks to the native alarm + overlay. Android only; every call degrades to a
/// no-op elsewhere rather than throwing.
class WaterService {
  static const _ch = MethodChannel('com.larossatech.jarvis/water');

  Future<bool> canDrawOverlays() async =>
      await _try<bool>('canDrawOverlays') ?? false;

  Future<void> requestOverlayPermission() => _try<void>('requestOverlayPermission');

  Future<bool> canScheduleExactAlarms() async =>
      await _try<bool>('canScheduleExactAlarms') ?? true;

  Future<void> requestExactAlarmPermission() =>
      _try<void>('requestExactAlarmPermission');

  Future<WaterSettings?> getSettings() async {
    final m = await _try<Map<dynamic, dynamic>>('getSettings');
    return m == null ? null : WaterSettings.fromMap(m);
  }

  Future<WaterSettings?> save({
    required bool enabled,
    required int intervalMin,
    required int startMin,
    required int endMin,
    required int targetMl,
  }) async {
    final m = await _try<Map<dynamic, dynamic>>('saveSettings', {
      'enabled': enabled,
      'intervalMin': intervalMin,
      'startMin': startMin,
      'endMin': endMin,
      'targetMl': targetMl,
    });
    return m == null ? null : WaterSettings.fromMap(m);
  }

  /// Shows the overlay right now, so the setting can be proved without waiting.
  Future<bool> preview() async => await _try<bool>('preview') ?? false;

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
