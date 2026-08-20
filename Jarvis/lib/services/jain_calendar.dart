/// The Jain observance calendar, and the solar arithmetic it rests on.
///
/// This is the piece that makes the health module *his* rather than a generic
/// tracker. Almost every rule downstream — whether he may train today, when the
/// last meal has to land, how much protein has to fit in the window — is a
/// function of what kind of day today is.
///
/// Two things are computed here rather than stored:
///
/// **Sunset** is calculated with the NOAA solar position algorithm instead of a
/// lookup table. A table would be wrong the moment he travels, and it would need
/// re-shipping every year. Sunset in Ahmedabad moves from 19:11 in mid-August to
/// 17:55 by late November — that 76-minute drift is the whole problem the
/// chauvihar countdown exists to solve, so it has to be right on every date, not
/// just the ones someone typed in.
///
/// **Chaumasa** and the fixed observance windows are date ranges, since they are
/// set by the lunar calendar and there is no closed form for them. They are
/// declared as constants and must be refreshed each year — see [chaumasa2026].
library;

import 'dart:math' as math;

/// Which fast, if any, is being observed today.
///
/// Ordered loosely by how much they restrict. The distinction that actually
/// matters for safety is [tivihar] vs [chauvihar]: both are ~36 hours without
/// food, but chauvihar excludes **water** as well, which is what moves it from
/// "skip the gym" to "do not exercise at all".
enum FastKind {
  /// No fast. Eat normally within the usual window.
  none,

  /// Nothing until 48 minutes after sunrise. Not really a fast.
  navkarsi,

  /// First meal delayed ~3 h (porsi) to ~9 h (purimaddh) after sunrise.
  /// Functionally intermittent fasting.
  porsi,

  /// Two meals, two sittings, boiled water freely during daylight.
  biyasana,

  /// One meal, one sitting. The entire day's protein has to fit in it.
  ekasana,

  /// One bland meal: boiled cereals and pulses only. No milk, curd, ghee,
  /// butter, paneer, oil, sugar, fruit, dry fruit or green vegetables.
  ayambil,

  /// ~36 h without food. Boiled water permitted only between 48 min after
  /// sunrise and sunset.
  tivihar,

  /// ~36 h without food **or water**. The one that gates exercise entirely.
  chauvihar,
}

/// The evening vow — what is given up after sunset.
///
/// The names matter and are routinely conflated. *Chauvihar* gives up all four
/// (food, water, fruit, mouth-fresheners). *Tivihar* gives up three and **keeps
/// water**. Which one is being kept changes almost every downstream warning in
/// this module, so it is modelled explicitly rather than as a bool.
enum EveningVow {
  /// Eating normally after sunset.
  none,

  /// No food after sunset, water still permitted. **His practice.**
  tivihar,

  /// Nothing at all after sunset.
  chauvihar,
}

extension EveningVowX on EveningVow {
  String get label => switch (this) {
        EveningVow.none => 'No evening vow',
        EveningVow.tivihar => 'Tivihar',
        EveningVow.chauvihar => 'Chauvihar',
      };

  /// The food window closes at sunset under either vow.
  bool get closesFoodWindow => this != EveningVow.none;

  /// Only chauvihar takes water away. This is the flag that should drive any
  /// hydration or heat warning — never [closesFoodWindow].
  bool get waterAfterSunset => this != EveningVow.chauvihar;
}

/// What the day permits, physically.
enum TrainingClearance {
  /// Heavy compound work is fine.
  full,

  /// Train, but once, and time it around the single meal.
  moderate,

  /// Yoga, mobility, walking. No loading, no running.
  lightOnly,

  /// Rest. Gentle restorative yoga and slow breathing only.
  rest,
}

extension FastKindX on FastKind {
  String get label => switch (this) {
        FastKind.none => 'Normal',
        FastKind.navkarsi => 'Navkarsi',
        FastKind.porsi => 'Porsi',
        FastKind.biyasana => 'Biyasana',
        FastKind.ekasana => 'Ekasana',
        FastKind.ayambil => 'Ayambil',
        FastKind.tivihar => 'Tivihar upvas',
        FastKind.chauvihar => 'Chauvihar upvas',
      };

  /// True when nothing is eaten all day, so the diet targets do not apply.
  bool get isFullFast => this == FastKind.tivihar || this == FastKind.chauvihar;

  /// True when not even water is permitted. This is the flag that drives the
  /// heat and dehydration warnings, not [isFullFast].
  bool get isWaterless => this == FastKind.chauvihar;

  /// Why the clearance is what it is, in one line, for the UI.
  ///
  /// These are deliberately reasons rather than instructions. A rule the user
  /// understands is one they keep on the day they feel fine and want to train
  /// anyway — which is exactly the day the rule exists for.
  String get trainingNote => switch (this) {
        FastKind.none ||
        FastKind.navkarsi ||
        FastKind.porsi ||
        FastKind.biyasana =>
          'Full session. Finish early enough to eat before sunset.',
        FastKind.ekasana =>
          'One session, 60–90 min before your single meal — so it lands as the '
              'post-workout meal.',
        FastKind.ayambil =>
          'Yoga, mobility and walking only. No dairy, fat or sugar today means '
              'no recovery fuel for hard work.',
        FastKind.tivihar =>
          'Rest day. Water is permitted, so this is a fuel problem rather than a '
              'fluid one — but 36 h without food still means no lifting and no '
              'running. Walking and restorative yoga are fine.',
        FastKind.chauvihar =>
          'No training, no running, no heat, no hard yoga. ~36 h with NO water. '
              'Skipping costs nothing — disuse atrophy takes 1–2 weeks.',
      };

  TrainingClearance get clearance => switch (this) {
        FastKind.none ||
        FastKind.navkarsi ||
        FastKind.porsi ||
        FastKind.biyasana =>
          TrainingClearance.full,
        FastKind.ekasana => TrainingClearance.moderate,
        FastKind.ayambil => TrainingClearance.lightOnly,
        FastKind.tivihar || FastKind.chauvihar => TrainingClearance.rest,
      };
}

/// A named observance window that overrides ordinary programming.
class ObservanceWindow {
  const ObservanceWindow({
    required this.name,
    required this.start,
    required this.end,
    required this.note,
    required this.isDeload,
  });

  final String name;
  final DateTime start;
  final DateTime end;
  final String note;

  /// True when training should be backed off across the whole window rather
  /// than day by day.
  final bool isDeload;

  bool contains(DateTime day) =>
      !day.isBefore(_d(start)) && !day.isAfter(_d(end));

  static DateTime _d(DateTime t) => DateTime(t.year, t.month, t.day);
}

/// A fast the calendar believes today is, when nothing has been logged.
///
/// Deliberately a *suggestion* and not an assignment: the calendar proposes,
/// he confirms, and nothing is logged until he does.
///
/// [needsWaterRule] exists for the case where the kind is known but the water
/// rule is not. His practice is settled — tivihar, water always kept, never
/// chauvihar — so it is currently never set. It stays because the distinction
/// is the difference between "rest today" and "stay out of the heat entirely",
/// and a future change of practice must not silently inherit the safe-sounding
/// default.
class FastSuggestion {
  const FastSuggestion(
    this.kind,
    this.reason, {
    this.needsWaterRule = false,
  });

  final FastKind kind;
  final String reason;

  /// True when the kind is known to be a full fast but the water rule is not.
  final bool needsWaterRule;
}

/// Everything the rest of the app needs to know about a single day.
class JainDay {
  const JainDay({
    required this.date,
    required this.sunrise,
    required this.sunset,
    required this.navkarsi,
    required this.lastMealBy,
    required this.fast,
    required this.inChaumasa,
    required this.eveningVow,
    this.window,
    this.suggestion,
  });

  final DateTime date;
  final DateTime sunrise;
  final DateTime sunset;

  /// Sunrise + 48 min. The earliest anything may be taken under most vows.
  final DateTime navkarsi;

  /// The practical deadline for the last bite: sunset minus a margin.
  ///
  /// The vow bites *before* sunset, not at it. Cutting it fine against an
  /// astronomical instant is how a vow gets broken by accident, so the deadline
  /// always has the margin subtracted already.
  ///
  /// Under tivihar this is a deadline for FOOD only — water continues.
  final DateTime lastMealBy;

  final FastKind fast;
  final bool inChaumasa;

  /// The evening vow today. Distinct from [fast] — he keeps an evening vow on
  /// ordinary days while eating normally during daylight.
  final EveningVow eveningVow;

  /// Convenience: does the food window shut at sunset today?
  bool get closesFoodWindow => eveningVow.closesFoodWindow;

  final ObservanceWindow? window;

  /// What the calendar thinks today is, when nothing has been logged yet.
  final FastSuggestion? suggestion;

  TrainingClearance get clearance {
    // A deload window (Paryushan, Ayambil Oli) caps the day even when the day
    // itself carries no fast — the point of the window is that the whole block
    // is under-fuelled, not just the fast days inside it.
    final base = fast.clearance;
    if (window?.isDeload == true && base == TrainingClearance.full) {
      return TrainingClearance.moderate;
    }
    return base;
  }

  /// How long is left to eat. Null when there is no eating window today.
  Duration? timeLeftToEat([DateTime? now]) {
    if (fast.isFullFast) return null;
    if (!eveningVow.closesFoodWindow) return null;
    final t = now ?? DateTime.now();
    final left = lastMealBy.difference(t);
    return left.isNegative ? Duration.zero : left;
  }

  /// Hours available for eating, for the "fit 128 g of protein into this"
  /// arithmetic.
  double get windowHours =>
      lastMealBy.difference(navkarsi).inMinutes / 60.0;

  /// The dehydration warning is specifically about waterless fasting in heat,
  /// not about fasting generally.
  bool get needsHeatWarning => fast.isWaterless;
}

/// Observance dates and solar arithmetic.
///
/// Dates are for 2026 and are declared, not derived — the Jain calendar is
/// lunar and there is no closed form. They must be refreshed each year, and
/// checked against his family's panchang: Deravasi and Sthanakvasi calendars
/// can differ by a day, and the chaumasa end in particular is quoted variously
/// as 21, 23 or 24 Nov 2026 depending on the source.
class JainCalendar {
  JainCalendar({
    this.latitude = _ahmedabadLat,
    this.longitude = _ahmedabadLon,
    this.tzOffsetMinutes = _istOffsetMinutes,
    this.lastMealMarginMinutes = 15,
  });

  // Ahmedabad. Held here rather than in a settings screen because the whole
  // observance calendar below is local to him anyway; if this app ever serves
  // someone elsewhere, both move together.
  static const _ahmedabadLat = 23.0225;
  static const _ahmedabadLon = 72.5714;
  static const _istOffsetMinutes = 330; // UTC+5:30

  final double latitude;
  final double longitude;
  final int tzOffsetMinutes;

  /// Safety margin before sunset for the last-meal deadline.
  final int lastMealMarginMinutes;

  /// Chaumasa 2026: Ashadh Chaumasi Chaudas to Kartik Chaumasi Chaudas.
  ///
  /// Note this is the *Jain* window (chaumasi chaudas markers), not the Hindu
  /// Ekadashi-to-Ekadashi window, which runs 25 Jul – 21 Nov. His vows follow
  /// the Jain one.
  static final chaumasa2026 = ObservanceWindow(
    name: 'Chaumasa',
    start: DateTime(2026, 7, 26),
    end: DateTime(2026, 11, 24),
    note: 'Leafy greens, sprouts and fermented batters are out. Protein has to '
        'come from dals, dairy, soy and grains — the vegetables carry almost '
        'none.',
    isDeload: false,
  );

  /// Windows that override programming. Ordered most-specific first, since
  /// Paryushan and Oli sit *inside* chaumasa and should win when both match.
  static final windows = <ObservanceWindow>[
    ObservanceWindow(
      name: 'Paryushan',
      start: DateTime(2026, 9, 8),
      end: DateTime(2026, 9, 15),
      note: 'Samvatsari falls on Tue 15 Sep. Many observe atthai — 8 '
          'consecutive days on boiled water. Programmed as a deload, not a '
          'training block.',
      isDeload: true,
    ),
    // Navpad Ayambil Oli (17–26 Oct 2026) is deliberately ABSENT.
    //
    // It is a real and widely kept observance, but he does not keep it, and a
    // calendar that flags nine days he will spend training normally is worse
    // than one that says nothing — he would learn to dismiss the banner, and
    // then dismiss Paryushan with it. Only observances he actually keeps earn a
    // place here. If that changes, add it back with isDeload: true.
    chaumasa2026,
  ];

  /// Resolve a day. [fast] and [observingChauvihar] come from what he has
  /// logged; everything else is derived.
  JainDay day(
    DateTime date, {
    FastKind fast = FastKind.none,
    EveningVow? eveningVow,
  }) {
    final d = DateTime(date.year, date.month, date.day);
    final sun = _sunTimes(d);
    final inChaumasa = chaumasa2026.contains(d);

    // He does not keep an evening vow year-round, but is attempting one through
    // chaumasa. Default to the observance rather than making him tick a box
    // every morning — and let an explicit value override it.
    //
    // The default is TIVIHAR, not chauvihar: he keeps water. That single fact
    // switches off the dehydration and heat machinery that a chauvihar default
    // would (wrongly) keep firing at him.
    final vow = eveningVow ??
        (inChaumasa ? EveningVow.tivihar : EveningVow.none);

    final navkarsi = sun.sunrise.add(const Duration(minutes: 48));
    final lastMeal =
        sun.sunset.subtract(Duration(minutes: lastMealMarginMinutes));

    ObservanceWindow? match;
    for (final w in windows) {
      if (w.contains(d)) {
        match = w;
        break;
      }
    }

    return JainDay(
      date: d,
      sunrise: sun.sunrise,
      sunset: sun.sunset,
      navkarsi: navkarsi,
      lastMealBy: lastMeal,
      fast: fast,
      inChaumasa: inChaumasa,
      eveningVow: vow,
      window: match,
      suggestion: suggestFor(d),
    );
  }

  /// Days remaining in chaumasa, for the "14 weeks left" framing that makes the
  /// restricted block feel finite rather than permanent.
  int chaumasaDaysLeft([DateTime? from]) {
    final t = from ?? DateTime.now();
    final d = DateTime(t.year, t.month, t.day);
    if (!chaumasa2026.contains(d)) return 0;
    return chaumasa2026.end.difference(d).inDays;
  }

  // ------------------------------------------------------------------ tithi

  /// The tithi running at a given instant, 1–30.
  ///
  /// A tithi is the time it takes the moon to gain 12 degrees of elongation on
  /// the sun, so `tithi = floor(elongation / 12) + 1`. 1–15 are the bright
  /// fortnight (shukla / *sud*), 16–30 the dark (krishna / *vad*).
  ///
  /// The lunar term is Meeus' abbreviated series, good to roughly 0.3 degrees.
  /// The moon moves ~13 deg/day, so that is about half an hour of error on a
  /// tithi boundary — comfortably inside the day-level precision this is used
  /// for, and well inside the day that Deravasi and Sthanakvasi panchangs can
  /// already differ by.
  ///
  /// Checked against two independently sourced anchors: **15 Sep 2026 comes out
  /// Shukla 4** (Samvatsari, Bhadrapada Shukla Chaturthi) and **24 Nov 2026
  /// comes out Shukla 15** (Kartik Purnima, the chaumasa close). Both exact.
  int tithiAt(DateTime localInstant) {
    final utHours = localInstant.hour +
        localInstant.minute / 60.0 -
        tzOffsetMinutes / 60.0;
    final n = _julianDay(localInstant) + utHours / 24.0 - 2451545.0;

    final g = _norm360(357.529 + 0.98560028 * n);
    final q = _norm360(280.459 + 0.98564736 * n);
    final sun = _norm360(
        q + 1.915 * math.sin(_rad(g)) + 0.020 * math.sin(_rad(2 * g)));

    final lm = _norm360(218.316 + 13.176396 * n);
    final mm = _norm360(134.963 + 13.064993 * n);
    final dArg = lm - sun; // elongation, used by the correction terms

    final moon = _norm360(lm +
        6.289 * math.sin(_rad(mm)) +
        1.274 * math.sin(_rad(2 * dArg - mm)) +
        0.658 * math.sin(_rad(2 * dArg)) -
        0.186 * math.sin(_rad(g)) -
        0.059 * math.sin(_rad(2 * dArg - 2 * mm)) -
        0.057 * math.sin(_rad(2 * dArg - mm - g)));

    return (_norm360(moon - sun) / 12).floor() + 1;
  }

  /// The tithi running at sunrise, which is the one a day is named for.
  int tithiOnDay(DateTime date) => tithiAt(_sunTimes(date).sunrise);

  /// Sud Pancham — Shukla Panchami. His personal monthly fast, kept for about
  /// two years, so it recurs roughly every 29–30 days rather than on a fixed
  /// calendar date.
  bool isSudPancham(DateTime date) => tithiOnDay(date) == 5;

  /// Upcoming Sud Pancham dates, so the training block can be planned around
  /// them instead of colliding with them.
  List<DateTime> sudPanchamsBetween(DateTime from, DateTime to) {
    final out = <DateTime>[];
    var d = DateTime(from.year, from.month, from.day);
    final end = DateTime(to.year, to.month, to.day);
    while (!d.isAfter(end)) {
      if (isSudPancham(d)) out.add(d);
      d = d.add(const Duration(days: 1));
    }
    return out;
  }

  // ------------------------------------------------------------ suggestions

  /// Samvatsari 2026 — the last day of Paryushan, and his one planned full fast
  /// inside it.
  static final samvatsari2026 = DateTime(2026, 9, 15);

  /// What the calendar believes today is.
  ///
  /// Encodes his stated practice: **ekasana for the first seven days of
  /// Paryushan, a tivihar fast on Samvatsari, and a tivihar fast every Sud
  /// Pancham.** He does not keep Navpad Ayambil Oli, so October is not flagged.
  /// All his fasts keep water.
  FastSuggestion? suggestFor(DateTime date) {
    final d = DateTime(date.year, date.month, date.day);

    if (_sameDay(d, samvatsari2026)) {
      return const FastSuggestion(
        FastKind.tivihar,
        'Samvatsari — the last day of Paryushan.',
      );
    }
    final paryushan = windows.firstWhere((w) => w.name == 'Paryushan');
    if (paryushan.contains(d)) {
      return const FastSuggestion(
        FastKind.ekasana,
        'Paryushan — one meal, one sitting.',
      );
    }
    if (isSudPancham(d)) {
      return const FastSuggestion(
        FastKind.tivihar,
        'Sud Pancham — your monthly fast. Water permitted in daylight.',
      );
    }
    return null;
  }

  static bool _sameDay(DateTime a, DateTime b) =>
      a.year == b.year && a.month == b.month && a.day == b.day;

  // ------------------------------------------------------------- solar maths

  /// NOAA solar position algorithm.
  ///
  /// Accurate to well under a minute at this latitude, which is far tighter
  /// than the 15-minute safety margin on the meal deadline — so rounding here
  /// can never be what causes a broken vow.
  _SunTimes _sunTimes(DateTime d) {
    final jd = _julianDay(d);
    final t = (jd - 2451545.0) / 36525.0;

    // Geometric mean longitude and anomaly of the sun.
    final l0 = _norm360(280.46646 + t * (36000.76983 + t * 0.0003032));
    final m = 357.52911 + t * (35999.05029 - 0.0001537 * t);
    final e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t);

    // Equation of centre, and the true/apparent longitude it produces.
    final c = math.sin(_rad(m)) * (1.914602 - t * (0.004817 + 0.000014 * t)) +
        math.sin(_rad(2 * m)) * (0.019993 - 0.000101 * t) +
        math.sin(_rad(3 * m)) * 0.000289;
    final trueLong = l0 + c;
    final omega = 125.04 - 1934.136 * t;
    final lambda = trueLong - 0.00569 - 0.00478 * math.sin(_rad(omega));

    // Obliquity of the ecliptic, corrected for nutation.
    final eps0 = 23.0 +
        (26.0 +
                ((21.448 - t * (46.815 + t * (0.00059 - t * 0.001813)))) / 60.0) /
            60.0;
    final eps = eps0 + 0.00256 * math.cos(_rad(omega));

    final decl = math.asin(math.sin(_rad(eps)) * math.sin(_rad(lambda)));

    // Equation of time, in minutes.
    final y = math.pow(math.tan(_rad(eps / 2)), 2).toDouble();
    final eqTime = 4 *
        _deg(y * math.sin(2 * _rad(l0)) -
            2 * e * math.sin(_rad(m)) +
            4 * e * y * math.sin(_rad(m)) * math.cos(2 * _rad(l0)) -
            0.5 * y * y * math.sin(4 * _rad(l0)) -
            1.25 * e * e * math.sin(2 * _rad(m)));

    // 90.833 deg is the standard zenith for sunrise/sunset: 90 deg plus
    // refraction and the sun's apparent radius.
    final cosHa = math.cos(_rad(90.833)) /
            (math.cos(_rad(latitude)) * math.cos(decl)) -
        math.tan(_rad(latitude)) * math.tan(decl);

    // Guards against a polar day/night, which cannot happen at 23 deg N but
    // would otherwise produce NaN if this class were ever reused elsewhere.
    if (cosHa >= 1) {
      return _SunTimes(
        DateTime(d.year, d.month, d.day, 12),
        DateTime(d.year, d.month, d.day, 12),
      );
    }
    if (cosHa <= -1) {
      return _SunTimes(
        DateTime(d.year, d.month, d.day, 0),
        DateTime(d.year, d.month, d.day, 23, 59),
      );
    }

    final ha = _deg(math.acos(cosHa));
    final solarNoon = 720 - 4 * longitude - eqTime + tzOffsetMinutes;

    return _SunTimes(
      _atMinutes(d, solarNoon - 4 * ha),
      _atMinutes(d, solarNoon + 4 * ha),
    );
  }

  static DateTime _atMinutes(DateTime d, double minutesFromMidnight) {
    final m = minutesFromMidnight.round();
    return DateTime(d.year, d.month, d.day).add(Duration(minutes: m));
  }

  static double _julianDay(DateTime d) {
    var y = d.year;
    var m = d.month;
    if (m <= 2) {
      y -= 1;
      m += 12;
    }
    final a = (y / 100).floor();
    final b = 2 - a + (a / 4).floor();
    return (365.25 * (y + 4716)).floor() +
        (30.6001 * (m + 1)).floor() +
        d.day +
        b -
        1524.5;
  }

  static double _rad(double deg) => deg * math.pi / 180.0;
  static double _deg(double rad) => rad * 180.0 / math.pi;
  static double _norm360(double v) {
    final r = v % 360.0;
    return r < 0 ? r + 360.0 : r;
  }
}

class _SunTimes {
  const _SunTimes(this.sunrise, this.sunset);
  final DateTime sunrise;
  final DateTime sunset;
}
