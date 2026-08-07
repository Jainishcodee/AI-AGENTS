import 'dart:convert';
import 'dart:math';

import 'package:flutter/services.dart' show rootBundle;
import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import '../models/reel_card.dart';

/// Local store for the cards distilled out of saved reels.
///
/// The deck itself ships as a read-only asset (`assets/deck.json`, built by
/// `reelflow/pack.py`); everything the user does to it lives in `task_state`
/// and `daily_pick`, so re-importing a newer deck never wipes progress.
class DeckDb {
  static const _dbName = 'reelflow.db';
  static const _asset = 'assets/deck.json';
  static const _schemaVersion = 3;

  Database? _db;
  Database get db => _db!;
  late Future<String?> Function() _loadDeck;

  /// FTS5 ships with the system SQLite on modern Android but not every device,
  /// so search degrades to LIKE rather than failing outright.
  bool _fts = false;

  /// [database] and [deckLoader] exist so the selection engine can be tested
  /// against an in-memory database without a device or an asset bundle.
  Future<void> init({
    Database? database,
    Future<String?> Function()? deckLoader,
  }) async {
    if (_db != null) return;
    _loadDeck = deckLoader ?? _loadFromAsset;
    if (database != null) {
      _db = database;
      await _createSchema(database);
    } else {
      _db = await openDatabase(
        p.join(await getDatabasesPath(), _dbName),
        version: _schemaVersion,
        onCreate: (d, _) => _createSchema(d),
        // Every statement is IF NOT EXISTS, so replaying it is how older
        // installs pick up tables added in a later version.
        onUpgrade: (d, _, _) => _createSchema(d),
      );
    }
    // _createSchema only runs on create/upgrade, so on a normal open the flag
    // has to be re-derived or search would silently stay on the LIKE path.
    _fts = await _hasFts();
    await _importIfNeeded();
  }

  Future<bool> _hasFts() async {
    final r = await db.rawQuery(
      "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'card_fts'",
    );
    return r.isNotEmpty;
  }

  Future<void> _createSchema(Database d) async {
    await d.execute('''
      CREATE TABLE IF NOT EXISTS cards(
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT, summary TEXT,
        domain TEXT, tags TEXT, url TEXT, owner TEXT, collection TEXT,
        evidence TEXT, confidence TEXT, thumb TEXT,
        steps TEXT, effort TEXT, horizon TEXT, recurrence TEXT,
        claim TEXT, why TEXT, applicability TEXT
      )''');
    // Added in v3. Existing installs already have the table, so patch it in.
    try {
      await d.execute('ALTER TABLE cards ADD COLUMN thumb TEXT');
    } catch (_) {
      // Column already present on a fresh create -- nothing to do.
    }
    await d.execute('''
      CREATE TABLE IF NOT EXISTS task_state(
        id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'backlog',
        progress INTEGER NOT NULL DEFAULT 0,
        completed_at TEXT, snooze_until TEXT,
        streak INTEGER NOT NULL DEFAULT 0
      )''');
    // One row per (day, card) so a restart re-reads the same list instead of
    // reshuffling, and so ticking a daily habit doesn't retire it forever.
    await d.execute('''
      CREATE TABLE IF NOT EXISTS daily_pick(
        day TEXT NOT NULL, card_id TEXT NOT NULL,
        done INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(day, card_id)
      )''');
    await d.execute(
        'CREATE INDEX IF NOT EXISTS idx_cards_kind ON cards(kind, horizon)');

    // Spaced repetition for facts. `box` is a Leitner level; a fact you keep
    // marking useful climbs it and comes back less often, which is what stops
    // a good rule turning into wallpaper.
    await d.execute('''
      CREATE TABLE IF NOT EXISTS fact_state(
        id TEXT PRIMARY KEY,
        box INTEGER NOT NULL DEFAULT 0,
        next_due TEXT,
        last_shown TEXT,
        useful_count INTEGER NOT NULL DEFAULT 0,
        retired INTEGER NOT NULL DEFAULT 0
      )''');
    await d.execute('''
      CREATE TABLE IF NOT EXISTS daily_fact(
        day TEXT PRIMARY KEY, card_id TEXT NOT NULL
      )''');

    try {
      await d.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS card_fts USING fts5(
          id UNINDEXED, title, summary, claim, why, applicability, tags, domain
        )''');
      _fts = true;
    } catch (_) {
      _fts = false; // older SQLite without FTS5 -- search falls back to LIKE
    }
  }

  Future<String?> _loadFromAsset() async {
    try {
      return await rootBundle.loadString(_asset);
    } catch (_) {
      return null; // no deck bundled yet -- Today just shows its empty state
    }
  }

  static String dayKey([DateTime? t]) {
    final d = t ?? DateTime.now();
    return '${d.year}-${d.month.toString().padLeft(2, '0')}'
        '-${d.day.toString().padLeft(2, '0')}';
  }

  // ---------------------------------------------------------------- import

  /// Upserts the shipped deck. Cards are replaced wholesale (the pipeline owns
  /// them); task_state rows are only ever inserted, never overwritten.
  Future<int> _importIfNeeded() async {
    final raw = await _loadDeck();
    if (raw == null) return 0;
    final list = (jsonDecode(raw) as List).cast<Map<String, dynamic>>();
    if (list.isEmpty) return 0;

    // Card count alone can't tell two decks apart -- successive pipeline runs
    // land on similar totals often enough that comparing sizes would silently
    // ignore a rebuilt deck -- so compare the actual ids.
    final incoming = list.map((j) => j['id'] as String).toSet();
    final present = (await db.query('cards', columns: ['id']))
        .map((r) => r['id'] as String)
        .toSet();
    if (present.length == incoming.length && present.containsAll(incoming)) {
      // Deck unchanged. An install upgraded from v1 still has an empty search
      // index though, so fill it before bailing out.
      if (_fts) {
        final indexed = Sqflite.firstIntValue(
                await db.rawQuery('SELECT COUNT(*) FROM card_fts')) ??
            0;
        if (indexed == 0) await _reindex(list);
      }
      return 0;
    }

    final batch = db.batch();
    if (_fts) batch.execute('DELETE FROM card_fts');
    for (final j in list) {
      final card = ReelCard.fromPack(j);
      batch.insert('cards', card.toRow(),
          conflictAlgorithm: ConflictAlgorithm.replace);
      if (card.isTask) {
        batch.insert('task_state', {'id': card.id},
            conflictAlgorithm: ConflictAlgorithm.ignore);
      } else {
        // Due immediately, so a freshly imported deck has facts to show today.
        batch.insert('fact_state', {'id': card.id, 'next_due': dayKey()},
            conflictAlgorithm: ConflictAlgorithm.ignore);
      }
      if (_fts) batch.insert('card_fts', _ftsRow(card));
    }

    // Cards the pipeline no longer emits have to go, or a deck built against an
    // older export keeps surfacing next to the current one. Their state and day
    // picks go with them -- a daily_pick row whose card is gone would otherwise
    // resolve to nothing and leave Today looking empty for the rest of the day.
    final gone = present.difference(incoming);
    if (gone.isNotEmpty) {
      final marks = List.filled(gone.length, '?').join(',');
      final ids = gone.toList();
      for (final t in ['cards', 'task_state', 'fact_state']) {
        batch.rawDelete('DELETE FROM $t WHERE id IN ($marks)', ids);
      }
      for (final t in ['daily_pick', 'daily_fact']) {
        batch.rawDelete('DELETE FROM $t WHERE card_id IN ($marks)', ids);
      }
    }

    await batch.commit(noResult: true);
    return list.length;
  }

  Map<String, Object?> _ftsRow(ReelCard c) => {
        'id': c.id,
        'title': c.title,
        'summary': c.summary,
        'claim': c.claim,
        'why': c.why,
        'applicability': c.applicability,
        'tags': c.tags.join(' '),
        'domain': c.domain,
      };

  Future<void> _reindex(List<Map<String, dynamic>> list) async {
    final batch = db.batch();
    batch.execute('DELETE FROM card_fts');
    for (final j in list) {
      batch.insert('card_fts', _ftsRow(ReelCard.fromPack(j)));
    }
    await batch.commit(noResult: true);
  }

  // ------------------------------------------------------------- selection

  static const _sel = '''
    SELECT c.*, s.status, s.progress, s.completed_at, s.snooze_until
    FROM cards c LEFT JOIN task_state s ON s.id = c.id
  ''';

  /// A task is back in the running unless it's finished for good, still
  /// snoozed, or a habit already done inside its own window.
  bool _eligible(Map<String, Object?> r, DateTime now) {
    final snooze = r['snooze_until'] as String?;
    if (snooze != null && snooze.compareTo(dayKey(now)) > 0) return false;

    final recur = (r['recurrence'] ?? 'once') as String;
    final doneAt = r['completed_at'] as String?;
    if (doneAt == null) return true;
    final done = DateTime.tryParse(doneAt);
    if (done == null) return true;

    return switch (recur) {
      'daily' => dayKey(done) != dayKey(now),
      'weekly' => now.difference(done).inDays >= 7,
      _ => statusFrom(r['status'] as String?) != TaskStatus.done,
    };
  }

  /// Today's list: one long-term thing to chip at, a couple of quick wins, and
  /// one short-term session. Randomised, but seeded on the date so it stays put
  /// for the whole day, and spread across domains so it isn't three gym tasks.
  Future<List<ReelCard>> todayTasks({int quick = 2}) async {
    final day = dayKey();

    final picked = await db.rawQuery(
      '$_sel JOIN daily_pick d ON d.card_id = c.id WHERE d.day = ?',
      [day],
    );
    if (picked.isNotEmpty) {
      return picked.map(ReelCard.fromRow).toList();
    }

    final now = DateTime.now();
    final rows = (await db.rawQuery("$_sel WHERE c.kind = 'task'"))
        .where((r) => _eligible(r, now))
        .toList();
    if (rows.isEmpty) return [];

    final rand = _seeded(day);
    rows.shuffle(rand);

    final chosen = <Map<String, Object?>>[];
    final domains = <String>{};
    void take(String horizon, int n) {
      var got = 0;
      // First pass prefers an unused domain; second fills the slot regardless,
      // so a thin backlog still produces a full day.
      for (final pass in [true, false]) {
        for (final r in rows) {
          if (got >= n) return;
          if (r['horizon'] != horizon || chosen.contains(r)) continue;
          final d = (r['domain'] ?? 'other') as String;
          if (pass && domains.contains(d)) continue;
          chosen.add(r);
          domains.add(d);
          got++;
        }
      }
    }

    take('long_term', 1);
    take('today', quick);
    take('short_term', 1);

    final batch = db.batch();
    for (final r in chosen) {
      batch.insert('daily_pick', {'day': day, 'card_id': r['id']},
          conflictAlgorithm: ConflictAlgorithm.ignore);
    }
    await batch.commit(noResult: true);

    return chosen.map(ReelCard.fromRow).toList();
  }

  /// Deterministic per-day shuffle. Same day in, same order out.
  Random _seeded(String day) {
    var h = 0;
    for (final c in day.codeUnits) {
      h = (h * 31 + c) & 0x7fffffff;
    }
    return Random(h);
  }

  Future<Set<String>> doneToday() async {
    final rows = await db.query('daily_pick',
        columns: ['card_id'], where: 'day = ? AND done = 1', whereArgs: [dayKey()]);
    return rows.map((r) => r['card_id'] as String).toSet();
  }

  /// Everything in a bucket, for the full list rather than today's slice.
  Future<List<ReelCard>> tasksByHorizon(Horizon h) async {
    final rows = await db.rawQuery(
      "$_sel WHERE c.kind = 'task' AND c.horizon = ? ORDER BY c.title",
      [horizonKey(h)],
    );
    return rows.map(ReelCard.fromRow).toList();
  }

  // ---------------------------------------------------------------- writes

  Future<void> setDone(String id, bool done) async {
    await db.insert(
      'daily_pick',
      {'day': dayKey(), 'card_id': id, 'done': done ? 1 : 0},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
    if (done) {
      final streak = Sqflite.firstIntValue(await db.rawQuery(
              'SELECT streak FROM task_state WHERE id = ?', [id])) ??
          0;
      await db.update(
        'task_state',
        {
          'status': statusKey(TaskStatus.done),
          'completed_at': DateTime.now().toIso8601String(),
          'streak': streak + 1,
        },
        where: 'id = ?',
        whereArgs: [id],
      );
    } else {
      await db.update(
        'task_state',
        {'status': statusKey(TaskStatus.backlog), 'completed_at': null},
        where: 'id = ?',
        whereArgs: [id],
      );
    }
  }

  /// Long-term work moves by percentage instead of a tick. Hitting 100 retires it.
  Future<void> setProgress(String id, int pct) async {
    final v = pct.clamp(0, 100);
    await db.update(
      'task_state',
      {
        'progress': v,
        'status': statusKey(v >= 100 ? TaskStatus.done : TaskStatus.active),
        if (v >= 100) 'completed_at': DateTime.now().toIso8601String(),
      },
      where: 'id = ?',
      whereArgs: [id],
    );
    if (v >= 100) await setDone(id, true);
  }

  /// Push a task out of the way for a few days so it stops crowding the list.
  Future<void> snooze(String id, {int days = 3}) async {
    await db.update(
      'task_state',
      {
        'status': statusKey(TaskStatus.snoozed),
        'snooze_until': dayKey(DateTime.now().add(Duration(days: days))),
      },
      where: 'id = ?',
      whereArgs: [id],
    );
    await db.delete('daily_pick',
        where: 'day = ? AND card_id = ?', whereArgs: [dayKey(), id]);
  }

  // ----------------------------------------------------------------- facts

  /// Leitner intervals in days. A fact you keep finding useful drifts toward
  /// the back of the queue instead of repeating until you stop reading it.
  static const _boxDays = [1, 3, 7, 21, 60, 180];

  static const _factSel = '''
    SELECT c.*, f.box, f.next_due, f.useful_count, f.retired
    FROM cards c LEFT JOIN fact_state f ON f.id = c.id
  ''';

  /// One fact a day, held steady until tomorrow. Prefers whatever is overdue;
  /// if nothing is due it shows the longest-unseen card rather than nothing.
  Future<ReelCard?> dailyFact() async {
    final day = dayKey();

    final held = await db.rawQuery(
      '$_factSel JOIN daily_fact d ON d.card_id = c.id WHERE d.day = ?',
      [day],
    );
    if (held.isNotEmpty) return ReelCard.fromRow(held.first);

    final due = await db.rawQuery(
      "$_factSel WHERE c.kind = 'fact' AND COALESCE(f.retired, 0) = 0 "
      "AND (f.next_due IS NULL OR f.next_due <= ?) "
      "ORDER BY f.next_due IS NULL DESC, f.next_due ASC",
      [day],
    );

    var pool = due;
    if (pool.isEmpty) {
      pool = await db.rawQuery(
        "$_factSel WHERE c.kind = 'fact' AND COALESCE(f.retired, 0) = 0 "
        "ORDER BY f.last_shown IS NULL DESC, f.last_shown ASC LIMIT 8",
      );
    }
    if (pool.isEmpty) return null;

    // Seeded on the date so the pick survives a restart, same as the task list.
    final head = pool.take(8).toList()..shuffle(_seeded(day));
    final chosen = head.first;

    await db.insert('daily_fact', {'day': day, 'card_id': chosen['id']},
        conflictAlgorithm: ConflictAlgorithm.replace);
    await db.update('fact_state', {'last_shown': day},
        where: 'id = ?', whereArgs: [chosen['id']]);
    return ReelCard.fromRow(chosen);
  }

  /// Useful pushes the fact further out; retiring stops it surfacing at all.
  Future<void> rateFact(String id, {required bool useful}) async {
    if (!useful) {
      await db.update('fact_state', {'retired': 1},
          where: 'id = ?', whereArgs: [id]);
      return;
    }
    final row = await db.query('fact_state',
        columns: ['box', 'useful_count'], where: 'id = ?', whereArgs: [id]);
    final box = (row.isEmpty ? 0 : (row.first['box'] as int? ?? 0));
    final used = (row.isEmpty ? 0 : (row.first['useful_count'] as int? ?? 0));
    final next = (box + 1).clamp(0, _boxDays.length - 1);
    await db.update(
      'fact_state',
      {
        'box': next,
        'useful_count': used + 1,
        'next_due': dayKey(DateTime.now().add(Duration(days: _boxDays[next]))),
      },
      where: 'id = ?',
      whereArgs: [id],
    );
  }

  Future<void> reviveFacts() async {
    await db.update('fact_state', {'retired': 0, 'box': 0, 'next_due': dayKey()});
  }

  Future<List<ReelCard>> factsByDomain(String? domain) async {
    final where = domain == null
        ? "c.kind = 'fact'"
        : "c.kind = 'fact' AND c.domain = ?";
    final rows = await db.rawQuery(
      '$_factSel WHERE $where ORDER BY c.title',
      domain == null ? null : [domain],
    );
    return rows.map(ReelCard.fromRow).toList();
  }

  // ---------------------------------------------------------------- search

  /// Searches titles, summaries, claims, reasoning and tags — so looking up
  /// "sunk cost" finds the card even when the caption never used the phrase.
  Future<List<ReelCard>> search(String query, {String? domain, CardKind? kind}) async {
    final q = query.trim();
    if (q.isEmpty && domain == null && kind == null) return [];

    final filters = <String>[];
    final args = <Object?>[];

    if (q.isNotEmpty) {
      if (_fts) {
        // Prefix-match the last token so results narrow as you type.
        final terms = q.split(RegExp(r'\s+')).where((t) => t.isNotEmpty).toList();
        final match = terms.map((t) => '"${t.replaceAll('"', '')}"*').join(' ');
        filters.add('c.id IN (SELECT id FROM card_fts WHERE card_fts MATCH ?)');
        args.add(match);
      } else {
        const cols = ['title', 'summary', 'claim', 'why', 'applicability', 'tags'];
        filters.add('(${cols.map((c) => 'c.$c LIKE ?').join(' OR ')})');
        args.addAll(List.filled(cols.length, '%$q%'));
      }
    }
    if (domain != null) {
      filters.add('c.domain = ?');
      args.add(domain);
    }
    if (kind != null) {
      filters.add('c.kind = ?');
      args.add(kind.name);
    }

    final rows = await db.rawQuery('''
      SELECT c.*, s.status, s.progress
      FROM cards c LEFT JOIN task_state s ON s.id = c.id
      WHERE ${filters.join(' AND ')}
      ORDER BY c.kind, c.title
      LIMIT 200
    ''', args);
    return rows.map(ReelCard.fromRow).toList();
  }

  /// Finds the task on today's list that best matches spoken words.
  ///
  /// Voice gives loose phrasing ("the skincare one"), so this scores today's
  /// picks on overlapping words rather than trying to match a title exactly,
  /// and returns null when nothing is a clear enough hit to act on.
  Future<ReelCard?> matchTodayTask(String spoken) async {
    final words = spoken
        .toLowerCase()
        .split(RegExp(r'[^a-z0-9]+'))
        .where((w) => w.length > 2)
        .toSet();
    if (words.isEmpty) return null;

    ReelCard? best;
    var bestScore = 0;
    for (final c in await todayTasks()) {
      final hay = '${c.title} ${c.summary} ${c.domain} ${c.tags.join(' ')}'
          .toLowerCase();
      final score = words.where(hay.contains).length;
      if (score > bestScore) {
        bestScore = score;
        best = c;
      }
    }
    return bestScore > 0 ? best : null;
  }

  /// The whole shelf, for the library's resting state.
  Future<List<ReelCard>> allCards() async {
    final rows = await db.rawQuery(
      'SELECT c.*, s.status, s.progress FROM cards c '
      'LEFT JOIN task_state s ON s.id = c.id ORDER BY c.kind, c.title',
    );
    return rows.map(ReelCard.fromRow).toList();
  }

  /// Domains that actually have cards, with counts, for the filter row.
  Future<List<(String, int)>> domains({CardKind? kind}) async {
    final rows = await db.rawQuery(
      'SELECT domain, COUNT(*) n FROM cards '
      '${kind != null ? 'WHERE kind = ?' : ''} '
      'GROUP BY domain ORDER BY n DESC',
      kind != null ? [kind.name] : null,
    );
    return rows
        .map((r) => ((r['domain'] ?? 'other') as String, r['n'] as int))
        .toList();
  }

  Future<Map<String, int>> counts() async {
    Future<int> q(String w, [List<Object?>? a]) async =>
        Sqflite.firstIntValue(
            await db.rawQuery('SELECT COUNT(*) FROM cards WHERE $w', a)) ??
        0;
    return {
      'tasks': await q("kind = 'task'"),
      'facts': await q("kind = 'fact'"),
      'today': await q("kind = 'task' AND horizon = 'today'"),
      'short': await q("kind = 'task' AND horizon = 'short_term'"),
      'long': await q("kind = 'task' AND horizon = 'long_term'"),
    };
  }
}
