/// The asana library, and the daily sequence built from it.
///
/// Seeded from what he already practised in 2021 — halasana, uttanasana,
/// garudasana, tree pose, bhujangasana and ustrasana — plus the postures the
/// posture-and-thoracic-extension evidence actually supports. Keeping his own
/// asanas in the list matters: he has done these before, they are familiar, and
/// familiarity is most of why the 2021 block stuck.
///
/// One of his is excluded rather than kept, and the library models exclusions as
/// first-class entries instead of silently dropping them. A posture that simply
/// vanishes from a list reads as an oversight; one that appears with a reason
/// and a substitute reads as a decision, and is far more likely to be respected.
library;

/// Where a posture sits in the sequence.
enum AsanaStage {
  /// Standing calibration against a wall — the reference he re-checks against.
  calibrate,

  /// Spinal mobility, done early while cold.
  mobility,

  /// Opens the front of the hips and chest — the desk-posture antagonists.
  opener,

  /// Loaded holds. The part with the best evidence for changing the curve.
  strength,

  /// Balance and proprioception.
  balance,

  /// Down-regulation.
  closing,
}

extension AsanaStageX on AsanaStage {
  String get label => switch (this) {
        AsanaStage.calibrate => 'CALIBRATE',
        AsanaStage.mobility => 'MOBILITY',
        AsanaStage.opener => 'OPEN',
        AsanaStage.strength => 'STRENGTH',
        AsanaStage.balance => 'BALANCE',
        AsanaStage.closing => 'CLOSE',
      };
}

/// When a posture enters the programme, or why it never does.
enum AsanaStatus {
  /// In from day one.
  core,

  /// Added from week 3–4, once the basics are comfortable.
  week3,

  /// Added from week 6+.
  week6,

  /// Never, without an in-person teacher.
  excluded,
}

class Asana {
  const Asana({
    required this.name,
    required this.sanskrit,
    required this.stage,
    required this.status,
    required this.hold,
    required this.seconds,
    required this.purpose,
    required this.cues,
    this.caution,
    this.substitute,
    this.alreadyPractised = false,
    this.restorative = false,
  });

  final String name;
  final String sanskrit;
  final AsanaStage stage;
  final AsanaStatus status;

  /// Human-readable dose, e.g. "3 x 30 s".
  final String hold;

  /// Total seconds, for the sequence length estimate.
  final int seconds;

  /// Why this one is in *his* plan specifically, not yoga-in-general benefits.
  final String purpose;

  final List<String> cues;
  final String? caution;

  /// What to do instead. Only set on [AsanaStatus.excluded] entries.
  final String? substitute;

  /// True for the ones he named from 2021.
  final bool alreadyPractised;

  /// Safe on a fast day, when only restorative work is permitted.
  final bool restorative;

  bool get isExcluded => status == AsanaStatus.excluded;

  String? get entersLabel => switch (status) {
        AsanaStatus.week3 => 'FROM WEEK 3',
        AsanaStatus.week6 => 'FROM WEEK 6',
        _ => null,
      };

  /// Whether this posture is in play in a given week of the programme.
  bool availableInWeek(int week) => switch (status) {
        AsanaStatus.core => true,
        AsanaStatus.week3 => week >= 3,
        AsanaStatus.week6 => week >= 6,
        AsanaStatus.excluded => false,
      };
}

class YogaLibrary {
  /// The full library, in sequence order.
  ///
  /// Order is deliberate and is not alphabetical: calibrate, mobilise while
  /// cold, open the front, then load. The strength entries (salabhasana, prone
  /// Y-T) sit late because they are the ones that actually change a thoracic
  /// curve, and they want a warm spine.
  static const all = <Asana>[
    Asana(
      name: 'Mountain, at a wall',
      sanskrit: 'Tadasana',
      stage: AsanaStage.calibrate,
      status: AsanaStatus.core,
      hold: '3 slow breaths',
      seconds: 60,
      purpose:
          'The reference position. Everything else is measured against how this '
          'felt at the start and at the end.',
      cues: [
        'Heels, sacrum, upper back and back of the head all touching the wall',
        'If the head will not reach without lifting the chin, do not force it — '
            'that gap IS the thoracic curve you are working on',
        'Breathe into the sides of the ribs, not the belly',
      ],
      restorative: true,
    ),
    Asana(
      name: 'Cat–Cow',
      sanskrit: 'Marjaryasana–Bitilasana',
      stage: AsanaStage.mobility,
      status: AsanaStatus.core,
      hold: '10 slow cycles',
      seconds: 120,
      purpose:
          'Segmental spinal movement before anything is loaded. The cheapest '
          'way to find which parts of your back actually move.',
      cues: [
        'Move one vertebra at a time — slower than feels natural',
        'Let the head follow the spine, do not lead with it',
        'Match one full cycle to one full breath',
      ],
      restorative: true,
    ),
    Asana(
      name: 'Thread the Needle',
      sanskrit: 'Parsva Balasana',
      stage: AsanaStage.mobility,
      status: AsanaStatus.core,
      hold: '5 /side',
      seconds: 120,
      purpose:
          'Thoracic rotation — the movement a desk takes away first, and the one '
          'no amount of stretching the lower back replaces.',
      cues: [
        'Hips stay stacked over the knees; the movement is in the ribs',
        'Reach the arm through and let the shoulder rest on the floor',
        'Do not push into the neck',
      ],
      restorative: true,
    ),
    Asana(
      name: 'Standing Forward Bend',
      sanskrit: 'Uttanasana',
      stage: AsanaStage.mobility,
      status: AsanaStatus.core,
      hold: '2 x 45 s',
      seconds: 90,
      purpose:
          'Posterior chain length. Useful before Romanian deadlifts and split '
          'squats, which is where your leg work now lives.',
      cues: [
        'Bend the knees as much as needed — hamstring length is not the point',
        'Hinge from the hips, do not round from the waist',
        'Let the head hang heavy',
      ],
      caution:
          'Come up slowly. Standing up fast from a full forward fold is the '
          'classic way to get light-headed — more so on a low-calorie day.',
      alreadyPractised: true,
    ),
    Asana(
      name: 'Downward Dog',
      sanskrit: 'Adho Mukha Svanasana',
      stage: AsanaStage.opener,
      status: AsanaStatus.core,
      hold: '3 x 30 s',
      seconds: 120,
      purpose:
          'Shoulder flexion and thoracic extension. The goal is the upper back, '
          'not the hamstrings.',
      cues: [
        'Keep the knees freely bent — straight legs are NOT the target here',
        'Push the floor away and let the chest sink toward the thighs',
        'Ears between the arms, not dropped below',
      ],
    ),
    Asana(
      name: 'Low Lunge',
      sanskrit: 'Anjaneyasana',
      stage: AsanaStage.opener,
      status: AsanaStatus.core,
      hold: '2 x 45 s /side',
      seconds: 180,
      purpose:
          'Hip flexor length. Nine hours of sitting shortens these, and they '
          'pull the pelvis into a tilt that costs you standing height.',
      cues: [
        'Tuck the tailbone under BEFORE leaning forward — otherwise the stretch '
            'lands in the lower back instead of the hip',
        'Squeeze the glute of the back leg',
        'Cushion under the back knee',
      ],
    ),
    Asana(
      name: 'Cobra (low)',
      sanskrit: 'Bhujangasana',
      stage: AsanaStage.opener,
      status: AsanaStatus.core,
      hold: '3 x 20–30 s',
      seconds: 90,
      purpose:
          'Thoracic extension against gravity. One you already know — the only '
          'change is going lower than you probably did.',
      cues: [
        'LOW cobra: elbows tucked in, pubic bone stays down',
        'Height is not the goal — where the bend happens is the goal',
        'If it pinches the lower back, you have gone too high',
      ],
      alreadyPractised: true,
    ),
    Asana(
      name: 'Locust / Prone Y-T',
      sanskrit: 'Salabhasana',
      stage: AsanaStage.strength,
      status: AsanaStatus.core,
      hold: '3 x 8–10',
      seconds: 180,
      purpose:
          'THE one with the best evidence in this sequence. Strengthening beats '
          'stretching for changing a thoracic curve — and this is the '
          'strengthening.',
      cues: [
        'Lift the chest and arms, not the chin',
        'Y shape then T shape — lower traps and rhomboids',
        'Reps, not a hold. Lower under control',
      ],
    ),
    Asana(
      name: 'Bridge',
      sanskrit: 'Setu Bandha Sarvangasana',
      stage: AsanaStage.strength,
      status: AsanaStatus.core,
      hold: '3 x 30 s',
      seconds: 120,
      purpose:
          'Glutes and posterior chain, plus a front-of-hip opener, with no load '
          'on the neck.',
      cues: [
        'Drive through the heels, ribs stay down',
        'Weight on the shoulders — never turn the head once you are up',
      ],
      restorative: true,
    ),
    Asana(
      name: 'Eagle',
      sanskrit: 'Garudasana',
      stage: AsanaStage.balance,
      status: AsanaStatus.core,
      hold: '30 s /side',
      seconds: 90,
      purpose:
          'Opens between the shoulder blades — the exact spot that closes up at '
          'a laptop. One of yours, and a genuinely good pick for your goal.',
      cues: [
        'Wrap the arms first, then lift the elbows to shoulder height',
        'Push the forearms away from the face to widen the upper back',
        'Legs can stay uncrossed while balance is still poor',
      ],
      alreadyPractised: true,
    ),
    Asana(
      name: 'Tree',
      sanskrit: 'Vrikshasana',
      stage: AsanaStage.balance,
      status: AsanaStatus.core,
      hold: '30–45 s /side',
      seconds: 90,
      purpose:
          'Single-leg balance and hip stability. Transfers directly to split '
          'squats and single-leg RDLs, which are now your main leg movements.',
      cues: [
        'Foot to the calf or the inner thigh — NEVER against the knee',
        'Fix the eyes on one point',
        'Press the foot and the leg into each other',
      ],
      alreadyPractised: true,
    ),
    Asana(
      name: 'Camel',
      sanskrit: 'Ustrasana',
      stage: AsanaStage.opener,
      status: AsanaStatus.week3,
      hold: '2 x 20–30 s',
      seconds: 60,
      purpose:
          'The deepest front-body opener in the sequence, and the strongest '
          'single counter to a desk-rounded upper back. This is the backward '
          'bend where you reach for your heels.',
      cues: [
        'START with hands on the sacrum, NOT reaching for the heels',
        'Hips stay stacked over the knees — do not sit back',
        'Lift the chest first; the head goes back LAST, and only if it is easy',
      ],
      caution:
          'Enters from week 3, not day one. Dropping the head back cold is how '
          'people hurt their neck in this one. If you feel it in the lower back '
          'rather than the front of the hips, come out.',
      alreadyPractised: true,
    ),
    Asana(
      name: 'Bow',
      sanskrit: 'Dhanurasana',
      stage: AsanaStage.opener,
      status: AsanaStatus.week6,
      hold: '2 x 20 s',
      seconds: 40,
      purpose:
          'Full front-body extension. Earned once cobra and camel are both '
          'comfortable.',
      cues: [
        'Kick the feet INTO the hands rather than pulling with the arms',
        'Breathe — this one makes people hold their breath',
      ],
      caution: 'Week 6 at the earliest, and only if camel is easy by then.',
    ),
    Asana(
      name: 'Thoracic extension over a towel roll',
      sanskrit: '—',
      stage: AsanaStage.strength,
      status: AsanaStatus.core,
      hold: '60–90 s',
      seconds: 90,
      purpose:
          'A rolled towel under the mid-back, arms overhead. Passive, boring, '
          'and one of the highest-value 90 seconds in the sequence for you.',
      cues: [
        'Roll goes at the mid-back, not the lower back',
        'Knees bent, feet flat',
        'Arms overhead only as far as they go without the ribs flaring',
      ],
      restorative: true,
    ),
    Asana(
      name: 'Supine chin tucks',
      sanskrit: '—',
      stage: AsanaStage.strength,
      status: AsanaStatus.core,
      hold: '10 x 5 s',
      seconds: 60,
      purpose:
          'Deep neck flexors — the forward-head half of the posture problem. '
          'Any consistent neck work beats a clever protocol done twice.',
      cues: [
        'Nod as if making a double chin, do not lift the head',
        'Hold 5 s, release fully',
      ],
      restorative: true,
    ),
    Asana(
      name: 'Legs up the wall',
      sanskrit: 'Viparita Karani',
      stage: AsanaStage.closing,
      status: AsanaStatus.core,
      hold: '2–5 min',
      seconds: 150,
      purpose:
          'The substitute for the inversions excluded below. Most of the '
          'perceived benefit, none of the load on the neck. Safe on a fast day.',
      cues: [
        'Sit side-on to the wall, then swing the legs up',
        'A cushion under the hips if the hamstrings complain',
      ],
      restorative: true,
    ),
    Asana(
      name: 'Savasana + slow breathing',
      sanskrit: 'Savasana',
      stage: AsanaStage.closing,
      status: AsanaStatus.core,
      hold: '12 breaths at ~6/min',
      seconds: 120,
      purpose:
          'Roughly six breaths a minute is the one breathing practice with '
          'solid, mechanistically understood evidence. Real, but acute — it will '
          'not fix a shifted sleep phase.',
      cues: [
        'In for about 4 s, out for about 6 s',
        'The long exhale is the active ingredient',
        'End with the wall check you started on',
      ],
      restorative: true,
    ),

    // ---- Excluded. Present on purpose, with reasons and substitutes. ----
    Asana(
      name: 'Plough',
      sanskrit: 'Halasana',
      stage: AsanaStage.closing,
      status: AsanaStatus.excluded,
      hold: '—',
      seconds: 0,
      purpose:
          'One you practised in 2021, and the one I am asking you to drop. It '
          'loads a fully flexed neck with most of your bodyweight.',
      cues: [],
      caution:
          'Neck injuries in the published yoga case reports are attributed '
          'specifically to plough, shoulderstand and headstand. The listed '
          'causes — self-teaching, no instructor, excess effort — describe '
          'learning from videos exactly.',
      substitute:
          'Legs up the wall (Viparita Karani), or a supine hamstring stretch '
          'with a strap. You lose nothing you were actually getting.',
      alreadyPractised: true,
    ),
    Asana(
      name: 'Shoulderstand',
      sanskrit: 'Sarvangasana',
      stage: AsanaStage.closing,
      status: AsanaStatus.excluded,
      hold: '—',
      seconds: 0,
      purpose: 'Same cervical loading as plough.',
      cues: [],
      caution: 'Cited alongside headstand in the yoga injury literature.',
      substitute: 'Legs up the wall (Viparita Karani).',
    ),
    Asana(
      name: 'Headstand',
      sanskrit: 'Sirsasana',
      stage: AsanaStage.closing,
      status: AsanaStatus.excluded,
      hold: '—',
      seconds: 0,
      purpose:
          'The single most-cited posture in published yoga injury case reports.',
      cues: [],
      caution:
          'Not without an in-person teacher. Serious adverse events across the '
          'yoga literature run about 1.9%, concentrated here.',
      substitute: 'Legs up the wall, or downward dog for the shoulder work.',
    ),
    Asana(
      name: 'Kapalbhati / Bhastrika',
      sanskrit: 'Kapalabhati, Bhastrika',
      stage: AsanaStage.closing,
      status: AsanaStatus.excluded,
      hold: '—',
      seconds: 0,
      purpose:
          'Forceful breathing. Physiologically the OPPOSITE of the slow '
          'breathing that has evidence behind it.',
      cues: [],
      caution:
          'Hyperventilation drops CO2, which cuts cerebral blood flow by around '
          '30%. Never on a fast day — fasting plus heat plus standing up '
          'supplies exactly the extra stressors that turn that into fainting. '
          'The "detox" and "belly fat" claims are unsupported.',
      substitute:
          'Slow breathing at ~6 breaths/min in savasana. Better evidence, no '
          'risk.',
    ),
  ];

  static List<Asana> get practising =>
      all.where((a) => !a.isExcluded).toList();

  static List<Asana> get excluded => all.where((a) => a.isExcluded).toList();

  /// The ones he named from 2021, whatever their status now.
  static List<Asana> get his => all.where((a) => a.alreadyPractised).toList();

  /// The sequence for a given week.
  static List<Asana> sequenceForWeek(int week) =>
      practising.where((a) => a.availableInWeek(week)).toList();

  /// The cut-down sequence for a fast day, when only restorative work is safe.
  ///
  /// Same rule the training screen enforces, applied to yoga: no long holds, no
  /// loaded extension, no forceful breathing.
  static List<Asana> get restorativeOnly =>
      practising.where((a) => a.restorative).toList();

  static int minutesFor(List<Asana> seq) =>
      (seq.fold<int>(0, (a, b) => a + b.seconds) / 60).round();
}
