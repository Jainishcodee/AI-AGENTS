import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/reel_card.dart';
import '../services/deck_db.dart';
import '../services/digest_settings.dart';
import '../services/water_service.dart';
import '../widgets/card_bits.dart';
import '../widgets/pirate_bits.dart';
import 'water_sheet.dart';

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
  final _water = WaterService();

  List<ReelCard> _cards = [];
  Set<String> _done = {};
  bool _loading = true;
  bool _waterOn = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final cards = await widget.deck.todayTasks();
    final done = await widget.deck.doneToday();
    final water = await _water.getSettings();
    if (!mounted) return;
    setState(() {
      _cards = cards;
      _done = done;
      _waterOn = water?.enabled ?? false;
      _loading = false;
    });
  }

  Future<void> _openWater() async {
    await showWaterSheet(context, _water);
    final s = await _water.getSettings();
    if (!mounted) return;
    setState(() => _waterOn = s?.enabled ?? false);
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

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator(color: kStraw));
    }
    if (_cards.isEmpty) {
      return _EmptyDock(onWater: _openWater, waterOn: _waterOn);
    }

    final left = _cards.where((c) => !_done.contains(c.id)).length;
    return RefreshIndicator(
      color: kStraw,
      backgroundColor: kDeck,
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 36),
        children: [
          _Header(
            left: left,
            total: _cards.length,
            waterOn: _waterOn,
            onWater: _openWater,
            digest: widget.digest,
            onDigest: _editDigest,
          ),
          const SizedBox(height: 14),
          const PosterRule(),
          const SizedBox(height: 16),
          for (final c in _cards) ...[
            _QuestCard(
              card: c,
              done: _done.contains(c.id),
              onToggle: () => _toggle(c),
              onSnooze: () => _snooze(c),
              onProgress: (p) => _setProgress(c, p),
            ),
            const SizedBox(height: 13),
          ],
          const SizedBox(height: 6),
          Center(
            child: Text(
              left == 0
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
}

// ----------------------------------------------------------------- header

class _Header extends StatelessWidget {
  const _Header({
    required this.left,
    required this.total,
    required this.waterOn,
    required this.onWater,
    required this.digest,
    required this.onDigest,
  });

  final int left, total;
  final bool waterOn;
  final VoidCallback onWater, onDigest;
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
                left == 0 ? 'All hands stood down.' : '$left of $total still open',
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
        Column(
          children: [
            IconButton(
              onPressed: onWater,
              tooltip: waterOn
                  ? 'Water nudge is on — tap to change'
                  : 'Get a water nudge',
              icon: Icon(
                waterOn ? Icons.water_drop : Icons.water_drop_outlined,
                color: waterOn ? kLogPose : kParchmentDim.withValues(alpha: 0.55),
                size: 20,
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
        ),
      ],
    );
  }
}

// ------------------------------------------------------------- quest card

class _QuestCard extends StatelessWidget {
  const _QuestCard({
    required this.card,
    required this.done,
    required this.onToggle,
    required this.onSnooze,
    required this.onProgress,
  });

  final ReelCard card;
  final bool done;
  final VoidCallback onToggle, onSnooze;
  final ValueChanged<int> onProgress;

  @override
  Widget build(BuildContext context) {
    final r = rankFor(card.horizon);

    return Opacity(
      opacity: done ? 0.62 : 1,
      child: Stack(
        children: [
          Container(
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [kDeck, kDeckSunk],
              ),
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: kStrawDeep.withValues(alpha: 0.30)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Rank bar across the top, the way a poster leads with the crime.
                Container(
                  decoration: BoxDecoration(
                    color: r.colour.withValues(alpha: 0.13),
                    borderRadius: const BorderRadius.vertical(top: Radius.circular(13)),
                    border: Border(
                      bottom: BorderSide(color: kStrawDeep.withValues(alpha: 0.28)),
                    ),
                  ),
                  padding: const EdgeInsets.fromLTRB(13, 8, 12, 8),
                  child: Row(
                    children: [
                      PosterLabel(r.rank, colour: r.colour),
                      const SizedBox(width: 8),
                      Text(
                        card.domain.toUpperCase(),
                        style: TextStyle(
                          fontSize: 9,
                          letterSpacing: 1.4,
                          fontWeight: FontWeight.w700,
                          color: kParchmentDim.withValues(alpha: 0.7),
                        ),
                      ),
                      const Spacer(),
                      if (card.recurrence != 'once')
                        Padding(
                          padding: const EdgeInsets.only(right: 7),
                          child: Icon(Icons.repeat,
                              size: 13, color: kParchmentDim.withValues(alpha: 0.6)),
                        ),
                      Text(
                        bountyFor(card),
                        style: const TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 0.3,
                          color: kStraw,
                          fontFeatures: [FontFeature.tabularFigures()],
                        ),
                      ),
                    ],
                  ),
                ),

                Padding(
                  padding: const EdgeInsets.fromLTRB(13, 12, 13, 4),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          if (!card.tracksProgress)
                            GestureDetector(
                              onTap: onToggle,
                              behavior: HitTestBehavior.opaque,
                              child: Padding(
                                padding: const EdgeInsets.only(right: 11, top: 1),
                                child: JollyRogerCheck(done: done, colour: r.colour),
                              ),
                            ),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  card.title,
                                  style: TextStyle(
                                    fontSize: 15.5,
                                    height: 1.3,
                                    fontWeight: FontWeight.w700,
                                    color: kParchment,
                                    decoration:
                                        done ? TextDecoration.lineThrough : null,
                                    decorationColor:
                                        kParchmentDim.withValues(alpha: 0.7),
                                  ),
                                ),
                                const SizedBox(height: 5),
                                Text(
                                  card.summary,
                                  style: TextStyle(
                                    fontSize: 13,
                                    height: 1.42,
                                    color: kParchmentDim.withValues(alpha: 0.85),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),

                      if (card.steps.isNotEmpty) ...[
                        const SizedBox(height: 13),
                        const PosterLabel('ORDERS'),
                        const SizedBox(height: 6),
                        for (final s in card.steps.take(4))
                          Padding(
                            padding: const EdgeInsets.only(bottom: 5),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Padding(
                                  padding: const EdgeInsets.only(top: 5, right: 9),
                                  child: Transform.rotate(
                                    angle: 0.785,
                                    child: Container(
                                      width: 4,
                                      height: 4,
                                      color: r.colour.withValues(alpha: 0.8),
                                    ),
                                  ),
                                ),
                                Expanded(
                                  child: Text(
                                    s,
                                    style: TextStyle(
                                      fontSize: 12.5,
                                      height: 1.42,
                                      color: kParchmentDim.withValues(alpha: 0.72),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                      ],

                      if (card.tracksProgress) ...[
                        const SizedBox(height: 14),
                        LogPose(
                          value: card.progress,
                          onAdvance: () => onProgress(card.progress + 10),
                        ),
                      ],
                    ],
                  ),
                ),

                Padding(
                  padding: const EdgeInsets.fromLTRB(6, 0, 12, 4),
                  child: Row(
                    children: [
                      if (card.url.isNotEmpty)
                        CardAction(
                          icon: Icons.play_circle_outline,
                          label: 'Reel',
                          color: kParchmentDim,
                          onTap: () => launchUrl(Uri.parse(card.url),
                              mode: LaunchMode.externalApplication),
                        ),
                      CardAction(
                        icon: Icons.sailing_outlined,
                        label: 'Set sail later',
                        color: kParchmentDim,
                        onTap: onSnooze,
                      ),
                      const Spacer(),
                      if (card.owner.isNotEmpty)
                        Text(
                          '@${card.owner}',
                          style: TextStyle(
                            fontSize: 10.5,
                            color: kParchmentDim.withValues(alpha: 0.45),
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          if (done)
            Positioned(
              top: 46,
              right: 16,
              child: ClearedStamp(
                label: card.tracksProgress ? 'LANDED' : 'CLEARED',
              ),
            ),
        ],
      ),
    );
  }
}

// ------------------------------------------------------------ empty state

class _EmptyDock extends StatelessWidget {
  const _EmptyDock({required this.onWater, required this.waterOn});
  final VoidCallback onWater;
  final bool waterOn;

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Center(
          child: Padding(
            padding: const EdgeInsets.all(36),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const StrawHat(size: 92),
                const SizedBox(height: 20),
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
          ),
        ),
        Positioned(
          top: 8,
          right: 8,
          child: IconButton(
            onPressed: onWater,
            tooltip: waterOn ? 'Water nudge is on' : 'Get a water nudge',
            icon: Icon(
              waterOn ? Icons.water_drop : Icons.water_drop_outlined,
              color: waterOn ? kLogPose : kParchmentDim.withValues(alpha: 0.55),
              size: 20,
            ),
          ),
        ),
      ],
    );
  }
}
