import 'dart:async';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

class VoiceService {
  final FlutterTts _tts = FlutterTts();
  final stt.SpeechToText _stt = stt.SpeechToText();

  bool _ttsReady = false;
  bool _sttReady = false;

  Completer<void>? _speakDone;

  Future<void> init() async {
    await _tts.setLanguage('en-US');
    await _tts.setSpeechRate(0.5);
    await _tts.setPitch(1.05);
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
