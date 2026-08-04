import 'dart:async';

import 'package:flutter/material.dart';

import '../models/reel_card.dart';
import '../services/deck_db.dart';
import '../widgets/card_bits.dart';
import 'facts_screen.dart' show showFactSheet;

/// Everything that came out of your saved reels, searchable.
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
    // With no query and no filters, show the whole shelf rather than nothing.
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
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const ScreenHeader(
                eyebrow: 'LIBRARY',
                title: 'Everything you saved.',
              ),
              const SizedBox(height: 14),
              _SearchField(controller: _controller, onChanged: _onTyped),
              const SizedBox(height: 12),
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
              const SizedBox(height: 10),
            ],
          ),
        ),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator(color: kTask))
              : _results.isEmpty
                  ? EmptyState(
                      icon: Icons.search_off,
                      title: 'Nothing matches',
                      body: _controller.text.trim().isEmpty
                          ? 'Import a deck to fill your library.'
                          : 'Try a different word, or clear the filters.',
                    )
                  : ListView.separated(
                      padding: const EdgeInsets.fromLTRB(16, 4, 16, 28),
                      itemCount: _results.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 10),
                      itemBuilder: (_, i) => _ResultRow(card: _results[i]),
                    ),
        ),
      ],
    );
  }
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
      textInputAction: TextInputAction.search,
      style: const TextStyle(color: Colors.white, fontSize: 15),
      decoration: InputDecoration(
        hintText: 'Search decisions, fitness, anything you saved',
        hintStyle: TextStyle(color: Colors.white.withOpacity(0.3), fontSize: 14),
        prefixIcon: Icon(Icons.search, color: Colors.white.withOpacity(0.35), size: 20),
        suffixIcon: controller.text.isEmpty
            ? null
            : IconButton(
                icon: Icon(Icons.close, color: Colors.white.withOpacity(0.35), size: 18),
                onPressed: () {
                  controller.clear();
                  onChanged('');
                },
              ),
        filled: true,
        fillColor: kSurface,
        contentPadding: const EdgeInsets.symmetric(vertical: 0, horizontal: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: Colors.white.withOpacity(0.08)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: Colors.white.withOpacity(0.08)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: kTask.withOpacity(0.6)),
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
          _chip('Tasks', kind == CardKind.task, kTask,
              () => onKind(kind == CardKind.task ? null : CardKind.task)),
          _chip('Facts', kind == CardKind.fact, kFact,
              () => onKind(kind == CardKind.fact ? null : CardKind.fact)),
          Container(
            width: 1,
            margin: const EdgeInsets.symmetric(horizontal: 6, vertical: 7),
            color: Colors.white.withOpacity(0.1),
          ),
          for (final (d, n) in domains)
            _chip('$d  $n', domain == d, Colors.white70,
                () => onDomain(domain == d ? null : d)),
        ],
      ),
    );
  }

  Widget _chip(String label, bool on, Color tone, VoidCallback tap) => Padding(
        padding: const EdgeInsets.only(right: 7),
        child: GestureDetector(
          onTap: tap,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: on ? tone.withOpacity(0.18) : kSurface,
              borderRadius: BorderRadius.circular(999),
              border: Border.all(
                color: on ? tone.withOpacity(0.6) : Colors.white.withOpacity(0.09),
              ),
            ),
            child: Text(
              label,
              style: TextStyle(
                fontSize: 11.5,
                fontWeight: on ? FontWeight.w600 : FontWeight.w400,
                color: on ? tone : Colors.white.withOpacity(0.55),
              ),
            ),
          ),
        ),
      );
}

class _ResultRow extends StatelessWidget {
  const _ResultRow({required this.card});
  final ReelCard card;

  @override
  Widget build(BuildContext context) {
    final accent = accentFor(card);
    final headline = card.isTask
        ? card.title
        : (card.claim.isNotEmpty ? card.claim : card.title);
    return GestureDetector(
      onTap: () => showFactSheet(context, card),
      child: Container(
        decoration: BoxDecoration(
          color: kSurface,
          borderRadius: BorderRadius.circular(14),
          border: Border(
            left: BorderSide(color: accent, width: 3),
            top: BorderSide(color: Colors.white.withOpacity(0.07)),
            right: BorderSide(color: Colors.white.withOpacity(0.07)),
            bottom: BorderSide(color: Colors.white.withOpacity(0.07)),
          ),
        ),
        padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Pill(text: card.isTask ? 'TASK' : 'FACT', color: accent),
                const SizedBox(width: 7),
                Pill(
                  text: card.domain.toUpperCase(),
                  color: Colors.white.withOpacity(0.32),
                ),
                if (card.isTask && card.isDone) ...[
                  const SizedBox(width: 7),
                  Icon(Icons.check_circle, size: 14, color: accent.withOpacity(0.8)),
                ],
              ],
            ),
            const SizedBox(height: 9),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (card.thumb.isNotEmpty) ...[
                  CardThumb(card: card),
                  const SizedBox(width: 12),
                ],
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        headline,
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 14.5,
                          height: 1.32,
                          fontWeight: FontWeight.w500,
                          color: Colors.white,
                        ),
                      ),
                      if (card.summary.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(
                          card.summary,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 12.5,
                            height: 1.4,
                            color: Colors.white.withOpacity(0.5),
                          ),
                        ),
                      ],
                    ],
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
