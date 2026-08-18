/// "Saitama 2.0" — the training programme, as data.
///
/// The design constraint here is not physiological, it's behavioural. He held
/// the original Saitama routine (100 push-ups / 100 sit-ups / 100 squats) daily
/// for months in 2021, and adherence dominates programme quality: a mediocre
/// programme run for twelve months beats an optimal one abandoned in week five.
/// No programming variable in the literature has an effect size close to the
/// difference between training and not training.
///
/// So the ritual is preserved exactly — daily, named, countable, no decisions at
/// execution time, no equipment dependency, a visible finish each day — and only
/// the contents change. What changes and why:
///
/// - **Pulling is added.** The original is all push, all quad, all trunk
///   flexion, with literally zero pulling. For someone with desk posture chasing
///   a posture goal, months of unopposed pushing is directionally wrong.
/// - **Unloaded squats are demoted to warm-up.** They sit around 10–15% of 1RM,
///   below the ~30% floor where hypertrophy happens at all. That is leg cardio,
///   and legs are exactly where he has the most to gain.
/// - **Sit-ups become anti-movement core.** A weaker case than the internet
///   claims, but a poor cost/benefit trunk choice regardless.
/// - **The 10 km run is removed outright.** See [runKmForWeek].
library;

import 'jain_calendar.dart';

/// Which layer a movement belongs to.
enum Tier {
  /// Every single day, no exceptions, deliberately easy enough for a bad day.
  ritual,

  /// Mon/Wed/Fri — the same tally performed as heavy near-failure work.
  hard,
}

enum Pattern { push, pull, legs, core }

class Exercise {
  const Exercise({
    required this.name,
    required this.pattern,
    required this.sets,
    required this.repRange,
    this.perSide = false,
    this.note,
  });

  final String name;
  final Pattern pattern;
  final int sets;
  final String repRange;
  final bool perSide;
  final String? note;

  String get display => perSide ? '$name  $sets × $repRange /side' : '$name  $sets × $repRange';
}

class Session {
  const Session({
    required this.name,
    required this.exercises,
    this.note,
  });

  final String name;
  final List<Exercise> exercises;
  final String? note;
}

/// What the programme asks for on a given date, after the calendar has had its
/// say.
class TrainingDay {
  const TrainingDay({
    required this.date,
    required this.clearance,
    required this.session,
    required this.ritualReps,
    required this.runKm,
    required this.phase,
    required this.blockedReason,
  });

  final DateTime date;
  final TrainingClearance clearance;

  /// Null on rest, upvas, and run-only days.
  final Session? session;

  /// The daily ritual, always present — it is the thing that survives every
  /// other cancellation.
  final int ritualReps;

  final double runKm;
  final String phase;

  /// Non-null when the calendar has overridden the programme. Shown instead of
  /// the session, with the reason, because a blocked day that gives no reason
  /// is a day he will train through.
  final String? blockedReason;

  bool get canLift => clearance == TrainingClearance.full ||
      clearance == TrainingClearance.moderate;
}

class TrainingPlan {
  TrainingPlan({DateTime? startedOn})
      : startedOn = startedOn ?? DateTime(2026, 8, 18);

  /// Week 1 of the on-ramp.
  final DateTime startedOn;

  int weekOf(DateTime d) {
    final days = DateTime(d.year, d.month, d.day)
        .difference(DateTime(startedOn.year, startedOn.month, startedOn.day))
        .inDays;
    return (days ~/ 7) + 1;
  }

  /// The 12-week on-ramp.
  ///
  /// He is stacking four new stressors at once — new lifting, new running, a
  /// calorie deficit, and chaumasa fasting. Starting all four at full volume in
  /// week one is the classic pattern that ends in injury or burnout by week six.
  /// Note that the deficit deliberately does not start until week three, and
  /// only once protein is consistently above 115 g.
  String phaseFor(int week) {
    if (week <= 2) {
      return 'On-ramp · 3 days, 2 sets, 3 RIR · eat at MAINTENANCE';
    }
    if (week <= 6) {
      return 'Build · 3–4 days, 3 sets, 2 RIR · small deficit once protein >115 g';
    }
    if (week <= 12) {
      return 'Load · 4 days, 1–2 RIR, 10–14 sets/muscle/wk · deficit 350–450 kcal';
    }
    return 'Reassess · waist, photos, training log';
  }

  int setsForWeek(int week) => week <= 2 ? 2 : 3;
  String rirForWeek(int week) => week <= 2 ? '3' : (week <= 6 ? '2' : '1–2');

  /// Running volume, in km for the whole week.
  ///
  /// The single most dangerous number in the original routine was 10 km daily.
  /// The randomised trial in obese novice runners compared 3 km/week against
  /// 6 km/week: injuries were 6.9% vs 18.5%. Doubling the *starting* dose
  /// roughly tripled injury rate in four weeks. At BMI 25.3 with no running
  /// base, 70 km/week would be ~23× the safest tested starting volume, on day
  /// one. So: start at 3, add 10% a week, and reaching 10 km in a single run is
  /// a 6–9 month goal rather than a starting condition.
  double runKmForWeek(int week) {
    var km = 3.0;
    for (var i = 1; i < week; i++) {
      km *= 1.10;
    }
    return km > 25 ? 25 : double.parse(km.toStringAsFixed(1));
  }

  static const fullBodyA = Session(
    name: 'Full-Body A',
    exercises: [
      Exercise(name: 'Goblet squat', pattern: Pattern.legs, sets: 3, repRange: '8–12'),
      Exercise(name: 'One-arm DB row', pattern: Pattern.pull, sets: 3, repRange: '8–12', perSide: true),
      Exercise(name: 'DB floor press / deficit push-up', pattern: Pattern.push, sets: 3, repRange: '8–15'),
      Exercise(name: 'DB Romanian deadlift', pattern: Pattern.legs, sets: 3, repRange: '10–12'),
      Exercise(name: 'DB overhead press', pattern: Pattern.push, sets: 3, repRange: '8–12'),
      Exercise(
        name: 'Band face pull',
        pattern: Pattern.pull,
        sets: 3,
        repRange: '15',
        note: 'The posture movement. Lower traps and rear delts — the exact '
            'thing desk work switches off.',
      ),
      Exercise(name: 'Dead bug', pattern: Pattern.core, sets: 3, repRange: '8', perSide: true),
    ],
  );

  static const fullBodyB = Session(
    name: 'Full-Body B',
    exercises: [
      Exercise(
        name: 'Rear-foot-elevated split squat',
        pattern: Pattern.legs,
        sets: 3,
        repRange: '8–10',
        perSide: true,
        note: 'Unilateral halves the load needed per leg — the best fix for '
            'the dumbbell leg-loading ceiling.',
      ),
      Exercise(name: 'Chin-up / inverted row under a table', pattern: Pattern.pull, sets: 3, repRange: 'AMRAP'),
      Exercise(name: 'DB floor fly / push-up variation', pattern: Pattern.push, sets: 3, repRange: '10–15'),
      Exercise(name: 'Single-leg RDL', pattern: Pattern.legs, sets: 3, repRange: '8', perSide: true),
      Exercise(name: 'DB lateral raise', pattern: Pattern.push, sets: 3, repRange: '12–20'),
      Exercise(name: 'DB curl', pattern: Pattern.pull, sets: 3, repRange: '10–15'),
      Exercise(name: 'Side plank', pattern: Pattern.core, sets: 3, repRange: '25 s', perSide: true),
    ],
  );

  /// The daily ritual: 100 reps, split four ways so pulling is never skipped.
  static const ritual = <(Pattern, int, String)>[
    (Pattern.push, 25, 'Push-ups (knees down if needed)'),
    (Pattern.pull, 25, 'Band pull-aparts or bodyweight rows'),
    (Pattern.legs, 25, 'Air squats — warm-up pace, not training'),
    (Pattern.core, 25, 'Dead bug / plank reps — no sit-ups'),
  ];

  /// ~18 min, run daily. The strengthening element (item 7) has the best
  /// evidence in the sequence; the wall check bookends it because the postural
  /// cueing practised outside sessions was part of what worked in the trials.
  static const yogaSequence = <String>[
    'Wall tadasana — heels/sacrum/upper back/head touching, 3 slow breaths',
    'Marjaryasana–Bitilasana × 10 slow cycles',
    'Parsva Balasana (thread the needle) × 5 /side',
    'Adho Mukha Svanasana 3 × 30 s — knees bent, chase thoracic extension',
    'Anjaneyasana 2 × 45 s /side — posterior tilt, back-leg glute squeeze',
    'Bhujangasana (LOW cobra, elbows tucked) 3 × 20–30 s',
    'Salabhasana / prone Y-T lifts 3 × 8–10  ← the strengthening element',
    'Setu Bandha 3 × 30 s',
    'Towel-roll supine thoracic extension 60–90 s',
    'Supine chin tucks 10 × 5 s',
    'Savasana — 12 breaths at ~6/min',
  ];

  /// Excluded outright, with the reason attached.
  ///
  /// Neck injuries in the yoga adverse-event literature are specifically
  /// attributed to headstand and shoulderstand, and headstand is the single
  /// most-cited posture in published case reports. The listed causes — poor
  /// alignment, excess effort, inadequate instruction, self-teaching — describe
  /// exactly a returner following videos with no teacher in the room.
  static const yogaExclusions = <String, String>{
    'Sirsasana (headstand)':
        'Most-cited posture in published yoga injury reports. Not without an '
            'in-person teacher.',
    'Sarvangasana (shoulderstand)':
        'Cervical loading. Use Viparita Karani (legs up the wall) instead — '
            'most of the benefit, none of the neck.',
    'Halasana (plough)': 'Same cervical risk as shoulderstand.',
    'Full padmasana': 'Knee risk for a returner; reviews advise beginners avoid it.',
    'Kapalbhati / Bhastrika':
        'Hyperventilation — physiologically the opposite of the slow breathing '
            'that has evidence. Never during a fast: hypocapnia cuts cerebral '
            'blood flow ~30%.',
  };

  /// Resolve today.
  TrainingDay dayFor(JainDay jd) {
    final week = weekOf(jd.date);
    final clearance = jd.clearance;
    final phase = phaseFor(week);

    // Upvas and ayambil override the programme entirely. This is the rule the
    // whole module exists to enforce: chauvihar upvas is ~36 hours with no
    // water, which is categorically different from Western "fasted training"
    // where every study permitted unlimited overnight fluid. And skipping is
    // nearly free — measurable disuse atrophy takes 1–2 weeks of complete
    // inactivity, so a 36-hour fast costs nothing worth risking heatstroke for.
    if (clearance == TrainingClearance.rest) {
      return TrainingDay(
        date: jd.date,
        clearance: clearance,
        session: null,
        ritualReps: 0,
        runKm: 0,
        phase: phase,
        blockedReason: jd.fast.trainingNote,
      );
    }
    if (clearance == TrainingClearance.lightOnly) {
      return TrainingDay(
        date: jd.date,
        clearance: clearance,
        session: null,
        ritualReps: 50,
        runKm: 0,
        phase: phase,
        blockedReason: jd.fast.trainingNote,
      );
    }

    // Mon/Wed/Fri lift; Tue/Thu/Sat run. Weekday-driven rather than
    // count-driven so a missed day never shifts the whole schedule sideways.
    final wd = jd.date.weekday;
    final lifts = week <= 2
        ? const {DateTime.monday, DateTime.wednesday, DateTime.friday}
        : const {DateTime.monday, DateTime.wednesday, DateTime.friday};
    final runs = {DateTime.tuesday, DateTime.thursday, DateTime.saturday};

    Session? s;
    if (lifts.contains(wd) && clearance == TrainingClearance.full) {
      s = (wd == DateTime.wednesday) ? fullBodyB : fullBodyA;
    } else if (clearance == TrainingClearance.moderate && lifts.contains(wd)) {
      // Ekasana: one session, timed before the single meal.
      s = (wd == DateTime.wednesday) ? fullBodyB : fullBodyA;
    }

    final weekKm = runKmForWeek(week);
    final km = runs.contains(wd) ? double.parse((weekKm / 3).toStringAsFixed(1)) : 0.0;

    return TrainingDay(
      date: jd.date,
      clearance: clearance,
      session: s,
      ritualReps: 100,
      runKm: km,
      phase: phase,
      blockedReason: null,
    );
  }

  /// When the last hard set has to be finished, so the post-workout meal still
  /// lands inside the window.
  ///
  /// Under chauvihar an evening session leaves him 12+ hours post-training with
  /// no protein at all — which for someone whose actual goal is adding muscle
  /// on a low-density diet is a real problem, not a rounding error. By November
  /// this deadline lands around 16:45.
  DateTime trainByFor(JainDay jd) =>
      jd.lastMealBy.subtract(const Duration(minutes: 60));
}
