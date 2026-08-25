/// Local store for health data.
///
/// **This is a separate database file from [DeckDb] on purpose.** The reel deck
/// is shipped as an asset, tracked in git, and rebuilt by the pipeline; health
/// data is none of those things. Keeping them in one file would mean a single
/// careless export, backup or debug dump carried both. A separate file also
/// makes [wipe] meaningful — one delete removes everything, with no risk of
/// taking the deck with it.
///
/// Nothing here leaves the device. There is no sync, no upload, and no cloud
/// mirror, and none should be added without a deliberate decision.
library;

import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import 'jain_calendar.dart';

/// One day's log.
class HealthDay {
  const HealthDay({
    required this.day,
    this.fast = FastKind.none,
    this.eveningVow,
    this.weightKg,
    this.waistCm,
    this.proteinG,
    this.kcal,
    this.trained = false,
    this.bedTime,
    this.wakeTime,
    this.ulcerCount,
    this.notes,
  });

  final String day; // yyyy-MM-dd
  final FastKind fast;

  /// Null means "not stated" — the calendar then falls back to his chaumasa
  /// default (tivihar) rather than to no vow at all.
  final EveningVow? eveningVow;
  final double? weightKg;
  final double? waistCm;
  final double? proteinG;
  final double? kcal;
  final bool trained;
  final String? bedTime;
  final String? wakeTime;
  final int? ulcerCount;
  final String? notes;

  Map<String, Object?> toRow() => {
        'day': day,
        'fast_kind': fast.name,
        'evening_vow': eveningVow?.name,
        'weight_kg': weightKg,
        'waist_cm': waistCm,
        'protein_g': proteinG,
        'kcal': kcal,
        'trained': trained ? 1 : 0,
        'bed_time': bedTime,
        'wake_time': wakeTime,
        'ulcer_count': ulcerCount,
        'notes': notes,
      };

  factory HealthDay.fromRow(Map<String, Object?> r) => HealthDay(
        day: r['day'] as String,
        fast: FastKind.values.firstWhere(
          (f) => f.name == r['fast_kind'],
          orElse: () => FastKind.none,
        ),
        eveningVow: r['evening_vow'] == null
            ? null
            : EveningVow.values.firstWhere(
                (v) => v.name == r['evening_vow'],
                orElse: () => EveningVow.tivihar,
              ),
        weightKg: (r['weight_kg'] as num?)?.toDouble(),
        waistCm: (r['waist_cm'] as num?)?.toDouble(),
        proteinG: (r['protein_g'] as num?)?.toDouble(),
        kcal: (r['kcal'] as num?)?.toDouble(),
        trained: (r['trained'] as int? ?? 0) == 1,
        bedTime: r['bed_time'] as String?,
        wakeTime: r['wake_time'] as String?,
        ulcerCount: r['ulcer_count'] as int?,
        notes: r['notes'] as String?,
      );
}

/// A single logged set. Without this the programme has no progressive overload,
/// which is the most common reason home training stalls.
class SetLog {
  const SetLog({
    required this.day,
    required this.exercise,
    required this.setIndex,
    required this.reps,
    this.weightKg,
    this.rir,
  });

  final String day;
  final String exercise;
  final int setIndex;
  final int reps;
  final double? weightKg;

  /// Reps in reserve. The programme runs at 1–3; logging it is what makes
  /// "add reps then add weight" checkable rather than a vibe.
  final int? rir;
}

/// How to read the weight trend today.
class WeightTrend {
  const WeightTrend({
    required this.average,
    required this.dayCount,
    required this.changePerWeek,
    required this.creatineMasked,
  });

  /// 7-day rolling average, or null with fewer than 3 readings.
  final double? average;
  final int dayCount;

  /// kg/week over the window. Negative is loss.
  final double? changePerWeek;

  /// True while creatine's 1–2 kg of intracellular water retention is still
  /// landing. During this period the scale is not measuring what he thinks it
  /// is, and the UI must say so — otherwise he concludes the diet failed in
  /// exactly the weeks it started working.
  final bool creatineMasked;
}

class HealthDb {
  static const _dbName = 'health.db';
  static const _schemaVersion = 1;

  Database? _db;
  Database get db => _db!;

  /// [database] lets the engine be tested in memory without a device.
  Future<void> init({Database? database}) async {
    if (_db != null) return;
    if (database != null) {
      _db = database;
      await _createSchema(database);
      return;
    }
    _db = await openDatabase(
      p.join(await getDatabasesPath(), _dbName),
      version: _schemaVersion,
      onCreate: (d, _) => _createSchema(d),
      onUpgrade: (d, _, _) => _createSchema(d),
    );
  }

  Future<void> _createSchema(Database d) async {
    await d.execute('''
      CREATE TABLE IF NOT EXISTS day_log(
        day TEXT PRIMARY KEY,
        fast_kind TEXT NOT NULL DEFAULT 'none',
        evening_vow TEXT,
        weight_kg REAL, waist_cm REAL,
        protein_g REAL, kcal REAL,
        trained INTEGER NOT NULL DEFAULT 0,
        bed_time TEXT, wake_time TEXT,
        ulcer_count INTEGER,
        notes TEXT
      )''');

    // Meals are stored per-item rather than as a day total so the per-meal
    // leucine rule can be checked. A day that hits 128 g of protein in four
    // meals that each miss the leucine threshold is not the same day as one
    // that hits it in four that clear it, and only per-meal rows can tell them
    // apart.
    await d.execute('''
      CREATE TABLE IF NOT EXISTS meal_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT NOT NULL, at TEXT,
        label TEXT,
        protein_g REAL NOT NULL DEFAULT 0,
        kcal REAL NOT NULL DEFAULT 0,
        leucine_g REAL NOT NULL DEFAULT 0,
        fibre_g REAL NOT NULL DEFAULT 0,
        dvidal INTEGER NOT NULL DEFAULT 0
      )''');
    await d.execute(
        'CREATE INDEX IF NOT EXISTS idx_meal_day ON meal_log(day)');

    await d.execute('''
      CREATE TABLE IF NOT EXISTS set_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT NOT NULL, exercise TEXT NOT NULL,
        set_index INTEGER NOT NULL,
        reps INTEGER NOT NULL, weight_kg REAL, rir INTEGER
      )''');
    await d.execute(
        'CREATE INDEX IF NOT EXISTS idx_set_day ON set_log(day, exercise)');

    // Start dates matter more than the fact of taking something: creatine's
    // water retention has to be dated to be discounted, and B12 should not be
    // judged before month five.
    await d.execute('''
      CREATE TABLE IF NOT EXISTS supplement(
        name TEXT PRIMARY KEY, started_on TEXT NOT NULL, note TEXT
      )''');

    // The action checklist. Only STATUS lives here — the catalogue of what the
    // actions are is plan content and lives in health_actions.dart, so a change
    // to the plan does not need a database migration.
    await d.execute('''
      CREATE TABLE IF NOT EXISTS milestone(
        key TEXT PRIMARY KEY,
        started_on TEXT,
        done_on TEXT,
        note TEXT
      )''');

    // Height and birth year live here rather than as constants in the source.
    //
    // They are only needed to compute BMR, so hardcoded defaults in Dart would
    // have been the obvious shortcut — but lib/ is tracked in git, and a
    // committed height and age is personal health data sitting in a repo that
    // gets pushed. The rule this module runs on is that health data lives in
    // this database and nowhere else, and a "harmless" default is exactly how
    // that rule erodes.
    await d.execute('''
      CREATE TABLE IF NOT EXISTS profile(
        id INTEGER PRIMARY KEY CHECK (id = 1),
        height_cm REAL, birth_year INTEGER
      )''');
  }

  // ---------------------------------------------------------------- profile

  Future<({double heightCm, int age})?> profile() async {
    final r = await db.query('profile', where: 'id = 1', limit: 1);
    if (r.isEmpty) return null;
    final h = (r.first['height_cm'] as num?)?.toDouble();
    final by = r.first['birth_year'] as int?;
    if (h == null || by == null) return null;
    return (heightCm: h, age: DateTime.now().year - by);
  }

  Future<void> setProfile({required double heightCm, required int birthYear}) =>
      db.insert(
        'profile',
        {'id': 1, 'height_cm': heightCm, 'birth_year': birthYear},
        conflictAlgorithm: ConflictAlgorithm.replace,
      );

  static String dayKey([DateTime? t]) {
    final d = t ?? DateTime.now();
    return '${d.year}-${d.month.toString().padLeft(2, '0')}'
        '-${d.day.toString().padLeft(2, '0')}';
  }

  // ----------------------------------------------------------------- writes

  /// Upsert a day without clobbering fields the caller did not set.
  ///
  /// The day row is written from several places — the fast picker, the weight
  /// entry, the training screen — and a plain replace would silently wipe
  /// whichever fields that particular caller happened not to know about.
  Future<void> upsertDay(HealthDay day) async {
    final row = day.toRow()..removeWhere((_, v) => v == null);
    final existing = await db.query('day_log',
        where: 'day = ?', whereArgs: [day.day], limit: 1);
    if (existing.isEmpty) {
      await db.insert('day_log', row,
          conflictAlgorithm: ConflictAlgorithm.replace);
    } else {
      await db.update('day_log', row, where: 'day = ?', whereArgs: [day.day]);
    }
  }

  Future<HealthDay?> getDay(String day) async {
    final r =
        await db.query('day_log', where: 'day = ?', whereArgs: [day], limit: 1);
    return r.isEmpty ? null : HealthDay.fromRow(r.first);
  }

  Future<void> logMeal({
    required String day,
    String? at,
    String? label,
    required double proteinG,
    required double kcal,
    required double leucineG,
    double fibreG = 0,
    bool dvidal = false,
  }) async {
    await db.insert('meal_log', {
      'day': day,
      'at': at,
      'label': label,
      'protein_g': proteinG,
      'kcal': kcal,
      'leucine_g': leucineG,
      'fibre_g': fibreG,
      'dvidal': dvidal ? 1 : 0,
    });
    await _rollUpDay(day);
  }

  /// Keeps `day_log` totals consistent with `meal_log` so the Today card can
  /// read one row instead of aggregating on every rebuild.
  Future<void> _rollUpDay(String day) async {
    final r = await db.rawQuery(
      'SELECT SUM(protein_g) p, SUM(kcal) k FROM meal_log WHERE day = ?',
      [day],
    );
    final p0 = (r.first['p'] as num?)?.toDouble() ?? 0;
    final k0 = (r.first['k'] as num?)?.toDouble() ?? 0;
    await upsertDay(HealthDay(day: day, proteinG: p0, kcal: k0));
  }

  Future<List<Map<String, Object?>>> mealsOn(String day) =>
      db.query('meal_log', where: 'day = ?', whereArgs: [day], orderBy: 'at');

  Future<void> logSet(SetLog s) async {
    await db.insert('set_log', {
      'day': s.day,
      'exercise': s.exercise,
      'set_index': s.setIndex,
      'reps': s.reps,
      'weight_kg': s.weightKg,
      'rir': s.rir,
    });
    await upsertDay(HealthDay(day: s.day, trained: true));
  }

  /// The best set logged for an exercise, for the "beat this" line on the
  /// training screen. Ranked by load first, then reps — which is the order
  /// double progression actually cares about.
  Future<Map<String, Object?>?> bestSet(String exercise) async {
    final r = await db.query(
      'set_log',
      where: 'exercise = ?',
      whereArgs: [exercise],
      orderBy: 'weight_kg DESC, reps DESC',
      limit: 1,
    );
    return r.isEmpty ? null : r.first;
  }

  Future<void> startSupplement(String name, {String? note, DateTime? on}) =>
      db.insert(
        'supplement',
        {'name': name, 'started_on': dayKey(on), 'note': note},
        conflictAlgorithm: ConflictAlgorithm.ignore,
      );

  Future<DateTime?> supplementStart(String name) async {
    final r = await db.query('supplement',
        where: 'name = ?', whereArgs: [name], limit: 1);
    if (r.isEmpty) return null;
    return DateTime.tryParse(r.first['started_on'] as String);
  }

  // ------------------------------------------------------------- milestones

  /// Raw status rows, keyed by milestone key.
  Future<Map<String, ({DateTime? started, DateTime? done, String? note})>>
      milestoneStatus() async {
    final rows = await db.query('milestone');
    return {
      for (final r in rows)
        r['key'] as String: (
          started: DateTime.tryParse((r['started_on'] as String?) ?? ''),
          done: DateTime.tryParse((r['done_on'] as String?) ?? ''),
          note: r['note'] as String?,
        )
    };
  }

  /// Mark an action started. Idempotent — re-marking does not reset the clock,
  /// which matters for the timed trials where the start date IS the measurement.
  Future<void> startMilestone(String key, {DateTime? on}) async {
    final existing = await db.query('milestone',
        where: 'key = ?', whereArgs: [key], limit: 1);
    if (existing.isNotEmpty && existing.first['started_on'] != null) return;
    await db.insert(
      'milestone',
      {'key': key, 'started_on': dayKey(on)},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> completeMilestone(String key, {DateTime? on, String? note}) async {
    final existing = await db.query('milestone',
        where: 'key = ?', whereArgs: [key], limit: 1);
    final started = existing.isEmpty
        ? dayKey(on)
        : (existing.first['started_on'] as String?) ?? dayKey(on);
    await db.insert(
      'milestone',
      {
        'key': key,
        'started_on': started,
        'done_on': dayKey(on),
        'note': note ?? (existing.isEmpty ? null : existing.first['note']),
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> clearMilestone(String key) =>
      db.delete('milestone', where: 'key = ?', whereArgs: [key]);

  // ------------------------------------------------------------------ reads

  /// Weight readings, newest first.
  Future<List<(String, double)>> weights({int limit = 60}) async {
    final r = await db.query(
      'day_log',
      columns: ['day', 'weight_kg'],
      where: 'weight_kg IS NOT NULL',
      orderBy: 'day DESC',
      limit: limit,
    );
    return r
        .map((x) => (x['day'] as String, (x['weight_kg'] as num).toDouble()))
        .toList();
  }

  Future<List<(String, double)>> waists({int limit = 26}) async {
    final r = await db.query(
      'day_log',
      columns: ['day', 'waist_cm'],
      where: 'waist_cm IS NOT NULL',
      orderBy: 'day DESC',
      limit: limit,
    );
    return r
        .map((x) => (x['day'] as String, (x['waist_cm'] as num).toDouble()))
        .toList();
  }

  /// Rolling weight trend, with the creatine caveat attached.
  ///
  /// Daily weight is noise; the 7-day average is the signal. And on a recomp
  /// where the *expected* change is only −0.15 to −0.25 kg/week, creatine's
  /// 1–2 kg of water retention is roughly eight weeks of progress in the wrong
  /// direction — so the first three weeks after starting it have to be flagged
  /// rather than read.
  Future<WeightTrend> weightTrend({int days = 7}) async {
    final rows = await weights(limit: days * 2);
    final creatineOn = await supplementStart('creatine');
    final masked = creatineOn != null &&
        DateTime.now().difference(creatineOn).inDays < 21;

    if (rows.length < 3) {
      return WeightTrend(
        average: rows.isEmpty ? null : rows.first.$2,
        dayCount: rows.length,
        changePerWeek: null,
        creatineMasked: masked,
      );
    }

    final recent = rows.take(days).toList();
    final avg = recent.map((e) => e.$2).reduce((a, b) => a + b) / recent.length;

    double? perWeek;
    if (rows.length >= days + 3) {
      final older = rows.skip(days).take(days).toList();
      final oldAvg =
          older.map((e) => e.$2).reduce((a, b) => a + b) / older.length;
      final first = DateTime.parse(recent.last.$1);
      final last = DateTime.parse(recent.first.$1);
      final span = last.difference(first).inDays;
      if (span > 0) perWeek = (avg - oldAvg) / span * 7;
    }

    return WeightTrend(
      average: avg,
      dayCount: recent.length,
      changePerWeek: perWeek,
      creatineMasked: masked,
    );
  }

  /// Re-derive maintenance calories from what actually happened.
  ///
  /// The Mifflin–St Jeor estimate carries roughly ±200 kcal of error, which is
  /// most of the intended deficit — so the estimate is a starting guess and
  /// this is the correction. Needs ~14 days of paired intake and weight before
  /// it means anything.
  ///
  /// `TDEE = mean intake + (7700 × kg change / days)`
  Future<double?> calibratedTdee({int minDays = 14}) async {
    final rows = await db.query(
      'day_log',
      columns: ['day', 'kcal', 'weight_kg'],
      where: 'kcal IS NOT NULL AND kcal > 0 AND weight_kg IS NOT NULL',
      orderBy: 'day ASC',
    );
    if (rows.length < minDays) return null;

    final kcals =
        rows.map((r) => (r['kcal'] as num).toDouble()).toList();
    final meanIntake = kcals.reduce((a, b) => a + b) / kcals.length;

    final firstW = (rows.first['weight_kg'] as num).toDouble();
    final lastW = (rows.last['weight_kg'] as num).toDouble();
    final span = DateTime.parse(rows.last['day'] as String)
        .difference(DateTime.parse(rows.first['day'] as String))
        .inDays;
    if (span <= 0) return null;

    return meanIntake + (7700 * (lastW - firstW) / span);
  }

  /// Ulcer counts over recent weeks, so the toothpaste swap has a denominator.
  /// An 8-week self-test with no baseline count is not a test.
  Future<List<(String, int)>> ulcerCounts({int limit = 16}) async {
    final r = await db.query(
      'day_log',
      columns: ['day', 'ulcer_count'],
      where: 'ulcer_count IS NOT NULL',
      orderBy: 'day DESC',
      limit: limit,
    );
    return r
        .map((x) => (x['day'] as String, x['ulcer_count'] as int))
        .toList();
  }

  // ------------------------------------------------------------------- wipe

  /// Delete every health row. Deliberately exposed in the UI.
  ///
  /// This data was collected on the understanding that it could be removed on
  /// request, and a delete that requires uninstalling the app is not a delete
  /// the user controls.
  Future<void> wipe() async {
    final b = db.batch();
    for (final t in [
      'day_log',
      'meal_log',
      'set_log',
      'supplement',
      'profile',
      'milestone',
    ]) {
      b.rawDelete('DELETE FROM $t');
    }
    await b.commit(noResult: true);
  }
}
