import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis/models/reel_card.dart';
import 'package:jarvis/services/deck_db.dart';
import 'package:jarvis/services/nudge_service.dart';
import 'package:jarvis/widgets/pirate_bits.dart';

ReelCard _task(String id, Horizon h) => ReelCard(
      id: id,
      kind: CardKind.task,
      title: 't',
      summary: 's',
      domain: 'health',
      tags: const [],
      url: '',
      owner: '',
      collection: '',
      evidence: '',
      confidence: 'high',
      horizon: h,
    );

void main() {
  group('day keys', () {
    test('pads month and day', () {
      expect(DeckDb.dayKey(DateTime(2026, 8, 6)), '2026-08-06');
      expect(DeckDb.dayKey(DateTime(2026, 12, 31)), '2026-12-31');
    });
  });

  group('horizons', () {
    test('round-trip through the database key', () {
      for (final h in Horizon.values) {
        expect(horizonFrom(horizonKey(h)), h);
      }
    });

    test('unknown values fall back to short term', () {
      expect(horizonFrom(null), Horizon.shortTerm);
      expect(horizonFrom('nonsense'), Horizon.shortTerm);
    });
  });

  group('bounties', () {
    test('are stable for a given card', () {
      final a = bountyFor(_task('DOdkYPJgXV-', Horizon.today));
      final b = bountyFor(_task('DOdkYPJgXV-', Horizon.today));
      expect(a, b);
    });

    test('scale with the horizon', () {
      int millions(String s) =>
          int.parse(s.replaceAll(RegExp(r'[^0-9]'), '')) ~/ 1000000;

      // Same id, different horizon: the long haul must be worth more than the
      // quick win, or the board stops telling you where the weight is.
      const id = 'DKl0092zzQw';
      expect(millions(bountyFor(_task(id, Horizon.today))), lessThan(30));
      expect(millions(bountyFor(_task(id, Horizon.longTerm))),
          greaterThanOrEqualTo(150));
    });

    test('are grouped in threes', () {
      expect(bountyFor(_task('abc', Horizon.today)), matches(r'^฿ [\d,]+$'));
    });
  });

  group('nudge settings', () {
    test('parse a native map', () {
      final s = NudgeSettings.fromMap(NudgeKind.water, {
        'enabled': true,
        'intervalMin': 45,
        'startMin': 7 * 60,
        'endMin': 22 * 60,
        'amount': 3000,
        'perNudge': 150,
        'nudgesPerDay': 20,
        'countToday': 3,
        'nextFireAt': 1754400000000,
      });
      expect(s.enabled, isTrue);
      expect(s.windowLabel, '07:00 – 22:00');
      expect(s.perNudge, 150);
    });

    test('each kind falls back to its own defaults', () {
      final w = NudgeSettings.fromMap(NudgeKind.water, const {});
      expect(w.intervalMin, 45);
      expect(w.windowLabel, '07:00 – 22:00');

      // The 20-20-20 rule, so the eye nudge must not inherit water's 45 min.
      final e = NudgeSettings.fromMap(NudgeKind.eyes, const {});
      expect(e.intervalMin, 20);
      expect(e.amount, 20);
      expect(e.windowLabel, '09:00 – 23:00');
    });

    test('copyWith leaves derived fields alone', () {
      final base = NudgeSettings.defaultsFor(NudgeKind.water);
      final s = base.copyWith(enabled: true, intervalMin: 60);
      expect(s.enabled, isTrue);
      expect(s.intervalMin, 60);
      // perNudge is computed natively, so the client must not invent one.
      expect(s.perNudge, base.perNudge);
    });

    test('summaries name the right unit', () {
      expect(NudgeSettings.defaultsFor(NudgeKind.water).summary, contains('ml'));
      expect(NudgeSettings.defaultsFor(NudgeKind.eyes).summary, contains('look away'));
    });
  });
}
