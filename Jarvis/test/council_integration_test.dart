import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:jarvis/screens/council_screen.dart';
import 'package:jarvis/services/council_service.dart';
import 'package:jarvis/services/reminder_service.dart';
import 'package:jarvis/services/jarvis_brain.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    dotenv.testLoad(fileInput: 'GEMINI_API_KEY=\nUSER_NAME=ANSH\n');
  });

  group('CouncilService Models', () {
    test('DueDecision parses json correctly for open and resolved cards', () {
      final openJson = {
        'id': 'card-1',
        'question': 'Should I switch to another team?',
        'created_at': '2026-10-01T12:00:00Z',
        'expected_outcome': {
          'statement': 'New team yields higher leverage within 6 months.',
          'check_on': '2026-12-01',
          'measurable_by': 'Quarterly impact score',
        },
        'synthesis': {
          'recommendation': {
            'action': 'Transition gradually over 4 weeks.',
          },
        },
      };

      final openCard = DueDecision.fromJson(openJson);
      expect(openCard.id, 'card-1');
      expect(openCard.question, 'Should I switch to another team?');
      expect(openCard.recommendation, 'Transition gradually over 4 weeks.');
      expect(openCard.prediction, 'New team yields higher leverage within 6 months.');
      expect(openCard.status, 'open');

      final resolvedJson = {
        'id': 'card-2',
        'question': 'Should I launch the beta today?',
        'created_at': '2026-08-01T12:00:00Z',
        'resolution': {
          'chose': 'Launched beta',
          'actual_outcome': 'Acquired 500 early users with minimal bug reports',
          'surprises': ['Faster adoption in EU than expected'],
        },
      };

      final resolvedCard = DueDecision.fromJson(resolvedJson);
      expect(resolvedCard.id, 'card-2');
      expect(resolvedCard.status, 'resolved');
      expect(resolvedCard.chose, 'Launched beta');
      expect(resolvedCard.actualOutcome, 'Acquired 500 early users with minimal bug reports');
      expect(resolvedCard.surprises, contains('Faster adoption in EU than expected'));
    });

    test('DeliberationResult parses synthesis and minority reports', () {
      final json = {
        'id': 'delib-101',
        'question': 'Should we adopt microservices or stay monolith?',
        'preset': 'execution',
        'depth': 'quick',
        'synthesis': {
          'recommendation': {
            'action': 'Retain modular monolith and optimize database queries.',
            'first_action': 'Profile slowest endpoints.',
            'do_not': ['Do not rewrite auth service'],
            'conditions': ['Scale stays under 50k DAU'],
          },
          'debate_summary': 'Tactician and Optimizer agreed on avoiding premature distribution overhead.',
          'confidence': {'level': 'high', 'score': 0.88},
          'council_blind_spot': 'Third-party API rate limits were not factored in.',
          'expected_outcome': {
            'statement': 'System handles peak traffic without latency spikes.',
            'check_in_days': 45,
            'check_on': '2026-12-10',
          },
          'minority_opinions': [
            {
              'module': 'analyst',
              'position': 'Split reporting database into separate replica.',
              'when_it_would_be_right': 'Read query ratio exceeds 80%',
            }
          ],
        },
      };

      final result = DeliberationResult.fromJson(json);
      expect(result.id, 'delib-101');
      expect(result.action, 'Retain modular monolith and optimize database queries.');
      expect(result.firstAction, 'Profile slowest endpoints.');
      expect(result.confidence, contains('high'));
      expect(result.blindSpot, contains('rate limits'));
      expect(result.checkInDays, 45);
      expect(result.minorityOpinions.length, 1);
      expect(result.minorityOpinions.first.module, 'analyst');
      expect(result.minorityOpinions.first.position, contains('reporting database'));
    });

    test('CouncilService settings save and load', () async {
      final reminders = ReminderService();
      final service = CouncilService(reminders);
      await service.load();
      expect(service.baseUrl, 'http://127.0.0.1:8787');

      await service.save(url: 'http://192.168.1.100:8787', secret: 'secret123');
      expect(service.baseUrl, 'http://192.168.1.100:8787');
      expect(service.token, 'secret123');

      final service2 = CouncilService(reminders);
      await service2.load();
      expect(service2.baseUrl, 'http://192.168.1.100:8787');
      expect(service2.token, 'secret123');
    });
  });

  group('JarvisBrain Council Intents', () {
    test('reports when no key is set or no decisions are due', () async {
      final reminders = ReminderService();
      final service = CouncilService(reminders);
      final brain = JarvisBrain(reminders: reminders, council: service);

      service.due = [];

      final reply = await brain.handle('Are any council decisions due?');
      expect(reply, isNotNull);
      expect(reply.spokenText, isNotEmpty);
    });
  });

  group('CouncilScreen Widget Tests', () {
    testWidgets('CouncilScreen mounts and displays 3 tabs', (tester) async {
      final reminders = ReminderService();
      final service = CouncilService(reminders);

      await tester.pumpWidget(
        MaterialApp(
          home: CouncilScreen(service: service),
        ),
      );

      // Verify tabs exist
      expect(find.text('Consult'), findsOneWidget);
      expect(find.text('Decisions'), findsOneWidget);
      expect(find.text('Engines'), findsOneWidget);

      // Verify main action exists
      expect(find.text('Deliberate Decision'), findsOneWidget);

      // Switch to Decisions tab
      await tester.tap(find.text('Decisions'));
      await tester.pumpAndSettle();
      expect(find.text('All (0)'), findsOneWidget);

      // Switch to Engines tab
      await tester.tap(find.text('Engines'));
      await tester.pumpAndSettle();
      expect(find.text('The Six Reasoning Engines'), findsOneWidget);
      expect(find.textContaining('ANALYST'), findsOneWidget);
      expect(find.textContaining('TACTICIAN'), findsOneWidget);
    });
  });
}

