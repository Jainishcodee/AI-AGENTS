import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis/widgets/pirate_bits.dart';

/// Renders the hand-painted quest-board art so it can be eyeballed without a
/// device. Text renders as blocks here (no real font in the test harness) —
/// what this is checking is the painting and the layout, not the copy.
void main() {
  testWidgets('quest board art', (tester) async {
    await tester.binding.setSurfaceSize(const Size(420, 620));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      MaterialApp(
        debugShowCheckedModeBanner: false,
        home: ColoredBox(
          color: const Color(0xFF0B0608),
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: const [
                    StrawHat(size: 54),
                    SizedBox(width: 16),
                    StrawHat(size: 92),
                  ],
                ),
                const SizedBox(height: 24),
                const PosterRule(),
                const SizedBox(height: 24),
                Row(
                  children: const [
                    JollyRogerCheck(done: false, colour: kQuestRed, size: 34),
                    SizedBox(width: 14),
                    JollyRogerCheck(done: true, colour: kQuestRed, size: 34),
                    SizedBox(width: 14),
                    JollyRogerCheck(done: true, colour: kStraw, size: 34),
                    SizedBox(width: 14),
                    JollyRogerCheck(done: true, colour: kLogPose, size: 34),
                  ],
                ),
                const SizedBox(height: 28),
                const ClearedStamp(),
                const SizedBox(height: 28),
                Container(
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: kDeck,
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(color: kStrawDeep),
                  ),
                  child: LogPose(value: 40, onAdvance: () {}),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/quest_board_art.png'),
    );
  });
}
