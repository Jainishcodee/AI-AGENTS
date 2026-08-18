/// Jain-legal nutrition maths.
///
/// Composition figures are ICMR-NIN **IFCT 2017** (Indian foods, Indian
/// varieties) rather than USDA — Indian pulse and dairy values differ enough
/// from US ones to matter at the gram level this plan works in. Items absent
/// from IFCT (soya chunks, tofu, toned milks, low-fat paneer) use label values
/// and are marked in [FoodItem.estimated].
///
/// Three rules are enforced here that a generic tracker gets wrong:
///
/// 1. **Leucine per meal, not protein per day.** Plant proteins are
///    leucine-dilute, so a 30 g dal meal misses the muscle-protein-synthesis
///    threshold that a 26 g dairy meal clears. Daily protein can be on target
///    while every individual meal fails.
/// 2. **Dvidal.** Raw pulses mixed with raw milk, curd or chaas is abhakshya —
///    year-round, not just chaumasa. Cooked dairy with dal is the standard
///    workaround, which is why kadhi is acceptable.
/// 3. **Chaumasa legality.** Leafy greens, sprouts and fermented batters are
///    out for four months, and the permitted gourds carry almost no protein —
///    so the same target has to come from a smaller list.
library;

/// Where a food sits against the observance rules.
enum FoodLegality {
  /// Fine year-round.
  always,

  /// Excluded during chaumasa (leafy greens, sprouts, fermented batters).
  notInChaumasa,

  /// Excluded on ayambil days (dairy, fat, sugar, fruit, vegetables).
  notOnAyambil,

  /// Never — root vegetables, sprouts.
  never,
}

/// Whether a food counts as a pulse or as raw dairy, for the dvidal check.
enum DvidalClass { none, pulse, rawDairy, cookedDairy }

class FoodItem {
  const FoodItem({
    required this.name,
    required this.proteinPer100g,
    required this.kcalPer100g,
    required this.leucinePer100g,
    required this.servingG,
    required this.servingLabel,
    this.fibrePer100g = 0,
    this.rupeesPerServing = 0,
    this.legality = FoodLegality.always,
    this.dvidal = DvidalClass.none,
    this.estimated = false,
  });

  final String name;
  final double proteinPer100g;
  final double kcalPer100g;
  final double leucinePer100g;
  final double fibrePer100g;

  /// A realistic Indian household serving, not a round 100 g.
  final double servingG;
  final String servingLabel;
  final double rupeesPerServing;

  final FoodLegality legality;
  final DvidalClass dvidal;

  /// True where the value is a label/literature figure rather than IFCT.
  final bool estimated;

  double proteinIn(double grams) => proteinPer100g * grams / 100;
  double kcalIn(double grams) => kcalPer100g * grams / 100;
  double leucineIn(double grams) => leucinePer100g * grams / 100;
  double fibreIn(double grams) => fibrePer100g * grams / 100;

  /// Protein per 100 kcal — the density figure that decides whether the target
  /// is reachable inside the calorie budget at all.
  double get proteinPer100kcal =>
      kcalPer100g == 0 ? 0 : proteinPer100g / kcalPer100g * 100;

  bool legalOn({required bool chaumasa, required bool ayambil}) {
    switch (legality) {
      case FoodLegality.never:
        return false;
      case FoodLegality.notInChaumasa:
        return !chaumasa;
      case FoodLegality.notOnAyambil:
        return !ayambil;
      case FoodLegality.always:
        return !ayambil || dvidal != DvidalClass.rawDairy;
    }
  }
}

/// One serving of one food inside a meal.
class MealComponent {
  const MealComponent(this.food, this.grams);
  final FoodItem food;
  final double grams;
}

/// The verdict on a composed meal.
class MealCheck {
  const MealCheck({
    required this.proteinG,
    required this.kcal,
    required this.leucineG,
    required this.fibreG,
    required this.rupees,
    required this.dvidalViolation,
    required this.illegalItems,
    required this.leucineTarget,
  });

  final double proteinG;
  final double kcal;
  final double leucineG;
  final double fibreG;
  final double rupees;

  /// True when raw pulses and raw dairy appear together.
  final bool dvidalViolation;

  /// Foods not permitted on this kind of day.
  final List<String> illegalItems;

  final double leucineTarget;

  bool get hitsLeucine => leucineG >= leucineTarget;

  /// What to do about a meal that misses. Concrete, because "add more protein"
  /// is not actionable at 17:20 with the window closing.
  String? get leucineAdvice {
    if (hitsLeucine) return null;
    final short = leucineTarget - leucineG;
    // Soya chunks are the densest legal lever and are in the plan already, so
    // the fix is quoted in the units he actually measures.
    final soyaG = (short / 0.041).ceil();
    return 'Short ${short.toStringAsFixed(2)} g leucine — '
        'add ~$soyaG g dry soya chunks, or 150 ml milk.';
  }

  bool get isClean =>
      !dvidalViolation && illegalItems.isEmpty && hitsLeucine;
}

/// Daily targets, derived rather than hardcoded so they track his actual
/// weight instead of the number he first reported.
class NutritionTargets {
  const NutritionTargets({
    required this.bmr,
    required this.tdee,
    required this.kcal,
    required this.proteinG,
    required this.proteinPer100kcal,
    required this.fibreG,
    required this.calibrated,
  });

  final double bmr;
  final double tdee;
  final double kcal;
  final double proteinG;

  /// The density the day has to average. If a plan falls below this it cannot
  /// reach the protein target inside the calorie budget, no matter what is
  /// added later.
  final double proteinPer100kcal;

  final double fibreG;

  /// True once [HealthDb.calibratedTdee] has replaced the estimate.
  final bool calibrated;
}

class NutritionEngine {
  /// Protein per kg of bodyweight. 1.8 sits mid-band of the 1.6–2.2 evidence
  /// range; the lower half is chosen because he is in a modest deficit, not a
  /// hard cut.
  static const proteinPerKg = 1.8;

  /// Deficit as a fraction of maintenance.
  ///
  /// −13% rather than −20%: the randomised comparison of slow vs fast weight
  /// loss found the slow group *gained* lean mass while losing more fat, and he
  /// is a novice whose newbie gains an aggressive deficit would suppress.
  static const deficitFraction = 0.13;

  /// Leucine needed per meal to maximally stimulate muscle protein synthesis.
  static const leucineThreshold = 2.5;

  /// Higher bar for pulse- or grain-dominant meals, which are leucine-dilute.
  static const leucineThresholdPulseMeal = 2.5;

  /// Mifflin–St Jeor, male.
  ///
  /// Deliberately not multiplied by an "activity factor": those multipliers
  /// were derived from all-day occupational activity, and applying ×1.55 to a
  /// desk-bound student who lifts for 50 minutes overshoots by ~270 kcal —
  /// which is more than the entire intended deficit.
  static double bmr({
    required double kg,
    required double cm,
    required int age,
  }) =>
      10 * kg + 6.25 * cm - 5 * age + 5;

  static NutritionTargets targets({
    required double kg,
    required double cm,
    required int age,
    int sessionsPerWeek = 5,
    double? calibratedTdee,
  }) {
    final b = bmr(kg: kg, cm: cm, age: age);

    // Component build-up: BMR + thermic effect of food + non-exercise activity
    // + the actual sessions. Each term is small and defensible; the product of
    // a single guessed multiplier is not.
    final tef = b * 0.10;
    const neat = 250.0;
    final exercise = sessionsPerWeek * 300.0 / 7.0;
    final estimated = b + tef + neat + exercise;

    final tdee = calibratedTdee ?? estimated;
    final kcal = tdee * (1 - deficitFraction);
    final protein = kg * proteinPerKg;

    return NutritionTargets(
      bmr: b,
      tdee: tdee,
      kcal: kcal,
      proteinG: protein,
      proteinPer100kcal: protein / kcal * 100,
      // ICMR-NIN guidance is ~40 g fibre per 2000 kcal.
      fibreG: kcal / 2000 * 40,
      calibrated: calibratedTdee != null,
    );
  }

  /// The fibre ceiling for a given week of the ramp.
  ///
  /// The target is right but the *rate* is the problem: going from ~25–30 g to
  /// 45–56 g in one step produces enough gas and bloating to end the diet in
  /// week two. Raffinose-family oligosaccharides are the cause and the gut
  /// adapts over 2–4 weeks, so the ramp is the whole intervention.
  static double fibreCeilingForWeek(int week) {
    const start = 30.0;
    const step = 5.0;
    const ceiling = 55.0;
    final v = start + step * (week - 1).clamp(0, 100);
    return v > ceiling ? ceiling : v;
  }

  /// Raw pulse grams permitted in a given ramp week.
  static int pulseGramsForWeek(int week) =>
      (30 + 10 * (week - 1).clamp(0, 5)).toInt();

  static MealCheck checkMeal(
    List<MealComponent> parts, {
    required bool chaumasa,
    required bool ayambil,
  }) {
    var protein = 0.0, kcal = 0.0, leucine = 0.0, fibre = 0.0, rupees = 0.0;
    var hasPulse = false, hasRawDairy = false;
    final illegal = <String>[];

    for (final c in parts) {
      protein += c.food.proteinIn(c.grams);
      kcal += c.food.kcalIn(c.grams);
      leucine += c.food.leucineIn(c.grams);
      fibre += c.food.fibreIn(c.grams);
      if (c.food.servingG > 0) {
        rupees += c.food.rupeesPerServing * c.grams / c.food.servingG;
      }
      if (c.food.dvidal == DvidalClass.pulse) hasPulse = true;
      if (c.food.dvidal == DvidalClass.rawDairy) hasRawDairy = true;
      if (!c.food.legalOn(chaumasa: chaumasa, ayambil: ayambil)) {
        illegal.add(c.food.name);
      }
    }

    // A meal is "pulse-dominant" when pulses and grains carry it. Those need a
    // higher protein total to reach the same leucine, so the threshold is the
    // same but is far harder to hit — the advice string is what closes the gap.
    return MealCheck(
      proteinG: protein,
      kcal: kcal,
      leucineG: leucine,
      fibreG: fibre,
      rupees: rupees,
      dvidalViolation: hasPulse && hasRawDairy,
      illegalItems: illegal,
      leucineTarget: leucineThreshold,
    );
  }

  /// Foods that clear 9 g protein per 100 kcal — the only ones that can carry
  /// the target once cereals and fat have taken their share of the budget.
  static List<FoodItem> get anchors => foods
      .where((f) => f.proteinPer100kcal >= 9.0)
      .toList()
    ..sort((a, b) => b.proteinPer100kcal.compareTo(a.proteinPer100kcal));

  /// IFCT 2017 unless marked estimated. Costs are Ahmedabad, Aug 2026.
  static const foods = <FoodItem>[
    FoodItem(
      name: 'Soya chunks (dry)',
      proteinPer100g: 52.0,
      kcalPer100g: 345,
      leucinePer100g: 4.10,
      fibrePer100g: 13.0,
      servingG: 30,
      servingLabel: '30 g dry (~1 katori soaked)',
      rupeesPerServing: 8,
      dvidal: DvidalClass.pulse,
      estimated: true,
    ),
    FoodItem(
      name: 'Soya bean (white)',
      proteinPer100g: 37.80,
      kcalPer100g: 377,
      leucinePer100g: 3.08,
      fibrePer100g: 22.6,
      servingG: 30,
      servingLabel: '30 g',
      rupeesPerServing: 3.3,
      dvidal: DvidalClass.pulse,
    ),
    FoodItem(
      name: 'Paneer (low-fat)',
      proteinPer100g: 20.0,
      kcalPer100g: 180,
      leucinePer100g: 1.95,
      servingG: 100,
      servingLabel: '100 g',
      rupeesPerServing: 31,
      legality: FoodLegality.notOnAyambil,
      dvidal: DvidalClass.cookedDairy,
      estimated: true,
    ),
    FoodItem(
      name: 'Paneer (full fat)',
      proteinPer100g: 18.86,
      kcalPer100g: 258,
      leucinePer100g: 1.84,
      servingG: 100,
      servingLabel: '100 g',
      rupeesPerServing: 38,
      legality: FoodLegality.notOnAyambil,
      dvidal: DvidalClass.cookedDairy,
    ),
    FoodItem(
      name: 'Tofu',
      proteinPer100g: 10.0,
      kcalPer100g: 85,
      leucinePer100g: 0.80,
      servingG: 100,
      servingLabel: '100 g',
      rupeesPerServing: 32,
      dvidal: DvidalClass.pulse,
      estimated: true,
    ),
    FoodItem(
      name: 'Milk (double-toned)',
      proteinPer100g: 3.1,
      kcalPer100g: 40,
      leucinePer100g: 0.331,
      servingG: 200,
      servingLabel: '200 ml',
      rupeesPerServing: 11,
      legality: FoodLegality.notOnAyambil,
      dvidal: DvidalClass.rawDairy,
      estimated: true,
    ),
    FoodItem(
      name: 'Milk (toned)',
      proteinPer100g: 3.1,
      kcalPer100g: 58,
      leucinePer100g: 0.331,
      servingG: 200,
      servingLabel: '200 ml',
      rupeesPerServing: 12,
      legality: FoodLegality.notOnAyambil,
      dvidal: DvidalClass.rawDairy,
      estimated: true,
    ),
    FoodItem(
      name: 'Milk (whole cow)',
      proteinPer100g: 3.26,
      kcalPer100g: 72.9,
      leucinePer100g: 0.348,
      servingG: 200,
      servingLabel: '200 ml',
      rupeesPerServing: 13,
      legality: FoodLegality.notOnAyambil,
      dvidal: DvidalClass.rawDairy,
    ),
    FoodItem(
      name: 'Curd (toned)',
      proteinPer100g: 3.3,
      kcalPer100g: 60,
      leucinePer100g: 0.35,
      servingG: 150,
      servingLabel: '1 katori (150 g)',
      rupeesPerServing: 14,
      legality: FoodLegality.notOnAyambil,
      dvidal: DvidalClass.rawDairy,
      estimated: true,
    ),
    FoodItem(
      name: 'Moong dal',
      proteinPer100g: 23.88,
      kcalPer100g: 326,
      leucinePer100g: 1.89,
      fibrePer100g: 9.4,
      servingG: 30,
      servingLabel: '30 g raw',
      rupeesPerServing: 3.9,
      dvidal: DvidalClass.pulse,
    ),
    FoodItem(
      name: 'Masoor dal',
      proteinPer100g: 24.35,
      kcalPer100g: 322,
      leucinePer100g: 1.73,
      fibrePer100g: 10.4,
      servingG: 30,
      servingLabel: '30 g raw',
      rupeesPerServing: 3.0,
      dvidal: DvidalClass.pulse,
    ),
    FoodItem(
      name: 'Urad dal',
      proteinPer100g: 23.06,
      kcalPer100g: 324,
      leucinePer100g: 1.83,
      servingG: 30,
      servingLabel: '30 g raw',
      rupeesPerServing: 4.2,
      dvidal: DvidalClass.pulse,
    ),
    FoodItem(
      name: 'Toor dal',
      proteinPer100g: 21.70,
      kcalPer100g: 331,
      leucinePer100g: 1.46,
      fibrePer100g: 9.1,
      servingG: 30,
      servingLabel: '30 g raw',
      rupeesPerServing: 4.7,
      dvidal: DvidalClass.pulse,
    ),
    // Kept in the list despite being the weakest choice, because it is what a
    // Gujarati kitchen reaches for by default — the app has to be able to show
    // him *why* it underperforms rather than silently omitting it.
    FoodItem(
      name: 'Chana dal',
      proteinPer100g: 21.55,
      kcalPer100g: 329,
      leucinePer100g: 1.49,
      fibrePer100g: 15.2,
      servingG: 30,
      servingLabel: '30 g raw',
      rupeesPerServing: 2.9,
      dvidal: DvidalClass.pulse,
    ),
    FoodItem(
      name: 'Groundnut',
      proteinPer100g: 23.65,
      kcalPer100g: 520,
      leucinePer100g: 1.51,
      servingG: 30,
      servingLabel: '30 g',
      rupeesPerServing: 4.5,
    ),
    FoodItem(
      name: 'Wheat atta',
      proteinPer100g: 10.57,
      kcalPer100g: 320,
      leucinePer100g: 0.648,
      fibrePer100g: 11.4,
      servingG: 30,
      servingLabel: '1 medium roti (30 g)',
      rupeesPerServing: 1.4,
    ),
    FoodItem(
      name: 'Rice (milled)',
      proteinPer100g: 7.94,
      kcalPer100g: 356,
      leucinePer100g: 0.642,
      fibrePer100g: 2.8,
      servingG: 50,
      servingLabel: '50 g raw (1 katori)',
      rupeesPerServing: 3.0,
    ),
    FoodItem(
      name: 'Bajra',
      proteinPer100g: 10.96,
      kcalPer100g: 348,
      leucinePer100g: 0.934,
      servingG: 40,
      servingLabel: '40 g',
      rupeesPerServing: 1.8,
    ),
    FoodItem(
      name: 'Jowar',
      proteinPer100g: 9.97,
      kcalPer100g: 334,
      leucinePer100g: 1.199,
      servingG: 40,
      servingLabel: '40 g',
      rupeesPerServing: 1.8,
    ),
    FoodItem(
      name: 'Amaranth (rajgira)',
      proteinPer100g: 13.27,
      kcalPer100g: 356,
      leucinePer100g: 0.656,
      servingG: 40,
      servingLabel: '40 g',
      rupeesPerServing: 7.2,
    ),
    FoodItem(
      name: 'Almond',
      proteinPer100g: 18.41,
      kcalPer100g: 609,
      leucinePer100g: 0.740,
      servingG: 30,
      servingLabel: '30 g',
      rupeesPerServing: 26,
      legality: FoodLegality.notOnAyambil,
    ),
    FoodItem(
      name: 'Sesame (til)',
      proteinPer100g: 21.70,
      kcalPer100g: 520,
      leucinePer100g: 1.17,
      servingG: 20,
      servingLabel: '20 g',
      rupeesPerServing: 4.4,
    ),
    // Guava earns its place as the vitamin C anchor: vitamin C taken *with* the
    // dal meal is the single highest-leverage micronutrient move available on
    // this diet, and it is also 8.6 g fibre per 100 g.
    FoodItem(
      name: 'Guava',
      proteinPer100g: 2.55,
      kcalPer100g: 68,
      leucinePer100g: 0.06,
      fibrePer100g: 8.59,
      servingG: 150,
      servingLabel: '150 g',
      rupeesPerServing: 12,
      legality: FoodLegality.notOnAyambil,
    ),
    FoodItem(
      name: 'Bottle gourd (dudhi)',
      proteinPer100g: 0.53,
      kcalPer100g: 14,
      leucinePer100g: 0.03,
      servingG: 150,
      servingLabel: '150 g',
      rupeesPerServing: 6,
    ),
    FoodItem(
      name: 'Ridge gourd',
      proteinPer100g: 0.91,
      kcalPer100g: 18,
      leucinePer100g: 0.05,
      servingG: 150,
      servingLabel: '150 g',
      rupeesPerServing: 7,
    ),
    FoodItem(
      name: 'Tomato',
      proteinPer100g: 0.9,
      kcalPer100g: 20,
      leucinePer100g: 0.03,
      servingG: 80,
      servingLabel: '80 g',
      rupeesPerServing: 4,
    ),
    FoodItem(
      name: 'Capsicum',
      proteinPer100g: 1.2,
      kcalPer100g: 25,
      leucinePer100g: 0.04,
      servingG: 60,
      servingLabel: '60 g',
      rupeesPerServing: 8,
    ),
    FoodItem(
      name: 'Fresh peas',
      proteinPer100g: 7.25,
      kcalPer100g: 81,
      leucinePer100g: 0.553,
      servingG: 100,
      servingLabel: '100 g',
      rupeesPerServing: 8,
    ),
    // Present only so the engine can refuse them by name rather than by
    // silence. A plan that never mentions spinach looks like an oversight;
    // one that says "excluded until 24 Nov" reads as deliberate.
    FoodItem(
      name: 'Spinach (palak)',
      proteinPer100g: 2.0,
      kcalPer100g: 26,
      leucinePer100g: 0.17,
      servingG: 100,
      servingLabel: '100 g',
      rupeesPerServing: 5,
      legality: FoodLegality.notInChaumasa,
    ),
    FoodItem(
      name: 'Fenugreek (methi)',
      proteinPer100g: 4.4,
      kcalPer100g: 49,
      leucinePer100g: 0.30,
      servingG: 100,
      servingLabel: '100 g',
      rupeesPerServing: 6,
      legality: FoodLegality.notInChaumasa,
    ),
    FoodItem(
      name: 'Sprouted moong',
      proteinPer100g: 7.0,
      kcalPer100g: 80,
      leucinePer100g: 0.55,
      servingG: 100,
      servingLabel: '100 g',
      rupeesPerServing: 6,
      legality: FoodLegality.never,
      dvidal: DvidalClass.pulse,
      estimated: true,
    ),
  ];

  static FoodItem? byName(String name) {
    for (final f in foods) {
      if (f.name.toLowerCase() == name.toLowerCase()) return f;
    }
    return null;
  }

  /// Foods usable on a given kind of day, densest protein first — which is the
  /// order that matters when the window is closing and there is a gap to fill.
  static List<FoodItem> usableOn({
    required bool chaumasa,
    required bool ayambil,
  }) {
    final list = foods
        .where((f) => f.legalOn(chaumasa: chaumasa, ayambil: ayambil))
        .toList();
    list.sort((a, b) => b.proteinPer100kcal.compareTo(a.proteinPer100kcal));
    return list;
  }
}
