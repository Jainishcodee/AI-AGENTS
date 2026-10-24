import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis/screens/health_screen.dart';
import 'package:jarvis/services/health_db.dart';
import 'package:jarvis/services/jain_calendar.dart';
import 'package:jarvis/services/training_plan.dart';

void main() {
  testWidgets('HealthScreen mounts and finishes loading without hanging', (tester) async {
    final db = HealthDb();
    final calendar = JainCalendar();
    final plan = TrainingPlan();

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: HealthScreen(
            db: db,
            calendar: calendar,
            plan: plan,
          ),
        ),
      ),
    );

    // Initial pump: loading indicator
    await tester.pump();

    // After async load completes
    await tester.pumpAndSettle();

    // CircularProgressIndicator should be gone
    expect(find.byType(CircularProgressIndicator), findsNothing);

    // The Health header and cards should be visible
    expect(find.text('HEALTH'), findsOneWidget);
    expect(find.text('SET UP'), findsOneWidget);
  });
}

