import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis/services/jain_calendar.dart';
import 'package:jarvis/services/nutrition_engine.dart';
import 'package:jarvis/services/training_plan.dart';

/// The health module's rules are the kind that fail silently: a sunset that is
/// twenty minutes late doesn't crash, it just quietly tells him he has time to
/// eat when he doesn't. So the arithmetic is pinned against independently
/// published values rather than against itself.
void main() {
  final cal = JainCalendar();

  group('solar arithmetic', () {
    // Reference sunsets for Ahmedabad (23.02N, 72.57E, IST), cross-checked
    // against sunrise-sunset.org and timeanddate. A 2-minute tolerance is far
    // tighter than the 15-minute safety margin the deadline already carries.
    final expected = <(DateTime, int, int)>[
      (_d(2026, 8, 18), 19, 11),
      (_d(2026, 8, 31), 19, 0),
      (_d(2026, 9, 15), 18, 45),
      (_d(2026, 9, 30), 18, 30),
      (_d(2026, 10, 15), 18, 15),
      (_d(2026, 10, 31), 18, 3),
      (_d(2026, 11, 15), 17, 56),
      (_d(2026, 11, 24), 17, 55),
    ];

    for (final (date, h, m) in expected) {
      test('sunset on ${date.day}/${date.month} is ~$h:$m', () {
        final jd = cal.day(date);
        final want = DateTime(date.year, date.month, date.day, h, m);
        final drift = jd.sunset.difference(want).inMinutes.abs();
        expect(drift, lessThanOrEqualTo(2),
            reason: 'got ${jd.sunset}, expected ~$want');
      });
    }

    test('sunrise on 18 Aug 2026 is ~06:18', () {
      final jd = cal.day(_d(2026, 8, 18));
      final want = DateTime(2026, 8, 18, 6, 18);
      expect(jd.sunrise.difference(want).inMinutes.abs(), lessThanOrEqualTo(2));
    });

    test('navkarsi is sunrise + 48 min', () {
      final jd = cal.day(_d(2026, 8, 18));
      expect(jd.navkarsi.difference(jd.sunrise).inMinutes, 48);
    });

    test('last meal deadline sits before sunset, never on it', () {
      final jd = cal.day(_d(2026, 11, 15));
      expect(jd.lastMealBy.isBefore(jd.sunset), isTrue);
      expect(jd.sunset.difference(jd.lastMealBy).inMinutes, 15);
    });

    test('the eating window really does shrink across chaumasa', () {
      final aug = cal.day(_d(2026, 8, 18)).windowHours;
      final nov = cal.day(_d(2026, 11, 24)).windowHours;
      expect(aug, greaterThan(nov));
      // ~12.1 h down to ~10.1 h. This 2-hour squeeze is the whole reason the
      // countdown card exists.
      expect(aug - nov, greaterThan(1.5));
    });
  });

  group('observance windows', () {
    test('18 Aug 2026 is inside chaumasa', () {
      expect(cal.day(_d(2026, 8, 18)).inChaumasa, isTrue);
    });

    test('1 Jul 2026 is outside chaumasa', () {
      expect(cal.day(_d(2026, 7, 1)).inChaumasa, isFalse);
    });

    test('Paryushan wins over chaumasa when both match', () {
      final jd = cal.day(_d(2026, 9, 10));
      expect(jd.window?.name, 'Paryushan');
      expect(jd.window?.isDeload, isTrue);
    });

    test('Ayambil Oli is picked up in October', () {
      expect(cal.day(_d(2026, 10, 20)).window?.name, 'Navpad Ayambil Oli');
    });

    test('chauvihar defaults on during chaumasa and off outside it', () {
      expect(cal.day(_d(2026, 8, 18)).observingChauvihar, isTrue);
      expect(cal.day(_d(2026, 7, 1)).observingChauvihar, isFalse);
    });

    test('an explicit chauvihar value overrides the chaumasa default', () {
      final jd = cal.day(_d(2026, 8, 18), observingChauvihar: false);
      expect(jd.observingChauvihar, isFalse);
      expect(jd.timeLeftToEat(), isNull);
    });
  });

  group('training is gated by the fast, not by the plan', () {
    final plan = TrainingPlan(startedOn: _d(2026, 8, 18));

    test('chauvihar upvas blocks everything, including the ritual', () {
      // Mon 24 Aug — a lifting day the programme would otherwise fill.
      final jd = cal.day(_d(2026, 8, 24), fast: FastKind.chauvihar);
      final td = plan.dayFor(jd);
      expect(td.clearance, TrainingClearance.rest);
      expect(td.session, isNull);
      expect(td.runKm, 0);
      expect(td.ritualReps, 0);
      expect(td.blockedReason, isNotNull);
    });

    test('tivihar upvas also blocks training', () {
      final jd = cal.day(_d(2026, 8, 24), fast: FastKind.tivihar);
      expect(plan.dayFor(jd).clearance, TrainingClearance.rest);
    });

    test('only chauvihar raises the waterless heat warning', () {
      expect(cal.day(_d(2026, 8, 24), fast: FastKind.chauvihar).needsHeatWarning,
          isTrue);
      expect(cal.day(_d(2026, 8, 24), fast: FastKind.tivihar).needsHeatWarning,
          isFalse);
    });

    test('ayambil allows light work only', () {
      final td = plan.dayFor(cal.day(_d(2026, 8, 24), fast: FastKind.ayambil));
      expect(td.clearance, TrainingClearance.lightOnly);
      expect(td.session, isNull);
      expect(td.runKm, 0);
    });

    test('biyasana is a full training day', () {
      final td = plan.dayFor(cal.day(_d(2026, 8, 24), fast: FastKind.biyasana));
      expect(td.clearance, TrainingClearance.full);
      expect(td.session?.name, 'Full-Body A');
    });

    test('a deload window caps an otherwise-clear day', () {
      // 10 Sep is inside Paryushan and is a Thursday.
      final td = plan.dayFor(cal.day(_d(2026, 9, 10)));
      expect(td.clearance, TrainingClearance.moderate);
    });

    test('Wednesday is Full-Body B', () {
      expect(plan.dayFor(cal.day(_d(2026, 8, 26))).session?.name, 'Full-Body B');
    });

    test('training must finish an hour before the eating window shuts', () {
      final jd = cal.day(_d(2026, 11, 16));
      final by = plan.trainByFor(jd);
      expect(jd.lastMealBy.difference(by).inMinutes, 60);
      // By mid-November that lands before 17:00, which is the collision worth
      // knowing about in August rather than discovering in November.
      expect(by.hour, lessThan(17));
    });
  });

  group('running volume', () {
    final plan = TrainingPlan(startedOn: _d(2026, 8, 18));

    test('starts at the evidence-supported 3 km per week, not 70', () {
      expect(plan.runKmForWeek(1), closeTo(3.0, 0.01));
    });

    test('progresses at ~10% a week', () {
      expect(plan.runKmForWeek(2), closeTo(3.3, 0.05));
      expect(plan.runKmForWeek(5), closeTo(4.4, 0.1));
    });

    test('does not reach 10 km/week before about week 14', () {
      expect(plan.runKmForWeek(12), lessThan(10));
    });

    test('is capped so a long block cannot compound into absurdity', () {
      expect(plan.runKmForWeek(60), lessThanOrEqualTo(25));
    });
  });

  // Deliberately round, synthetic numbers — 70 kg / 170 cm / 25 yr. These test
  // the formula, and the real body measurements belong in the on-device
  // database, not in a file that gets pushed. See HealthDb.profile.
  group('nutrition targets', () {
    const kg = 70.0, cm = 170.0, age = 25;

    test('Mifflin-St Jeor matches the hand calculation', () {
      // 10(70) + 6.25(170) - 5(25) + 5 = 700 + 1062.5 - 125 + 5
      expect(NutritionEngine.bmr(kg: kg, cm: cm, age: age),
          closeTo(1642.5, 0.01));
    });

    test('TDEE uses the component build-up, not a x1.55 multiplier', () {
      final t = NutritionEngine.targets(kg: kg, cm: cm, age: age);
      // x1.55 on this BMR would give 2546. The build-up lands ~275 lower,
      // which is more than the entire intended deficit.
      expect(t.tdee, greaterThan(2150));
      expect(t.tdee, lessThan(2400));
    });

    test('protein target is 1.8 g/kg', () {
      final t = NutritionEngine.targets(kg: kg, cm: cm, age: age);
      expect(t.proteinG, closeTo(kg * 1.8, 0.5));
    });

    test('required protein density is the ~6.4 g/100 kcal that makes it hard',
        () {
      final t = NutritionEngine.targets(kg: kg, cm: cm, age: age);
      expect(t.proteinPer100kcal, closeTo(6.4, 0.5));
    });

    test('a calibrated TDEE overrides the estimate', () {
      final t = NutritionEngine.targets(
          kg: kg, cm: cm, age: age, calibratedTdee: 2100);
      expect(t.tdee, 2100);
      expect(t.calibrated, isTrue);
    });
  });

  group('Jain food rules', () {
    final soya = NutritionEngine.byName('Soya chunks (dry)')!;
    final moong = NutritionEngine.byName('Moong dal')!;
    final curd = NutritionEngine.byName('Curd (toned)')!;
    final paneer = NutritionEngine.byName('Paneer (low-fat)')!;
    final palak = NutritionEngine.byName('Spinach (palak)')!;
    final sprouts = NutritionEngine.byName('Sprouted moong')!;

    test('raw dairy plus pulse trips the dvidal rule', () {
      final c = NutritionEngine.checkMeal(
        [MealComponent(moong, 60), MealComponent(curd, 150)],
        chaumasa: true,
        ayambil: false,
      );
      expect(c.dvidalViolation, isTrue);
    });

    test('cooked dairy with a pulse does not — this is why kadhi is fine', () {
      final c = NutritionEngine.checkMeal(
        [MealComponent(moong, 60), MealComponent(paneer, 100)],
        chaumasa: true,
        ayambil: false,
      );
      expect(c.dvidalViolation, isFalse);
    });

    test('leafy greens are rejected during chaumasa but fine outside it', () {
      expect(palak.legalOn(chaumasa: true, ayambil: false), isFalse);
      expect(palak.legalOn(chaumasa: false, ayambil: false), isTrue);
    });

    test('sprouts are rejected year-round, not just in chaumasa', () {
      expect(sprouts.legalOn(chaumasa: false, ayambil: false), isFalse);
    });

    test('ayambil strips out dairy', () {
      expect(paneer.legalOn(chaumasa: true, ayambil: true), isFalse);
      expect(curd.legalOn(chaumasa: true, ayambil: true), isFalse);
    });

    test('soya chunks are the density anchor the plan leans on', () {
      expect(soya.proteinPer100kcal, greaterThan(15));
      expect(NutritionEngine.anchors.first.name, 'Soya chunks (dry)');
    });

    test('every anchor clears 9 g protein per 100 kcal', () {
      for (final f in NutritionEngine.anchors) {
        expect(f.proteinPer100kcal, greaterThanOrEqualTo(9.0),
            reason: f.name);
      }
    });
  });

  group('the leucine trap', () {
    final chana = NutritionEngine.byName('Chana dal')!;
    final atta = NutritionEngine.byName('Wheat atta')!;
    final rice = NutritionEngine.byName('Rice (milled)')!;
    final paneer = NutritionEngine.byName('Paneer (low-fat)')!;
    final milk = NutritionEngine.byName('Milk (double-toned)')!;

    test('the 11:00 chana-dal meal misses the threshold — the known weak spot',
        () {
      final c = NutritionEngine.checkMeal(
        [MealComponent(chana, 60), MealComponent(rice, 55)],
        chaumasa: true,
        ayambil: false,
      );
      // ~18 g protein but only ~1.25 g leucine: chana dal is the most
      // leucine-dilute pulse at 6.9%.
      expect(c.proteinG, greaterThan(15));
      expect(c.hitsLeucine, isFalse);
      expect(c.leucineAdvice, contains('soya'));
    });

    test('a dairy meal clears it on much less protein', () {
      final c = NutritionEngine.checkMeal(
        [MealComponent(paneer, 150), MealComponent(atta, 75)],
        chaumasa: true,
        ayambil: false,
      );
      expect(c.hitsLeucine, isTrue);
    });

    test('a day can hit its protein target while every meal fails', () {
      // The exact failure mode a generic tracker cannot see.
      final meal = [MealComponent(chana, 55), MealComponent(atta, 60)];
      final c = NutritionEngine.checkMeal(meal,
          chaumasa: true, ayambil: false);
      final dayProtein = c.proteinG * 4;
      expect(dayProtein, greaterThan(70));
      expect(c.hitsLeucine, isFalse);
    });

    test('adding milk to the weak meal fixes it', () {
      final c = NutritionEngine.checkMeal(
        [
          MealComponent(chana, 60),
          MealComponent(rice, 55),
          MealComponent(milk, 300),
        ],
        chaumasa: true,
        ayambil: false,
      );
      // Note this is legal only because the dal is cooked, not raw-mixed.
      expect(c.leucineG, greaterThan(2.0));
    });
  });

  group('fibre ramp', () {
    test('starts at 30 g of raw pulse and climbs 10 g a week', () {
      expect(NutritionEngine.pulseGramsForWeek(1), 30);
      expect(NutritionEngine.pulseGramsForWeek(3), 50);
      expect(NutritionEngine.pulseGramsForWeek(6), 80);
    });

    test('stops climbing after the ramp rather than running away', () {
      expect(NutritionEngine.pulseGramsForWeek(10), 80);
      expect(NutritionEngine.fibreCeilingForWeek(20), lessThanOrEqualTo(55));
    });
  });

  group('the on-ramp holds back the deficit', () {
    final plan = TrainingPlan(startedOn: _d(2026, 8, 18));

    test('weeks 1-2 are explicitly at maintenance', () {
      expect(plan.phaseFor(1), contains('MAINTENANCE'));
      expect(plan.phaseFor(2), contains('MAINTENANCE'));
    });

    test('the deficit only appears from week 3', () {
      expect(plan.phaseFor(3), isNot(contains('MAINTENANCE')));
    });

    test('sets and effort both start low', () {
      expect(plan.setsForWeek(1), 2);
      expect(plan.rirForWeek(1), '3');
      expect(plan.setsForWeek(8), 3);
    });
  });
}

DateTime _d(int y, int m, int d) => DateTime(y, m, d);
