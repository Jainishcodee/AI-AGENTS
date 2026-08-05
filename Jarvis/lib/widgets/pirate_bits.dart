import 'dart:math' as math;
import 'package:flutter/material.dart';

import '../models/reel_card.dart';

/// Straw-hat palette for the Today board.
///
/// Warm and aged rather than the app's cool red/teal, so the quest log reads as
/// its own place — but [kQuestRed] is the app's primary accent, which keeps it
/// in the same family as the rest of Jarvis.
const kStraw = Color(0xFFE5B84B); // hat straw
const kStrawDeep = Color(0xFFB8873A); // hat shadow / rules
const kQuestRed = Color(0xFFE74848); // hat ribbon, matches the app accent
const kParchment = Color(0xFFE8D5A9); // poster text
const kParchmentDim = Color(0xFFA79470);
const kLogPose = Color(0xFF4FA8C4); // long-haul voyage blue
const kDeck = Color(0xFF1E1712); // aged card
const kDeckSunk = Color(0xFF171210);

/// Quest rank, styled off the horizon. A quick job is deck duty; the long haul
/// is the Grand Line.
({String rank, String flavour, Color colour}) rankFor(Horizon h) => switch (h) {
      Horizon.today => (rank: 'DECK DUTY', flavour: 'before sundown', colour: kQuestRed),
      Horizon.shortTerm => (rank: 'ISLAND ARC', flavour: 'this stretch', colour: kStraw),
      Horizon.longTerm => (rank: 'GRAND LINE', flavour: 'the long haul', colour: kLogPose),
    };

/// A stable bounty per card, so the same quest is always worth the same.
///
/// Seeded off the id rather than random, and scaled by horizon so the long
/// hauls are visibly the ones worth chasing.
String bountyFor(ReelCard c) {
  var h = 0;
  for (final u in c.id.codeUnits) {
    h = (h * 31 + u) & 0x7fffffff;
  }
  final (lo, hi) = switch (c.horizon) {
    Horizon.today => (3, 30),
    Horizon.shortTerm => (30, 150),
    Horizon.longTerm => (150, 1500),
  };
  final millions = lo + (h % (hi - lo));
  final value = millions * 1000000;
  return '฿ ${_group(value)}';
}

String _group(int v) {
  final s = v.toString();
  final b = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    if (i > 0 && (s.length - i) % 3 == 0) b.write(',');
    b.write(s[i]);
  }
  return b.toString();
}

// --------------------------------------------------------------- the hat

/// Luffy's hat, painted rather than shipped as an asset — same approach the
/// mascot uses, so it stays crisp at any size and adds nothing to the APK.
class StrawHat extends StatelessWidget {
  const StrawHat({super.key, this.size = 58});
  final double size;

  @override
  Widget build(BuildContext context) =>
      CustomPaint(size: Size(size, size * 0.72), painter: _StrawHatPainter());
}

class _StrawHatPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    final p = Paint()..isAntiAlias = true;

    // A shader is still modulated by the paint's alpha, so every gradient fill
    // below resets the colour to opaque first — otherwise the last stroke's
    // translucency silently darkens it.
    void opaque() => p
      ..color = const Color(0xFFFFFFFF)
      ..style = PaintingStyle.fill;

    // Crown first: a dome that the brim will then sit in front of.
    final crownRect = Rect.fromLTRB(w * 0.28, h * 0.13, w * 0.72, h * 0.74);
    final crown = Path()
      ..moveTo(crownRect.left, crownRect.bottom)
      ..cubicTo(
        crownRect.left, crownRect.top,
        crownRect.right, crownRect.top,
        crownRect.right, crownRect.bottom,
      )
      ..close();
    opaque();
    p.shader = const LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFFF2D274), kStrawDeep],
    ).createShader(crownRect);
    canvas.drawPath(crown, p);
    p.shader = null;

    // Brim: a wide disc, lit from the top-left.
    final brimRect = Rect.fromCenter(
      center: Offset(w * 0.5, h * 0.78),
      width: w,
      height: h * 0.44,
    );
    opaque();
    p.shader = const LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [kStraw, kStrawDeep],
    ).createShader(brimRect);
    canvas.drawOval(brimRect, p);
    p.shader = null;

    // Straw weave: faint spokes radiating across the brim.
    p
      ..color = kStrawDeep.withValues(alpha: 0.5)
      ..style = PaintingStyle.stroke
      ..strokeWidth = math.max(0.6, w * 0.008);
    for (var i = 0; i < 20; i++) {
      final a = (i / 20) * math.pi * 2;
      canvas.drawLine(
        Offset(w * 0.5 + math.cos(a) * w * 0.17, h * 0.78 + math.sin(a) * h * 0.075),
        Offset(w * 0.5 + math.cos(a) * w * 0.49, h * 0.78 + math.sin(a) * h * 0.215),
        p,
      );
    }

    // The red band sits where the crown meets the brim, with a tail to the right.
    p
      ..style = PaintingStyle.fill
      ..color = kQuestRed;
    final band = Rect.fromCenter(
      center: Offset(w * 0.5, h * 0.585),
      width: w * 0.455,
      height: h * 0.135,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(band, Radius.circular(h * 0.035)),
      p,
    );
    final tail = Path()
      ..moveTo(w * 0.70, h * 0.545)
      ..lineTo(w * 0.83, h * 0.50)
      ..lineTo(w * 0.80, h * 0.655)
      ..close();
    canvas.drawPath(tail, p);

    // Brim edge, to lift it off a dark background.
    p
      ..color = kStrawDeep
      ..style = PaintingStyle.stroke
      ..strokeWidth = math.max(0.8, w * 0.012);
    canvas.drawOval(brimRect, p);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

// ------------------------------------------------------------ jolly roger

/// The quest tick: an empty ring until it's done, then the crew's mark.
class JollyRogerCheck extends StatelessWidget {
  const JollyRogerCheck({
    super.key,
    required this.done,
    required this.colour,
    this.size = 28,
  });
  final bool done;
  final Color colour;
  final double size;

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: done ? colour.withValues(alpha: 0.22) : Colors.transparent,
        shape: BoxShape.circle,
        border: Border.all(
          color: done ? colour : kParchmentDim.withValues(alpha: 0.55),
          width: 2,
        ),
      ),
      child: done
          ? CustomPaint(painter: _SkullPainter(colour))
          : null,
    );
  }
}

class _SkullPainter extends CustomPainter {
  _SkullPainter(this.colour);
  final Color colour;

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    final p = Paint()
      ..color = colour
      ..isAntiAlias = true;
    final hole = Paint()..blendMode = BlendMode.clear;

    // Everything happens inside one layer: the sockets are punched out of the
    // skull, so the skull must not also be drawn underneath the layer or the
    // holes get filled straight back in.
    canvas.saveLayer(Offset.zero & size, Paint());

    canvas.drawOval(
      Rect.fromCenter(
          center: Offset(w * 0.5, h * 0.42), width: w * 0.68, height: h * 0.60),
      p,
    );
    // Jaw, slightly narrower than the cranium.
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromCenter(
            center: Offset(w * 0.5, h * 0.72), width: w * 0.38, height: h * 0.24),
        Radius.circular(w * 0.06),
      ),
      p,
    );

    // Eye sockets, big enough to still read at 28 px.
    canvas.drawOval(
      Rect.fromCenter(
          center: Offset(w * 0.34, h * 0.40), width: w * 0.22, height: h * 0.24),
      hole,
    );
    canvas.drawOval(
      Rect.fromCenter(
          center: Offset(w * 0.66, h * 0.40), width: w * 0.22, height: h * 0.24),
      hole,
    );
    // Nose.
    final nose = Path()
      ..moveTo(w * 0.5, h * 0.50)
      ..lineTo(w * 0.44, h * 0.60)
      ..lineTo(w * 0.56, h * 0.60)
      ..close();
    canvas.drawPath(nose, hole);
    // A single tooth gap, which is all that survives at this size.
    canvas.drawRect(
      Rect.fromCenter(
          center: Offset(w * 0.5, h * 0.74), width: w * 0.055, height: h * 0.16),
      hole,
    );

    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _SkullPainter old) => old.colour != colour;
}

// ----------------------------------------------------------------- stamps

/// The rotated "CLEARED" mark slapped across a finished quest.
class ClearedStamp extends StatelessWidget {
  const ClearedStamp({super.key, this.label = 'CLEARED'});
  final String label;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Transform.rotate(
        angle: -0.22,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
          decoration: BoxDecoration(
            border: Border.all(color: kQuestRed.withValues(alpha: 0.75), width: 2.5),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 15,
              letterSpacing: 3.5,
              fontWeight: FontWeight.w900,
              color: kQuestRed.withValues(alpha: 0.85),
            ),
          ),
        ),
      ),
    );
  }
}

/// The poster's top rule: a hairline with a diamond notch, like a torn edge.
class PosterRule extends StatelessWidget {
  const PosterRule({super.key, this.colour = kStrawDeep});
  final Color colour;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(child: Container(height: 1, color: colour.withValues(alpha: 0.45))),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 7),
          child: Transform.rotate(
            angle: math.pi / 4,
            child: Container(width: 5, height: 5, color: colour.withValues(alpha: 0.8)),
          ),
        ),
        Expanded(child: Container(height: 1, color: colour.withValues(alpha: 0.45))),
      ],
    );
  }
}

/// Label in the poster's voice: wide-tracked, heavy, small.
class PosterLabel extends StatelessWidget {
  const PosterLabel(this.text, {super.key, this.colour = kParchmentDim, this.size = 9.5});
  final String text;
  final Color colour;
  final double size;

  @override
  Widget build(BuildContext context) => Text(
        text,
        style: TextStyle(
          fontSize: size,
          letterSpacing: 2.2,
          fontWeight: FontWeight.w800,
          color: colour,
        ),
      );
}

/// The long-haul progress readout: a voyage line with the ship where you are.
class LogPose extends StatelessWidget {
  const LogPose({
    super.key,
    required this.value,
    required this.onAdvance,
  });
  final int value;
  final VoidCallback onAdvance;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const PosterLabel('LOG POSE', colour: kLogPose),
            const Spacer(),
            Text(
              '$value%',
              style: const TextStyle(
                fontSize: 11.5,
                fontWeight: FontWeight.w800,
                color: kLogPose,
                fontFeatures: [FontFeature.tabularFigures()],
              ),
            ),
          ],
        ),
        const SizedBox(height: 7),
        Row(
          children: [
            Expanded(
              child: LayoutBuilder(
                builder: (context, c) {
                  final x = (c.maxWidth - 16) * (value.clamp(0, 100) / 100);
                  return SizedBox(
                    height: 16,
                    child: Stack(
                      clipBehavior: Clip.none,
                      children: [
                        Positioned(
                          left: 0,
                          right: 0,
                          top: 7,
                          child: Container(
                            height: 2,
                            decoration: BoxDecoration(
                              color: kLogPose.withValues(alpha: 0.18),
                              borderRadius: BorderRadius.circular(2),
                            ),
                          ),
                        ),
                        Positioned(
                          left: 0,
                          width: x + 8,
                          top: 7,
                          child: Container(
                            height: 2,
                            decoration: BoxDecoration(
                              color: kLogPose,
                              borderRadius: BorderRadius.circular(2),
                            ),
                          ),
                        ),
                        AnimatedPositioned(
                          duration: const Duration(milliseconds: 260),
                          curve: Curves.easeOut,
                          left: x,
                          top: 0,
                          child: const Icon(Icons.sailing, size: 16, color: kLogPose),
                        ),
                      ],
                    ),
                  );
                },
              ),
            ),
            const SizedBox(width: 10),
            GestureDetector(
              onTap: onAdvance,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: kLogPose.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: kLogPose.withValues(alpha: 0.45)),
                ),
                child: const Text(
                  'SAIL ON',
                  style: TextStyle(
                    fontSize: 10,
                    letterSpacing: 1.2,
                    fontWeight: FontWeight.w800,
                    color: kLogPose,
                  ),
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}
