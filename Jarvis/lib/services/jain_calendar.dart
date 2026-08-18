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
          'No training. ~36 h without food, water only in daylight.',
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
    required this.observingChauvihar,
    this.window,
  });

  final DateTime date;
  final DateTime sunrise;
  final DateTime sunset;

  /// Sunrise + 48 min. The earliest anything may be taken under most vows.
  final DateTime navkarsi;

  /// The practical deadline for the last bite or sip: sunset minus a margin.
  ///
  /// Chauvihar means the last intake is *before* sunset, not at it. Cutting it
  /// fine against an astronomical instant is how a vow gets broken by accident,
  /// so the app always shows a deadline with the margin already subtracted.
  final DateTime lastMealBy;

  final FastKind fast;
  final bool inChaumasa;

  /// Whether he is keeping chauvihar today. Distinct from [fast] — he can keep
  /// chauvihar (nothing after sunset) while eating normally during the day.
  final bool observingChauvihar;

  final ObservanceWindow? window;

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
    if (!observingChauvihar) return null;
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
    ObservanceWindow(
      name: 'Navpad Ayambil Oli',
      start: DateTime(2026, 10, 17),
      end: DateTime(2026, 10, 26),
      note: 'Nine consecutive ayambils: one bland meal a day, no milk, curd, '
          'ghee, oil, sugar, fruit or green vegetables. Expect ~9 days at '
          '40–60 g protein. Maintain, do not progress.',
      isDeload: true,
    ),
    chaumasa2026,
  ];

  /// Resolve a day. [fast] and [observingChauvihar] come from what he has
  /// logged; everything else is derived.
  JainDay day(
    DateTime date, {
    FastKind fast = FastKind.none,
    bool? observingChauvihar,
  }) {
    final d = DateTime(date.year, date.month, date.day);
    final sun = _sunTimes(d);
    final inChaumasa = chaumasa2026.contains(d);

    // He does not keep chauvihar year-round, but is attempting it through
    // chaumasa. Default to the observance rather than making him tick a box
    // every morning — and let an explicit value override it.
    final chauvihar = observingChauvihar ?? inChaumasa;

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
      observingChauvihar: chauvihar,
      window: match,
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
