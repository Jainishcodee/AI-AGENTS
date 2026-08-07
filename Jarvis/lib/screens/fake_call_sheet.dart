import 'package:flutter/material.dart';

import '../services/fake_call_service.dart';

/// Where the fake caller is set up, ahead of time.
///
/// Configuring is the one part that doesn't need hiding -- you do it long
/// before you need it. Only the trigger has to be invisible.
class FakeCallSheet extends StatefulWidget {
  const FakeCallSheet({super.key, required this.service});

  final FakeCallService service;

  static Future<void> show(BuildContext context, FakeCallService s) {
    return showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF18101A),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
      ),
      builder: (_) => Padding(
        // Keeps the fields above the keyboard.
        padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom,
        ),
        child: FakeCallSheet(service: s),
      ),
    );
  }

  @override
  State<FakeCallSheet> createState() => _FakeCallSheetState();
}

class _FakeCallSheetState extends State<FakeCallSheet> {
  late final TextEditingController _name =
      TextEditingController(text: widget.service.name);
  late final TextEditingController _number =
      TextEditingController(text: widget.service.number);
  late int _delay = widget.service.delaySecs;

  static const _delays = [30, 60, 120, 300, 600];

  @override
  void dispose() {
    _name.dispose();
    _number.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    await widget.service.save(
      name: _name.text,
      number: _number.text,
      delaySecs: _delay,
    );
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 18, 20, 24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Fake call',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w700,
              color: Colors.white,
            ),
          ),
          const SizedBox(height: 6),
          const Text(
            'Long-press the mascot to arm it. Nothing shows on screen.',
            style: TextStyle(color: Colors.white54, fontSize: 13),
          ),
          const SizedBox(height: 18),
          TextField(
            controller: _name,
            style: const TextStyle(color: Colors.white),
            decoration: const InputDecoration(
              labelText: 'Caller name',
              hintText: 'Mom',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _number,
            keyboardType: TextInputType.phone,
            style: const TextStyle(color: Colors.white),
            decoration: const InputDecoration(labelText: 'Number'),
          ),
          const SizedBox(height: 20),
          const Text('Rings after', style: TextStyle(color: Colors.white70)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            children: [
              for (final d in _delays)
                ChoiceChip(
                  label: Text(widget.service.prettyDelay(d)),
                  selected: _delay == d,
                  onSelected: (_) => setState(() => _delay = d),
                ),
            ],
          ),
          const SizedBox(height: 22),
          SizedBox(
            width: double.infinity,
            child: FilledButton(onPressed: _save, child: const Text('Save')),
          ),
        ],
      ),
    );
  }
}
