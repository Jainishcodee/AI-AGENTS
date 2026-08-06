import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

class VoiceService {
  final FlutterTts _tts = FlutterTts();
  final stt.SpeechToText _stt = stt.SpeechToText();

  bool _ttsReady = false;
  bool _sttReady = false;

  Completer<void>? _speakDone;

  /// The voice actually in use, so the UI can show what was picked.
  String voiceName = '';

  Future<void> init() async {
    await _tts.setLanguage(dotenv.env['TTS_LOCALE'] ?? 'en-GB');
    await _pickBestVoice();

    // Android's default is flat and slow. Dropping the pitch a little and
    // pushing the rate up is most of the difference between "screen reader"
    // and something you'd want talking to you.
    await _tts.setSpeechRate(_envDouble('TTS_RATE', 0.54));
    await _tts.setPitch(_envDouble('TTS_PITCH', 0.92));
    await _tts.setVolume(1.0);
    await _tts.awaitSpeakCompletion(true);

    _tts.setCompletionHandler(() {
      _speakDone?.complete();
      _speakDone = null;
    });
    _tts.setErrorHandler((msg) {
      if (!(_speakDone?.isCompleted ?? true)) {
        _speakDone!.complete();
      }
      _speakDone = null;
    });
    _ttsReady = true;

    _sttReady = await _stt.initialize(
      onError: (e) {},
      onStatus: (s) {},
    );
  }

  double _envDouble(String key, double fallback) =>
      double.tryParse(dotenv.env[key] ?? '') ?? fallback;

  /// Picks the best-sounding English voice the phone actually has.
  ///
  /// Android ships several tiers under the same engine: the `-network` voices
  /// are markedly better than the compressed `-local` ones, and the default is
  /// usually neither. Set TTS_VOICE in .env to pin a specific one.
  Future<void> _pickBestVoice() async {
    final pinned = dotenv.env['TTS_VOICE'];

    try {
      final raw = await _tts.getVoices;
      if (raw is! List) return;

      final voices = raw
          .whereType<Map>()
          .map((m) => (
                name: (m['name'] ?? '').toString(),
                locale: (m['locale'] ?? '').toString(),
              ))
          .where((v) => v.name.isNotEmpty)
          .toList();
      if (voices.isEmpty) return;

      if (pinned != null && pinned.isNotEmpty) {
        final hit = voices.where((v) => v.name == pinned);
        if (hit.isNotEmpty) {
          await _tts.setVoice({'name': hit.first.name, 'locale': hit.first.locale});
          voiceName = hit.first.name;
          return;
        }
      }

      int score(({String name, String locale}) v) {
        final n = v.name.toLowerCase();
        final l = v.locale.toLowerCase();
        if (!l.startsWith('en')) return -1;

        var s = 0;
        if (n.contains('network')) s += 40; // the good tier
        if (n.contains('male') && !n.contains('female')) s += 30;
        if (l.startsWith('en-gb')) s += 12;
        if (l.startsWith('en-us')) s += 8;
        if (l.startsWith('en-in')) s += 4;
        if (n.contains('female')) s -= 25;
        return s;
      }

      final ranked = voices.where((v) => score(v) >= 0).toList()
        ..sort((a, b) => score(b).compareTo(score(a)));
      if (ranked.isEmpty) return;

      await _tts.setVoice({'name': ranked.first.name, 'locale': ranked.first.locale});
      voiceName = ranked.first.name;
    } catch (e) {
      // Some engines don't implement getVoices; the language setting still applies.
      debugPrint('voice pick skipped: $e');
    }
  }

  /// Every English voice on the device, for a picker in settings.
  Future<List<({String name, String locale})>> availableVoices() async {
    try {
      final raw = await _tts.getVoices;
      if (raw is! List) return const [];
      return raw
          .whereType<Map>()
          .map((m) => (
                name: (m['name'] ?? '').toString(),
                locale: (m['locale'] ?? '').toString(),
              ))
          .where((v) => v.locale.toLowerCase().startsWith('en'))
          .toList();
    } catch (_) {
      return const [];
    }
  }

  Future<void> useVoice(String name, String locale) async {
    await _tts.setVoice({'name': name, 'locale': locale});
    voiceName = name;
  }

  bool get isReady => _ttsReady;
  bool get sttAvailable => _sttReady;

  Future<void> speak(String text) async {
    if (text.trim().isEmpty) return;
    if (!_ttsReady) await init();
    _speakDone = Completer<void>();
    await _tts.speak(text);
    await _speakDone!.future;
  }

  Future<void> stop() async {
    await _tts.stop();
    if (!(_speakDone?.isCompleted ?? true)) _speakDone!.complete();
  }

  /// Starts listening. [onResult] is called with the FINAL transcription only.
  /// [onPartial] is called repeatedly with partial transcriptions for live UI.
  Future<bool> listen({
    required void Function(String text) onResult,
    void Function(String text)? onPartial,
  }) async {
    if (!_sttReady) {
      _sttReady = await _stt.initialize();
      if (!_sttReady) return false;
    }
    await _stt.listen(
      listenOptions: stt.SpeechListenOptions(
        listenMode: stt.ListenMode.confirmation,
        partialResults: true,
        cancelOnError: true,
      ),
      pauseFor: const Duration(seconds: 3),
      listenFor: const Duration(seconds: 20),
      onResult: (r) {
        if (r.finalResult) {
          onResult(r.recognizedWords);
        } else if (onPartial != null) {
          onPartial(r.recognizedWords);
        }
      },
    );
    return true;
  }

  Future<void> stopListening() => _stt.stop();
  bool get isListening => _stt.isListening;
}
