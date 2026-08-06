import 'package:flutter/material.dart';

import '../services/nudge_service.dart';
import '../widgets/pirate_bits.dart';

/// Settings for one nudge.
///
/// Water: the National Academies put adequate intake at 3.7 L/day of total
/// water for men and 2.7 L for women, about a fifth of which comes from food —
/// so the drinking target lands near 3.0 L and 2.2 L, comfortably under the
/// ~1 L/hour the kidneys can clear.
///
/// Eyes: the 20-20-20 rule is endorsed by the American Optometric Association,
/// but the evidence for the exact numbers is thin — a 2023 trial found 20-second
/// breaks every 20 minutes ineffective, and suggested longer ones. Hence the
/// break length being settable up to two minutes.
Future<void> showNudgeSheet(
  BuildContext context,
  NudgeService service,
  NudgeKind kind,
) {
  return showModalBottomSheet(
    context: context,
    backgroundColor: kDeck,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => _NudgeSheet(service: service, kind: kind),
  );
}

Color accentForKind(NudgeKind k) => switch (k) {
      NudgeKind.water => const Color(0xFF4FC3F7),
      NudgeKind.eyes => const Color(0xFFFFB347),
    };

IconData iconForKind(NudgeKind k, {required bool on}) => switch (k) {
      NudgeKind.water => on ? Icons.water_drop : Icons.water_drop_outlined,
      NudgeKind.eyes => on ? Icons.visibility : Icons.visibility_outlined,
    };

class _NudgeSheet extends StatefulWidget {
  const _NudgeSheet({required this.service, required this.kind});
  final NudgeService service;
  final NudgeKind kind;

  @override
  State<_NudgeSheet> createState() => _NudgeSheetState();
}

class _NudgeSheetState extends State<_NudgeSheet> {
  late NudgeSettings _s = NudgeSettings.defaultsFor(widget.kind);
  bool _loading = true;
  bool _canOverlay = false;
  bool _canExact = true;

  Color get _accent => accentForKind(widget.kind);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final s = await widget.service.getSettings(widget.kind);
    final overlay = await widget.service.canDrawOverlays();
    final exact = await widget.service.canScheduleExactAlarms();
    if (!mounted) return;
    setState(() {
      _s = s ?? NudgeSettings.defaultsFor(widget.kind);
      _canOverlay = overlay;
      _canExact = exact;
      _loading = false;
    });
  }

  Future<void> _push(NudgeSettings next) async {
    setState(() => _s = next);
    final saved = await widget.service.save(next);
    if (!mounted || saved == null) return;
    setState(() => _s = saved);
  }

  Future<void> _toggle(bool on) async {
    if (on && !_canOverlay) {
      await widget.service.requestOverlayPermission();
      if (!mounted) return;
      final ok = await widget.service.canDrawOverlays();
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
      return SizedBox(
        height: 260,
        child: Center(child: CircularProgressIndicator(color: _accent)),
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
                color: kParchmentDim.withValues(alpha: 0.35),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              Icon(iconForKind(widget.kind, on: true), color: _accent, size: 20),
              const SizedBox(width: 9),
              Expanded(
                child: Text(
                  '${widget.kind.label} nudge',
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                    color: kParchment,
                  ),
                ),
              ),
              Switch(
                value: _s.enabled,
                activeThumbColor: _accent,
                onChanged: _toggle,
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            widget.kind.blurb,
            style: TextStyle(
              fontSize: 13,
              height: 1.4,
              color: kParchmentDim.withValues(alpha: 0.8),
            ),
          ),
          const SizedBox(height: 18),

          if (!_canOverlay)
            _Notice(
              icon: Icons.layers_outlined,
              text: 'Needs "display over other apps" permission.',
              action: 'Grant',
              onTap: () async {
                await widget.service.requestOverlayPermission();
                final ok = await widget.service.canDrawOverlays();
                if (mounted) setState(() => _canOverlay = ok);
              },
            ),
          if (!_canExact)
            _Notice(
              icon: Icons.alarm,
              text: 'Without exact alarms the timing drifts by a few minutes.',
              action: 'Fix',
              onTap: () async {
                await widget.service.requestExactAlarmPermission();
                final ok = await widget.service.canScheduleExactAlarms();
                if (mounted) setState(() => _canExact = ok);
              },
            ),

          _label('EVERY'),
          _Chips<int>(
            values: widget.kind.intervalChoices,
            selected: _s.intervalMin,
            accent: _accent,
            labelFor: (v) => '$v min',
            noteFor: (v) => v == widget.kind.suggestedInterval ? 'suggested' : null,
            onPick: (v) => _push(_s.copyWith(intervalMin: v)),
          ),
          const SizedBox(height: 18),

          _label(widget.kind.amountTitle),
          _Chips<int>(
            values: widget.kind.amountChoices,
            selected: _s.amount,
            accent: _accent,
            labelFor: widget.kind.amountLabel,
            noteFor: widget.kind.amountNote,
            onPick: (v) => _push(_s.copyWith(amount: v)),
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
                border: Border.all(color: kStrawDeep.withValues(alpha: 0.3)),
              ),
              child: Row(
                children: [
                  Text(
                    _s.windowLabel,
                    style: const TextStyle(
                      fontSize: 15,
                      color: kParchment,
                      fontFeatures: [FontFeature.tabularFigures()],
                    ),
                  ),
                  const Spacer(),
                  Icon(Icons.edit_outlined,
                      size: 17, color: kParchmentDim.withValues(alpha: 0.5)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 20),

          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: _accent.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(12),
              border: Border(
                left: BorderSide(color: _accent.withValues(alpha: 0.5), width: 2),
              ),
            ),
            child: Text(
              _summary(),
              style: TextStyle(fontSize: 13, height: 1.45, color: _accent),
            ),
          ),
          const SizedBox(height: 14),

          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () async {
                final messenger = ScaffoldMessenger.of(context);
                final navigator = Navigator.of(context);
                final ok = await widget.service.preview(widget.kind);
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
              icon: const Icon(Icons.play_circle_outline, size: 17),
              label: const Text('Show it now', style: TextStyle(fontSize: 12.5)),
              style: TextButton.styleFrom(foregroundColor: _accent),
            ),
          ),
        ],
      ),
    );
  }

  String _summary() {
    final done = _s.enabled ? '\n${_s.countToday} done today.' : '';
    return switch (widget.kind) {
      NudgeKind.water =>
        'About ${_s.perNudge} ml a time, ${_s.nudgesPerDay} times across '
            '${_s.windowLabel}.$done',
      NudgeKind.eyes =>
        'A ${_s.perNudge}-second look away every ${_s.intervalMin} minutes '
            'across ${_s.windowLabel} — up to ${_s.nudgesPerDay} a day.$done',
    };
  }

  Widget _label(String s) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(
          s,
          style: TextStyle(
            fontSize: 10,
            letterSpacing: 1.8,
            fontWeight: FontWeight.w700,
            color: kParchmentDim.withValues(alpha: 0.55),
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
    required this.accent,
    this.noteFor,
  });

  final List<T> values;
  final T selected;
  final Color accent;
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
                    ? accent.withValues(alpha: 0.18)
                    : Colors.white.withValues(alpha: 0.05),
                borderRadius: BorderRadius.circular(999),
                border: Border.all(
                  color: v == selected
                      ? accent.withValues(alpha: 0.6)
                      : kStrawDeep.withValues(alpha: 0.3),
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
                          ? accent
                          : kParchmentDim.withValues(alpha: 0.75),
                    ),
                  ),
                  if (noteFor?.call(v) != null) ...[
                    const SizedBox(width: 6),
                    Text(
                      noteFor!.call(v)!,
                      style: TextStyle(
                        fontSize: 10,
                        color: (v == selected ? accent : kParchmentDim)
                            .withValues(alpha: 0.55),
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
