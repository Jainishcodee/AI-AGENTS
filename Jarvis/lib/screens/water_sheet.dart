import 'package:flutter/material.dart';

import '../services/water_service.dart';
import '../widgets/card_bits.dart';

/// Settings for the water nudge.
///
/// The numbers here aren't arbitrary: the National Academies put adequate
/// intake at 3.7 L/day of total water for men and 2.7 L for women, about a
/// fifth of which comes from food — so the drinking-water target lands near
/// 3.0 L and 2.2 L. Spread over waking hours that's roughly 200 ml an hour,
/// comfortably under the ~1 L/hour the kidneys can clear.
Future<void> showWaterSheet(BuildContext context, WaterService water) {
  return showModalBottomSheet(
    context: context,
    backgroundColor: kSurface,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => _WaterSheet(water: water),
  );
}

const _kWater = Color(0xFF4FC3F7);

class _WaterSheet extends StatefulWidget {
  const _WaterSheet({required this.water});
  final WaterService water;

  @override
  State<_WaterSheet> createState() => _WaterSheetState();
}

class _WaterSheetState extends State<_WaterSheet> {
  WaterSettings _s = WaterSettings.empty;
  bool _loading = true;
  bool _canOverlay = false;
  bool _canExact = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final s = await widget.water.getSettings();
    final overlay = await widget.water.canDrawOverlays();
    final exact = await widget.water.canScheduleExactAlarms();
    if (!mounted) return;
    setState(() {
      _s = s ?? WaterSettings.empty;
      _canOverlay = overlay;
      _canExact = exact;
      _loading = false;
    });
  }

  Future<void> _push(WaterSettings next) async {
    setState(() => _s = next);
    final saved = await widget.water.save(
      enabled: next.enabled,
      intervalMin: next.intervalMin,
      startMin: next.startMin,
      endMin: next.endMin,
      targetMl: next.targetMl,
    );
    if (!mounted || saved == null) return;
    setState(() => _s = saved);
  }

  Future<void> _toggle(bool on) async {
    if (on && !_canOverlay) {
      await widget.water.requestOverlayPermission();
      // The grant happens in Settings, so re-check when we're resumed.
      if (!mounted) return;
      final ok = await widget.water.canDrawOverlays();
      if (!mounted) return;
      setState(() => _canOverlay = ok);
      if (!ok) return;
    }
    await _push(_s.copyWith(enabled: on));
  }

  Future<void> _pickWindow() async {
    final start = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: _s.startMin ~/ 60, minute: _s.startMin % 60),
      helpText: 'First nudge of the day',
    );
    if (start == null || !mounted) return;
    final end = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: _s.endMin ~/ 60, minute: _s.endMin % 60),
      helpText: 'Last nudge of the day',
    );
    if (end == null) return;
    await _push(_s.copyWith(
      startMin: start.hour * 60 + start.minute,
      endMin: end.hour * 60 + end.minute,
    ));
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const SizedBox(
        height: 260,
        child: Center(child: CircularProgressIndicator(color: _kWater)),
      );
    }

    return SafeArea(
      child: ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.fromLTRB(20, 14, 20, 24),
        children: [
          Center(
            child: Container(
              width: 38,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.18),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              const Icon(Icons.water_drop, color: _kWater, size: 20),
              const SizedBox(width: 9),
              const Expanded(
                child: Text(
                  'Water nudge',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    color: Colors.white,
                  ),
                ),
              ),
              Switch(
                value: _s.enabled,
                activeThumbColor: _kWater,
                onChanged: _toggle,
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            'Jarvis slides in over whatever you\'re doing and drinks, so you '
            'remember to as well.',
            style: TextStyle(
              fontSize: 13,
              height: 1.4,
              color: Colors.white.withValues(alpha: 0.55),
            ),
          ),
          const SizedBox(height: 18),

          if (!_canOverlay)
            _Notice(
              icon: Icons.layers_outlined,
              text: 'Needs "display over other apps" permission.',
              action: 'Grant',
              onTap: () async {
                await widget.water.requestOverlayPermission();
                final ok = await widget.water.canDrawOverlays();
                if (mounted) setState(() => _canOverlay = ok);
              },
            ),
          if (!_canExact)
            _Notice(
              icon: Icons.alarm,
              text: 'Without exact alarms the timing drifts by a few minutes.',
              action: 'Fix',
              onTap: () async {
                await widget.water.requestExactAlarmPermission();
                final ok = await widget.water.canScheduleExactAlarms();
                if (mounted) setState(() => _canExact = ok);
              },
            ),

          _label('EVERY'),
          _Chips<int>(
            values: const [30, 45, 60, 90],
            selected: _s.intervalMin,
            labelFor: (v) => '$v min',
            noteFor: (v) => v == 45 ? 'suggested' : null,
            onPick: (v) => _push(_s.copyWith(intervalMin: v)),
          ),
          const SizedBox(height: 18),

          _label('DAILY TARGET'),
          _Chips<int>(
            values: const [2200, 2600, 3000, 3500],
            selected: _s.targetMl,
            labelFor: (v) => '${(v / 1000).toStringAsFixed(1)} L',
            noteFor: (v) => switch (v) {
              2200 => 'women',
              3000 => 'men',
              _ => null,
            },
            onPick: (v) => _push(_s.copyWith(targetMl: v)),
          ),
          const SizedBox(height: 18),

          _label('WAKING HOURS'),
          GestureDetector(
            onTap: _pickWindow,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.05),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.white.withValues(alpha: 0.09)),
              ),
              child: Row(
                children: [
                  Text(
                    _s.windowLabel,
                    style: const TextStyle(
                      fontSize: 15,
                      color: Colors.white,
                      fontFeatures: [FontFeature.tabularFigures()],
                    ),
                  ),
                  const Spacer(),
                  Icon(Icons.edit_outlined,
                      size: 17, color: Colors.white.withValues(alpha: 0.4)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),

          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: _kWater.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(12),
              border: Border(
                left: BorderSide(color: _kWater.withValues(alpha: 0.5), width: 2),
              ),
            ),
            child: Text(
              'That works out to about ${_s.perNudgeMl} ml a time, '
              '${_s.nudgesPerDay} times across ${_s.windowLabel}.'
              '${_s.enabled ? '\n${_s.countToday} done today.' : ''}',
              style: const TextStyle(
                fontSize: 13,
                height: 1.45,
                color: _kWater,
              ),
            ),
          ),
          const SizedBox(height: 14),

          Align(
            alignment: Alignment.centerLeft,
            child: CardAction(
              icon: Icons.play_circle_outline,
              label: 'Show it now',
              color: _kWater,
              onTap: () async {
                // Resolve both before the await so the closure never touches a
                // BuildContext that the sheet may have popped out from under.
                final messenger = ScaffoldMessenger.of(context);
                final navigator = Navigator.of(context);
                final ok = await widget.water.preview();
                if (!mounted) return;
                if (ok) {
                  navigator.pop();
                } else {
                  messenger.showSnackBar(
                    const SnackBar(
                      content: Text('Grant the overlay permission first'),
                      behavior: SnackBarBehavior.floating,
                    ),
                  );
                }
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _label(String s) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(
          s,
          style: TextStyle(
            fontSize: 10,
            letterSpacing: 1.8,
            fontWeight: FontWeight.w700,
            color: Colors.white.withValues(alpha: 0.4),
          ),
        ),
      );
}

class _Chips<T> extends StatelessWidget {
  const _Chips({
    required this.values,
    required this.selected,
    required this.labelFor,
    required this.onPick,
    this.noteFor,
  });

  final List<T> values;
  final T selected;
  final String Function(T) labelFor;
  final String? Function(T)? noteFor;
  final ValueChanged<T> onPick;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final v in values)
          GestureDetector(
            onTap: () => onPick(v),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
              decoration: BoxDecoration(
                color: v == selected
                    ? _kWater.withValues(alpha: 0.18)
                    : Colors.white.withValues(alpha: 0.05),
                borderRadius: BorderRadius.circular(999),
                border: Border.all(
                  color: v == selected
                      ? _kWater.withValues(alpha: 0.6)
                      : Colors.white.withValues(alpha: 0.09),
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    labelFor(v),
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: v == selected ? FontWeight.w700 : FontWeight.w400,
                      color: v == selected
                          ? _kWater
                          : Colors.white.withValues(alpha: 0.6),
                    ),
                  ),
                  if (noteFor?.call(v) != null) ...[
                    const SizedBox(width: 6),
                    Text(
                      noteFor!.call(v)!,
                      style: TextStyle(
                        fontSize: 10,
                        color: (v == selected ? _kWater : Colors.white)
                            .withValues(alpha: 0.45),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
      ],
    );
  }
}

class _Notice extends StatelessWidget {
  const _Notice({
    required this.icon,
    required this.text,
    required this.action,
    required this.onTap,
  });
  final IconData icon;
  final String text, action;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
      decoration: BoxDecoration(
        color: const Color(0xFFFFB347).withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(icon, size: 17, color: const Color(0xFFFFB347)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                fontSize: 12.5,
                height: 1.35,
                color: Color(0xFFFFB347),
              ),
            ),
          ),
          TextButton(
            onPressed: onTap,
            style: TextButton.styleFrom(
              foregroundColor: const Color(0xFFFFB347),
              minimumSize: const Size(0, 32),
            ),
            child: Text(action, style: const TextStyle(fontSize: 12.5)),
          ),
        ],
      ),
    );
  }
}
