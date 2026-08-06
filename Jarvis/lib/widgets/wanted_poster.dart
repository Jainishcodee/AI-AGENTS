import 'dart:math' as math;
import 'package:flutter/material.dart';

import '../models/reel_card.dart';
import 'pirate_bits.dart';

/// Ink and paper for the bounty board.
const kInk = Color(0xFF2A1D10);
const kInkSoft = Color(0xFF5C4630);
const kPaper = Color(0xFFE9D9AE);
const kPaperDeep = Color(0xFFC8AC77);

/// A domain gets a silhouette, because none of these reels shipped a cover
/// photo — and a blank frame would look broken where a bad drawing looks
/// like the joke the posters are already making.
IconData glyphFor(String domain) => switch (domain.toLowerCase()) {
      'health' => Icons.local_hospital,
      'fitness' => Icons.fitness_center,
      'productivity' => Icons.bolt,
      'mindset' => Icons.psychology_alt,
      'relationships' => Icons.people_alt,
      'skincare' => Icons.face_retouching_natural,
      'travel' => Icons.flight_takeoff,
      'style' => Icons.checkroom,
      'tech' => Icons.memory,
      'career' => Icons.work_outline,
      'decision-making' => Icons.alt_route,
      'spirituality' => Icons.self_improvement,
      'finance' => Icons.savings,
      'food' => Icons.restaurant,
      _ => Icons.auto_awesome,
    };

// --------------------------------------------------------------- parchment

/// Aged paper, painted rather than shipped: a warm gradient, a few coffee
/// rings, paper fibres and a burnt vignette. Seeded per card so each poster
/// weathers differently but always the same way.
class ParchmentPanel extends StatelessWidget {
  const ParchmentPanel({
    super.key,
    required this.child,
    required this.seed,
    this.radius = 6,
  });

  final Widget child;
  final int seed;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: CustomPaint(
        painter: _ParchmentPainter(seed),
        child: child,
      ),
    );
  }
}

class _ParchmentPainter extends CustomPainter {
  _ParchmentPainter(this.seed);
  final int seed;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final rnd = math.Random(seed);
    final p = Paint()..isAntiAlias = true;

    // Base sheet.
    p.shader = const LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [Color(0xFFF0E2BC), kPaper, kPaperDeep],
      stops: [0.0, 0.45, 1.0],
    ).createShader(rect);
    canvas.drawRect(rect, p);
    p.shader = null;

    // Paper fibres.
    p
      ..color = kPaperDeep.withValues(alpha: 0.16)
      ..strokeWidth = 0.7;
    for (var i = 0; i < 26; i++) {
      final y = rnd.nextDouble() * size.height;
      canvas.drawLine(
        Offset(rnd.nextDouble() * size.width * 0.3, y),
        Offset(size.width - rnd.nextDouble() * size.width * 0.3, y),
        p,
      );
    }

    // Stains: a couple of rings and a blotch.
    for (var i = 0; i < 3; i++) {
      final c = Offset(
        rnd.nextDouble() * size.width,
        rnd.nextDouble() * size.height,
      );
      final r = size.width * (0.10 + rnd.nextDouble() * 0.16);
      canvas.drawCircle(
        c,
        r,
        Paint()
          ..color = const Color(0xFF8A6A3C).withValues(alpha: 0.05)
          ..style = PaintingStyle.fill,
      );
      canvas.drawCircle(
        c,
        r,
        Paint()
          ..color = const Color(0xFF8A6A3C).withValues(alpha: 0.09)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.4,
      );
    }

    // Scorched edges.
    canvas.drawRect(
      rect,
      Paint()
        ..shader = RadialGradient(
          radius: 0.85,
          colors: [
            Colors.transparent,
            const Color(0xFF6B4A22).withValues(alpha: 0.10),
            const Color(0xFF43290F).withValues(alpha: 0.34),
          ],
          stops: const [0.55, 0.82, 1.0],
        ).createShader(rect),
    );
  }

  @override
  bool shouldRepaint(covariant _ParchmentPainter old) => old.seed != seed;
}

/// The double rule that frames a poster's inner block.
class InkRule extends StatelessWidget {
  const InkRule({super.key, this.alpha = 0.55});
  final double alpha;

  @override
  Widget build(BuildContext context) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(height: 1.6, color: kInk.withValues(alpha: alpha)),
          const SizedBox(height: 2),
          Container(height: 0.8, color: kInk.withValues(alpha: alpha * 0.7)),
        ],
      );
}

// ------------------------------------------------------------------ poster

/// A task, as a bounty poster: WANTED, a mugshot, the crime, the price.
class WantedPoster extends StatelessWidget {
  const WantedPoster({
    super.key,
    required this.card,
    required this.done,
    required this.onToggle,
    required this.onSnooze,
    required this.onProgress,
    required this.onOpenReel,
  });

  final ReelCard card;
  final bool done;
  final VoidCallback onToggle, onSnooze, onOpenReel;
  final ValueChanged<int> onProgress;

  int get _seed {
    var h = 7;
    for (final u in card.id.codeUnits) {
      h = (h * 31 + u) & 0x7fffffff;
    }
    return h;
  }

  @override
  Widget build(BuildContext context) {
    final r = rankFor(card.horizon);

    return Opacity(
      opacity: done ? 0.72 : 1,
      child: Stack(
        children: [
          Container(
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(6),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.55),
                  blurRadius: 18,
                  offset: const Offset(0, 8),
                ),
              ],
            ),
            child: ParchmentPanel(
              seed: _seed,
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 12, 14, 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const _PosterWord('WANTED', size: 34, spacing: 7),
                    const SizedBox(height: 6),
                    const InkRule(),
                    const SizedBox(height: 10),

                    // Mugshot.
                    Expanded(
                      flex: 5,
                      child: Container(
                        decoration: BoxDecoration(
                          border: Border.all(color: kInk.withValues(alpha: 0.62), width: 2),
                          color: const Color(0xFFD9C495).withValues(alpha: 0.55),
                        ),
                        child: _Mugshot(card: card),
                      ),
                    ),
                    const SizedBox(height: 9),
                    _PosterWord(r.rank, size: 12.5, spacing: 4, alpha: 0.78),
                    const SizedBox(height: 7),

                    // The crime.
                    Expanded(
                      flex: 4,
                      child: SingleChildScrollView(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              card.title,
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontSize: 15,
                                height: 1.22,
                                fontWeight: FontWeight.w900,
                                color: kInk,
                                decoration: done ? TextDecoration.lineThrough : null,
                                decorationColor: kInk.withValues(alpha: 0.6),
                              ),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              card.summary,
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                fontSize: 11.5,
                                height: 1.38,
                                color: kInkSoft,
                              ),
                            ),
                            if (card.steps.isNotEmpty) ...[
                              const SizedBox(height: 9),
                              for (final s in card.steps.take(3))
                                Padding(
                                  padding: const EdgeInsets.only(bottom: 3),
                                  child: Text(
                                    '·  $s',
                                    style: const TextStyle(
                                      fontSize: 10.5,
                                      height: 1.35,
                                      color: kInkSoft,
                                    ),
                                  ),
                                ),
                            ],
                          ],
                        ),
                      ),
                    ),

                    const SizedBox(height: 8),
                    const InkRule(alpha: 0.4),
                    const SizedBox(height: 7),
                    Text(
                      bountyFor(card),
                      textAlign: TextAlign.center,
                      style: const TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 0.5,
                        color: kInk,
                        fontFeatures: [FontFeature.tabularFigures()],
                      ),
                    ),
                    const SizedBox(height: 2),

                    if (card.tracksProgress) ...[
                      const SizedBox(height: 6),
                      _PaperProgress(
                        value: card.progress,
                        onAdvance: () => onProgress(card.progress + 10),
                      ),
                    ],

                    const SizedBox(height: 6),
                    Row(
                      children: [
                        const _PosterWord('MARINE', size: 9, spacing: 2.4, alpha: 0.55),
                        const Spacer(),
                        Text(
                          card.owner.isEmpty ? card.domain : '@${card.owner}',
                          style: TextStyle(
                            fontSize: 9,
                            color: kInkSoft.withValues(alpha: 0.75),
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ),

          if (done)
            Positioned(
              top: 58,
              left: 0,
              right: 0,
              child: Center(
                child: ClearedStamp(label: card.tracksProgress ? 'LANDED' : 'CAPTURED'),
              ),
            ),

          // Actions live on the paper's edge so they don't fight the layout.
          Positioned(
            top: 6,
            right: 6,
            child: GestureDetector(
              onTap: card.tracksProgress ? null : onToggle,
              behavior: HitTestBehavior.opaque,
              child: card.tracksProgress
                  ? const SizedBox.shrink()
                  : JollyRogerCheck(done: done, colour: kInk, size: 26),
            ),
          ),
          Positioned(
            top: 6,
            left: 6,
            child: Row(
              children: [
                _PaperTap(icon: Icons.sailing_outlined, onTap: onSnooze),
                if (card.url.isNotEmpty) ...[
                  const SizedBox(width: 2),
                  _PaperTap(icon: Icons.play_circle_outline, onTap: onOpenReel),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Heavy, wide-tracked poster type.
class _PosterWord extends StatelessWidget {
  const _PosterWord(this.text, {required this.size, required this.spacing, this.alpha = 1.0});
  final String text;
  final double size, spacing, alpha;

  @override
  Widget build(BuildContext context) => Text(
        text,
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: size,
          letterSpacing: spacing,
          fontWeight: FontWeight.w900,
          height: 1.0,
          color: kInk.withValues(alpha: alpha),
        ),
      );
}

class _PaperTap extends StatelessWidget {
  const _PaperTap({required this.icon, required this.onTap});
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: Padding(
          padding: const EdgeInsets.all(4),
          child: Icon(icon, size: 17, color: kInk.withValues(alpha: 0.6)),
        ),
      );
}

class _Mugshot extends StatelessWidget {
  const _Mugshot({required this.card});
  final ReelCard card;

  @override
  Widget build(BuildContext context) {
    if (card.thumb.isNotEmpty) {
      return Image.asset(
        card.thumb,
        fit: BoxFit.cover,
        errorBuilder: (_, _, _) => _silhouette(),
      );
    }
    return _silhouette();
  }

  Widget _silhouette() => Center(
        child: Icon(
          glyphFor(card.domain),
          size: 54,
          color: kInk.withValues(alpha: 0.34),
        ),
      );
}

/// Long-haul progress, drawn as a ruled line on the paper.
class _PaperProgress extends StatelessWidget {
  const _PaperProgress({required this.value, required this.onAdvance});
  final int value;
  final VoidCallback onAdvance;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Stack(
            children: [
              Container(height: 4, color: kInk.withValues(alpha: 0.16)),
              FractionallySizedBox(
                widthFactor: value.clamp(0, 100) / 100,
                child: Container(height: 4, color: kInk.withValues(alpha: 0.72)),
              ),
            ],
          ),
        ),
        const SizedBox(width: 8),
        GestureDetector(
          onTap: onAdvance,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              border: Border.all(color: kInk.withValues(alpha: 0.55)),
            ),
            child: Text(
              '$value%  SAIL',
              style: const TextStyle(
                fontSize: 9,
                fontWeight: FontWeight.w900,
                letterSpacing: 0.8,
                color: kInk,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

// --------------------------------------------------------------- log card

/// A fact, as a page torn from the ship's log: the claim in ink, the reasoning
/// under it, and the moment it's worth reaching for.
class LogCard extends StatelessWidget {
  const LogCard({
    super.key,
    required this.card,
    this.onRate,
    this.rated = false,
    this.onOpenReel,
    this.compact = false,
  });

  final ReelCard card;
  final ValueChanged<bool>? onRate;
  final bool rated, compact;
  final VoidCallback? onOpenReel;

  int get _seed {
    var h = 13;
    for (final u in card.id.codeUnits) {
      h = (h * 31 + u) & 0x7fffffff;
    }
    return h;
  }

  @override
  Widget build(BuildContext context) {
    final claim = card.claim.isNotEmpty ? card.claim : card.title;

    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(6),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.5),
            blurRadius: 14,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      child: ParchmentPanel(
        seed: _seed,
        child: Padding(
          padding: EdgeInsets.all(compact ? 12 : 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(glyphFor(card.domain), size: 13, color: kInk.withValues(alpha: 0.6)),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      compact ? card.domain.toUpperCase() : "SHIP'S LOG  ·  ${card.domain.toUpperCase()}",
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 9,
                        letterSpacing: 2,
                        fontWeight: FontWeight.w900,
                        color: kInk.withValues(alpha: 0.62),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 7),
              const InkRule(alpha: 0.45),
              SizedBox(height: compact ? 9 : 13),

              Expanded(
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        claim,
                        maxLines: compact ? 5 : null,
                        overflow: compact ? TextOverflow.ellipsis : null,
                        style: TextStyle(
                          fontSize: compact ? 13 : 17,
                          height: 1.3,
                          fontWeight: FontWeight.w800,
                          color: kInk,
                        ),
                      ),
                      if (!compact && card.why.isNotEmpty) ...[
                        const SizedBox(height: 10),
                        Text(
                          card.why,
                          style: const TextStyle(
                            fontSize: 12,
                            height: 1.45,
                            color: kInkSoft,
                          ),
                        ),
                      ],
                      if (!compact && card.applicability.isNotEmpty) ...[
                        const SizedBox(height: 12),
                        Container(
                          padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
                          decoration: BoxDecoration(
                            border: Border(
                              left: BorderSide(color: kInk.withValues(alpha: 0.5), width: 2),
                            ),
                            color: kInk.withValues(alpha: 0.05),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'USE WHEN',
                                style: TextStyle(
                                  fontSize: 8.5,
                                  letterSpacing: 1.8,
                                  fontWeight: FontWeight.w900,
                                  color: kInk.withValues(alpha: 0.6),
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                card.applicability,
                                style: const TextStyle(
                                  fontSize: 11.5,
                                  height: 1.4,
                                  color: kInk,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),

              if (!compact) ...[
                const SizedBox(height: 10),
                const InkRule(alpha: 0.3),
                const SizedBox(height: 6),
                Row(
                  children: [
                    if (onRate != null && !rated) ...[
                      _InkButton(label: 'WORTH KEEPING', onTap: () => onRate!(true)),
                      const SizedBox(width: 8),
                      _InkButton(label: 'NOT FOR ME', onTap: () => onRate!(false), faint: true),
                    ] else if (rated)
                      Text(
                        'Logged.',
                        style: TextStyle(
                          fontSize: 10.5,
                          fontStyle: FontStyle.italic,
                          color: kInkSoft.withValues(alpha: 0.8),
                        ),
                      ),
                    const Spacer(),
                    if (onOpenReel != null && card.url.isNotEmpty)
                      GestureDetector(
                        onTap: onOpenReel,
                        behavior: HitTestBehavior.opaque,
                        child: Icon(Icons.play_circle_outline,
                            size: 18, color: kInk.withValues(alpha: 0.6)),
                      ),
                  ],
                ),
              ] else if (card.owner.isNotEmpty)
                Text(
                  '@${card.owner}',
                  style: TextStyle(fontSize: 8.5, color: kInkSoft.withValues(alpha: 0.7)),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _InkButton extends StatelessWidget {
  const _InkButton({required this.label, required this.onTap, this.faint = false});
  final String label;
  final VoidCallback onTap;
  final bool faint;

  @override
  Widget build(BuildContext context) => GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
          decoration: BoxDecoration(
            border: Border.all(color: kInk.withValues(alpha: faint ? 0.32 : 0.62)),
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 8.5,
              letterSpacing: 1.1,
              fontWeight: FontWeight.w900,
              color: kInk.withValues(alpha: faint ? 0.5 : 0.85),
            ),
          ),
        ),
      );
}

// -------------------------------------------------------------- mini card

/// Library tile: a poster shrunk to a thumbnail, tasks and facts alike.
class MiniPoster extends StatelessWidget {
  const MiniPoster({super.key, required this.card, required this.onTap});
  final ReelCard card;
  final VoidCallback onTap;

  int get _seed {
    var h = 29;
    for (final u in card.id.codeUnits) {
      h = (h * 31 + u) & 0x7fffffff;
    }
    return h;
  }

  @override
  Widget build(BuildContext context) {
    final isTask = card.isTask;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(5),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.45),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: ParchmentPanel(
          seed: _seed,
          radius: 5,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(10, 9, 10, 9),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  isTask ? 'WANTED' : "SHIP'S LOG",
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 10,
                    letterSpacing: 2.4,
                    fontWeight: FontWeight.w900,
                    color: kInk.withValues(alpha: 0.85),
                  ),
                ),
                const SizedBox(height: 5),
                const InkRule(alpha: 0.4),
                const SizedBox(height: 7),
                Expanded(
                  child: Container(
                    decoration: BoxDecoration(
                      border: Border.all(color: kInk.withValues(alpha: 0.45)),
                      color: const Color(0xFFD9C495).withValues(alpha: 0.5),
                    ),
                    child: Center(
                      child: Icon(glyphFor(card.domain),
                          size: 26, color: kInk.withValues(alpha: 0.32)),
                    ),
                  ),
                ),
                const SizedBox(height: 7),
                Text(
                  card.kind == CardKind.fact && card.claim.isNotEmpty
                      ? card.claim
                      : card.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 10.5,
                    height: 1.25,
                    fontWeight: FontWeight.w800,
                    color: kInk,
                  ),
                ),
                const SizedBox(height: 5),
                Text(
                  isTask ? bountyFor(card) : card.domain.toUpperCase(),
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 9.5,
                    fontWeight: FontWeight.w900,
                    letterSpacing: isTask ? 0 : 1.4,
                    color: kInk.withValues(alpha: 0.75),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ------------------------------------------------------------ nudge chit

/// A small pinned card for a standing habit — water, eyes — sitting under the
/// bounty board. Deliberately half the width of a poster: these are background
/// business, not today's quests.
class NudgeChit extends StatelessWidget {
  const NudgeChit({
    super.key,
    required this.label,
    required this.detail,
    required this.icon,
    required this.accent,
    required this.on,
    required this.countToday,
    required this.onTap,
  });

  final String label, detail;
  final IconData icon;
  final Color accent;
  final bool on;
  final int countToday;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.fromLTRB(11, 10, 11, 10),
        decoration: BoxDecoration(
          color: kDeck,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: on
                ? accent.withValues(alpha: 0.45)
                : kStrawDeep.withValues(alpha: 0.28),
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 32,
              height: 32,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: accent.withValues(alpha: on ? 0.18 : 0.07),
              ),
              child: Icon(
                icon,
                size: 17,
                color: on ? accent : kParchmentDim.withValues(alpha: 0.5),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    label,
                    style: TextStyle(
                      fontSize: 12.5,
                      fontWeight: FontWeight.w700,
                      color: on ? kParchment : kParchmentDim.withValues(alpha: 0.75),
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    on ? detail : 'off',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 10,
                      color: kParchmentDim.withValues(alpha: 0.6),
                    ),
                  ),
                ],
              ),
            ),
            if (on && countToday > 0)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(
                  '$countToday',
                  style: TextStyle(
                    fontSize: 10.5,
                    fontWeight: FontWeight.w800,
                    color: accent,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

// --------------------------------------------------------------- carousel

/// Horizontal deck with a perspective tilt, so the neighbours sit back from
/// the one you're reading.
class PosterCarousel extends StatefulWidget {
  const PosterCarousel({
    super.key,
    required this.count,
    required this.builder,
    this.height = 470,
    this.viewportFraction = 0.74,
  });

  final int count;
  final Widget Function(BuildContext, int) builder;
  final double height, viewportFraction;

  @override
  State<PosterCarousel> createState() => _PosterCarouselState();
}

class _PosterCarouselState extends State<PosterCarousel> {
  late final PageController _pc =
      PageController(viewportFraction: widget.viewportFraction);
  double _page = 0;

  @override
  void initState() {
    super.initState();
    _pc.addListener(() {
      if (_pc.hasClients && _pc.page != null) {
        setState(() => _page = _pc.page!);
      }
    });
  }

  @override
  void dispose() {
    _pc.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        SizedBox(
          height: widget.height,
          child: PageView.builder(
            controller: _pc,
            itemCount: widget.count,
            clipBehavior: Clip.none,
            itemBuilder: (context, i) {
              final delta = (i - _page).clamp(-1.5, 1.5);
              final tilt = delta * 0.42; // radians of yaw
              final scale = 1 - delta.abs() * 0.16;

              return Center(
                child: Transform(
                  alignment: Alignment.center,
                  transform: Matrix4.identity()
                    ..setEntry(3, 2, 0.0013) // perspective
                    ..rotateY(tilt)
                    ..scaleByDouble(scale, scale, 1, 1),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 6),
                    child: widget.builder(context, i),
                  ),
                ),
              );
            },
          ),
        ),
        const SizedBox(height: 12),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            for (var i = 0; i < widget.count; i++)
              AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                margin: const EdgeInsets.symmetric(horizontal: 3),
                width: (_page.round() == i) ? 16 : 6,
                height: 6,
                decoration: BoxDecoration(
                  color: (_page.round() == i)
                      ? kStraw
                      : kParchmentDim.withValues(alpha: 0.35),
                  borderRadius: BorderRadius.circular(3),
                ),
              ),
          ],
        ),
      ],
    );
  }
}
