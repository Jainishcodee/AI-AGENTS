import 'dart:math' as math;
import 'package:flutter/material.dart';

enum MascotState { idle, listening, thinking, talking }

/// Gehrman Sparrow, standing in for Jarvis on the home screen.
///
/// The figure is a cut-out asset rather than painted geometry, so the state
/// (idle / listening / thinking / talking) has to be carried entirely by motion
/// and the aura behind him: a slow float at rest, a breathing pulse while he's
/// listening, a slight sway while he thinks, a bob while he talks. Each state
/// also owns a colour, matching the chip under him on the home screen.
class Mascot extends StatefulWidget {
  final MascotState state;
  final double size;

  const Mascot({
    super.key,
    required this.state,
    this.size = 220,
  });

  @override
  State<Mascot> createState() => _MascotState();
}

class _MascotState extends State<Mascot> with TickerProviderStateMixin {
  late final AnimationController _idle;
  late final AnimationController _pulse;
  late final AnimationController _wobble;

  @override
  void initState() {
    super.initState();
    _idle = AnimationController(vsync: this, duration: const Duration(seconds: 3))
      ..repeat(reverse: true);
    _pulse = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat(reverse: true);
    _wobble = AnimationController(vsync: this, duration: const Duration(milliseconds: 280))
      ..repeat(reverse: true);
  }

  @override
  void dispose() {
    _idle.dispose();
    _pulse.dispose();
    _wobble.dispose();
    super.dispose();
  }

  /// The aura colour per state, kept in step with the state chip on the home
  /// screen so the two never disagree about what Jarvis is doing.
  Color get _aura => switch (widget.state) {
        MascotState.idle => const Color(0xFFE74848),
        MascotState.listening => const Color(0xFF00E5C9),
        MascotState.thinking => const Color(0xFFFFB347),
        MascotState.talking => const Color(0xFFE74848),
      };

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([_idle, _pulse, _wobble]),
      builder: (context, _) {
        final float = math.sin(_idle.value * math.pi * 2) * 6;

        double scale = 1.0;
        double wobbleX = 0.0;
        double glow = 0.0;
        double rotation = 0.0;

        switch (widget.state) {
          case MascotState.idle:
            scale = 1.0 + math.sin(_idle.value * math.pi * 2) * 0.015;
            glow = 0.20;
            break;
          case MascotState.listening:
            scale = 1.0 + _pulse.value * 0.055;
            glow = 0.45 + _pulse.value * 0.40;
            break;
          case MascotState.thinking:
            wobbleX = math.sin(_pulse.value * math.pi * 2) * 3;
            rotation = math.sin(_pulse.value * math.pi * 2) * 0.035;
            glow = 0.30;
            break;
          case MascotState.talking:
            scale = 1.0 + _wobble.value * 0.035;
            wobbleX = (_wobble.value - 0.5) * 4;
            glow = 0.50;
            break;
        }

        return SizedBox(
          width: widget.size,
          height: widget.size * 1.16,
          child: Stack(
            alignment: Alignment.center,
            children: [
              // Aura behind him, so the state reads even at a glance.
              Positioned.fill(
                child: IgnorePointer(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: RadialGradient(
                        radius: 0.62,
                        colors: [
                          _aura.withValues(alpha: 0.42 * glow),
                          _aura.withValues(alpha: 0.10 * glow),
                          Colors.transparent,
                        ],
                        stops: const [0.0, 0.55, 1.0],
                      ),
                    ),
                  ),
                ),
              ),
              // A ring that only shows up while he's actually listening.
              if (widget.state == MascotState.listening)
                Positioned.fill(
                  child: IgnorePointer(
                    child: Center(
                      child: Container(
                        width: widget.size * (0.86 + _pulse.value * 0.16),
                        height: widget.size * (0.86 + _pulse.value * 0.16),
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: _aura.withValues(alpha: 0.30 * (1 - _pulse.value)),
                            width: 1.5,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              Transform.translate(
                offset: Offset(wobbleX, float),
                child: Transform.rotate(
                  angle: rotation,
                  child: Transform.scale(
                    scale: scale,
                    child: Image.asset(
                      'assets/mascot/gehrman.png',
                      width: widget.size,
                      fit: BoxFit.contain,
                      filterQuality: FilterQuality.medium,
                      // If the asset ever goes missing the home screen should
                      // still work, just without him.
                      errorBuilder: (_, _, _) => SizedBox(
                        width: widget.size,
                        height: widget.size,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
