import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';

import 'screens/facts_screen.dart';
import 'screens/fake_call_sheet.dart';
import 'screens/incoming_call_screen.dart';
import 'screens/library_screen.dart';
import 'screens/market_alerts_sheet.dart';
import 'screens/today_screen.dart';
import 'services/deck_db.dart';
import 'services/digest_settings.dart';
import 'services/fake_call_service.dart';
import 'services/jarvis_brain.dart';
import 'services/reminder_service.dart';
import 'services/stock_alert_service.dart';
import 'services/voice_service.dart';
import 'widgets/mascot.dart';

final deckDb = DeckDb();
// One instance app-wide: reminders and the daily digest share a notification
// channel setup, so permission is only ever requested once.
final reminders = ReminderService();
final digest = DigestSettings(reminders);
final fakeCall = FakeCallService(reminders);
final stockAlerts = StockAlertService(reminders);

/// Lets a notification tap open a screen without a BuildContext to hand.
final navigatorKey = GlobalKey<NavigatorState>();

/// Answering the fake call means tapping its notification, which can happen
/// while the app is backgrounded or not running at all.
void _openFakeCall() {
  fakeCall.cancel();
  navigatorKey.currentState?.push(
    MaterialPageRoute(
      fullscreenDialog: true,
      builder: (_) => IncomingCallScreen(
        name: fakeCall.name,
        number: fakeCall.number,
      ),
    ),
  );
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  try {
    await dotenv.load(fileName: '.env');
  } catch (_) {
    // .env missing — app still runs but Gemini will ask for a key.
  }
  try {
    await deckDb.init();
  } catch (_) {
    // No deck yet — the Today tab shows its empty state rather than crashing.
  }
  // Must be set before init(), which is what registers the tap handler.
  reminders.onTapped = (payload) {
    if (payload == FakeCallService.payload) _openFakeCall();
  };
  try {
    await fakeCall.load();
    await digest.load();
    // Re-arm on every launch so the repeating text reflects today's counts.
    await digest.apply(deckDb);
  } catch (_) {
    // Notification permission refused or unavailable — the app is still usable.
  }
  try {
    // Market alerts from the StockSeer box. Failing here must not block launch:
    // the PC is often off, and Jarvis has nothing to do with markets otherwise.
    await stockAlerts.init();
    unawaited(stockAlerts.syncIpoCalendar());
  } catch (_) {
    // No PC on the network, or alerts disabled. Everything else still works.
  }
  runApp(const JarvisApp());
}

class JarvisApp extends StatelessWidget {
  const JarvisApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Jarvis',
      navigatorKey: navigatorKey,
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
      home: const RootShell(),
    );
  }
}

/// Two places to be: talk to Jarvis, or work through what today asks of you.
class RootShell extends StatefulWidget {
  const RootShell({super.key});

  @override
  State<RootShell> createState() => _RootShellState();
}

class _RootShellState extends State<RootShell> {
  int _tab = 0;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // IndexedStack so the mascot's voice session and the day's list both
      // survive a tab switch instead of rebuilding from scratch.
      body: IndexedStack(
        index: _tab,
        children: [
          const JarvisHome(),
          SafeArea(child: TodayScreen(deck: deckDb, digest: digest)),
          SafeArea(child: FactsScreen(deck: deckDb)),
          SafeArea(child: LibraryScreen(deck: deckDb)),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _tab,
        onDestinationSelected: (i) => setState(() => _tab = i),
        height: 64,
        backgroundColor: const Color(0xFF120B14),
        indicatorColor: const Color(0xFFE74848).withOpacity(0.22),
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.graphic_eq, color: Colors.white54),
            selectedIcon: Icon(Icons.graphic_eq, color: Color(0xFFE74848)),
            label: 'Jarvis',
          ),
          NavigationDestination(
            icon: Icon(Icons.check_circle_outline, color: Colors.white54),
            selectedIcon: Icon(Icons.check_circle, color: Color(0xFFE74848)),
            label: 'Today',
          ),
          NavigationDestination(
            icon: Icon(Icons.lightbulb_outline, color: Colors.white54),
            selectedIcon: Icon(Icons.lightbulb, color: Color(0xFF00E5C9)),
            label: 'Facts',
          ),
          NavigationDestination(
            icon: Icon(Icons.grid_view_outlined, color: Colors.white54),
            selectedIcon: Icon(Icons.grid_view, color: Color(0xFFE74848)),
            label: 'Library',
          ),
        ],
      ),
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
  final _brain = JarvisBrain(deck: deckDb, reminders: reminders);

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
                // Arming the fake call. Long-pressing the mascot looks like
                // idly holding the phone, and deliberately shows no dialog or
                // snackbar -- a visible confirmation in front of the person
                // you're escaping would defeat the entire feature. The single
                // haptic tick is the only feedback.
                GestureDetector(
                  onLongPress: () async {
                    // Belt and braces: arm() already swallows its own failures,
                    // but an exception escaping an async gesture callback has
                    // no handler above it and takes the app down.
                    try {
                      final at = await fakeCall.arm();
                      await HapticFeedback.mediumImpact();
                      // A second tick means it didn't take, readable in a pocket
                      // without anything appearing on screen.
                      if (at == null) {
                        await Future<void>.delayed(
                            const Duration(milliseconds: 140));
                        await HapticFeedback.mediumImpact();
                      }
                    } catch (e) {
                      debugPrint('fake call arm failed: $e');
                    }
                  },
                  child: Mascot(state: _state, size: mascotSize),
                ),
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
          // Setting the caller up is the one part that needn't hide, but it
          // still lives behind a long-press so no control on screen hints at
          // what the mascot gesture does.
          GestureDetector(
            onLongPress: () => FakeCallSheet.show(context, fakeCall),
            child: const Text(
              'JARVIS',
              style: TextStyle(
                fontSize: 18,
                letterSpacing: 4,
                fontWeight: FontWeight.w700,
                color: Color(0xFFE74848),
              ),
            ),
          ),
          const Spacer(),
          IconButton(
            tooltip: 'Market alerts',
            onPressed: () => MarketAlertsSheet.show(context, stockAlerts),
            icon: const Icon(Icons.candlestick_chart_outlined,
                color: Colors.white70),
          ),
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
