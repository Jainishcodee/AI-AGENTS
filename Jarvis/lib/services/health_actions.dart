/// The action checklist — what to do, in what order, and when to judge it.
///
/// This is the catalogue only. Status lives in `health.db`, so revising the plan
/// never needs a database migration, and the plan itself never carries personal
/// data into tracked source.
///
/// Two kinds of entry, and the difference matters:
///
/// **One-off** actions are done and stay done — a blood draw, a tape measure
/// round the navel, buying plates.
///
/// **Trials** have a start date and a verdict date, because the whole point is
/// the comparison. Switching toothpaste and then forgetting when you switched
/// turns an eight-week experiment into a vague impression. The start date IS the
/// measurement, which is why [HealthDb.startMilestone] refuses to reset it.
library;

enum ActionKind { oneOff, trial }

class HealthAction {
  const HealthAction({
    required this.key,
    required this.title,
    required this.why,
    required this.kind,
    this.detail,
    this.trialWeeks,
    this.blocking = false,
  });

  final String key;
  final String title;

  /// One line, in plain terms. Shown on the card.
  final String why;

  final ActionKind kind;

  /// The specifics — what to ask for, what to buy, what it costs.
  final String? detail;

  /// How long before the trial can be judged. Null for one-offs.
  final int? trialWeeks;

  /// Sits in the red slot at the top until it is done.
  final bool blocking;
}

/// An action with its stored status folded in.
class ResolvedAction {
  const ResolvedAction({
    required this.action,
    required this.started,
    required this.done,
    required this.now,
  });

  final HealthAction action;
  final DateTime? started;
  final DateTime? done;
  final DateTime now;

  bool get isDone => done != null;
  bool get isActive => started != null && done == null;
  bool get notStarted => started == null && done == null;

  /// Weeks elapsed since the trial began, 1-based.
  int? get trialWeek {
    if (started == null || action.trialWeeks == null) return null;
    return (now.difference(started!).inDays ~/ 7) + 1;
  }

  /// When the trial can be judged.
  DateTime? get judgeOn {
    if (started == null || action.trialWeeks == null) return null;
    return started!.add(Duration(days: action.trialWeeks! * 7));
  }

  bool get trialReady {
    final j = judgeOn;
    return j != null && !now.isBefore(j);
  }

  /// 0..1 through the trial window.
  double get trialProgress {
    if (started == null || action.trialWeeks == null) return 0;
    final total = action.trialWeeks! * 7;
    final elapsed = now.difference(started!).inDays;
    return (elapsed / total).clamp(0.0, 1.0);
  }
}

class HealthActions {
  /// Ordered by what should happen next.
  ///
  /// The dentist entry sits first and is expected to be ticked immediately —
  /// it stays in the list rather than being deleted so the record of *when* it
  /// happened survives, and so the follow-up below has something to hang off.
  static const catalogue = <HealthAction>[
    HealthAction(
      key: 'dentist',
      title: 'Periodontal exam',
      why: 'Mobile teeth at 20 is the one finding that does not wait.',
      kind: ActionKind.oneOff,
      detail: 'Probing depths, radiographs, mobility grading, bleeding on '
          'probing. Anything less is a look, not an exam.',
      blocking: true,
    ),
    HealthAction(
      key: 'bloods',
      title: 'Blood panel',
      why: 'Recurrent mouth ulcers are a recognised reason to screen, and a '
          'strict Jain diet is a high-risk one.',
      kind: ActionKind.oneOff,
      detail: 'CBC with differential · B12 · ferritin WITH CRP · folate · '
          'tTG-IgA + total IgA · HbA1c. Roughly Rs 1,200–2,000 at Thyrocare, '
          'Metropolis or Lal Path. Do NOT go gluten-free before the coeliac '
          'test — it invalidates the result.',
      blocking: true,
    ),
    HealthAction(
      key: 'toothpaste',
      title: 'SLS-free toothpaste trial',
      why: 'Cheap experiment on the ulcers. Evidence is limited, so it needs a '
          'before and after, not an impression.',
      kind: ActionKind.trial,
      trialWeeks: 8,
      detail: 'Log ulcer count weekly. Without a baseline there is nothing to '
          'compare against, and the trial answers nothing.',
    ),
    HealthAction(
      key: 'waist',
      title: 'Baseline waist',
      why: 'The primary progress metric. Weight will barely move; this will.',
      kind: ActionKind.oneOff,
      detail: 'At the navel, morning, before eating. Indian male action '
          'threshold is 90 cm.',
    ),
    HealthAction(
      key: 'height',
      title: 'Baseline height',
      why: 'Replaces the estimate, and sets the posture reference.',
      kind: ActionKind.oneOff,
      detail: 'Barefoot, heels and back to a wall, MORNING. Diurnal loss is '
          '~19 mm, so an evening measurement reads ~2 cm short.',
    ),
    HealthAction(
      key: 'ketoconazole',
      title: 'Ketoconazole 2% scalp trial',
      why: 'Treats the scalp inflammation before drawing any conclusion about '
          'the hairline.',
      kind: ActionKind.trial,
      trialWeeks: 12,
      detail: 'Ketomac or Scalpe+, twice weekly, left on the scalp 5 minutes. '
          'Reassess the hairline at 12 weeks with DRY hair — wet hair makes '
          'density unreadable.',
    ),
    HealthAction(
      key: 'plates',
      title: 'Dumbbell plates to 20–24 kg/hand',
      why: 'The 15 kg ceiling caps goblet squats in about 6–8 weeks.',
      kind: ActionKind.oneOff,
      detail: 'Rs 500–900. You own the handles already, so this is plates only '
          '— the best value purchase on the list.',
    ),
    HealthAction(
      key: 'pullup',
      title: 'Doorway pull-up bar',
      why: 'Pulling is the hole in the old routine and the fix for desk posture.',
      kind: ActionKind.oneOff,
      detail: 'Rs 700–2,000. Leverage/doorway-frame model, not screw-in. Test '
          'the frame with a slow partial hang first.',
    ),
    HealthAction(
      key: 'creatine',
      title: 'Creatine 5 g/day',
      why: 'Strongest evidence on the list precisely because you are a lifelong '
          'vegetarian — you start 20–30% depleted.',
      kind: ActionKind.oneOff,
      detail: 'Plain micronized monohydrate POWDER, not capsules (gelatin). '
          '~Rs 10/day. Expect 1–2 kg of water weight in the first 3 weeks — '
          'the app will discount the scale for you.',
    ),
    HealthAction(
      key: 'dentist_recheck',
      title: 'Dental recheck',
      why: 'A visual exam that finds nothing does not fully close a mobility '
          'question — early bone loss is found by probing, not by looking.',
      kind: ActionKind.trial,
      trialWeeks: 12,
      detail: 'If the first visit did not include a probing chart and X-rays, '
          'ask for them at the recheck. If the mobility is gone by then, the '
          'question is closed.',
    ),
  ];

  static HealthAction? byKey(String key) {
    for (final a in catalogue) {
      if (a.key == key) return a;
    }
    return null;
  }

  /// Fold stored status into the catalogue.
  static List<ResolvedAction> resolve(
    Map<String, ({DateTime? started, DateTime? done, String? note})> status, {
    DateTime? now,
  }) {
    final t = now ?? DateTime.now();
    return catalogue.map((a) {
      final s = status[a.key];
      return ResolvedAction(
        action: a,
        started: s?.started,
        done: s?.done,
        now: t,
      );
    }).toList();
  }

  /// The single thing to do next.
  ///
  /// Blocking items first, then the rest in catalogue order. A trial that is
  /// merely running is not "next" — it is already happening — so active trials
  /// are skipped unless they are ready to judge.
  static ResolvedAction? next(List<ResolvedAction> resolved) {
    for (final r in resolved) {
      if (r.action.blocking && !r.isDone) return r;
    }
    for (final r in resolved) {
      if (r.trialReady && !r.isDone) return r;
      if (r.notStarted) return r;
    }
    return null;
  }

  static List<ResolvedAction> outstanding(List<ResolvedAction> resolved) =>
      resolved.where((r) => !r.isDone).toList();

  static List<ResolvedAction> runningTrials(List<ResolvedAction> resolved) =>
      resolved
          .where((r) =>
              r.action.kind == ActionKind.trial && r.isActive)
          .toList();
}
