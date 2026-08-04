import 'package:flutter/material.dart';

import '../models/reel_card.dart';

/// Shared palette, lifted from the app theme in main.dart so the reel screens
/// and the mascot screen stay the same app.
const kTask = Color(0xFFE74848);
const kFact = Color(0xFF00E5C9);
const kAmber = Color(0xFFFFB347);
const kSurface = Color(0xFF18101A);
const kSunk = Color(0xFF120B14);

/// Horizon drives the stripe colour on tasks; facts get the teal.
Color accentFor(ReelCard c) {
  if (!c.isTask) return kFact;
  return switch (c.horizon) {
    Horizon.today => kTask,
    Horizon.shortTerm => kAmber,
    Horizon.longTerm => kFact,
  };
}

/// The reel's cover image. Renders nothing when there isn't one, so layouts
/// stay correct whether or not `media.py` has been able to fetch thumbnails.
class CardThumb extends StatelessWidget {
  const CardThumb({
    super.key,
    required this.card,
    this.size = 52,
    this.radius = 10,
  });
  final ReelCard card;
  final double size, radius;

  @override
  Widget build(BuildContext context) {
    if (card.thumb.isEmpty) return const SizedBox.shrink();
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: Image.asset(
        card.thumb,
        width: size,
        height: size,
        fit: BoxFit.cover,
        // A card can outlive its image if a deck ships before the thumbnails do.
        errorBuilder: (_, _, _) => const SizedBox.shrink(),
      ),
    );
  }
}

/// Wide cover for the fact of the day, where there's room for one.
class CardBanner extends StatelessWidget {
  const CardBanner({super.key, required this.card});
  final ReelCard card;

  @override
  Widget build(BuildContext context) {
    if (card.thumb.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: AspectRatio(
          aspectRatio: 16 / 9,
          child: Image.asset(
            card.thumb,
            fit: BoxFit.cover,
            errorBuilder: (_, _, _) => const SizedBox.shrink(),
          ),
        ),
      ),
    );
  }
}

class Pill extends StatelessWidget {
  const Pill({super.key, required this.text, required this.color});
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withOpacity(0.14),
        borderRadius: BorderRadius.circular(5),
      ),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 9.5,
          letterSpacing: 1.1,
          fontWeight: FontWeight.w700,
          color: color,
        ),
      ),
    );
  }
}

class CardAction extends StatelessWidget {
  const CardAction({
    super.key,
    required this.icon,
    required this.label,
    required this.onTap,
    this.color,
  });
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return TextButton.icon(
      onPressed: onTap,
      icon: Icon(icon, size: 16),
      label: Text(label, style: const TextStyle(fontSize: 12)),
      style: TextButton.styleFrom(
        foregroundColor: color ?? Colors.white.withOpacity(0.45),
        padding: const EdgeInsets.symmetric(horizontal: 8),
        minimumSize: const Size(0, 34),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.body,
  });
  final IconData icon;
  final String title, body;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(36),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 46, color: Colors.white.withOpacity(0.22)),
            const SizedBox(height: 14),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w600,
                color: Colors.white70,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              body,
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 13, color: Colors.white.withOpacity(0.4)),
            ),
          ],
        ),
      ),
    );
  }
}

/// Section eyebrow + headline used at the top of each reel screen.
class ScreenHeader extends StatelessWidget {
  const ScreenHeader({
    super.key,
    required this.eyebrow,
    required this.title,
    this.subtitle,
  });
  final String eyebrow, title;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          eyebrow,
          style: TextStyle(
            fontSize: 11,
            letterSpacing: 3,
            fontWeight: FontWeight.w700,
            color: Colors.white.withOpacity(0.45),
          ),
        ),
        const SizedBox(height: 6),
        Text(
          title,
          style: const TextStyle(
            fontSize: 26,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.5,
            color: Colors.white,
            height: 1.15,
          ),
        ),
        if (subtitle != null) ...[
          const SizedBox(height: 4),
          Text(
            subtitle!,
            style: TextStyle(fontSize: 13, color: Colors.white.withOpacity(0.5)),
          ),
        ],
      ],
    );
  }
}
