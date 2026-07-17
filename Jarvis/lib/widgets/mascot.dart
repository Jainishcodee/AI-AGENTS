import 'dart:math' as math;
import 'package:flutter/material.dart';

enum MascotState { idle, listening, thinking, talking }

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
  late final AnimationController _blink;
  late final AnimationController _mouth;

  @override
  void initState() {
    super.initState();
    _idle = AnimationController(vsync: this, duration: const Duration(seconds: 3))
      ..repeat(reverse: true);
    _pulse = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat(reverse: true);
    _wobble = AnimationController(vsync: this, duration: const Duration(milliseconds: 280))
      ..repeat(reverse: true);
    _mouth = AnimationController(vsync: this, duration: const Duration(milliseconds: 220))
      ..repeat(reverse: true);
    _blink = AnimationController(vsync: this, duration: const Duration(milliseconds: 140));
    _scheduleBlink();
  }

  void _scheduleBlink() async {
    while (mounted) {
      await Future.delayed(Duration(milliseconds: 2200 + math.Random().nextInt(2500)));
      if (!mounted) return;
      await _blink.forward();
      await _blink.reverse();
    }
  }

  @override
  void dispose() {
    _idle.dispose();
    _pulse.dispose();
    _wobble.dispose();
    _blink.dispose();
    _mouth.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: Listenable.merge([_idle, _pulse, _wobble, _blink, _mouth]),
      builder: (context, _) {
        final float = math.sin(_idle.value * math.pi * 2) * 6;

        double scale = 1.0;
        double wobbleX = 0.0;
        double glow = 0.0;
        double rotation = 0.0;

        switch (widget.state) {
          case MascotState.idle:
            scale = 1.0 + math.sin(_idle.value * math.pi * 2) * 0.015;
            glow = 0.18;
            break;
          case MascotState.listening:
            scale = 1.0 + _pulse.value * 0.08;
            glow = 0.45 + _pulse.value * 0.4;
            break;
          case MascotState.thinking:
            scale = 1.0;
            wobbleX = math.sin(_pulse.value * math.pi * 2) * 3;
            rotation = math.sin(_pulse.value * math.pi * 2) * 0.04;
            glow = 0.25;
            break;
          case MascotState.talking:
            scale = 1.0 + _wobble.value * 0.04;
            wobbleX = (_wobble.value - 0.5) * 4;
            glow = 0.5;
            break;
        }

        final blink = _blink.value;
        final mouthOpen = widget.state == MascotState.talking ? _mouth.value : 0.0;

        return Transform.translate(
          offset: Offset(wobbleX, float),
          child: Transform.rotate(
            angle: rotation,
            child: Transform.scale(
              scale: scale,
              child: CustomPaint(
                size: Size(widget.size, widget.size),
                painter: _LuffyPainter(
                  glow: glow,
                  blink: blink,
                  mouthOpen: mouthOpen,
                  state: widget.state,
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

class _LuffyPainter extends CustomPainter {
  final double glow;
  final double blink;
  final double mouthOpen;
  final MascotState state;

  _LuffyPainter({
    required this.glow,
    required this.blink,
    required this.mouthOpen,
    required this.state,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2 + size.height * 0.04);
    final r = size.width * 0.32; // head radius

    // ambient glow behind
    final glowPaint = Paint()
      ..shader = RadialGradient(
        colors: [
          const Color(0xFFFFC857).withOpacity(0.55 * glow),
          const Color(0xFFFFC857).withOpacity(0.0),
        ],
      ).createShader(Rect.fromCircle(center: center, radius: r * 2.4));
    canvas.drawCircle(center, r * 2.4, glowPaint);

    _drawScarf(canvas, center, r);   // little red collar peeking under chin
    _drawHair(canvas, center, r);    // black hair (back, before head)
    _drawHead(canvas, center, r);    // skin-tone face
    _drawSideHair(canvas, center, r); // sideburn-ish bangs over head edges
    _drawScar(canvas, center, r);    // signature under-eye scar
    _drawEyes(canvas, center, r);
    _drawCheeks(canvas, center, r);
    _drawMouth(canvas, center, r);
    _drawHat(canvas, center, r);     // straw hat on top (drawn last so it overlaps hair)
  }

  void _drawScarf(Canvas canvas, Offset c, double r) {
    final paint = Paint()..color = const Color(0xFFC62828);
    final path = Path()
      ..moveTo(c.dx - r * 0.8, c.dy + r * 0.85)
      ..quadraticBezierTo(
        c.dx, c.dy + r * 1.15,
        c.dx + r * 0.8, c.dy + r * 0.85,
      )
      ..lineTo(c.dx + r * 0.9, c.dy + r * 1.1)
      ..quadraticBezierTo(
        c.dx, c.dy + r * 1.35,
        c.dx - r * 0.9, c.dy + r * 1.1,
      )
      ..close();
    canvas.drawPath(path, paint);
    // darker shadow line
    final shadow = Paint()
      ..color = const Color(0xFF8A1B1B)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    canvas.drawPath(path, shadow);
  }

  void _drawHair(Canvas canvas, Offset c, double r) {
    final hair = Paint()..color = const Color(0xFF141414);
    // chunky messy hair shape: oval slightly above head
    final hairPath = Path()
      ..addOval(Rect.fromCenter(
        center: c.translate(0, -r * 0.15),
        width: r * 2.1,
        height: r * 1.9,
      ));
    // jagged tufts on top
    hairPath.moveTo(c.dx - r * 0.85, c.dy - r * 0.75);
    hairPath.lineTo(c.dx - r * 0.6, c.dy - r * 1.15);
    hairPath.lineTo(c.dx - r * 0.35, c.dy - r * 0.8);
    hairPath.lineTo(c.dx - r * 0.1, c.dy - r * 1.2);
    hairPath.lineTo(c.dx + r * 0.2, c.dy - r * 0.85);
    hairPath.lineTo(c.dx + r * 0.5, c.dy - r * 1.15);
    hairPath.lineTo(c.dx + r * 0.8, c.dy - r * 0.8);
    hairPath.close();
    canvas.drawPath(hairPath, hair);
  }

  void _drawHead(Canvas canvas, Offset c, double r) {
    // shadow under chin
    final shadow = Paint()
      ..color = Colors.black.withOpacity(0.18)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8);
    canvas.drawCircle(c.translate(0, r * 0.18), r * 0.95, shadow);

    // face — slightly egg shape
    final face = Paint()
      ..shader = RadialGradient(
        center: const Alignment(-0.2, -0.2),
        radius: 1.1,
        colors: const [
          Color(0xFFFFE2C0),
          Color(0xFFFFCB95),
          Color(0xFFE6A66B),
        ],
        stops: const [0.0, 0.65, 1.0],
      ).createShader(Rect.fromCircle(center: c, radius: r));
    canvas.drawOval(
      Rect.fromCenter(center: c, width: r * 1.9, height: r * 2.05),
      face,
    );
  }

  void _drawSideHair(Canvas canvas, Offset c, double r) {
    final hair = Paint()..color = const Color(0xFF141414);
    // tiny bangs poking down on forehead
    final bangs = Path()
      ..moveTo(c.dx - r * 0.55, c.dy - r * 0.55)
      ..quadraticBezierTo(
        c.dx - r * 0.3, c.dy - r * 0.25,
        c.dx - r * 0.05, c.dy - r * 0.55,
      )
      ..quadraticBezierTo(
        c.dx + r * 0.2, c.dy - r * 0.25,
        c.dx + r * 0.45, c.dy - r * 0.55,
      )
      ..quadraticBezierTo(
        c.dx + r * 0.55, c.dy - r * 0.7,
        c.dx + r * 0.4, c.dy - r * 0.75,
      )
      ..lineTo(c.dx - r * 0.55, c.dy - r * 0.75)
      ..close();
    canvas.drawPath(bangs, hair);
  }

  void _drawScar(Canvas canvas, Offset c, double r) {
    // Luffy's signature scar — two short lines under his left eye
    final scar = Paint()
      ..color = const Color(0xFF8A1B1B)
      ..strokeWidth = 2.0
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    final cx = c.dx - r * 0.30;
    final cy = c.dy + r * 0.10;
    canvas.drawLine(Offset(cx - r * 0.06, cy), Offset(cx + r * 0.05, cy + r * 0.05), scar);
    canvas.drawLine(Offset(cx - r * 0.04, cy + r * 0.07), Offset(cx + r * 0.07, cy + r * 0.12), scar);
  }

  void _drawEyes(Canvas canvas, Offset c, double r) {
    final eyeY = -r * 0.15;
    final eyeOffset = r * 0.32;
    final eyeR = r * 0.13;

    void drawEye(Offset p) {
      if (blink > 0.5) {
        final line = Paint()
          ..color = const Color(0xFF141414)
          ..strokeWidth = 2.5
          ..strokeCap = StrokeCap.round;
        canvas.drawLine(p.translate(-eyeR * 0.9, 0), p.translate(eyeR * 0.9, 0), line);
        return;
      }
      // sclera
      canvas.drawCircle(p, eyeR, Paint()..color = Colors.white);
      // big black pupil — Luffy's eyes are almost all pupil
      canvas.drawCircle(p, eyeR * 0.78, Paint()..color = const Color(0xFF0B0B0B));
      // sparkle
      canvas.drawCircle(
        p.translate(-eyeR * 0.28, -eyeR * 0.32),
        eyeR * 0.22,
        Paint()..color = Colors.white,
      );
    }

    drawEye(c.translate(-eyeOffset, eyeY));
    drawEye(c.translate(eyeOffset, eyeY));
  }

  void _drawCheeks(Canvas canvas, Offset c, double r) {
    final blush = Paint()
      ..color = const Color(0xFFFF8A8A).withOpacity(0.55)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4);
    canvas.drawCircle(c.translate(-r * 0.55, r * 0.18), r * 0.13, blush);
    canvas.drawCircle(c.translate(r * 0.55, r * 0.18), r * 0.13, blush);
  }

  void _drawMouth(Canvas canvas, Offset c, double r) {
    final mouthCenter = c.translate(0, r * 0.42);
    final lipPaint = Paint()
      ..color = const Color(0xFF2A0808)
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    if (state == MascotState.thinking) {
      // tight neutral line
      canvas.drawLine(
        mouthCenter.translate(-r * 0.18, 0),
        mouthCenter.translate(r * 0.18, 0),
        lipPaint,
      );
      return;
    }

    final openAmount = state == MascotState.talking ? (0.4 + mouthOpen * 0.7) : 0.0;
    final mouthHeight = r * 0.18 * (1.0 + openAmount * 1.6);
    final mouthWidth = r * 0.55;

    final mouthRect = Rect.fromCenter(
      center: mouthCenter,
      width: mouthWidth,
      height: mouthHeight,
    );

    if (openAmount > 0.1) {
      // open mouth — dark interior + teeth on top
      final interior = Paint()..color = const Color(0xFF4A1010);
      canvas.drawArc(mouthRect, 0, math.pi, true, interior);
      // top teeth
      final teeth = Paint()..color = Colors.white;
      final teethRect = Rect.fromLTWH(
        mouthRect.left + 4,
        mouthRect.top + mouthRect.height * 0.05,
        mouthRect.width - 8,
        mouthRect.height * 0.22,
      );
      canvas.drawRect(teethRect, teeth);
      // outline
      canvas.drawArc(mouthRect, 0, math.pi, true, lipPaint);
    } else {
      // big grin arc
      final smileRect = Rect.fromCenter(
        center: mouthCenter,
        width: mouthWidth,
        height: r * 0.35,
      );
      canvas.drawArc(smileRect, 0.15, math.pi - 0.3, false, lipPaint);
      // small white teeth strip suggesting grin
      final teeth = Paint()..color = Colors.white;
      final teethRect = Rect.fromCenter(
        center: mouthCenter.translate(0, -r * 0.02),
        width: mouthWidth * 0.7,
        height: r * 0.06,
      );
      canvas.drawRect(teethRect, teeth);
    }
  }

  void _drawHat(Canvas canvas, Offset c, double r) {
    // brim — wide flat oval
    final brimY = c.dy - r * 0.75;
    final brimRect = Rect.fromCenter(
      center: Offset(c.dx, brimY),
      width: r * 3.2,
      height: r * 0.55,
    );
    final brimShadow = Paint()
      ..color = Colors.black.withOpacity(0.18)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4);
    canvas.drawOval(brimRect.translate(0, 4), brimShadow);

    final brim = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: const [
          Color(0xFFF5DEB3),
          Color(0xFFD9B97A),
        ],
      ).createShader(brimRect);
    canvas.drawOval(brimRect, brim);

    // crown — dome
    final crownRect = Rect.fromCenter(
      center: Offset(c.dx, brimY - r * 0.3),
      width: r * 1.7,
      height: r * 0.85,
    );
    final crown = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: const [
          Color(0xFFE8C879),
          Color(0xFFB58A3C),
        ],
      ).createShader(crownRect);
    final crownPath = Path()
      ..moveTo(crownRect.left, crownRect.bottom)
      ..quadraticBezierTo(
        crownRect.left, crownRect.top,
        crownRect.center.dx, crownRect.top,
      )
      ..quadraticBezierTo(
        crownRect.right, crownRect.top,
        crownRect.right, crownRect.bottom,
      )
      ..close();
    canvas.drawPath(crownPath, crown);

    // red ribbon around base of crown
    final ribbon = Paint()..color = const Color(0xFFD32F2F);
    final ribbonRect = Rect.fromCenter(
      center: Offset(c.dx, crownRect.bottom - r * 0.04),
      width: r * 1.7,
      height: r * 0.18,
    );
    canvas.drawRect(ribbonRect, ribbon);
    // ribbon highlight
    final ribbonHi = Paint()..color = const Color(0xFFFF6F6F).withOpacity(0.6);
    canvas.drawRect(
      Rect.fromLTWH(ribbonRect.left, ribbonRect.top, ribbonRect.width, ribbonRect.height * 0.35),
      ribbonHi,
    );

    // straw-weave hint lines on brim
    final straw = Paint()
      ..color = const Color(0xFFB58A3C).withOpacity(0.55)
      ..strokeWidth = 1;
    for (int i = -3; i <= 3; i++) {
      final x = c.dx + i * (r * 0.45);
      canvas.drawLine(
        Offset(x, brimY - r * 0.18),
        Offset(x + r * 0.15, brimY + r * 0.18),
        straw,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _LuffyPainter old) =>
      old.glow != glow ||
      old.blink != blink ||
      old.mouthOpen != mouthOpen ||
      old.state != state;
}
