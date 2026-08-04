import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/reel_card.dart';
import '../services/deck_db.dart';
import '../services/digest_settings.dart';
import '../widgets/card_bits.dart';

/// The daily list: a few things pulled out of the reels you saved, chosen for
/// today and held steady until tomorrow.
class TodayScreen extends StatefulWidget {
  const TodayScreen({super.key, required this.deck, this.digest});
  final DeckDb deck;
  final DigestSettings? digest;

  @override
  State<TodayScreen> createState() => _TodayScreenState();
}

class _TodayScreenState extends State<TodayScreen> {
  List<ReelCard> _cards = [];
  Set<String> _done = {};
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final cards = await widget.deck.todayTasks();
    final done = await widget.deck.doneToday();
    if (!mounted) return;
    setState(() {
      _cards = cards;
      _done = done;
      _loading = false;
    });
  }

  Future<void> _editDigest() async {
    final d = widget.digest;
    if (d == null) return;

    if (d.enabled) {
      await d.save(on: false);
      await d.apply(widget.deck);
      if (!mounted) return;
      setState(() {});
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Daily nudge off'),
          behavior: SnackBarBehavior.floating,
        ),
      );
      return;
    }

    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: d.hour, minute: d.minute),
      helpText: 'Nudge me at',
    );
    if (picked == null) return;
    await d.save(on: true, h: picked.hour, m: picked.minute);
    await d.apply(widget.deck);
    if (!mounted) return;
    setState(() {});
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Daily nudge at ${d.pretty}'),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

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
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Snoozed "${c.title}" for 3 days'),
        behavior: SnackBarBehavior.floating,
      ),
    );
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
      return const Center(child: CircularProgressIndicator(color: kTask));
    }
    if (_cards.isEmpty) {
      return const EmptyState(
        icon: Icons.inbox_outlined,
        title: 'Nothing queued',
        body: 'Import a deck from your saved reels to start getting daily tasks.',
      );
    }

    final left = _cards.where((c) => !_done.contains(c.id)).length;
    return RefreshIndicator(
      color: kTask,
      backgroundColor: kSurface,
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: ScreenHeader(
                  eyebrow: 'TODAY',
                  title: left == 0
                      ? 'All done for today.'
                      : '$left of ${_cards.length} left',
                  subtitle: 'Pulled from the reels you saved.',
                ),
              ),
              if (widget.digest != null)
                IconButton(
                  onPressed: _editDigest,
                  tooltip: widget.digest!.enabled
                      ? 'Daily nudge at ${widget.digest!.pretty} — tap to turn off'
                      : 'Get a daily nudge',
                  icon: Icon(
                    widget.digest!.enabled
                        ? Icons.notifications_active
                        : Icons.notifications_none,
                    color: widget.digest!.enabled
                        ? kTask
                        : Colors.white.withOpacity(0.4),
                    size: 21,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 18),
          for (final c in _cards) ...[
            _TaskCard(
              card: c,
              done: _done.contains(c.id),
              onToggle: () => _toggle(c),
              onSnooze: () => _snooze(c),
              onProgress: (p) => _setProgress(c, p),
            ),
            const SizedBox(height: 12),
          ],
        ],
      ),
    );
  }
}

class _TaskCard extends StatelessWidget {
  const _TaskCard({
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

  Color get _accent => switch (card.horizon) {
        Horizon.today => kTask,
        Horizon.shortTerm => const Color(0xFFFFB347),
        Horizon.longTerm => kFact,
      };

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: done ? 0.55 : 1,
      child: Container(
        decoration: BoxDecoration(
          color: kSurface,
          borderRadius: BorderRadius.circular(16),
          border: Border(
            left: BorderSide(color: _accent, width: 3),
            top: BorderSide(color: Colors.white.withOpacity(0.07)),
            right: BorderSide(color: Colors.white.withOpacity(0.07)),
            bottom: BorderSide(color: Colors.white.withOpacity(0.07)),
          ),
        ),
        padding: const EdgeInsets.fromLTRB(14, 14, 12, 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Pill(text: horizonLabel(card.horizon).toUpperCase(), color: _accent),
                const SizedBox(width: 8),
                Pill(
                  text: card.domain.toUpperCase(),
                  color: Colors.white.withOpacity(0.35),
                ),
                const Spacer(),
                if (card.recurrence != 'once')
                  Icon(Icons.repeat,
                      size: 15, color: Colors.white.withOpacity(0.4)),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!card.tracksProgress)
                  GestureDetector(
                    onTap: onToggle,
                    behavior: HitTestBehavior.opaque,
                    child: Padding(
                      padding: const EdgeInsets.only(right: 12, top: 2),
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 180),
                        width: 24,
                        height: 24,
                        decoration: BoxDecoration(
                          color: done ? _accent : Colors.transparent,
                          borderRadius: BorderRadius.circular(7),
                          border: Border.all(
                            color: done ? _accent : Colors.white.withOpacity(0.35),
                            width: 2,
                          ),
                        ),
                        child: done
                            ? const Icon(Icons.check, size: 16, color: Colors.white)
                            : null,
                      ),
                    ),
                  ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        card.title,
                        style: TextStyle(
                          fontSize: 16,
                          height: 1.3,
                          fontWeight: FontWeight.w600,
                          color: Colors.white,
                          decoration: done ? TextDecoration.lineThrough : null,
                          decorationColor: Colors.white54,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        card.summary,
                        style: TextStyle(
                          fontSize: 13.5,
                          height: 1.4,
                          color: Colors.white.withOpacity(0.62),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
            if (card.steps.isNotEmpty) ...[
              const SizedBox(height: 12),
              for (final s in card.steps.take(4))
                Padding(
                  padding: const EdgeInsets.only(bottom: 5, left: 2),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Padding(
                        padding: const EdgeInsets.only(top: 6, right: 9),
                        child: Container(
                          width: 4,
                          height: 4,
                          decoration: BoxDecoration(
                            color: _accent.withOpacity(0.7),
                            shape: BoxShape.circle,
                          ),
                        ),
                      ),
                      Expanded(
                        child: Text(
                          s,
                          style: TextStyle(
                            fontSize: 12.5,
                            height: 1.4,
                            color: Colors.white.withOpacity(0.55),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
            if (card.tracksProgress) ...[
              const SizedBox(height: 12),
              _Progress(value: card.progress, accent: _accent, onChange: onProgress),
            ],
            const SizedBox(height: 6),
            Row(
              children: [
                if (card.url.isNotEmpty)
                  CardAction(
                    icon: Icons.play_circle_outline,
                    label: 'Reel',
                    onTap: () => launchUrl(Uri.parse(card.url),
                        mode: LaunchMode.externalApplication),
                  ),
                CardAction(icon: Icons.snooze, label: 'Snooze', onTap: onSnooze),
                const Spacer(),
                if (card.owner.isNotEmpty)
                  Text(
                    '@${card.owner}',
                    style: TextStyle(
                      fontSize: 11,
                      color: Colors.white.withOpacity(0.28),
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

/// Long-term work moves in steps rather than a single tick.
class _Progress extends StatelessWidget {
  const _Progress({
    required this.value,
    required this.accent,
    required this.onChange,
  });
  final int value;
  final Color accent;
  final ValueChanged<int> onChange;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              '$value%',
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: accent,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(3),
                child: LinearProgressIndicator(
                  value: value / 100,
                  minHeight: 5,
                  backgroundColor: Colors.white.withOpacity(0.09),
                  valueColor: AlwaysStoppedAnimation(accent),
                ),
              ),
            ),
            const SizedBox(width: 10),
            GestureDetector(
              onTap: () => onChange(value + 10),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 5),
                decoration: BoxDecoration(
                  color: accent.withOpacity(0.16),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  '+10%',
                  style: TextStyle(
                    fontSize: 11.5,
                    fontWeight: FontWeight.w700,
                    color: accent,
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
