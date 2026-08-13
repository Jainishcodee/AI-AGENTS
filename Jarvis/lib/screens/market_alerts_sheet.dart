import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../services/stock_alert_service.dart';

/// Where the StockSeer link is configured.
///
/// The one setting that actually matters is the PC's address, and getting it
/// wrong is silent -- alerts simply never arrive. So this screen leads with a
/// connection test rather than burying it, and a test alert you can feel.
class MarketAlertsSheet extends StatefulWidget {
  const MarketAlertsSheet({super.key, required this.service});

  final StockAlertService service;

  static Future<void> show(BuildContext context, StockAlertService s) {
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF18101A),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
      ),
      builder: (_) => Padding(
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom,
        ),
        child: MarketAlertsSheet(service: s),
      ),
    );
  }

  @override
  State<MarketAlertsSheet> createState() => _MarketAlertsSheetState();
}

class _MarketAlertsSheetState extends State<MarketAlertsSheet> {
  late final TextEditingController _url =
      TextEditingController(text: widget.service.baseUrl);
  late bool _enabled = widget.service.enabled;

  String? _status;
  bool _busy = false;
  List<Map<String, dynamic>> _calendar = const [];

  @override
  void initState() {
    super.initState();
    _loadCalendar();
  }

  @override
  void dispose() {
    _url.dispose();
    super.dispose();
  }

  Future<void> _run(String label, Future<String> Function() action) async {
    setState(() {
      _busy = true;
      _status = '$label…';
    });
    String result;
    try {
      result = await action();
    } catch (e) {
      result = 'Failed: $e';
    }
    if (mounted) {
      setState(() {
        _busy = false;
        _status = result;
      });
    }
  }

  Future<void> _save() => _run('Saving', () async {
        await widget.service.configure(url: _url.text, on: _enabled);
        final msg = await widget.service.testConnection();
        _loadCalendar();
        return msg;
      });

  Future<void> _testAlert() => _run('Sending', () async {
        await widget.service.configure(url: _url.text, on: _enabled);
        final res = await http
            .post(Uri.parse('${widget.service.baseUrl}/api/notify/test'))
            .timeout(const Duration(seconds: 8));
        if (res.statusCode != 200) return 'PC returned HTTP ${res.statusCode}';
        // The alert is queued on the PC; the normal poll delivers it, which
        // also proves the real delivery path rather than a shortcut.
        await widget.service.poll();
        return 'Sent. Your phone should buzz within a moment.';
      });

  Future<void> _syncCalendar() => _run('Syncing', () async {
        final n = await widget.service.syncIpoCalendar();
        _loadCalendar();
        return n == 0
            ? 'Nothing new to schedule.'
            : 'Scheduled $n IPO alarm(s) on this phone.';
      });

  Future<void> _loadCalendar() async {
    try {
      final res = await http
          .get(Uri.parse('${widget.service.baseUrl}/api/ipo/calendar'))
          .timeout(const Duration(seconds: 8));
      if (res.statusCode != 200) return;
      final list = (jsonDecode(res.body) as List).cast<Map<String, dynamic>>();
      if (mounted) setState(() => _calendar = list);
    } catch (_) {
      // PC unreachable; the section just stays empty.
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 18, 20, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Market alerts',
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: Colors.white,
              ),
            ),
            const SizedBox(height: 6),
            const Text(
              'IPO deadlines and listing-day alerts from StockSeer on your PC. '
              'Both devices need to be on the same wifi.',
              style: TextStyle(color: Colors.white54, fontSize: 13),
            ),
            const SizedBox(height: 18),

            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: _enabled,
              onChanged: (v) => setState(() => _enabled = v),
              title: const Text('Alerts on',
                  style: TextStyle(color: Colors.white)),
              subtitle: const Text('Vibrates for IPO deadlines and stops',
                  style: TextStyle(color: Colors.white38, fontSize: 12)),
            ),
            const SizedBox(height: 8),

            TextField(
              controller: _url,
              keyboardType: TextInputType.url,
              autocorrect: false,
              style: const TextStyle(color: Colors.white),
              decoration: const InputDecoration(
                labelText: "PC address",
                hintText: 'http://192.168.1.5:8765',
                helperText: 'Find it with: ipconfig | findstr IPv4',
                helperStyle: TextStyle(color: Colors.white38, fontSize: 11),
              ),
            ),
            const SizedBox(height: 16),

            Row(
              children: [
                Expanded(
                  child: FilledButton(
                    onPressed: _busy ? null : _save,
                    child: const Text('Save & test'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton(
                    onPressed: _busy ? null : _testAlert,
                    child: const Text('Buzz me'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _busy ? null : _syncCalendar,
                icon: const Icon(Icons.event_available, size: 18),
                label: const Text('Schedule IPO alarms on this phone'),
              ),
            ),
            const SizedBox(height: 6),
            const Text(
              'Scheduled alarms fire even with Jarvis closed and the PC off. '
              'Listing-day price alerts need Jarvis open.',
              style: TextStyle(color: Colors.white38, fontSize: 11),
            ),

            if (_status != null) ...[
              const SizedBox(height: 16),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.06),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Row(
                  children: [
                    if (_busy)
                      const SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                    if (_busy) const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        _status!,
                        style: const TextStyle(
                            color: Colors.white70, fontSize: 12.5),
                      ),
                    ),
                  ],
                ),
              ),
            ],

            if (_calendar.isNotEmpty) ...[
              const SizedBox(height: 22),
              const Text('Coming up',
                  style: TextStyle(color: Colors.white70, fontSize: 13)),
              const SizedBox(height: 8),
              for (final e in _calendar) _CalendarRow(event: e),
              const SizedBox(height: 8),
              const Text(
                'Allotment is where the edge is: mainboard issues averaged '
                '+13.5% from issue price to listing across 176 IPOs. Buying at '
                'the listing open is a coin flip.',
                style: TextStyle(color: Colors.white38, fontSize: 11),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _CalendarRow extends StatelessWidget {
  const _CalendarRow({required this.event});

  final Map<String, dynamic> event;

  @override
  Widget build(BuildContext context) {
    final ipo = (event['ipo'] as Map).cast<String, dynamic>();
    final urgency = event['urgency'] as String? ?? 'info';
    final colour = switch (urgency) {
      'critical' => const Color(0xFFD03B3B),
      'act' => const Color(0xFFFAB219),
      _ => Colors.white38,
    };
    final band = (ipo['price_range'] as String?)?.isNotEmpty == true
        ? ipo['price_range'] as String
        : 'Rs.${ipo['issue_price']}';

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 3,
            height: 34,
            margin: const EdgeInsets.only(right: 10, top: 2),
            decoration: BoxDecoration(
              color: colour,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      ipo['symbol'] as String? ?? '?',
                      style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                          fontSize: 13),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      (event['kind'] as String? ?? '').replaceAll('_', ' '),
                      style: TextStyle(color: colour, fontSize: 11),
                    ),
                    const Spacer(),
                    Text(
                      (ipo['is_sme'] as bool? ?? false) ? 'SME' : 'MAIN',
                      style: const TextStyle(
                          color: Colors.white24, fontSize: 10),
                    ),
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  '${ipo['company']} · $band',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white38, fontSize: 11.5),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
