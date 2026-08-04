import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/reel_card.dart';
import '../services/deck_db.dart';
import '../widgets/card_bits.dart';

/// One fact a day from the reels you saved, plus the whole shelf underneath.
///
/// Rating a card useful pushes it further out rather than removing it, so the
/// rules you care about keep coming back on a widening interval.
class FactsScreen extends StatefulWidget {
  const FactsScreen({super.key, required this.deck});
  final DeckDb deck;

  @override
  State<FactsScreen> createState() => _FactsScreenState();
}

class _FactsScreenState extends State<FactsScreen> {
  ReelCard? _today;
  List<ReelCard> _all = [];
  List<(String, int)> _domains = [];
  String? _domain;
  bool _loading = true;
  bool _rated = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final today = await widget.deck.dailyFact();
    final all = await widget.deck.factsByDomain(_domain);
    final domains = await widget.deck.domains(kind: CardKind.fact);
    if (!mounted) return;
    setState(() {
      _today = today;
      _all = all;
      _domains = domains;
      _loading = false;
    });
  }

  Future<void> _rate(ReelCard c, bool useful) async {
    await widget.deck.rateFact(c.id, useful: useful);
    if (!mounted) return;
    setState(() => _rated = true);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        behavior: SnackBarBehavior.floating,
        content: Text(useful
            ? 'Kept — this one comes back later.'
            : 'Retired — you won\'t see this again.'),
        action: useful
            ? null
            : SnackBarAction(
                label: 'Undo',
                onPressed: () async {
                  await widget.deck.rateFact(c.id, useful: true);
                  if (mounted) setState(() => _rated = false);
                },
              ),
      ),
    );
  }

  Future<void> _pickDomain(String? d) async {
    setState(() => _domain = d);
    final all = await widget.deck.factsByDomain(d);
    if (mounted) setState(() => _all = all);
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator(color: kFact));
    }
    if (_today == null && _all.isEmpty) {
      return const EmptyState(
        icon: Icons.lightbulb_outline,
        title: 'No facts yet',
        body: 'Facts show up here once a deck with them is imported.',
      );
    }

    return RefreshIndicator(
      color: kFact,
      backgroundColor: kSurface,
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
        children: [
          const ScreenHeader(
            eyebrow: 'FACT OF THE DAY',
            title: 'Something you saved,\nworth remembering.',
          ),
          const SizedBox(height: 18),
          if (_today != null)
            _HeroFact(
              card: _today!,
              rated: _rated,
              onRate: (useful) => _rate(_today!, useful),
            ),
          const SizedBox(height: 28),
          Row(
            children: [
              Text(
                'ALL FACTS',
                style: TextStyle(
                  fontSize: 11,
                  letterSpacing: 2.5,
                  fontWeight: FontWeight.w700,
                  color: Colors.white.withOpacity(0.45),
                ),
              ),
              const SizedBox(width: 8),
              Text(
                '${_all.length}',
                style: TextStyle(
                  fontSize: 11,
                  color: Colors.white.withOpacity(0.3),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          _DomainRow(
            domains: _domains,
            selected: _domain,
            onPick: _pickDomain,
          ),
          const SizedBox(height: 14),
          for (final f in _all) ...[
            _FactRow(card: f),
            const SizedBox(height: 10),
          ],
        ],
      ),
    );
  }
}

/// The day's card, given room to breathe: claim first, reasoning under it.
class _HeroFact extends StatelessWidget {
  const _HeroFact({
    required this.card,
    required this.rated,
    required this.onRate,
  });
  final ReelCard card;
  final bool rated;
  final ValueChanged<bool> onRate;

  @override
  Widget build(BuildContext context) {
    final claim = card.claim.isNotEmpty ? card.claim : card.title;
    return Container(
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF15252A), kSurface],
        ),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: kFact.withOpacity(0.28)),
      ),
      padding: const EdgeInsets.fromLTRB(18, 18, 16, 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Pill(text: card.domain.toUpperCase(), color: kFact),
              const Spacer(),
              if (card.owner.isNotEmpty)
                Text(
                  '@${card.owner}',
                  style: TextStyle(
                    fontSize: 11,
                    color: Colors.white.withOpacity(0.3),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 14),
          CardBanner(card: card),
          Text(
            claim,
            style: const TextStyle(
              fontSize: 19,
              height: 1.35,
              fontWeight: FontWeight.w600,
              color: Colors.white,
            ),
          ),
          if (card.why.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(
              card.why,
              style: TextStyle(
                fontSize: 13.5,
                height: 1.45,
                color: Colors.white.withOpacity(0.6),
              ),
            ),
          ],
          if (card.applicability.isNotEmpty) ...[
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
              decoration: BoxDecoration(
                color: kFact.withOpacity(0.09),
                borderRadius: BorderRadius.circular(10),
                border: Border(left: BorderSide(color: kFact.withOpacity(0.5), width: 2)),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.bolt, size: 15, color: kFact.withOpacity(0.85)),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      card.applicability,
                      style: TextStyle(
                        fontSize: 12.5,
                        height: 1.4,
                        color: kFact.withOpacity(0.85),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 8),
          Row(
            children: [
              if (rated)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                  child: Text(
                    'Noted.',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.white.withOpacity(0.35),
                    ),
                  ),
                )
              else ...[
                CardAction(
                  icon: Icons.bookmark_added_outlined,
                  label: 'Useful',
                  color: kFact,
                  onTap: () => onRate(true),
                ),
                CardAction(
                  icon: Icons.visibility_off_outlined,
                  label: 'Not for me',
                  onTap: () => onRate(false),
                ),
              ],
              const Spacer(),
              if (card.url.isNotEmpty)
                CardAction(
                  icon: Icons.play_circle_outline,
                  label: 'Reel',
                  onTap: () => launchUrl(Uri.parse(card.url),
                      mode: LaunchMode.externalApplication),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _DomainRow extends StatelessWidget {
  const _DomainRow({
    required this.domains,
    required this.selected,
    required this.onPick,
  });
  final List<(String, int)> domains;
  final String? selected;
  final ValueChanged<String?> onPick;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 34,
      child: ListView(
        scrollDirection: Axis.horizontal,
        children: [
          _chip('All', selected == null, () => onPick(null)),
          for (final (d, n) in domains)
            _chip('$d  $n', selected == d, () => onPick(d)),
        ],
      ),
    );
  }

  Widget _chip(String label, bool on, VoidCallback tap) => Padding(
        padding: const EdgeInsets.only(right: 8),
        child: GestureDetector(
          onTap: tap,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 7),
            decoration: BoxDecoration(
              color: on ? kFact.withOpacity(0.18) : kSurface,
              borderRadius: BorderRadius.circular(999),
              border: Border.all(
                color: on ? kFact.withOpacity(0.6) : Colors.white.withOpacity(0.09),
              ),
            ),
            child: Text(
              label,
              style: TextStyle(
                fontSize: 12,
                fontWeight: on ? FontWeight.w600 : FontWeight.w400,
                color: on ? kFact : Colors.white.withOpacity(0.55),
              ),
            ),
          ),
        ),
      );
}

/// Collapsed row in the shelf; tapping opens the full card.
class _FactRow extends StatelessWidget {
  const _FactRow({required this.card});
  final ReelCard card;

  @override
  Widget build(BuildContext context) {
    final claim = card.claim.isNotEmpty ? card.claim : card.title;
    return GestureDetector(
      onTap: () => showFactSheet(context, card),
      child: Container(
        decoration: BoxDecoration(
          color: kSurface,
          borderRadius: BorderRadius.circular(14),
          border: Border(
            left: const BorderSide(color: kFact, width: 3),
            top: BorderSide(color: Colors.white.withOpacity(0.07)),
            right: BorderSide(color: Colors.white.withOpacity(0.07)),
            bottom: BorderSide(color: Colors.white.withOpacity(0.07)),
          ),
        ),
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              claim,
              maxLines: 3,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 14,
                height: 1.35,
                fontWeight: FontWeight.w500,
                color: Colors.white,
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Pill(
                  text: card.domain.toUpperCase(),
                  color: Colors.white.withOpacity(0.35),
                ),
                const Spacer(),
                if (card.owner.isNotEmpty)
                  Text(
                    '@${card.owner}',
                    style: TextStyle(
                      fontSize: 10.5,
                      color: Colors.white.withOpacity(0.26),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Full fact, opened from a list row. Shared with the Library screen.
Future<void> showFactSheet(BuildContext context, ReelCard card) {
  return showModalBottomSheet(
    context: context,
    backgroundColor: kSurface,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (_) => DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.6,
      maxChildSize: 0.92,
      builder: (_, controller) => ListView(
        controller: controller,
        padding: const EdgeInsets.fromLTRB(20, 14, 20, 28),
        children: [
          Center(
            child: Container(
              width: 38,
              height: 4,
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.18),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 18),
          Row(
            children: [
              Pill(
                text: card.isTask ? 'TASK' : 'FACT',
                color: accentFor(card),
              ),
              const SizedBox(width: 8),
              Pill(
                text: card.domain.toUpperCase(),
                color: Colors.white.withOpacity(0.35),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Text(
            card.claim.isNotEmpty ? card.claim : card.title,
            style: const TextStyle(
              fontSize: 19,
              height: 1.35,
              fontWeight: FontWeight.w600,
              color: Colors.white,
            ),
          ),
          if (card.summary.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(
              card.summary,
              style: TextStyle(
                fontSize: 14,
                height: 1.45,
                color: Colors.white.withOpacity(0.65),
              ),
            ),
          ],
          if (card.why.isNotEmpty) ...[
            const SizedBox(height: 16),
            _sheetLabel('WHY'),
            Text(
              card.why,
              style: TextStyle(
                fontSize: 13.5,
                height: 1.45,
                color: Colors.white.withOpacity(0.6),
              ),
            ),
          ],
          if (card.applicability.isNotEmpty) ...[
            const SizedBox(height: 16),
            _sheetLabel('USE WHEN'),
            Text(
              card.applicability,
              style: TextStyle(
                fontSize: 13.5,
                height: 1.45,
                color: kFact.withOpacity(0.85),
              ),
            ),
          ],
          if (card.steps.isNotEmpty) ...[
            const SizedBox(height: 16),
            _sheetLabel('STEPS'),
            for (final s in card.steps)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Text(
                  '·  $s',
                  style: TextStyle(
                    fontSize: 13.5,
                    height: 1.4,
                    color: Colors.white.withOpacity(0.6),
                  ),
                ),
              ),
          ],
          if (card.evidence.isNotEmpty) ...[
            const SizedBox(height: 16),
            _sheetLabel('FROM THE REEL'),
            Text(
              '"${card.evidence}"',
              style: TextStyle(
                fontSize: 12.5,
                height: 1.45,
                fontStyle: FontStyle.italic,
                color: Colors.white.withOpacity(0.4),
              ),
            ),
          ],
          const SizedBox(height: 20),
          if (card.url.isNotEmpty)
            Align(
              alignment: Alignment.centerLeft,
              child: CardAction(
                icon: Icons.play_circle_outline,
                label: 'Open the reel',
                color: accentFor(card),
                onTap: () => launchUrl(Uri.parse(card.url),
                    mode: LaunchMode.externalApplication),
              ),
            ),
        ],
      ),
    ),
  );
}

Widget _sheetLabel(String s) => Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Text(
        s,
        style: const TextStyle(
          fontSize: 10,
          letterSpacing: 1.6,
          fontWeight: FontWeight.w700,
          color: Color(0xFF7E6A74),
        ),
      ),
    );
