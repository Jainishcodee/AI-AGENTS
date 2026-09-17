import 'package:flutter/material.dart';

import '../services/council_service.dart';
import '../widgets/pirate_bits.dart';

/// Recording what actually happened, from the phone.
///
/// This is the single highest-value screen in the Cognitive OS integration, and
/// the reason the integration exists at all. The council's programs are copyable
/// in an afternoon; a corpus of resolved decisions belonging to one person is not
/// — and the corpus only exists if this form is easy enough that somebody fills it
/// in sixty days after they stopped thinking about the decision.
///
/// Three deliberate choices, carried over from the web form because they are about
/// the data rather than the platform:
///
/// - **"What did you actually do" is free text, not a picker.** People do not
///   choose from the menu. A card where you did something no module proposed is a
///   direct measurement of the council's blind spot, and constraining the answer
///   would delete the most informative rows in the dataset.
/// - **Surprises are their own field.** "What nobody predicted" is a distinct
///   signal and feeds a council-level prior, so it is not a notes box.
/// - **The prediction is shown while you write.** It was recorded before the
///   outcome was known; seeing it here is what makes this a check rather than a
///   reminiscence.
class CouncilCheckinSheet extends StatefulWidget {
  const CouncilCheckinSheet({super.key, required this.service});

  final CouncilService service;

  static Future<void> show(BuildContext context, CouncilService service) {
    return showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: kDeck,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
      ),
      builder: (_) => CouncilCheckinSheet(service: service),
    );
  }

  @override
  State<CouncilCheckinSheet> createState() => _CouncilCheckinSheetState();
}

class _CouncilCheckinSheetState extends State<CouncilCheckinSheet> {
  DueDecision? _open;
  bool _busy = false;
  String? _error;

  final _chose = TextEditingController();
  final _outcome = TextEditingController();
  final _surprise = TextEditingController();

  @override
  void dispose() {
    _chose.dispose();
    _outcome.dispose();
    _surprise.dispose();
    super.dispose();
  }

  bool get _ready =>
      _chose.text.trim().length > 2 && _outcome.text.trim().length > 2;

  Future<void> _submit() async {
    final card = _open;
    if (card == null || !_ready || _busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });

    final problem = await widget.service.resolve(
      card.id,
      chose: _chose.text.trim(),
      outcome: _outcome.text.trim(),
      surprises: [_surprise.text.trim()],
    );

    if (!mounted) return;
    setState(() => _busy = false);

    if (problem != null) {
      setState(() => _error = problem);
      return;
    }

    _chose.clear();
    _outcome.clear();
    _surprise.clear();
    setState(() => _open = null);

    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Recorded. Every module was scored against it.'),
      ),
    );
    if (widget.service.due.isEmpty && mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final inset = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.only(bottom: inset),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.88,
        ),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(18, 14, 18, 22),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Center(
                child: Container(
                  width: 38,
                  height: 4,
                  decoration: BoxDecoration(
                    color: kStraw.withValues(alpha: 0.5),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              Text(
                _open == null ? 'Decisions due for review' : 'What happened?',
                style: const TextStyle(
                  color: kStraw,
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 10),
              if (_open == null) ..._list() else ..._form(_open!),
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _list() {
    final due = widget.service.due;
    if (due.isEmpty) {
      return const [
        Padding(
          padding: EdgeInsets.symmetric(vertical: 24),
          child: Text(
            'Nothing is due. Decisions appear here on the date the council '
            'said to check back — usually 30 to 90 days out.',
            style: TextStyle(color: Colors.white70, height: 1.4),
          ),
        ),
      ];
    }

    return [
      const Text(
        'The council made a prediction before it knew. Closing one of these is '
        'the only thing that teaches it anything.',
        style: TextStyle(color: Colors.white60, fontSize: 12.5, height: 1.4),
      ),
      const SizedBox(height: 12),
      for (final card in due)
        Card(
          color: Colors.white.withValues(alpha: 0.04),
          margin: const EdgeInsets.only(bottom: 8),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
            side: BorderSide(color: kStraw.withValues(alpha: 0.22)),
          ),
          child: ListTile(
            title: Text(
              card.question,
              style: const TextStyle(color: Colors.white, fontSize: 14.5),
            ),
            subtitle: Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                card.overdueDays > 0
                    ? 'due ${card.overdueDays} day(s) ago'
                    : 'due today',
                style: TextStyle(
                  color: kStraw.withValues(alpha: 0.85),
                  fontSize: 12,
                ),
              ),
            ),
            trailing: const Icon(Icons.chevron_right, color: kStraw),
            onTap: () => setState(() => _open = card),
          ),
        ),
    ];
  }

  List<Widget> _form(DueDecision card) {
    return [
      Text(
        card.question,
        style: const TextStyle(color: Colors.white, fontSize: 14.5, height: 1.35),
      ),
      const SizedBox(height: 12),
      if (card.prediction.isNotEmpty)
        Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.04),
            borderRadius: BorderRadius.circular(8),
            border: Border(left: BorderSide(color: kStraw, width: 2)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'WHAT THE COUNCIL PREDICTED, BEFORE IT KNEW',
                style: TextStyle(
                  color: Colors.white54,
                  fontSize: 10,
                  letterSpacing: 0.8,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                card.prediction,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  height: 1.4,
                ),
              ),
              if (card.measurableBy.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  'measured by ${card.measurableBy}',
                  style: const TextStyle(color: Colors.white38, fontSize: 11),
                ),
              ],
            ],
          ),
        ),
      const SizedBox(height: 16),
      _field(
        'What did you actually do?',
        _chose,
        hint: 'Stayed, but asked for the offer in writing with a deadline.',
        help: 'In your own words. If you did something no module suggested, say '
            'that — it is the most useful answer in here.',
        lines: 2,
      ),
      _field(
        'What happened as a result?',
        _outcome,
        hint: 'The offer arrived nine days later.',
        lines: 3,
      ),
      _field(
        'Did anything happen that nobody predicted?',
        _surprise,
        hint: 'Someone nobody mentioned turned out to decide it.',
        help: 'Optional, and its own field rather than a note — it feeds a '
            'council-level prior about what the six keep missing.',
        lines: 2,
      ),
      if (_error != null) ...[
        const SizedBox(height: 6),
        Text(
          _error!,
          style: const TextStyle(color: Color(0xFFE08A8A), fontSize: 12.5, height: 1.35),
        ),
      ],
      const SizedBox(height: 14),
      Row(
        children: [
          TextButton(
            onPressed: _busy ? null : () => setState(() => _open = null),
            child: const Text('Back', style: TextStyle(color: Colors.white54)),
          ),
          const Spacer(),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: kStraw,
              foregroundColor: const Color(0xFF2A1D10),
            ),
            onPressed: _ready && !_busy ? _submit : null,
            child: Text(_busy ? 'Scoring the council…' : 'Record and score'),
          ),
        ],
      ),
      const SizedBox(height: 6),
      const Text(
        'Every module gets graded against what it said. The grader is never '
        'shown how confident any of them were.',
        style: TextStyle(color: Colors.white38, fontSize: 11, height: 1.35),
      ),
    ];
  }

  Widget _field(
    String label,
    TextEditingController controller, {
    String hint = '',
    String help = '',
    int lines = 2,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: Colors.white70,
              fontSize: 12.5,
              fontWeight: FontWeight.w600,
            ),
          ),
          if (help.isNotEmpty) ...[
            const SizedBox(height: 3),
            Text(
              help,
              style: const TextStyle(color: Colors.white38, fontSize: 11, height: 1.3),
            ),
          ],
          const SizedBox(height: 6),
          TextField(
            controller: controller,
            maxLines: lines,
            // 15px or larger: anything smaller makes the viewport zoom on focus on
            // some devices, and a zoom you have to pinch back out of is enough
            // friction to abandon the form.
            style: const TextStyle(color: Colors.white, fontSize: 15),
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(
              hintText: hint,
              hintStyle: const TextStyle(color: Colors.white24, fontSize: 13),
              filled: true,
              fillColor: Colors.white.withValues(alpha: 0.05),
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: kStraw.withValues(alpha: 0.25)),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: BorderSide(color: kStraw.withValues(alpha: 0.25)),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(8),
                borderSide: const BorderSide(color: kStraw),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
