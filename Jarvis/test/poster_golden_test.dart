import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis/models/reel_card.dart';
import 'package:jarvis/widgets/wanted_poster.dart';

ReelCard _card({
  required String id,
  required String title,
  required Horizon horizon,
  String domain = 'health',
  int progress = 0,
}) =>
    ReelCard(
      id: id,
      kind: CardKind.task,
      title: title,
      summary: 'Pair specific foods to target bloating, low energy and brain fog.',
      domain: domain,
      tags: const ['nutrition'],
      url: 'https://example.com',
      owner: 'endbackpain',
      collection: '',
      evidence: '',
      confidence: 'high',
      steps: const ['Banana with black pepper', 'Watermelon with salt'],
      horizon: horizon,
      progress: progress,
    );

void main() {
  testWidgets('wanted posters', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1120, 520));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final cards = [
      _card(id: 'DOdkYPJgXV-', title: 'Try five health-boosting food combos', horizon: Horizon.today),
      _card(id: 'DXqZ11aaBcd', title: 'Build a two-week skincare routine', horizon: Horizon.shortTerm, domain: 'skincare'),
      _card(id: 'DKl0092zzQw', title: 'Learn conversational Japanese', horizon: Horizon.longTerm, domain: 'career', progress: 40),
    ];

    await tester.pumpWidget(
      MaterialApp(
        debugShowCheckedModeBanner: false,
        home: ColoredBox(
          color: const Color(0xFF0B0608),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                for (var i = 0; i < cards.length; i++)
                  Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 8),
                      child: WantedPoster(
                        card: cards[i],
                        done: i == 1,
                        onToggle: () {},
                        onSnooze: () {},
                        onProgress: (_) {},
                        onOpenReel: () {},
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    await expectLater(
      find.byType(MaterialApp),
      matchesGoldenFile('goldens/wanted_posters.png'),
    );
  });
}
