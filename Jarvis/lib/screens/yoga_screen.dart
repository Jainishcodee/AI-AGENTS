import 'package:flutter/material.dart';

import '../services/jain_calendar.dart';
import '../services/yoga_library.dart';
import '../widgets/card_bits.dart';

/// The daily asana sequence, as cards.
///
/// Built on the same card grammar as the reel screens — accent stripe, eyebrow
/// pills, expand for detail — so this reads as part of Jarvis rather than a
/// bolted-on fitness app.
///
/// Two things here are not decoration:
///
/// **The excluded postures are shown, not hidden.** He named halasana as one he
/// used to do, and it is the one posture in his list I am asking him to drop.
/// Quietly omitting it would look like I forgot; showing it with the reason and
/// a substitute is the only version that survives him wondering where it went.
///
/// **The fast-day rule is enforced here too.** On an upvas the list collapses to
/// the restorative subset, for the same reason the training screen refuses to
/// hand him a session.
class YogaScreen extends StatefulWidget {
  const YogaScreen({
    super.key,
    required this.week,
    required this.clearance,
    this.fastLabel,
  });

  final int week;
  final TrainingClearance clearance;
  final String? fastLabel;

  @override
  State<YogaScreen> createState() => _YogaScreenState();
}

class _YogaScreenState extends State<YogaScreen> {
  final _open = <String>{};
  final _done = <String>{};

  bool get _restrictedDay =>
      widget.clearance == TrainingClearance.rest ||
      widget.clearance == TrainingClearance.lightOnly;

  List<Asana> get _sequence => _restrictedDay
      ? YogaLibrary.restorativeOnly
      : YogaLibrary.sequenceForWeek(widget.week);

  @override
  Widget build(BuildContext context) {
    final seq = _sequence;
    final mins = YogaLibrary.minutesFor(seq);
    final excluded = YogaLibrary.excluded;

    return Scaffold(
      backgroundColor: const Color(0xFF0B0608),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        iconTheme: const IconThemeData(color: Colors.white70),
      ),
      body: SafeArea(
        top: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(18, 0, 18, 40),
          children: [
            ScreenHeader(
              eyebrow: 'DAILY PRACTICE',
              title: 'Yoga',
              subtitle: _restrictedDay
                  ? 'Restorative only today · ${seq.length} postures'
                  : '~$mins min · week ${widget.week} · ${seq.length} postures',
            ),
            const SizedBox(height: 16),

            if (_restrictedDay) _fastBanner(),
            if (_restrictedDay) const SizedBox(height: 14),

            _progressStrip(seq),
            const SizedBox(height: 16),

            ...seq.map(_asanaCard),

            const SizedBox(height: 26),
            _excludedHeader(),
            const SizedBox(height: 10),
            ...excluded.map(_excludedCard),
          ],
        ),
      ),
    );
  }

  // ------------------------------------------------------------------ chrome

  Widget _fastBanner() => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: kAmber.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: kAmber.withValues(alpha: 0.45)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.self_improvement, color: kAmber, size: 18),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    widget.fastLabel == null
                        ? 'Restricted day'
                        : '${widget.fastLabel} today',
                    style: const TextStyle(
                      color: kAmber,
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Restorative postures only — no long holds, no loaded '
                    'extension, no forceful breathing.',
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.7),
                      fontSize: 12,
                      height: 1.4,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      );

  Widget _progressStrip(List<Asana> seq) {
    final done = seq.where((a) => _done.contains(a.name)).length;
    return Row(
      children: [
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: seq.isEmpty ? 0 : done / seq.length,
              minHeight: 6,
              backgroundColor: Colors.white.withValues(alpha: 0.07),
              valueColor: AlwaysStoppedAnimation(
                done == seq.length && seq.isNotEmpty ? kFact : kTask,
              ),
            ),
          ),
        ),
        const SizedBox(width: 12),
        Text(
          '$done / ${seq.length}',
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.5),
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }

  static Color _stageColour(AsanaStage s) => switch (s) {
        AsanaStage.calibrate => const Color(0xFF9B8AFF),
        AsanaStage.mobility => kFact,
        AsanaStage.opener => kAmber,
        AsanaStage.strength => kTask,
        AsanaStage.balance => const Color(0xFF6FC3FF),
        AsanaStage.closing => const Color(0xFF7A7A7A),
      };

  // ------------------------------------------------------------------- cards

  Widget _asanaCard(Asana a) {
    final open = _open.contains(a.name);
    final done = _done.contains(a.name);
    final accent = _stageColour(a.stage);

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: Container(
          decoration: BoxDecoration(
            color: kSurface,
            border: Border.all(color: Colors.white.withValues(alpha: 0.07)),
            borderRadius: BorderRadius.circular(16),
          ),
          child: IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Stage stripe, same device the reel cards use for horizon.
                Container(
                  width: 4,
                  color: accent.withValues(alpha: done ? 0.35 : 1),
                ),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(14, 12, 12, 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Wrap(
                          spacing: 6,
                          runSpacing: 6,
                          children: [
                            Pill(text: a.stage.label, color: accent),
                            if (a.alreadyPractised)
                              const Pill(
                                text: 'YOURS · 2021',
                                color: kFact,
                              ),
                            if (a.entersLabel != null)
                              Pill(text: a.entersLabel!, color: kAmber),
                          ],
                        ),
                        const SizedBox(height: 10),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    a.name,
                                    style: TextStyle(
                                      color: done
                                          ? Colors.white.withValues(alpha: 0.45)
                                          : Colors.white,
                                      fontSize: 16,
                                      fontWeight: FontWeight.w700,
                                      height: 1.2,
                                      decoration: done
                                          ? TextDecoration.lineThrough
                                          : null,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    a.sanskrit,
                                    style: TextStyle(
                                      color: Colors.white.withValues(alpha: 0.4),
                                      fontSize: 12,
                                      fontStyle: FontStyle.italic,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            GestureDetector(
                              onTap: () => setState(() {
                                done
                                    ? _done.remove(a.name)
                                    : _done.add(a.name);
                              }),
                              child: Container(
                                width: 30,
                                height: 30,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: done
                                      ? kFact.withValues(alpha: 0.2)
                                      : Colors.transparent,
                                  border: Border.all(
                                    color: done
                                        ? kFact
                                        : Colors.white.withValues(alpha: 0.2),
                                  ),
                                ),
                                child: Icon(
                                  Icons.check,
                                  size: 16,
                                  color: done
                                      ? kFact
                                      : Colors.white.withValues(alpha: 0.25),
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          a.hold,
                          style: TextStyle(
                            color: accent.withValues(alpha: 0.9),
                            fontSize: 12.5,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        if (open) ...[
                          const SizedBox(height: 12),
                          Text(
                            a.purpose,
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.72),
                              fontSize: 12.5,
                              height: 1.45,
                            ),
                          ),
                          const SizedBox(height: 10),
                          ...a.cues.map(
                            (c) => Padding(
                              padding: const EdgeInsets.only(bottom: 5),
                              child: Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Container(
                                    margin:
                                        const EdgeInsets.only(top: 6, right: 8),
                                    width: 4,
                                    height: 4,
                                    decoration: BoxDecoration(
                                      color: accent.withValues(alpha: 0.8),
                                      shape: BoxShape.circle,
                                    ),
                                  ),
                                  Expanded(
                                    child: Text(
                                      c,
                                      style: const TextStyle(
                                        color: Colors.white70,
                                        fontSize: 12.5,
                                        height: 1.4,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                          if (a.caution != null) ...[
                            const SizedBox(height: 6),
                            _caution(a.caution!),
                          ],
                        ],
                        Align(
                          alignment: Alignment.centerLeft,
                          child: CardAction(
                            icon: open
                                ? Icons.keyboard_arrow_up
                                : Icons.keyboard_arrow_down,
                            label: open ? 'Less' : 'How to do it',
                            onTap: () => setState(() {
                              open ? _open.remove(a.name) : _open.add(a.name);
                            }),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _excludedHeader() => Row(
        children: [
          const Icon(Icons.block, color: kTask, size: 16),
          const SizedBox(width: 8),
          const Text(
            'NOT IN THIS PLAN',
            style: TextStyle(
              color: kTask,
              fontSize: 11,
              letterSpacing: 2.2,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Container(
              height: 1,
              color: kTask.withValues(alpha: 0.2),
            ),
          ),
        ],
      );

  Widget _excludedCard(Asana a) {
    final open = _open.contains(a.name);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Container(
        decoration: BoxDecoration(
          color: kSunk,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: kTask.withValues(alpha: 0.25)),
        ),
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        a.name,
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.6),
                          fontSize: 14.5,
                          fontWeight: FontWeight.w700,
                          decoration: TextDecoration.lineThrough,
                          decorationColor: kTask.withValues(alpha: 0.7),
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        a.sanskrit,
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.32),
                          fontSize: 11.5,
                          fontStyle: FontStyle.italic,
                        ),
                      ),
                    ],
                  ),
                ),
                if (a.alreadyPractised)
                  const Pill(text: 'YOU DID THIS', color: kAmber),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              a.purpose,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.6),
                fontSize: 12,
                height: 1.4,
              ),
            ),
            if (open) ...[
              const SizedBox(height: 10),
              if (a.caution != null) _caution(a.caution!),
              if (a.substitute != null) ...[
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: kFact.withValues(alpha: 0.09),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: kFact.withValues(alpha: 0.3)),
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.swap_horiz, color: kFact, size: 15),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          a.substitute!,
                          style: const TextStyle(
                            color: kFact,
                            fontSize: 12,
                            height: 1.4,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ],
            Align(
              alignment: Alignment.centerLeft,
              child: CardAction(
                icon: open
                    ? Icons.keyboard_arrow_up
                    : Icons.keyboard_arrow_down,
                label: open ? 'Less' : 'Why, and what instead',
                color: kTask.withValues(alpha: 0.75),
                onTap: () => setState(() {
                  open ? _open.remove(a.name) : _open.add(a.name);
                }),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _caution(String s) => Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: kAmber.withValues(alpha: 0.09),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.warning_amber_rounded, color: kAmber, size: 15),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                s,
                style: const TextStyle(
                  color: kAmber,
                  fontSize: 12,
                  height: 1.4,
                ),
              ),
            ),
          ],
        ),
      );
}
