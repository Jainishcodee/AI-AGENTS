import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

import 'services/jarvis_brain.dart';
import 'services/voice_service.dart';
import 'widgets/mascot.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  try {
    await dotenv.load(fileName: '.env');
  } catch (_) {
    // .env missing — app still runs but Gemini will ask for a key.
  }
  runApp(const JarvisApp());
}

class JarvisApp extends StatelessWidget {
  const JarvisApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Jarvis',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0B0608),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFFE74848),
          secondary: Color(0xFF00E5C9),
          surface: Color(0xFF18101A),
        ),
        useMaterial3: true,
      ),
      home: const JarvisHome(),
    );
  }
}

class JarvisHome extends StatefulWidget {
  const JarvisHome({super.key});

  @override
  State<JarvisHome> createState() => _JarvisHomeState();
}

class _JarvisHomeState extends State<JarvisHome> {
  final _voice = VoiceService();
  final _brain = JarvisBrain();

  MascotState _state = MascotState.idle;
  String _chatLine = "Tap the mic and talk to me.";
  String _lastUser = "";
  String _lastStatus = "";
  bool _booting = true;

  @override
  void initState() {
    super.initState();
    _boot();
  }

  Future<void> _boot() async {
    await _voice.init();
    await _brain.init();
    if (!mounted) return;
    setState(() => _booting = false);
    final name = dotenv.env['USER_NAME'] ?? '';
    final greet = name.isEmpty ? "Jarvis online." : "Welcome back, $name.";
    setState(() => _state = MascotState.talking);
    await _voice.speak(greet);
    if (mounted) setState(() => _state = MascotState.idle);
  }

  Future<void> _onMicPressed() async {
    if (_booting) return;

    if (_state == MascotState.talking) {
      await _voice.stop();
      setState(() => _state = MascotState.idle);
      return;
    }
    if (_voice.isListening) {
      await _voice.stopListening();
      setState(() => _state = MascotState.idle);
      return;
    }

    setState(() {
      _state = MascotState.listening;
      _chatLine = "Listening...";
      _lastUser = "";
    });

    final ok = await _voice.listen(
      onPartial: (t) {
        if (mounted) setState(() => _lastUser = t);
      },
      onResult: (text) async {
        await _voice.stopListening();
        if (!mounted) return;
        setState(() {
          _state = MascotState.thinking;
          _lastUser = text;
          _chatLine = "Thinking...";
        });

        final reply = await _brain.handle(text);
        if (!mounted) return;
        setState(() {
          _state = MascotState.talking;
          _chatLine = reply.spokenText;
          _lastStatus = reply.statusLine ?? "";
        });
        await _voice.speak(reply.spokenText);
        if (!mounted) return;
        setState(() => _state = MascotState.idle);
      },
    );

    if (!ok && mounted) {
      setState(() {
        _state = MascotState.idle;
        _chatLine = "Microphone permission denied or unavailable.";
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final mascotSize = math.min(size.width * 0.6, 260.0);
    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: [
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: RadialGradient(
                    center: const Alignment(0, -0.3),
                    radius: 1.1,
                    colors: [
                      const Color(0xFF2A0F12),
                      Colors.black,
                    ],
                  ),
                ),
              ),
            ),
            Column(
              children: [
                _topBar(),
                const Spacer(),
                Mascot(state: _state, size: mascotSize),
                const SizedBox(height: 24),
                _stateChip(),
                const Spacer(),
                _chatCard(),
                const SizedBox(height: 24),
                _micButton(),
                const SizedBox(height: 36),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _topBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 0),
      child: Row(
        children: [
          const Text(
            'JARVIS',
            style: TextStyle(
              fontSize: 18,
              letterSpacing: 4,
              fontWeight: FontWeight.w700,
              color: Color(0xFFE74848),
            ),
          ),
          const Spacer(),
          IconButton(
            tooltip: 'Reset chat',
            onPressed: () {
              _brain.gemini.resetConversation();
              setState(() {
                _chatLine = "Conversation cleared.";
                _lastUser = "";
                _lastStatus = "";
              });
            },
            icon: const Icon(Icons.refresh, color: Colors.white70),
          ),
        ],
      ),
    );
  }

  Widget _stateChip() {
    final (label, color) = switch (_state) {
      MascotState.idle => ("READY", const Color(0xFF7A7A7A)),
      MascotState.listening => ("LISTENING", const Color(0xFF00E5C9)),
      MascotState.thinking => ("THINKING", const Color(0xFFFFB347)),
      MascotState.talking => ("SPEAKING", const Color(0xFFE74848)),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
      decoration: BoxDecoration(
        color: color.withOpacity(0.15),
        border: Border.all(color: color.withOpacity(0.6)),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          letterSpacing: 2.5,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }

  Widget _chatCard() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 18),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF18101A).withOpacity(0.85),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: Colors.white.withOpacity(0.08)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (_lastUser.isNotEmpty) ...[
              Text(
                'YOU',
                style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 2,
                  color: Colors.white.withOpacity(0.55),
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                _lastUser,
                style: const TextStyle(color: Colors.white70, fontSize: 14),
              ),
              const SizedBox(height: 12),
            ],
            Text(
              'JARVIS',
              style: TextStyle(
                fontSize: 10,
                letterSpacing: 2,
                color: const Color(0xFFE74848).withOpacity(0.9),
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              _chatLine,
              style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.35),
            ),
            if (_lastStatus.isNotEmpty) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: const Color(0xFF00E5C9).withOpacity(0.15),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  _lastStatus,
                  style: const TextStyle(
                    color: Color(0xFF00E5C9),
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _micButton() {
    final isActive = _state == MascotState.listening;
    return GestureDetector(
      onTap: _onMicPressed,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 250),
        width: 86,
        height: 86,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: isActive ? const Color(0xFF00E5C9) : const Color(0xFFE74848),
          boxShadow: [
            BoxShadow(
              color: (isActive
                      ? const Color(0xFF00E5C9)
                      : const Color(0xFFE74848))
                  .withOpacity(0.55),
              blurRadius: 28,
              spreadRadius: 4,
            ),
          ],
        ),
        child: Icon(
          isActive ? Icons.stop_rounded : Icons.mic,
          color: Colors.white,
          size: 38,
        ),
      ),
    );
  }
}
