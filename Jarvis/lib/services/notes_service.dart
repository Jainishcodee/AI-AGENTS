import 'package:android_intent_plus/android_intent.dart';
import 'package:android_intent_plus/flag.dart';

import '../models/todo_task.dart';
import 'todo_db.dart';

class NotesService {
  NotesService({this.todoDb});

  final TodoDb? todoDb;

  /// Saves the note locally in ANSH's task & notes list, and also tries Google Keep
  /// / Android share intent so external notes work as well.
  Future<bool> saveNote(String content) async {
    final body = content.trim();
    if (body.isEmpty) return false;

    // Save locally in ANSH todo & notes store
    if (todoDb != null) {
      final lines = body.split('\n');
      final title = lines.first.trim();
      final remainingNotes = lines.length > 1 ? lines.sublist(1).join('\n').trim() : '';
      final task = TodoTask(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        title: title.length > 60 ? '${title.substring(0, 57)}...' : title,
        notes: remainingNotes.isNotEmpty ? remainingNotes : body,
        category: 'Notes',
        priority: TaskPriority.medium,
      );
      try {
        await todoDb!.saveTask(task);
      } catch (_) {}
    }

    final keep = AndroidIntent(
      action: 'android.intent.action.SEND',
      type: 'text/plain',
      package: 'com.google.android.keep',
      arguments: <String, dynamic>{
        'android.intent.extra.TEXT': body,
        'android.intent.extra.SUBJECT': 'Note from ANSH',
      },
      flags: <int>[Flag.FLAG_ACTIVITY_NEW_TASK],
    );

    try {
      await keep.launch();
      return true;
    } catch (_) {
      // Fall through to a chooser so any notes app works
    }

    final share = AndroidIntent(
      action: 'android.intent.action.SEND',
      type: 'text/plain',
      arguments: <String, dynamic>{
        'android.intent.extra.TEXT': body,
        'android.intent.extra.SUBJECT': 'Note from ANSH',
      },
      flags: <int>[Flag.FLAG_ACTIVITY_NEW_TASK],
    );
    try {
      await share.launchChooser('Save this note in');
      return true;
    } catch (_) {
      // Even if external share fails, local save succeeded
      return todoDb != null;
    }
  }
}
