import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import '../models/todo_task.dart';

class TodoDb {
  static const _dbName = 'todo_notes.db';
  static const _schemaVersion = 1;

  Database? _db;
  Database get db => _db!;
  bool get isOpen => _db != null && _db!.isOpen;

  // In-memory fallback if SQLite fails or on test environments
  final List<TodoTask> _fallbackTasks = [];

  Future<Database?> _getDb() async {
    if (_db != null && _db!.isOpen) return _db;
    try {
      await init();
    } catch (_) {
      return null;
    }
    return _db;
  }

  Future<void> init({Database? database}) async {
    if (_db != null && _db!.isOpen) return;
    if (database != null) {
      _db = database;
      await _createSchema(database);
      return;
    }
    try {
      _db = await openDatabase(
        p.join(await getDatabasesPath(), _dbName),
        version: _schemaVersion,
        onCreate: (d, _) => _createSchema(d),
        onUpgrade: (d, _, _) => _createSchema(d),
      );
    } catch (_) {
      // In-memory or platform fallback handles operations
    }
  }

  Future<void> _createSchema(Database d) async {
    await d.execute('''
      CREATE TABLE IF NOT EXISTS todos(
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        notes TEXT,
        priority TEXT NOT NULL DEFAULT 'medium',
        status TEXT NOT NULL DEFAULT 'todo',
        category TEXT NOT NULL DEFAULT 'General',
        due_date TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    ''');
    await d.execute('CREATE INDEX IF NOT EXISTS idx_todo_priority ON todos(priority)');
    await d.execute('CREATE INDEX IF NOT EXISTS idx_todo_status ON todos(status)');
    await d.execute('CREATE INDEX IF NOT EXISTS idx_todo_category ON todos(category)');
  }

  Future<List<TodoTask>> allTasks() async {
    final d = await _getDb();
    if (d == null) {
      return List.unmodifiable(_fallbackTasks);
    }
    final rows = await d.query(
      'todos',
      orderBy: "CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, created_at DESC",
    );
    return rows.map(TodoTask.fromMap).toList();
  }

  Future<void> saveTask(TodoTask task) async {
    final d = await _getDb();
    if (d == null) {
      final idx = _fallbackTasks.indexWhere((t) => t.id == task.id);
      if (idx >= 0) {
        _fallbackTasks[idx] = task;
      } else {
        _fallbackTasks.insert(0, task);
      }
      return;
    }
    await d.insert(
      'todos',
      task.toMap(),
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> deleteTask(String id) async {
    final d = await _getDb();
    if (d == null) {
      _fallbackTasks.removeWhere((t) => t.id == id);
      return;
    }
    await d.delete('todos', where: 'id = ?', whereArgs: [id]);
  }

  Future<void> toggleDone(String id) async {
    final d = await _getDb();
    if (d == null) {
      final idx = _fallbackTasks.indexWhere((t) => t.id == id);
      if (idx >= 0) {
        final current = _fallbackTasks[idx];
        final nextStatus = current.isDone ? TodoStatus.todo : TodoStatus.done;
        _fallbackTasks[idx] = current.copyWith(status: nextStatus);
      }
      return;
    }

    final rows = await d.query('todos', where: 'id = ?', whereArgs: [id], limit: 1);
    if (rows.isEmpty) return;
    final task = TodoTask.fromMap(rows.first);
    final nextStatus = task.isDone ? TodoStatus.todo : TodoStatus.done;
    await d.update(
      'todos',
      {
        'status': nextStatus.name,
        'updated_at': DateTime.now().toIso8601String(),
      },
      where: 'id = ?',
      whereArgs: [id],
    );
  }

  Future<List<String>> categories() async {
    final d = await _getDb();
    if (d == null) {
      final cats = _fallbackTasks.map((t) => t.category).toSet().toList();
      if (cats.isEmpty) return ['General', 'Work', 'Personal', 'Ideas'];
      return cats;
    }
    final rows = await d.rawQuery('SELECT DISTINCT category FROM todos WHERE category IS NOT NULL AND category != ""');
    final list = rows.map((r) => r['category'] as String).toList();
    if (!list.contains('General')) list.insert(0, 'General');
    return list;
  }
}

