import 'dart:async';
import 'package:flutter/material.dart';

import '../services/council_service.dart';
import 'council_checkin_sheet.dart';

const Color kCouncilRed = Color(0xFFE74848);
const Color kCouncilTeal = Color(0xFF00E5C9);
const Color kCouncilGold = Color(0xFFF1D483);
const Color kCouncilDark = Color(0xFF160E18);

class CouncilScreen extends StatefulWidget {
  const CouncilScreen({super.key, required this.service});

  final CouncilService service;

  static Future<void> show(BuildContext context, CouncilService service) {
    return Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => CouncilScreen(service: service),
      ),
    );
  }

  @override
  State<CouncilScreen> createState() => _CouncilScreenState();
}

class _CouncilScreenState extends State<CouncilScreen> with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final TextEditingController _questionCtrl = TextEditingController();
  final TextEditingController _notesCtrl = TextEditingController();

  String _preset = 'full';
  String _depth = 'quick';
  bool _busy = false;
  String? _deliberateError;
  DeliberationResult? _lastResult;

  List<DueDecision> _cards = [];
  bool _loadingCards = false;
  String _cardFilter = 'all'; // 'all', 'due', 'open', 'resolved'

  bool _connected = false;
  bool _checkingHealth = false;

  final Map<String, Map<String, String>> _engineInfo = {
    'analyst': {
      'skin': 'Klein',
      'focus': 'Evidence before conclusion',
      'tool': 'Probability trees & base rates',
    },
    'tactician': {
      'skin': 'Lumian',
      'focus': 'Action under uncertainty',
      'tool': '≥7 options & asymmetry tables',
    },
    'strategist': {
      'skin': 'Alger',
      'focus': 'Power and incentives',
      'tool': 'Stakeholder graphs & hidden leverage',
    },
    'psychologist': {
      'skin': 'Audrey',
      'focus': 'Human dynamics & cost',
      'tool': '9-dimension profile per person',
    },
    'optimizer': {
      'skin': 'Fors',
      'focus': 'Constraint & efficiency',
      'tool': 'One binding constraint & waste audit',
    },
    'ethicist': {
      'skin': 'Leonard',
      'focus': 'Values and regret',
      'tool': '1/5/10y regret & harm ledger',
    },
  };

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    _checkStatus();
    _loadCards();
  }

  @override
  void dispose() {
    _tabController.dispose();
    _questionCtrl.dispose();
    _notesCtrl.dispose();
    super.dispose();
  }

  Future<void> _checkStatus() async {
    setState(() => _checkingHealth = true);
    final ok = await widget.service.reachable();
    if (mounted) {
      setState(() {
        _connected = ok;
        _checkingHealth = false;
      });
    }
  }

  Future<void> _loadCards() async {
    setState(() => _loadingCards = true);
    await widget.service.refresh();
    final cards = await widget.service.listCards();
    if (mounted) {
      setState(() {
        _cards = cards;
        _loadingCards = false;
      });
    }
  }

  Future<void> _runDeliberation() async {
    final q = _questionCtrl.text.trim();
    if (q.length < 5) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please enter a clear decision question.')),
      );
      return;
    }

    setState(() {
      _busy = true;
      _deliberateError = null;
      _lastResult = null;
    });

    try {
      final res = await widget.service.deliberate(
        question: q,
        preset: _preset,
        depth: _depth,
        contextNotes: _notesCtrl.text.trim(),
      );
      if (mounted) {
        setState(() {
          _lastResult = res;
          _busy = false;
        });
        _loadCards();
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _deliberateError = e.toString().replaceFirst('Exception: ', '');
          _busy = false;
        });
      }
    }
  }

  void _showSettingsDialog() {
    final urlCtrl = TextEditingController(text: widget.service.baseUrl);
    final tokenCtrl = TextEditingController(text: widget.service.token);
    String? testResult;
    bool testing = false;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setDialogState) {
          return AlertDialog(
            backgroundColor: const Color(0xFF1E1320),
            title: const Row(
              children: [
                Icon(Icons.tune, color: kCouncilTeal, size: 20),
                SizedBox(width: 8),
                Text('Cognitive OS Settings', style: TextStyle(color: Colors.white, fontSize: 16)),
              ],
            ),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Server Endpoint',
                    style: TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 6),
                  TextField(
                    controller: urlCtrl,
                    style: const TextStyle(color: Colors.white, fontSize: 13),
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: Colors.black38,
                      hintText: 'http://127.0.0.1:8787',
                      hintStyle: const TextStyle(color: Colors.white24),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 6,
                    children: [
                      _presetUrlChip('127.0.0.1:8787', 'http://127.0.0.1:8787', urlCtrl, setDialogState),
                      _presetUrlChip('10.0.2.2:8787', 'http://10.0.2.2:8787', urlCtrl, setDialogState),
                      _presetUrlChip('localhost:8787', 'http://localhost:8787', urlCtrl, setDialogState),
                    ],
                  ),
                  const SizedBox(height: 14),
                  const Text(
                    'Token / Secret (Optional)',
                    style: TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 6),
                  TextField(
                    controller: tokenCtrl,
                    style: const TextStyle(color: Colors.white, fontSize: 13),
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: Colors.black38,
                      hintText: 'COUNCIL_TOKEN',
                      hintStyle: const TextStyle(color: Colors.white24),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                  ),
                  const SizedBox(height: 14),
                  OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: kCouncilTeal,
                      side: const BorderSide(color: kCouncilTeal),
                    ),
                    onPressed: testing
                        ? null
                        : () async {
                            setDialogState(() => testing = true);
                            final prevUrl = widget.service.baseUrl;
                            final prevToken = widget.service.token;
                            widget.service.baseUrl = urlCtrl.text.trim();
                            widget.service.token = tokenCtrl.text.trim();

                            final res = await widget.service.testConnection();
                            setDialogState(() {
                              testing = false;
                              testResult = res['message'] as String;
                            });

                            if (!(res['ok'] as bool)) {
                              widget.service.baseUrl = prevUrl;
                              widget.service.token = prevToken;
                            }
                          },
                    icon: testing
                        ? const SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: kCouncilTeal))
                        : const Icon(Icons.wifi_tethering, size: 16),
                    label: const Text('Test Connection'),
                  ),
                  if (testResult != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      testResult!,
                      style: TextStyle(
                        color: testResult!.contains('Connected') ? Colors.greenAccent : Colors.orangeAccent,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(ctx).pop(),
                child: const Text('Cancel', style: TextStyle(color: Colors.white54)),
              ),
              FilledButton(
                style: FilledButton.styleFrom(backgroundColor: kCouncilRed),
                onPressed: () async {
                  await widget.service.save(
                    url: urlCtrl.text.trim(),
                    secret: tokenCtrl.text.trim(),
                  );
                  if (ctx.mounted) Navigator.of(ctx).pop();
                  _checkStatus();
                  _loadCards();
                },
                child: const Text('Save'),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _presetUrlChip(String label, String url, TextEditingController ctrl, StateSetter setDialogState) {
    return ActionChip(
      label: Text(label, style: const TextStyle(fontSize: 10.5, color: Colors.white70)),
      backgroundColor: Colors.white10,
      onPressed: () {
        setDialogState(() => ctrl.text = url);
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0B0608),
      appBar: AppBar(
        backgroundColor: const Color(0xFF140B16),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Cognitive OS',
              style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold),
            ),
            Text(
              'The Tarot Council · 6 Thinking Engines',
              style: TextStyle(color: Colors.white.withOpacity(0.55), fontSize: 11),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: _connected ? 'Connected' : 'Offline',
            icon: _checkingHealth
                ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : Icon(
                    Icons.circle,
                    size: 14,
                    color: _connected ? const Color(0xFF4CAF50) : const Color(0xFFF44336),
                  ),
            onPressed: _checkStatus,
          ),
          IconButton(
            tooltip: 'Server Settings',
            icon: const Icon(Icons.settings_outlined, color: Colors.white70),
            onPressed: _showSettingsDialog,
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: kCouncilRed,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white54,
          tabs: [
            const Tab(text: 'Consult'),
            Tab(
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text('Decisions'),
                  if (widget.service.due.isNotEmpty) ...[
                    const SizedBox(width: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: kCouncilRed,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(
                        '${widget.service.due.length}',
                        style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const Tab(text: 'Engines'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _buildConsultTab(),
          _buildDecisionsTab(),
          _buildEnginesTab(),
        ],
      ),
    );
  }

  // ------------------------------------------------------------- TAB 1: CONSULT
  Widget _buildConsultTab() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (!_connected)
          Container(
            margin: const EdgeInsets.only(bottom: 16),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.amber.withOpacity(0.12),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: Colors.amber.withOpacity(0.4)),
            ),
            child: Row(
              children: [
                const Icon(Icons.warning_amber_rounded, color: Colors.amber, size: 20),
                const SizedBox(width: 10),
                const Expanded(
                  child: Text(
                    'Cannot reach Cognitive OS at the configured endpoint. Tap settings to configure or verify the PC is running.',
                    style: TextStyle(color: Colors.white70, fontSize: 12),
                  ),
                ),
                TextButton(
                  onPressed: _showSettingsDialog,
                  child: const Text('Configure', style: TextStyle(color: Colors.amber, fontSize: 12)),
                ),
              ],
            ),
          ),

        // Prompt header
        const Text(
          'What decision do you need to make?',
          style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 4),
        const Text(
          'Six independent algorithms will analyse this, attack each other\'s reasoning, and commit to one action with dissent left intact.',
          style: TextStyle(color: Colors.white60, fontSize: 12),
        ),
        const SizedBox(height: 12),

        // Question field
        TextField(
          controller: _questionCtrl,
          maxLines: 3,
          style: const TextStyle(color: Colors.white, fontSize: 14),
          decoration: InputDecoration(
            filled: true,
            fillColor: kCouncilDark,
            hintText: 'e.g. Should I accept the senior architect offer, or stay and lead the AI team?',
            hintStyle: const TextStyle(color: Colors.white24, fontSize: 13),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: BorderSide(color: Colors.white.withOpacity(0.1)),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: const BorderSide(color: kCouncilRed),
            ),
          ),
        ),
        const SizedBox(height: 10),

        // Context / facts field (optional)
        TextField(
          controller: _notesCtrl,
          maxLines: 2,
          style: const TextStyle(color: Colors.white, fontSize: 13),
          decoration: InputDecoration(
            filled: true,
            fillColor: kCouncilDark,
            hintText: 'Additional context or constraints (optional)...',
            hintStyle: const TextStyle(color: Colors.white24, fontSize: 12),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: BorderSide(color: Colors.white.withOpacity(0.1)),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: const BorderSide(color: kCouncilTeal),
            ),
          ),
        ),
        const SizedBox(height: 14),

        // Presets & Depth row
        Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Council Preset', style: TextStyle(color: Colors.white70, fontSize: 12, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 6),
                  DropdownButtonFormField<String>(
                    initialValue: _preset,
                    dropdownColor: const Color(0xFF1C1322),
                    style: const TextStyle(color: Colors.white, fontSize: 12.5),
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: kCouncilDark,
                      contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    items: const [
                      DropdownMenuItem(value: 'full', child: Text('Full (All 6 Minds)')),
                      DropdownMenuItem(value: 'strategy', child: Text('Strategy & Power')),
                      DropdownMenuItem(value: 'execution', child: Text('Execution & Speed')),
                      DropdownMenuItem(value: 'people', child: Text('Human Dynamics')),
                      DropdownMenuItem(value: 'life', child: Text('Life & Values')),
                    ],
                    onChanged: (v) {
                      if (v != null) setState(() => _preset = v);
                    },
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Reasoning Depth', style: TextStyle(color: Colors.white70, fontSize: 12, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 6),
                  DropdownButtonFormField<String>(
                    initialValue: _depth,
                    dropdownColor: const Color(0xFF1C1322),
                    style: const TextStyle(color: Colors.white, fontSize: 12.5),
                    decoration: InputDecoration(
                      filled: true,
                      fillColor: kCouncilDark,
                      contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    items: const [
                      DropdownMenuItem(value: 'quick', child: Text('Quick (~8 calls)')),
                      DropdownMenuItem(value: 'standard', child: Text('Standard (~20 calls)')),
                    ],
                    onChanged: (v) {
                      if (v != null) setState(() => _depth = v);
                    },
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 18),

        // Action button
        SizedBox(
          width: double.infinity,
          height: 48,
          child: FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: kCouncilRed,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
            ),
            onPressed: _busy ? null : _runDeliberation,
            icon: _busy
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.flash_on, size: 20),
            label: Text(
              _busy ? 'The Council is deliberating...' : 'Deliberate Decision',
              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
            ),
          ),
        ),

        if (_deliberateError != null) ...[
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.red.withOpacity(0.12),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: Colors.red.withOpacity(0.4)),
            ),
            child: Row(
              children: [
                const Icon(Icons.error_outline, color: Colors.redAccent, size: 20),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    _deliberateError!,
                    style: const TextStyle(color: Colors.white70, fontSize: 12),
                  ),
                ),
              ],
            ),
          ),
        ],

        // Deliberation result view
        if (_lastResult != null) ...[
          const SizedBox(height: 24),
          _buildResultCard(_lastResult!),
        ],
      ],
    );
  }

  Widget _buildResultCard(DeliberationResult res) {
    return Container(
      decoration: BoxDecoration(
        color: kCouncilDark,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: kCouncilRed.withOpacity(0.4)),
      ),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: kCouncilRed.withOpacity(0.2),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Text('RECOMMENDATION', style: TextStyle(color: kCouncilRed, fontSize: 11, fontWeight: FontWeight.w800)),
              ),
              const Spacer(),
              if (res.confidence.isNotEmpty)
                Text('Confidence: ${res.confidence}', style: const TextStyle(color: Colors.white54, fontSize: 11)),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            res.action,
            style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold, height: 1.3),
          ),
          if (res.firstAction.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              'First Step: ${res.firstAction}',
              style: const TextStyle(color: kCouncilTeal, fontSize: 13, fontWeight: FontWeight.w600),
            ),
          ],
          if (res.debateSummary.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Divider(color: Colors.white12),
            const SizedBox(height: 6),
            const Text('SYNTHESIS', style: TextStyle(color: Colors.white54, fontSize: 11, fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            Text(
              res.debateSummary,
              style: const TextStyle(color: Colors.white70, fontSize: 12.5, height: 1.4),
            ),
          ],
          if (res.minorityOpinions.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Divider(color: Colors.white12),
            const SizedBox(height: 6),
            const Text('DISSENT & MINORITY OPINIONS', style: TextStyle(color: kCouncilGold, fontSize: 11, fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            ...res.minorityOpinions.map(
              (m) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('${m.module.toUpperCase()}: ', style: const TextStyle(color: kCouncilGold, fontSize: 11.5, fontWeight: FontWeight.bold)),
                    Expanded(
                      child: Text(
                        '${m.position}${m.whenRight.isNotEmpty ? ' (Right if: ${m.whenRight})' : ''}',
                        style: const TextStyle(color: Colors.white70, fontSize: 11.5),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
          if (res.blindSpot.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              'Blind spot: ${res.blindSpot}',
              style: const TextStyle(color: Colors.orangeAccent, fontSize: 11.5, fontStyle: FontStyle.italic),
            ),
          ],
          if (res.prediction.isNotEmpty) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.04),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('FALSIFIABLE PREDICTION', style: TextStyle(color: Colors.white54, fontSize: 10, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 2),
                  Text(res.prediction, style: const TextStyle(color: Colors.white, fontSize: 12)),
                  const SizedBox(height: 4),
                  Text('Check-in scheduled in ${res.checkInDays} days.', style: const TextStyle(color: kCouncilTeal, fontSize: 11)),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  // ------------------------------------------------------------- TAB 2: DECISIONS
  Widget _buildDecisionsTab() {
    final filtered = _cards.where((c) {
      if (_cardFilter == 'due') return c.status == 'due';
      if (_cardFilter == 'open') return c.status == 'open';
      if (_cardFilter == 'resolved') return c.status == 'resolved';
      return true;
    }).toList();

    return Column(
      children: [
        // Filter bar
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 6),
          child: Row(
            children: [
              _filterChip('All (${_cards.length})', 'all'),
              const SizedBox(width: 8),
              _filterChip('Due (${_cards.where((c) => c.status == 'due').length})', 'due'),
              const SizedBox(width: 8),
              _filterChip('Open (${_cards.where((c) => c.status == 'open').length})', 'open'),
              const SizedBox(width: 8),
              _filterChip('Resolved (${_cards.where((c) => c.status == 'resolved').length})', 'resolved'),
            ],
          ),
        ),
        const Divider(color: Colors.white12),

        Expanded(
          child: _loadingCards
              ? const Center(child: CircularProgressIndicator(color: kCouncilRed))
              : filtered.isEmpty
                  ? Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.style_outlined, size: 48, color: Colors.white.withOpacity(0.2)),
                          const SizedBox(height: 10),
                          const Text(
                            'No decisions found in this view.',
                            style: TextStyle(color: Colors.white54, fontSize: 13),
                          ),
                          const SizedBox(height: 4),
                          const Text(
                            'Deliberate a new decision or change filters.',
                            style: TextStyle(color: Colors.white30, fontSize: 11),
                          ),
                        ],
                      ),
                    )
                  : RefreshIndicator(
                      color: kCouncilRed,
                      onRefresh: _loadCards,
                      child: ListView.separated(
                        padding: const EdgeInsets.all(16),
                        itemCount: filtered.length,
                        separatorBuilder: (_, _) => const SizedBox(height: 10),
                        itemBuilder: (ctx, i) => _decisionCardItem(filtered[i]),
                      ),
                    ),
        ),
      ],
    );
  }

  Widget _filterChip(String label, String value) {
    final active = _cardFilter == value;
    return InkWell(
      borderRadius: BorderRadius.circular(20),
      onTap: () => setState(() => _cardFilter = value),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(
          color: active ? kCouncilRed.withOpacity(0.2) : Colors.white10,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: active ? kCouncilRed : Colors.transparent),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: active ? Colors.white : Colors.white60,
            fontSize: 11.5,
            fontWeight: active ? FontWeight.bold : FontWeight.normal,
          ),
        ),
      ),
    );
  }

  Widget _decisionCardItem(DueDecision card) {
    Color badgeColor = Colors.grey;
    String badgeText = 'OPEN';
    if (card.status == 'due') {
      badgeColor = kCouncilGold;
      badgeText = card.overdueDays > 0 ? '${card.overdueDays}d OVERDUE' : 'DUE TODAY';
    } else if (card.status == 'resolved') {
      badgeColor = const Color(0xFF4CAF50);
      badgeText = 'RESOLVED';
    } else if (card.daysRemaining > 0) {
      badgeText = 'IN ${card.daysRemaining}d';
    }

    return Container(
      decoration: BoxDecoration(
        color: kCouncilDark,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: card.status == 'due' ? kCouncilGold.withOpacity(0.4) : Colors.white.withOpacity(0.08),
        ),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(10),
          onTap: () async {
            if (card.status == 'due') {
              await CouncilCheckinSheet.show(context, widget.service);
              _loadCards();
            } else {
              _showDecisionDetail(card);
            }
          },
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: badgeColor.withOpacity(0.18),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        badgeText,
                        style: TextStyle(color: badgeColor, fontSize: 9.5, fontWeight: FontWeight.bold),
                      ),
                    ),
                    const Spacer(),
                    Text(
                      '${card.createdAt.year}-${card.createdAt.month.toString().padLeft(2, '0')}-${card.createdAt.day.toString().padLeft(2, '0')}',
                      style: const TextStyle(color: Colors.white38, fontSize: 11),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  card.question,
                  style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w600),
                ),
                if (card.recommendation.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    'Recommendation: ${card.recommendation}',
                    style: const TextStyle(color: kCouncilTeal, fontSize: 12),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
                if (card.prediction.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    'Prediction: ${card.prediction}',
                    style: const TextStyle(color: Colors.white54, fontSize: 11),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
                if (card.status == 'due') ...[
                  const SizedBox(height: 8),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      Text(
                        'Tap to record what happened →',
                        style: TextStyle(color: kCouncilGold.withOpacity(0.9), fontSize: 11, fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _showDecisionDetail(DueDecision card) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF18101C),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
      builder: (ctx) => Padding(
        padding: const EdgeInsets.all(20),
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(card.question, style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
              const SizedBox(height: 12),
              if (card.recommendation.isNotEmpty) ...[
                const Text('RECOMMENDATION', style: TextStyle(color: kCouncilTeal, fontSize: 11, fontWeight: FontWeight.bold)),
                const SizedBox(height: 2),
                Text(card.recommendation, style: const TextStyle(color: Colors.white70, fontSize: 13)),
                const SizedBox(height: 12),
              ],
              if (card.prediction.isNotEmpty) ...[
                const Text('EXPECTED OUTCOME', style: TextStyle(color: Colors.white54, fontSize: 11, fontWeight: FontWeight.bold)),
                const SizedBox(height: 2),
                Text(card.prediction, style: const TextStyle(color: Colors.white70, fontSize: 13)),
                const SizedBox(height: 12),
              ],
              if (card.actualOutcome != null) ...[
                const Text('ACTUAL OUTCOME RECORDED', style: TextStyle(color: Colors.greenAccent, fontSize: 11, fontWeight: FontWeight.bold)),
                const SizedBox(height: 2),
                Text(card.actualOutcome!, style: const TextStyle(color: Colors.white, fontSize: 13)),
                const SizedBox(height: 12),
              ],
              if (card.chose != null) ...[
                const Text('ACTION CHOSEN', style: TextStyle(color: Colors.white54, fontSize: 11, fontWeight: FontWeight.bold)),
                const SizedBox(height: 2),
                Text(card.chose!, style: const TextStyle(color: Colors.white, fontSize: 13)),
                const SizedBox(height: 12),
              ],
              if (card.notes != null && card.notes!.isNotEmpty) ...[
                const Text('NOTES', style: TextStyle(color: Colors.white54, fontSize: 11, fontWeight: FontWeight.bold)),
                const SizedBox(height: 2),
                Text(card.notes!, style: const TextStyle(color: Colors.white70, fontSize: 12)),
              ],
            ],
          ),
        ),
      ),
    );
  }

  // ------------------------------------------------------------- TAB 3: ENGINES
  Widget _buildEnginesTab() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text(
          'The Six Reasoning Engines',
          style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 4),
        const Text(
          'Programs that execute structured stages over your question, validating formal artifacts in code rather than persona prompts.',
          style: TextStyle(color: Colors.white60, fontSize: 12),
        ),
        const SizedBox(height: 16),
        ..._engineInfo.entries.map((e) {
          final id = e.key;
          final info = e.value;
          return Container(
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: kCouncilDark,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: Colors.white.withOpacity(0.08)),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                CircleAvatar(
                  radius: 18,
                  backgroundColor: kCouncilRed.withOpacity(0.18),
                  child: Text(
                    id.substring(0, 1).toUpperCase(),
                    style: const TextStyle(color: kCouncilRed, fontWeight: FontWeight.bold),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Text(
                            id.toUpperCase(),
                            style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.bold),
                          ),
                          const SizedBox(width: 6),
                          Text(
                            '(${info['skin']})',
                            style: TextStyle(color: Colors.white.withOpacity(0.4), fontSize: 11),
                          ),
                        ],
                      ),
                      const SizedBox(height: 2),
                      Text(
                        info['focus']!,
                        style: const TextStyle(color: kCouncilTeal, fontSize: 11.5),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        'Enforced: ${info['tool']}',
                        style: const TextStyle(color: Colors.white54, fontSize: 11),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          );
        }),
      ],
    );
  }
}
