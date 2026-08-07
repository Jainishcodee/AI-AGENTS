import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// The ringing screen. Deliberately plain and system-like -- none of the app's
/// red-and-teal styling -- because anything recognisably "Jarvis" would give
/// the game away to whoever glances over.
class IncomingCallScreen extends StatefulWidget {
  const IncomingCallScreen({
    super.key,
    required this.name,
    required this.number,
    this.onEnded,
  });

  final String name;
  final String number;
  final VoidCallback? onEnded;

  @override
  State<IncomingCallScreen> createState() => _IncomingCallScreenState();
}

class _IncomingCallScreenState extends State<IncomingCallScreen> {
  Timer? _buzz;
  Timer? _tick;
  bool _answered = false;
  int _seconds = 0;

  @override
  void initState() {
    super.initState();
    // The notification channel supplies the ringtone; this adds the pulse so
    // the phone still reads as ringing once the screen is open and the
    // notification has stopped being the thing making noise.
    _buzz = Timer.periodic(const Duration(milliseconds: 900), (_) {
      HapticFeedback.heavyImpact();
    });
  }

  @override
  void dispose() {
    _buzz?.cancel();
    _tick?.cancel();
    super.dispose();
  }

  void _answer() {
    _buzz?.cancel();
    setState(() => _answered = true);
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() => _seconds++);
    });
  }

  void _end() {
    _buzz?.cancel();
    _tick?.cancel();
    widget.onEnded?.call();
    if (mounted) Navigator.of(context).maybePop();
  }

  String get _elapsed {
    final m = (_seconds ~/ 60).toString().padLeft(2, '0');
    final s = (_seconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  @override
  Widget build(BuildContext context) {
    final initial = widget.name.trim().isEmpty
        ? '?'
        : widget.name.trim()[0].toUpperCase();

    // Back must not dismiss a ringing call -- a stray swipe mid-escape would
    // drop you back into the app in front of the person you're avoiding.
    return PopScope(
      canPop: false,
      child: Scaffold(
        backgroundColor: const Color(0xFF101014),
        body: SafeArea(
          child: Column(
            children: [
              const Spacer(flex: 2),
              Text(
                _answered ? _elapsed : 'Incoming call',
                style: const TextStyle(
                  color: Colors.white54,
                  fontSize: 16,
                  letterSpacing: 1.5,
                ),
              ),
              const SizedBox(height: 28),
              CircleAvatar(
                radius: 56,
                backgroundColor: const Color(0xFF2E2E36),
                child: Text(
                  initial,
                  style: const TextStyle(
                    fontSize: 44,
                    color: Colors.white,
                    fontWeight: FontWeight.w400,
                  ),
                ),
              ),
              const SizedBox(height: 24),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                child: Text(
                  widget.name,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    fontSize: 32,
                    color: Colors.white,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                widget.number,
                style: const TextStyle(color: Colors.white60, fontSize: 16),
              ),
              const Spacer(flex: 3),
              Padding(
                padding: const EdgeInsets.only(bottom: 48),
                child: _answered
                    ? _CallButton(
                        color: const Color(0xFFE0342B),
                        icon: Icons.call_end,
                        label: 'End',
                        onTap: _end,
                      )
                    : Row(
                        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                        children: [
                          _CallButton(
                            color: const Color(0xFFE0342B),
                            icon: Icons.call_end,
                            label: 'Decline',
                            onTap: _end,
                          ),
                          _CallButton(
                            color: const Color(0xFF2BB673),
                            icon: Icons.call,
                            label: 'Accept',
                            onTap: _answer,
                          ),
                        ],
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CallButton extends StatelessWidget {
  const _CallButton({
    required this.color,
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final Color color;
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Material(
          color: color,
          shape: const CircleBorder(),
          child: InkWell(
            customBorder: const CircleBorder(),
            onTap: onTap,
            child: SizedBox(
              width: 72,
              height: 72,
              child: Icon(icon, color: Colors.white, size: 30),
            ),
          ),
        ),
        const SizedBox(height: 10),
        Text(label, style: const TextStyle(color: Colors.white70, fontSize: 13)),
      ],
    );
  }
}
