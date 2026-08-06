import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis/models/reel_card.dart';
import 'package:jarvis/widgets/wanted_poster.dart';

ReelCard _fact(String id, String domain) => ReelCard(
      id: id,
      kind: CardKind.fact,
      title: 'Sunk cost fallacy',
      summary: 'Past spend is not a reason to keep going.',
      domain: domain,
      tags: const ['decisions'],
      url: 'https://example.com',
      owner: 'nathanbarry',
      collection: '',
      evidence: '',
      confidence: 'high',
      claim: 'Money already spent should never justify spending more.',
      why: 'The cost is gone either way; only the future return is still a choice.',
      applicability: 'Deciding whether to abandon a project you have poured months into.',
    );

ReelCard _task(String id, String domain) => ReelCard(
      id: id,
      kind: CardKind.task,
      title: 'Build a two-week skincare routine',
      summary: 'Layer actives on alternating nights.',
      domain: domain,
      tags: const [],
      url: '',
      owner: 'skinbyaz',
      collection: '',
      evidence: '',
      confidence: 'high',
      horizon: Horizon.shortTerm,
    );

void main() {
  testWidgets('log card and library tiles', (tester) async {
    await tester.binding.setSurfaceSize(const Size(820, 700));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      MaterialApp(
        debugShowCheckedModeBanner: false,
        home: ColoredBox(
          color: const Color(0xFF0B0608),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Full log card, as the fact of the day.
                Expanded(
                  flex: 3,
                  child: SizedBox(
                    height: 340,
                    child: LogCard(
                      card: _fact('DCCc9w3MDuG', 'decision-making'),
                      onRate: (_) {},
                      onOpenReel: () {},
                    ),
                  ),
                ),
                const SizedBox(width: 14),
                // Compact log card, as it appears in the sideways deck.
                Expanded(
                  flex: 2,
                  child: SizedBox(
                    height: 210,
                    child: LogCard(card: _fact('DKl00z9zzQw', 'mindset'), compact: true),
                  ),
                ),
                const SizedBox(width: 14),
                // Library tiles.
                Expanded(
                  flex: 2,
                  child: SizedBox(
                    height: 300,
                    child: Column(
                      children: [
                        Expanded(child: MiniPoster(card: _task('DOdkYPJgXV-', 'skincare'), onTap: () {})),
                        const SizedBox(height: 12),
                        Expanded(child: MiniPoster(card: _fact('DXqZ11aaBcd', 'health'), onTap: () {})),
                      ],
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
      matchesGoldenFile('goldens/log_and_library.png'),
    );
  });
}
