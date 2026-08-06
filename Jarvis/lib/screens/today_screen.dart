import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/reel_card.dart';
import '../services/deck_db.dart';
import '../services/digest_settings.dart';
import '../services/nudge_service.dart';
import '../widgets/pirate_bits.dart';
import '../widgets/wanted_poster.dart';
import 'nudge_sheet.dart';

/// The day's quest log.
///
/// Same selection engine as before — a long haul, a couple of quick wins, one
/// short-term job, held steady until tomorrow — dressed as a bounty board so
/// the list reads like something worth doing rather than a chore sheet.
class TodayScreen extends StatefulWidget {
  const TodayScreen({super.key, required this.deck, this.digest});
  final DeckDb deck;
  final DigestSettings? digest;

  @override
  State<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends State<TodayScreen> {
  final _nudges = NudgeService();

  List<ReelCard> _cards = [];
  Set<String> _done = {};
  bool _loading = true;

  final Map<NudgeKind, NudgeSettings> _habits = {
    for (final k in NudgeKind.values) k: NudgeSettings.defaultsFor(k),
  };

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final cards = await widget.deck.todayTasks();
    final done = await widget.deck.doneToday();
    final fetched = <NudgeKind, NudgeSettings>{};
    for (final k in NudgeKind.values) {
      final s = await _nudges.getSettings(k);
      if (s != null) fetched[k] = s;
    }
    if (!mounted) return;
    setState(() {
      _cards = cards;
      _done = done;
      _habits.addAll(fetched);
      _loading = false;
    });
  }

  Future<void> _openNudge(NudgeKind kind) async {
    await showNudgeSheet(context, _nudges, kind);
    final s = await _nudges.getSettings(kind);
    if (!mounted || s == null) return;
    setState(() => _habits[kind] = s);
  }

  Future<void> _editDigest() async {
    final d = widget.digest;
    if (d == null) return;

    if (d.enabled) {
      await d.save(on: false);
      await d.apply(widget.deck);
      if (!mounted) return;
      setState(() {});
      _toast('Daily nudge off');
      return;
    }

    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: d.hour, minute: d.minute),
      helpText: 'Muster the crew at',
    );
    if (picked == null) return;
    await d.save(on: true, h: picked.hour, m: picked.minute);
    await d.apply(widget.deck);
    if (!mounted) return;
    setState(() {});
    _toast('Daily nudge at ${d.pretty}');
  }

  void _toast(String msg) => ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(msg), behavior: SnackBarBehavior.floating),
      );

  Future<void> _toggle(ReelCard c) async {
    final next = !_done.contains(c.id);
    await widget.deck.setDone(c.id, next);
    if (!mounted) return;
    setState(() => next ? _done.add(c.id) : _done.remove(c.id));
  }

  Future<void> _snooze(ReelCard c) async {
    await widget.deck.snooze(c.id);
    if (!mounted) return;
    setState(() => _cards.removeWhere((x) => x.id == c.id));
    _toast('"${c.title}" left for another voyage');
  }

  Future<void> _setProgress(ReelCard c, int pct) async {
    await widget.deck.setProgress(c.id, pct);
    if (!mounted) return;
    setState(() {
      final i = _cards.indexWhere((x) => x.id == c.id);
      if (i >= 0) _cards[i] = c.copyWith(progress: pct);
      if (pct >= 100) _done.add(c.id);
    });
  }

  /// The standing habits, pinned under the header where they can be found.
  Widget _habitRow() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        children: [
          for (final k in NudgeKind.values) ...[
            Expanded(
              child: NudgeChit(
                label: k.label,
                detail: _habits[k]!.summary,
                icon: iconForKind(k, on: _habits[k]!.enabled),
                accent: accentForKind(k),
                on: _habits[k]!.enabled,
                countToday: _habits[k]!.countToday,
                onTap: () => _openNudge(k),
              ),
            ),
            if (k != NudgeKind.values.last) const SizedBox(width: 10),
          ],
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator(color: kStraw));
    }

    final left = _cards.where((c) => !_done.contains(c.id)).length;

    // The board scrolls sideways: one poster at a time, the rest angled away.
    // The page itself still scrolls vertically so the header, habit cards and
    // footer can breathe on short screens.
    return RefreshIndicator(
      color: kStraw,
      backgroundColor: kDeck,
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(0, 10, 0, 28),
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: _Header(
              left: left,
              total: _cards.length,
              digest: widget.digest,
              onDigest: _editDigest,
            ),
          ),
          const SizedBox(height: 12),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: PosterRule(),
          ),
          const SizedBox(height: 12),
          _habitRow(),
          const SizedBox(height: 16),
          if (_cards.isEmpty)
            _emptyBoard()
          else
            PosterCarousel(
              count: _cards.length,
              height: 452,
              builder: (context, i) {
                final c = _cards[i];
                return WantedPoster(
                  card: c,
                  done: _done.contains(c.id),
                  onToggle: () => _toggle(c),
                  onSnooze: () => _snooze(c),
                  onProgress: (p) => _setProgress(c, p),
                  onOpenReel: () => launchUrl(Uri.parse(c.url),
                      mode: LaunchMode.externalApplication),
                );
              },
            ),
          const SizedBox(height: 14),
          Center(
            child: Text(
              _cards.isEmpty
                  ? 'Even pirates take shore leave.'
                  : left == 0
                      ? '"I\'m gonna be King of the Pirates!"'
                      : 'Bounties rise for those who finish what they start.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 11.5,
                fontStyle: FontStyle.italic,
                color: kParchmentDim.withValues(alpha: 0.6),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _emptyBoard() => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 36, vertical: 30),
        child: Column(
          children: [
            const StrawHat(size: 84),
            const SizedBox(height: 18),
            const Text(
              'No quests on the board',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 17,
                fontWeight: FontWeight.w700,
                color: kParchment,
              ),
            ),
            const SizedBox(height: 7),
            Text(
              'Import a deck from your saved reels and the crew will have '
              'something to do.',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 13,
                height: 1.45,
                color: kParchmentDim.withValues(alpha: 0.65),
              ),
            ),
          ],
        ),
      );
}

// ----------------------------------------------------------------- header

class _Header extends StatelessWidget {
  const _Header({
    required this.left,
    required this.total,
    required this.digest,
    required this.onDigest,
  });

  final int left, total;
  final VoidCallback onDigest;
  final DigestSettings? digest;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(top: 2, right: 13),
          child: StrawHat(size: 54),
        ),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const PosterLabel('SIDE QUESTS  ·  TODAY', colour: kStraw, size: 10),
              const SizedBox(height: 5),
              Text(
                total == 0
                    ? 'Nothing on the board.'
                    : left == 0
                        ? 'All hands stood down.'
                        : '$left of $total still open',
                style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.4,
                  height: 1.12,
                  color: kParchment,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                'Pulled from the reels you saved.',
                style: TextStyle(
                  fontSize: 12.5,
                  color: kParchmentDim.withValues(alpha: 0.75),
                ),
              ),
            ],
          ),
        ),
        if (digest != null)
          IconButton(
            onPressed: onDigest,
            tooltip: digest!.enabled
                ? 'Muster at ${digest!.pretty} — tap to turn off'
                : 'Muster the crew daily',
            icon: Icon(
              digest!.enabled ? Icons.notifications_active : Icons.notifications_none,
              color: digest!.enabled
                  ? kStraw
                  : kParchmentDim.withValues(alpha: 0.55),
              size: 20,
            ),
          ),
      ],
    );
  }
}
