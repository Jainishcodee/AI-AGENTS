import 'dart:async';

import 'package:flutter/material.dart';

import '../services/health_db.dart';
import '../services/jain_calendar.dart';
import '../services/nutrition_engine.dart';
import '../services/training_plan.dart';
import '../services/yoga_library.dart';
import 'yoga_screen.dart';

/// The health tab.
///
/// Ordered by what actually decides the day rather than by what is fun to look
/// at. The eating-window countdown leads because it is the only thing here with
/// a hard deadline that moves — sunset in Ahmedabad drifts 76 minutes across
/// chaumasa, so "dinner before sunset" stops being a fixed habit and becomes a
/// number worth showing. Training clearance sits second because on a fast day
/// it overrides everything below it.
class HealthScreen extends StatefulWidget {
  const HealthScreen({
    super.key,
    required this.db,
    required this.calendar,
    required this.plan,
  });

  final HealthDb db;
  final JainCalendar calendar;
  final TrainingPlan plan;

  @override
  State<HealthScreen> createState() => _HealthScreenState();
}

class _HealthScreenState extends State<HealthScreen> {
  static const _red = Color(0xFFE74848);
  static const _teal = Color(0xFF00E5C9);
  static const _amber = Color(0xFFFFB347);
  static const _surface = Color(0xFF18101A);

  Timer? _tick;
  JainDay? _today;
  HealthDay? _log;
  WeightTrend? _trend;
  NutritionTargets? _targets;
  bool _loading = true;

  /// True until height, birth year and a first weight exist in the database.
  bool _needsSetup = false;

  @override
  void initState() {
    super.initState();
    _load();
    // One tick a minute is enough for a countdown measured in hours, and keeps
    // this off the per-second rebuild path while the tab sits in the
    // IndexedStack.
    _tick = Timer.periodic(const Duration(minutes: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    final key = HealthDb.dayKey();
    final log = await widget.db.getDay(key);
    final trend = await widget.db.weightTrend();
    final calibrated = await widget.db.calibratedTdee();
    final profile = await widget.db.profile();

    final jd = widget.calendar.day(
      DateTime.now(),
      fast: log?.fast ?? FastKind.none,
      eveningVow: log?.eveningVow,
    );

    // Targets need a body to compute against. Height and age come from the
    // database, never from a constant in this file — see HealthDb.profile.
    // Weight falls back to the last logged reading rather than to a guess.
    NutritionTargets? targets;
    final kg = trend.average ?? log?.weightKg;
    if (profile != null && kg != null) {
      targets = NutritionEngine.targets(
        kg: kg,
        cm: profile.heightCm,
        age: profile.age,
        calibratedTdee: calibrated,
      );
    }

    if (!mounted) return;
    setState(() {
      _today = jd;
      _log = log;
      _trend = trend;
      _targets = targets;
      _needsSetup = profile == null || kg == null;
      _loading = false;
    });
  }

  /// Ask once for the two numbers BMR needs, plus a first weight.
  Future<void> _runSetup() async {
    final height = TextEditingController();
    final year = TextEditingController();
    final weight = TextEditingController();

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: _surface,
        title: const Text('Set up', style: TextStyle(color: Colors.white)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _field(height, 'Height (cm) — measure in the morning'),
            const SizedBox(height: 10),
            _field(year, 'Birth year'),
            const SizedBox(height: 10),
            _field(weight, 'Weight (kg)'),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel', style: TextStyle(color: Colors.white54)),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Save', style: TextStyle(color: _teal)),
          ),
        ],
      ),
    );
    if (ok != true) return;

    final h = double.tryParse(height.text.trim());
    final y = int.tryParse(year.text.trim());
    final w = double.tryParse(weight.text.trim());
    if (h == null || y == null || w == null) return;

    await widget.db.setProfile(heightCm: h, birthYear: y);
    await widget.db
        .upsertDay(HealthDay(day: HealthDb.dayKey(), weightKg: w));
    await _load();
  }

  Widget _field(TextEditingController c, String label) => TextField(
        controller: c,
        keyboardType: TextInputType.number,
        style: const TextStyle(color: Colors.white),
        decoration: InputDecoration(
          labelText: label,
          labelStyle: TextStyle(
            color: Colors.white.withValues(alpha: 0.5),
            fontSize: 12,
          ),
          enabledBorder: UnderlineInputBorder(
            borderSide:
                BorderSide(color: Colors.white.withValues(alpha: 0.2)),
          ),
          focusedBorder: const UnderlineInputBorder(
            borderSide: BorderSide(color: _teal),
          ),
        ),
      );

  Future<void> _setFast(FastKind f) async {
    await widget.db.upsertDay(HealthDay(day: HealthDb.dayKey(), fast: f));
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator(color: _red));
    }
    final jd = _today!;
    final t = _targets;
    final td = widget.plan.dayFor(jd);

    return RefreshIndicator(
      color: _red,
      backgroundColor: _surface,
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
        children: [
          _header(jd),
          const SizedBox(height: 14),
          // The calendar, training and dentist cards work without a body
          // profile; only the calorie and protein maths needs one. So the
          // setup prompt sits inline rather than gating the whole tab — the
          // fasting rules are the safety-relevant part and should never be
          // behind a form.
          if (_needsSetup) ...[
            _setupCard(),
            const SizedBox(height: 12),
          ],
          if (jd.suggestion != null && jd.fast == FastKind.none) ...[
            _suggestionCard(jd.suggestion!),
            const SizedBox(height: 12),
          ],
          _windowCard(jd, t),
          const SizedBox(height: 12),
          _trainingCard(td, jd),
          const SizedBox(height: 12),
          _yogaCard(jd, td),
          const SizedBox(height: 12),
          if (t != null) ...[
            _proteinCard(t, jd),
            const SizedBox(height: 12),
          ],
          _measurementCard(),
          const SizedBox(height: 12),
          _fastPicker(jd),
          const SizedBox(height: 12),
          _priorityCard(),
        ],
      ),
    );
  }

  /// The calendar knows today is an observance day; it asks rather than assumes.
  ///
  /// His practice is settled — tivihar, water always — so the two-button branch
  /// below is currently dead for him. It stays because the tivihar/chauvihar
  /// distinction decides whether a day is "rest" or "rest, and stay out of the
  /// heat", and a future change must not silently inherit today's answer.
  Widget _suggestionCard(FastSuggestion s) => _card(
        border: _amber,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _label('TODAY LOOKS LIKE A FAST', _amber),
            const SizedBox(height: 8),
            Text(
              s.reason,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 15,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            if (s.needsWaterRule) ...[
              Text(
                'Which one are you keeping? This changes the safety rules, so '
                'it is not guessed.',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.7),
                  fontSize: 12.5,
                  height: 1.4,
                ),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: _choice('Tivihar', 'water in daylight',
                        () => _setFast(FastKind.tivihar)),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: _choice('Chauvihar', 'nothing at all',
                        () => _setFast(FastKind.chauvihar)),
                  ),
                ],
              ),
            ] else
              _choice(s.kind.label, 'confirm', () => _setFast(s.kind)),
            const SizedBox(height: 8),
            Text(
              'Computed from the tithi at sunrise. Check it against your '
              'family panchang — calendars can differ by a day.',
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.35),
                fontSize: 10.5,
                height: 1.3,
              ),
            ),
          ],
        ),
      );

  Widget _choice(String title, String sub, VoidCallback onTap) =>
      GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: BoxDecoration(
            color: _amber.withValues(alpha: 0.14),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: _amber.withValues(alpha: 0.55)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(
                  color: _amber,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                sub,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.5),
                  fontSize: 10.5,
                ),
              ),
            ],
          ),
        ),
      );

  Widget _setupCard() => _card(
        border: _teal,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _label('SET UP', _teal),
            const SizedBox(height: 8),
            Text(
              'Height, birth year and a first weight. Stored on this device '
              'only — never in the app source, never uploaded.',
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.7),
                fontSize: 12.5,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 10),
            GestureDetector(
              onTap: _runSetup,
              child: Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 16, vertical: 9),
                decoration: BoxDecoration(
                  color: _teal.withValues(alpha: 0.18),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: _teal.withValues(alpha: 0.6)),
                ),
                child: const Text(
                  'Enter',
                  style: TextStyle(
                    color: _teal,
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ),
          ],
        ),
      );

  // ---------------------------------------------------------------- header

  Widget _header(JainDay jd) {
    final left = widget.calendar.chaumasaDaysLeft();
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'HEALTH',
                style: TextStyle(
                  fontSize: 18,
                  letterSpacing: 4,
                  fontWeight: FontWeight.w700,
                  color: _red,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                jd.inChaumasa
                    ? 'Chaumasa · $left days left'
                    : 'Normal observance',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.6),
                  fontSize: 12,
                ),
              ),
            ],
          ),
        ),
        if (jd.window != null && jd.window!.isDeload)
          _pill(jd.window!.name, _amber),
      ],
    );
  }

  // ------------------------------------------------------- eating window

  /// The hero card: how long is left to eat.
  ///
  /// This is the number that is genuinely hard to hold in your head, because it
  /// moves every day and collides with an evening that does not. From
  /// mid-October the last meal has to land around 17:15–17:30, which is a
  /// logistics problem before it is a nutrition one.
  Widget _windowCard(JainDay jd, NutritionTargets? t) {
    if (jd.fast.isFullFast) {
      return _card(
        border: _red,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _label('FASTING TODAY', _red),
            const SizedBox(height: 8),
            Text(
              jd.fast.label,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 22,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            if (jd.needsHeatWarning)
              _warnRow(
                'No water for ~36 h. Stay indoors and out of the heat. '
                'Break the fast for confusion, fainting, no urine for 12+ h, '
                'or persistent vomiting.',
              )
            else
              Text(
                'Boiled water permitted from ${_hhmm(jd.navkarsi)} to '
                '${_hhmm(jd.sunset)}. Drink to thirst, not to a quota.',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.75),
                  fontSize: 13,
                  height: 1.4,
                ),
              ),
          ],
        ),
      );
    }

    if (!jd.closesFoodWindow) {
      return _card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _label('EATING WINDOW', _teal),
            const SizedBox(height: 6),
            Text(
              'Open — no evening vow today.',
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.8),
                fontSize: 14,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              'Sunset ${_hhmm(jd.sunset)}',
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.45),
                fontSize: 12,
              ),
            ),
          ],
        ),
      );
    }

    final left = jd.timeLeftToEat();
    final closed = left == null || left == Duration.zero;
    // Under two hours is when it stops being background information and starts
    // needing a decision about the last meal.
    final urgent = !closed && left.inMinutes < 120;
    final colour = closed ? _red : (urgent ? _amber : _teal);

    return _card(
      border: colour,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _label(closed ? 'WINDOW CLOSED' : 'TIME LEFT TO EAT', colour),
          const SizedBox(height: 8),
          Text(
            closed
                ? 'Nothing until ${_hhmm(jd.navkarsi)} tomorrow'
                : '${left.inHours}h ${left.inMinutes % 60}m',
            style: TextStyle(
              color: colour,
              fontSize: closed ? 18 : 34,
              fontWeight: FontWeight.w700,
              height: 1.1,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Last bite by ${_hhmm(jd.lastMealBy)}  ·  sunset ${_hhmm(jd.sunset)}',
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.6),
              fontSize: 12.5,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            t == null
                ? 'Window ${jd.windowHours.toStringAsFixed(1)} h'
                : 'Window ${jd.windowHours.toStringAsFixed(1)} h — '
                    'all ${t.proteinG.round()} g of protein fits inside it',
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.4),
              fontSize: 11.5,
            ),
          ),
          if (urgent) ...[
            const SizedBox(height: 10),
            if (jd.eveningVow.waterAfterSunset)
              Text(
                'Water continues after sunset under tivihar — only food stops. '
                'Aim the last meal at protein, not volume.',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.55),
                  fontSize: 11.5,
                  height: 1.4,
                ),
              )
            else
              _warnRow(
                'Keep this last meal low-fibre — dairy or paneer, under ~8 g. '
                'Under chauvihar it sits 11–13 h with no water behind it.',
              ),
          ],
        ],
      ),
    );
  }

  // ------------------------------------------------------------- training

  Widget _trainingCard(TrainingDay td, JainDay jd) {
    if (td.blockedReason != null) {
      return _card(
        border: _amber,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _label('TRAINING', _amber),
            const SizedBox(height: 8),
            Row(
              children: [
                const Icon(Icons.pan_tool_outlined, color: _amber, size: 18),
                const SizedBox(width: 8),
                Text(
                  td.clearance == TrainingClearance.rest
                      ? 'Rest today'
                      : 'Light only',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              td.blockedReason!,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.75),
                fontSize: 13,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'Permitted: gentle restorative yoga, slow walking, slow breathing.',
              style: TextStyle(
                color: _teal.withValues(alpha: 0.85),
                fontSize: 12.5,
              ),
            ),
          ],
        ),
      );
    }

    final s = td.session;
    final trainBy = widget.plan.trainByFor(jd);

    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _label('TRAINING', _teal),
              const Spacer(),
              Text(
                'Week ${widget.plan.weekOf(jd.date)}',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.4),
                  fontSize: 11,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            td.phase,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.5),
              fontSize: 11.5,
            ),
          ),
          const SizedBox(height: 12),

          // The daily ritual comes first because it is the part that never gets
          // cancelled. Everything below it is conditional; this is not.
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: _red.withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: _red.withValues(alpha: 0.3)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'DAILY RITUAL · ${td.ritualReps} reps',
                  style: const TextStyle(
                    color: _red,
                    fontSize: 10.5,
                    letterSpacing: 1.6,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                ...TrainingPlan.ritual.map(
                  (r) => Padding(
                    padding: const EdgeInsets.only(bottom: 3),
                    child: Text(
                      '${r.$2} · ${r.$3}',
                      style: const TextStyle(
                        color: Colors.white70,
                        fontSize: 12.5,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '+ 10 min yoga. Mark the X even on a bad day.',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.45),
                    fontSize: 11.5,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ],
            ),
          ),

          if (s != null) ...[
            const SizedBox(height: 14),
            Row(
              children: [
                Text(
                  s.name.toUpperCase(),
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 13,
                    letterSpacing: 1.4,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const Spacer(),
                Text(
                  '${widget.plan.setsForWeek(widget.plan.weekOf(jd.date))} sets · '
                  '${widget.plan.rirForWeek(widget.plan.weekOf(jd.date))} RIR',
                  style: TextStyle(
                    color: _teal.withValues(alpha: 0.8),
                    fontSize: 11,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            ...s.exercises.map(
              (e) => Padding(
                padding: const EdgeInsets.only(bottom: 5),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      margin: const EdgeInsets.only(top: 5, right: 8),
                      width: 6,
                      height: 6,
                      decoration: BoxDecoration(
                        color: _patternColour(e.pattern),
                        shape: BoxShape.circle,
                      ),
                    ),
                    Expanded(
                      child: Text(
                        e.display,
                        style: const TextStyle(
                          color: Colors.white70,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],

          if (td.runKm > 0) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                const Icon(Icons.directions_run, color: _teal, size: 16),
                const SizedBox(width: 8),
                Text(
                  'Easy run — ${td.runKm} km',
                  style: const TextStyle(color: Colors.white70, fontSize: 13),
                ),
              ],
            ),
          ],

          if (jd.closesFoodWindow) ...[
            const SizedBox(height: 12),
            Text(
              'Finish by ${_hhmm(trainBy)} so the post-workout meal lands '
              'before the window shuts.',
              style: TextStyle(
                color: _amber.withValues(alpha: 0.9),
                fontSize: 12,
                height: 1.35,
              ),
            ),
          ],
        ],
      ),
    );
  }

  /// Entry point to the asana cards.
  ///
  /// Surfaces the count and length for today rather than a generic "Yoga"
  /// button, because on a fast day the sequence collapses to the restorative
  /// subset and the card should say so before he taps into it.
  Widget _yogaCard(JainDay jd, TrainingDay td) {
    final restricted = td.clearance == TrainingClearance.rest ||
        td.clearance == TrainingClearance.lightOnly;
    final seq = restricted
        ? YogaLibrary.restorativeOnly
        : YogaLibrary.sequenceForWeek(widget.plan.weekOf(jd.date));
    final mins = YogaLibrary.minutesFor(seq);

    return GestureDetector(
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => YogaScreen(
            week: widget.plan.weekOf(jd.date),
            clearance: td.clearance,
            fastLabel: jd.fast == FastKind.none ? null : jd.fast.label,
          ),
        ),
      ),
      child: _card(
        child: Row(
          children: [
            Container(
              width: 42,
              height: 42,
              decoration: BoxDecoration(
                color: const Color(0xFF9B8AFF).withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.self_improvement,
                  color: Color(0xFF9B8AFF), size: 22),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Yoga',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    restricted
                        ? '${seq.length} restorative postures — fast day'
                        : '${seq.length} postures · ~$mins min',
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.5),
                      fontSize: 12,
                    ),
                  ),
                ],
              ),
            ),
            Icon(Icons.chevron_right,
                color: Colors.white.withValues(alpha: 0.3)),
          ],
        ),
      ),
    );
  }

  static Color _patternColour(Pattern p) => switch (p) {
        Pattern.push => const Color(0xFFE74848),
        Pattern.pull => const Color(0xFF00E5C9),
        Pattern.legs => const Color(0xFFFFB347),
        Pattern.core => const Color(0xFF9B8AFF),
      };

  // -------------------------------------------------------------- protein

  Widget _proteinCard(NutritionTargets t, JainDay jd) {
    if (jd.fast.isFullFast) return const SizedBox.shrink();

    final got = _log?.proteinG ?? 0;
    final pct = (got / t.proteinG).clamp(0.0, 1.0);
    final kcalGot = _log?.kcal ?? 0;

    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _label('PROTEIN', _teal),
              const Spacer(),
              if (!t.calibrated)
                Text(
                  'TDEE estimated',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.35),
                    fontSize: 10.5,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text(
                '${got.round()}',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 30,
                  fontWeight: FontWeight.w700,
                ),
              ),
              Text(
                ' / ${t.proteinG.round()} g',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.5),
                  fontSize: 15,
                ),
              ),
              const Spacer(),
              Text(
                '${kcalGot.round()} / ${t.kcal.round()} kcal',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.5),
                  fontSize: 12,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: pct,
              minHeight: 7,
              backgroundColor: Colors.white.withValues(alpha: 0.08),
              valueColor: AlwaysStoppedAnimation(pct >= 1 ? _teal : _red),
            ),
          ),
          const SizedBox(height: 12),

          // The rule a generic tracker misses: daily protein can be on target
          // while every individual meal misses the leucine threshold, because
          // plant protein is leucine-dilute.
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.04),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'PER-MEAL RULE',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.5),
                    fontSize: 9.5,
                    letterSpacing: 1.4,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 6),
                const Text(
                  'Dairy-dominant meal: 25–30 g protein.\n'
                  'Pulse- or grain-dominant meal: 35–40 g.',
                  style: TextStyle(
                    color: Colors.white70,
                    fontSize: 12.5,
                    height: 1.4,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  'Both need ≥2.5 g leucine. A 30 g dal meal still misses it.',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.45),
                    fontSize: 11.5,
                  ),
                ),
              ],
            ),
          ),

          if (jd.inChaumasa) ...[
            const SizedBox(height: 10),
            _warnRow(
              'Chaumasa: gourds carry almost no protein. Hitting '
              '${t.proteinG.round()} g means more soya chunks and paneer — '
              'not more sabzi.',
            ),
          ],
        ],
      ),
    );
  }

  // ---------------------------------------------------------- measurement

  Widget _measurementCard() {
    final tr = _trend;
    final waist = _log?.waistCm;

    return _card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _label('THE NUMBER THAT MATTERS', _teal),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: _stat(
                  'WAIST',
                  waist == null ? '—' : '${waist.toStringAsFixed(1)} cm',
                  waist == null
                      ? 'Log it weekly, morning, fasted'
                      : (waist >= 90
                          ? 'Above the 90 cm Indian male cutoff'
                          : 'Under the 90 cm cutoff'),
                  waist != null && waist >= 90 ? _amber : _teal,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _stat(
                  'WEIGHT (7d avg)',
                  tr?.average == null
                      ? '—'
                      : '${tr!.average!.toStringAsFixed(1)} kg',
                  tr?.changePerWeek == null
                      ? 'Needs ~10 days of readings'
                      : '${tr!.changePerWeek! >= 0 ? '+' : ''}'
                          '${tr.changePerWeek!.toStringAsFixed(2)} kg/wk',
                  Colors.white.withValues(alpha: 0.6),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (tr?.creatineMasked == true)
            _warnRow(
              'Creatine started under 21 days ago. It holds 1–2 kg of water — '
              'roughly eight weeks of expected progress, in the wrong '
              'direction. Ignore the scale, read the waist.',
            )
          else
            Text(
              'Expect the scale to barely move. Recomposition shows up as a '
              'flat weight and a shrinking waist — if the waist is falling, it '
              'is working. Do not cut further.',
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.45),
                fontSize: 11.5,
                height: 1.4,
              ),
            ),
        ],
      ),
    );
  }

  Widget _stat(String label, String value, String sub, Color c) => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.04),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.45),
                fontSize: 9.5,
                letterSpacing: 1.2,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              value,
              style: TextStyle(
                color: c,
                fontSize: 20,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              sub,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.4),
                fontSize: 10.5,
                height: 1.3,
              ),
            ),
          ],
        ),
      );

  // ----------------------------------------------------------- fast picker

  Widget _fastPicker(JainDay jd) => _card(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _label("TODAY'S OBSERVANCE", _teal),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: FastKind.values.map((f) {
                final on = jd.fast == f;
                return GestureDetector(
                  onTap: () => _setFast(f),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 12, vertical: 7),
                    decoration: BoxDecoration(
                      color: on
                          ? _red.withValues(alpha: 0.22)
                          : Colors.white.withValues(alpha: 0.05),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: on
                            ? _red.withValues(alpha: 0.7)
                            : Colors.white.withValues(alpha: 0.10),
                      ),
                    ),
                    child: Text(
                      f.label,
                      style: TextStyle(
                        color: on ? Colors.white : Colors.white60,
                        fontSize: 12,
                        fontWeight: on ? FontWeight.w700 : FontWeight.w400,
                      ),
                    ),
                  ),
                );
              }).toList(),
            ),
          ],
        ),
      );

  // -------------------------------------------------------------- priority

  /// Deliberately last on screen and deliberately unmissable in colour.
  ///
  /// It stays until the appointment happens. Everything else in this module is
  /// a six-month project; periodontal bone loss is the one thing here that does
  /// not wait and does not come back.
  Widget _priorityCard() => _card(
        border: _red,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _label('BEFORE ANY OF THIS', _red),
            const SizedBox(height: 8),
            const Text(
              'Dentist — periodontal exam',
              style: TextStyle(
                color: Colors.white,
                fontSize: 15,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              'Ask for all four: full-mouth probing depths, radiographs, '
              'mobility grading, bleeding on probing. Anything less is a sales '
              'pitch, not an exam.',
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.7),
                fontSize: 12.5,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              'Then bloods: CBC + differential, B12, ferritin WITH CRP, folate, '
              'tTG-IgA, HbA1c.',
              style: TextStyle(
                color: _teal.withValues(alpha: 0.85),
                fontSize: 12,
                height: 1.4,
              ),
            ),
          ],
        ),
      );

  // ----------------------------------------------------------------- chrome

  Widget _card({required Widget child, Color? border}) => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: _surface.withValues(alpha: 0.85),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(
            color: (border ?? Colors.white).withValues(
              alpha: border == null ? 0.08 : 0.35,
            ),
          ),
        ),
        child: child,
      );

  Widget _label(String s, Color c) => Text(
        s,
        style: TextStyle(
          color: c,
          fontSize: 10,
          letterSpacing: 2,
          fontWeight: FontWeight.w700,
        ),
      );

  Widget _pill(String s, Color c) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: c.withValues(alpha: 0.15),
          border: Border.all(color: c.withValues(alpha: 0.6)),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(
          s,
          style: TextStyle(
            color: c,
            fontSize: 10,
            letterSpacing: 1.2,
            fontWeight: FontWeight.w700,
          ),
        ),
      );

  Widget _warnRow(String s) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.only(top: 1, right: 8),
            child: Icon(Icons.warning_amber_rounded, color: _amber, size: 15),
          ),
          Expanded(
            child: Text(
              s,
              style: const TextStyle(
                color: _amber,
                fontSize: 12,
                height: 1.4,
              ),
            ),
          ),
        ],
      );

  static String _hhmm(DateTime t) =>
      '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
}
