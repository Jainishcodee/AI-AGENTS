import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_dotenv/flutter_dotenv.dart';

class GeminiResult {
  final String text;
  final Map<String, dynamic>? action;
  GeminiResult(this.text, this.action);
}

class GeminiService {
  static const _model = 'gemini-2.5-flash';
  static const _endpoint =
      'https://generativelanguage.googleapis.com/v1beta/models/$_model:generateContent';

  String get _apiKey => dotenv.env['GEMINI_API_KEY'] ?? '';
  bool get hasKey =>
      _apiKey.isNotEmpty && _apiKey != 'PASTE_YOUR_GEMINI_KEY_HERE';

  final List<Map<String, dynamic>> _history = [];

  String get _systemPrompt {
    final name = dotenv.env['USER_NAME'] ?? 'Sir';
    final now = DateTime.now();
    return '''
You are Jarvis, $name's personal AI assistant. You speak in short, direct, helpful sentences — think calm British butler, never wordy. Current time: ${now.toIso8601String()}.

You MUST respond with a single JSON object on one line, no markdown, no code fences. Schema:
{"say": "<what you will speak out loud>", "action": null | {"type": "<intent>", ...params}}

Available intents (use ONLY these):
- {"type":"weather","location":"<city or null>"}            // ask about weather
- {"type":"note","content":"<the note text>"}                // user wants to save a note
- {"type":"reminder","content":"<what to remind>","when":"<ISO8601 datetime>"}  // schedule reminder
- {"type":"spotify","query":"<song or artist or playlist>"}  // play music on Spotify
- {"type":"today_tasks"}                                     // what should I do today
- {"type":"daily_fact"}                                      // fact of the day / teach me something
- {"type":"complete_task","query":"<words from the task>"}   // mark a task finished
- {"type":"find_saved","query":"<what to look for>"}         // search saved reels/tasks/facts
- {"type":"stop"}                                            // user wants to stop / cancel

The last four read from $name's own saved Instagram reels, which have been turned
into tasks and facts. Use find_saved whenever they ask what they saved about a
topic, or to recall something they know they saw.

Examples:
User: "What's the weather in Mumbai?"
Reply: {"say":"Let me check Mumbai for you.","action":{"type":"weather","location":"Mumbai"}}

User: "Take a note: buy milk and eggs"
Reply: {"say":"Got it. Opening your notes now.","action":{"type":"note","content":"buy milk and eggs"}}

User: "Remind me to call mom at 6pm today"
Reply: {"say":"Reminder set for six this evening.","action":{"type":"reminder","content":"call mom","when":"${now.toIso8601String().substring(0, 10)}T18:00:00"}}

User: "Play some lofi on Spotify"
Reply: {"say":"Opening Spotify with lofi.","action":{"type":"spotify","query":"lofi"}}

User: "What should I do today?"
Reply: {"say":"Here's today's list.","action":{"type":"today_tasks"}}

User: "Tell me something useful"
Reply: {"say":"Your fact for today.","action":{"type":"daily_fact"}}

User: "I finished the skincare one"
Reply: {"say":"Marking it done.","action":{"type":"complete_task","query":"skincare"}}

User: "What did I save about decision making?"
Reply: {"say":"Searching what you saved.","action":{"type":"find_saved","query":"decision making"}}

User: "Who won the cricket match yesterday?"
Reply: {"say":"I can't check the news, but I can help with weather, notes, reminders, or music.","action":null}

If the request is small-talk or general chat with no action needed, return action: null and just answer briefly in "say". Never invent intents. Output JSON only.
''';
  }

  Future<GeminiResult> ask(String userText) async {
    if (!hasKey) {
      return GeminiResult(
        "I need a Gemini API key first. Open dot env in the Jarvis folder and paste your key.",
        null,
      );
    }

    _history.add({
      'role': 'user',
      'parts': [
        {'text': userText}
      ],
    });

    final body = {
      'system_instruction': {
        'parts': [
          {'text': _systemPrompt}
        ]
      },
      'contents': _history,
      'generationConfig': {
        'temperature': 0.4,
        'maxOutputTokens': 250,
        'responseMimeType': 'application/json',
      },
    };

    try {
      final resp = await http.post(
        Uri.parse('$_endpoint?key=$_apiKey'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(body),
      );
      if (resp.statusCode != 200) {
        String detail = '';
        try {
          final err = jsonDecode(resp.body) as Map<String, dynamic>;
          detail = (err['error']?['message'] as String?) ?? '';
        } catch (_) {}
        final hint = switch (resp.statusCode) {
          429 => "Rate limit. Wait a minute and try again, or your free tier may not include this model.",
          400 => "Bad request. The API key may be invalid.",
          403 => "Access denied. Enable the Generative Language API for your project.",
          404 => "Model not found. Google may have renamed it.",
          _ => "",
        };
        return GeminiResult(
          "Gemini error ${resp.statusCode}. $hint ${detail.isNotEmpty ? '($detail)' : ''}".trim(),
          null,
        );
      }
      final data = jsonDecode(resp.body) as Map<String, dynamic>;
      final candidates = data['candidates'] as List?;
      if (candidates == null || candidates.isEmpty) {
        return GeminiResult("I didn't catch that. Try again?", null);
      }
      final raw = (candidates.first['content']['parts'][0]['text'] as String).trim();

      _history.add({
        'role': 'model',
        'parts': [
          {'text': raw}
        ],
      });
      if (_history.length > 20) {
        _history.removeRange(0, _history.length - 20);
      }

      try {
        final parsed = jsonDecode(raw) as Map<String, dynamic>;
        final say = (parsed['say'] as String?) ?? raw;
        final action = parsed['action'];
        return GeminiResult(
            say, action is Map<String, dynamic> ? action : null);
      } catch (_) {
        return GeminiResult(raw, null);
      }
    } catch (e) {
      return GeminiResult("Network is being shy. Try again in a moment.", null);
    }
  }

  void resetConversation() => _history.clear();
}
