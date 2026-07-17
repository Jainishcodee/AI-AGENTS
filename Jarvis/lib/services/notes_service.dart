import 'package:android_intent_plus/android_intent.dart';
import 'package:android_intent_plus/flag.dart';

class NotesService {
  /// Tries Google Keep first; falls back to the generic ACTION_SEND so the user
  /// can pick whichever notes app they have (Samsung Notes, OneNote, etc.).
  Future<bool> saveNote(String content) async {
    final body = content.trim();
    if (body.isEmpty) return false;

    final keep = AndroidIntent(
      action: 'android.intent.action.SEND',
      type: 'text/plain',
      package: 'com.google.android.keep',
      arguments: <String, dynamic>{
        'android.intent.extra.TEXT': body,
        'android.intent.extra.SUBJECT': 'Note from Jarvis',
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
        'android.intent.extra.SUBJECT': 'Note from Jarvis',
      },
      flags: <int>[Flag.FLAG_ACTIVITY_NEW_TASK],
    );
    try {
      await share.launchChooser('Save this note in');
      return true;
    } catch (_) {
      return false;
    }
  }
}
