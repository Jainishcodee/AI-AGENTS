import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:jarvis/models/todo_task.dart';
import 'package:jarvis/screens/todo_screen.dart';
import 'package:jarvis/services/todo_db.dart';

void main() {
  group('TodoDb & TodoScreen', () {
    test('saveTask and toggleDone works with in-memory fallback', () async {
      final db = TodoDb();
      final task = TodoTask(
        id: 't1',
        title: 'Review stockseer pipeline',
        notes: 'Check IPO calendar alerts and notification delivery',
        priority: TaskPriority.urgent,
        category: 'Work',
      );

      await db.saveTask(task);
      var all = await db.allTasks();
      expect(all.length, 1);
      expect(all.first.title, 'Review stockseer pipeline');
      expect(all.first.isDone, false);
      expect(all.first.priority, TaskPriority.urgent);

      await db.toggleDone('t1');
      all = await db.allTasks();
      expect(all.first.isDone, true);

      await db.deleteTask('t1');
      all = await db.allTasks();
      expect(all.isEmpty, true);
    });

    testWidgets('TodoScreen mounts, shows empty state and handles add',
        (tester) async {
      final db = TodoDb();
      await db.saveTask(
        TodoTask(
          id: 't2',
          title: 'Notion style task',
          notes: 'Important notes attached here',
          priority: TaskPriority.high,
        ),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: TodoScreen(todoDb: db),
          ),
        ),
      );

      await tester.pumpAndSettle();

      expect(find.text('PRIORITY & NOTES'), findsOneWidget);
      expect(find.text('Notion style task'), findsOneWidget);
      expect(find.text('Important notes attached here'), findsOneWidget);
      expect(find.text('P2'), findsOneWidget);
    });
  });
}

