import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/reel_card.dart';
import '../services/deck_db.dart';
import '../widgets/pirate_bits.dart';
import '../widgets/wanted_poster.dart';

/// One page of the ship's log a day, plus every page you've filled.
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
      // A refresh can hand back a different card, so the rating UI resets with it.
      _rated = false;
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
            : 'Struck from the log — you won\'t see it again.'),
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
      return const Center(child: CircularProgressIndicator(color: kStraw));
    }
    if (_today == null && _all.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(36),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const StrawHat(size: 80),
              const SizedBox(height: 18),
              const Text(
                'The log is empty',
                style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: kParchment,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                'Facts show up here once a deck with them is imported.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 13,
                  height: 1.45,
                  color: kParchmentDim.withValues(alpha: 0.65),
                ),
              ),
            ],
          ),
        ),
      );
    }

    return RefreshIndicator(
      color: kStraw,
      backgroundColor: kDeck,
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(0, 10, 0, 30),
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const PosterLabel("TODAY'S ENTRY", colour: kStraw, size: 10),
                      const SizedBox(height: 5),
                      const Text(
                        'Something you saved,\nworth remembering.',
                        style: TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.w800,
                          letterSpacing: -0.3,
                          height: 1.18,
                          color: kParchment,
                        ),
                      ),
                    ],
                  ),
                ),
                Text(
                  '${_all.length}',
                  style: TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.w900,
                    color: kStraw.withValues(alpha: 0.35),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: PosterRule(),
          ),
          const SizedBox(height: 16),

          if (_today != null)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: SizedBox(
                height: 330,
                child: LogCard(
                  card: _today!,
                  rated: _rated,
                  onRate: (useful) => _rate(_today!, useful),
                  onOpenReel: () => launchUrl(Uri.parse(_today!.url),
                      mode: LaunchMode.externalApplication),
                ),
              ),
            ),

          const SizedBox(height: 26),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(
              children: [
                const PosterLabel('THE WHOLE LOG'),
                const SizedBox(width: 8),
                Text(
                  '${_all.length}',
                  style: TextStyle(
                    fontSize: 10,
                    color: kParchmentDim.withValues(alpha: 0.5),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 11),
          _DomainRow(domains: _domains, selected: _domain, onPick: _pickDomain),
          const SizedBox(height: 14),

          // Sideways deck: browsing the log should feel like flipping pages.
          SizedBox(
            height: 210,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              itemCount: _all.length,
              separatorBuilder: (_, _) => const SizedBox(width: 12),
              itemBuilder: (context, i) => SizedBox(
                width: 168,
                child: GestureDetector(
                  onTap: () => showFactSheet(context, _all[i]),
                  child: LogCard(card: _all[i], compact: true),
                ),
              ),
            ),
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
      height: 32,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
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
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: on ? kStraw.withValues(alpha: 0.20) : Colors.transparent,
              borderRadius: BorderRadius.circular(999),
              border: Border.all(
                color: on
                    ? kStraw.withValues(alpha: 0.7)
                    : kStrawDeep.withValues(alpha: 0.35),
              ),
            ),
            child: Text(
              label,
              style: TextStyle(
                fontSize: 11.5,
                fontWeight: on ? FontWeight.w700 : FontWeight.w400,
                color: on ? kStraw : kParchmentDim.withValues(alpha: 0.75),
              ),
            ),
          ),
        ),
      );
}

/// Full card, opened from a list row. Shared with the Library screen.
Future<void> showFactSheet(BuildContext context, ReelCard card) {
  return showModalBottomSheet(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    builder: (_) => DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.68,
      maxChildSize: 0.94,
      builder: (_, controller) => Container(
        decoration: const BoxDecoration(
          color: kDeck,
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
        child: ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(18, 12, 18, 26),
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
            const SizedBox(height: 16),
            SizedBox(
              height: 380,
              child: LogCard(
                card: card,
                onOpenReel: card.url.isEmpty
                    ? null
                    : () => launchUrl(Uri.parse(card.url),
                        mode: LaunchMode.externalApplication),
              ),
            ),
            if (card.steps.isNotEmpty) ...[
              const SizedBox(height: 18),
              const PosterLabel('ORDERS'),
              const SizedBox(height: 8),
              for (final s in card.steps)
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Text(
                    '·  $s',
                    style: TextStyle(
                      fontSize: 13,
                      height: 1.4,
                      color: kParchmentDim.withValues(alpha: 0.8),
                    ),
                  ),
                ),
            ],
            if (card.evidence.isNotEmpty) ...[
              const SizedBox(height: 18),
              const PosterLabel('FROM THE REEL'),
              const SizedBox(height: 8),
              Text(
                '"${card.evidence}"',
                style: TextStyle(
                  fontSize: 12.5,
                  height: 1.45,
                  fontStyle: FontStyle.italic,
                  color: kParchmentDim.withValues(alpha: 0.55),
                ),
              ),
            ],
          ],
        ),
      ),
    ),
  );
}
