import 'dart:async';

import 'package:flutter/material.dart';

import '../models/reel_card.dart';
import '../services/deck_db.dart';
import '../widgets/pirate_bits.dart';
import '../widgets/wanted_poster.dart';
import 'facts_screen.dart' show showFactSheet;

/// Everything that came out of your saved reels, as a wall of posters.
///
/// Search covers the spoken content too, so a reel whose caption never used
/// the words you remember can still be found by them.
class LibraryScreen extends StatefulWidget {
  const LibraryScreen({super.key, required this.deck});
  final DeckDb deck;

  @override
  State<LibraryScreen> createState() => _LibraryScreenState();
}

class _LibraryScreenState extends State<LibraryScreen> {
  final _controller = TextEditingController();
  Timer? _debounce;

  List<ReelCard> _results = [];
  List<(String, int)> _domains = [];
  String? _domain;
  CardKind? _kind;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _boot();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  Future<void> _boot() async {
    final domains = await widget.deck.domains();
    if (!mounted) return;
    setState(() => _domains = domains);
    await _run();
  }

  Future<void> _run() async {
    final q = _controller.text;
    // With no query and no filters, show the whole wall rather than nothing.
    final bare = q.trim().isEmpty && _domain == null && _kind == null;
    final results = bare
        ? await widget.deck.allCards()
        : await widget.deck.search(q, domain: _domain, kind: _kind);
    if (!mounted) return;
    setState(() {
      _results = results;
      _loading = false;
    });
  }

  void _onTyped(String _) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 220), _run);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        PosterLabel('THE ARCHIVE', colour: kStraw, size: 10),
                        SizedBox(height: 5),
                        Text(
                          'Everything you saved.',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w800,
                            letterSpacing: -0.3,
                            color: kParchment,
                          ),
                        ),
                      ],
                    ),
                  ),
                  Text(
                    '${_results.length}',
                    style: TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.w900,
                      color: kStraw.withValues(alpha: 0.35),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              _SearchField(controller: _controller, onChanged: _onTyped),
              const SizedBox(height: 11),
              _FilterRow(
                domains: _domains,
                domain: _domain,
                kind: _kind,
                onDomain: (d) {
                  setState(() => _domain = d);
                  _run();
                },
                onKind: (k) {
                  setState(() => _kind = k);
                  _run();
                },
              ),
              const SizedBox(height: 12),
            ],
          ),
        ),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator(color: kStraw))
              : _results.isEmpty
                  ? _empty()
                  : GridView.builder(
                      padding: const EdgeInsets.fromLTRB(16, 2, 16, 28),
                      gridDelegate:
                          const SliverGridDelegateWithFixedCrossAxisCount(
                        crossAxisCount: 2,
                        mainAxisSpacing: 14,
                        crossAxisSpacing: 14,
                        childAspectRatio: 0.66,
                      ),
                      itemCount: _results.length,
                      itemBuilder: (context, i) => MiniPoster(
                        card: _results[i],
                        onTap: () => showFactSheet(context, _results[i]),
                      ),
                    ),
        ),
      ],
    );
  }

  Widget _empty() => Center(
        child: Padding(
          padding: const EdgeInsets.all(34),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.search_off,
                  size: 42, color: kParchmentDim.withValues(alpha: 0.3)),
              const SizedBox(height: 14),
              const Text(
                'Nothing matches',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: kParchment,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                _controller.text.trim().isEmpty
                    ? 'Import a deck to fill the archive.'
                    : 'Try a different word, or clear the filters.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 13,
                  color: kParchmentDim.withValues(alpha: 0.6),
                ),
              ),
            ],
          ),
        ),
      );
}

class _SearchField extends StatelessWidget {
  const _SearchField({required this.controller, required this.onChanged});
  final TextEditingController controller;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      onChanged: onChanged,
      style: const TextStyle(color: kParchment, fontSize: 14.5),
      cursorColor: kStraw,
      decoration: InputDecoration(
        hintText: 'Search the archive…',
        hintStyle: TextStyle(
          color: kParchmentDim.withValues(alpha: 0.5),
          fontSize: 14,
        ),
        prefixIcon: Icon(Icons.search,
            size: 19, color: kParchmentDim.withValues(alpha: 0.6)),
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(vertical: 12, horizontal: 14),
        filled: true,
        fillColor: kDeck,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: kStrawDeep.withValues(alpha: 0.35)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: kStrawDeep.withValues(alpha: 0.35)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: kStraw.withValues(alpha: 0.7)),
        ),
      ),
    );
  }
}

class _FilterRow extends StatelessWidget {
  const _FilterRow({
    required this.domains,
    required this.domain,
    required this.kind,
    required this.onDomain,
    required this.onKind,
  });

  final List<(String, int)> domains;
  final String? domain;
  final CardKind? kind;
  final ValueChanged<String?> onDomain;
  final ValueChanged<CardKind?> onKind;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 32,
      child: ListView(
        scrollDirection: Axis.horizontal,
        children: [
          _chip('All', domain == null && kind == null, () {
            onKind(null);
            onDomain(null);
          }),
          _chip('Wanted', kind == CardKind.task,
              () => onKind(kind == CardKind.task ? null : CardKind.task)),
          _chip('Log', kind == CardKind.fact,
              () => onKind(kind == CardKind.fact ? null : CardKind.fact)),
          Padding(
            padding: const EdgeInsets.only(right: 8, top: 6, bottom: 6),
            child: Container(width: 1, color: kStrawDeep.withValues(alpha: 0.3)),
          ),
          for (final (d, n) in domains)
            _chip('$d  $n', domain == d, () => onDomain(domain == d ? null : d)),
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
