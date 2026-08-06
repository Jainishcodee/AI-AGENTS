import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis/widgets/mascot.dart';

/// Renders Gehrman in all four states so the aura, ring and framing can be
/// checked without a phone. The animations repeat forever, so this pumps fixed
/// durations rather than settling.
void main() {
  testWidgets('mascot states', (tester) async {
    await tester.binding.setSurfaceSize(const Size(900, 340));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      const MaterialApp(
        debugShowCheckedModeBanner: false,
        home: ColoredBox(
          color: Color(0xFF0B0608),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              Mascot(state: MascotState.idle, size: 190),
              Mascot(state: MascotState.listening, size: 190),
              Mascot(state: MascotState.thinking, size: 190),
              Mascot(state: MascotState.talking, size: 190),
            ],
          ),
        ),
      ),
    );

    // Asset images resolve asynchronously; force them in before capturing.
    await tester.runAsync(() async {
      for (final e in find.byType(Image).evaluate()) {
        await precacheImage((e.widget as Image).image, e);
      }
    });
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 450));

    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/mascot_states.png'),
    );
  });
}
