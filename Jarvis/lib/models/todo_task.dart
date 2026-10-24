import 'package:flutter/material.dart';

enum TaskPriority {
  urgent,
  high,
  medium,
  low;

  String get label => switch (this) {
        TaskPriority.urgent => 'Urgent',
        TaskPriority.high => 'High',
        TaskPriority.medium => 'Medium',
        TaskPriority.low => 'Low',
      };

  String get tag => switch (this) {
        TaskPriority.urgent => 'P1',
        TaskPriority.high => 'P2',
        TaskPriority.medium => 'P3',
        TaskPriority.low => 'P4',
      };

  Color get color => switch (this) {
        TaskPriority.urgent => const Color(0xFFE74848),
        TaskPriority.high => const Color(0xFFFFB347),
        TaskPriority.medium => const Color(0xFF00E5C9),
        TaskPriority.low => const Color(0xFF8E8E93),
      };
}

enum TodoStatus {
  todo,
  inProgress,
  done;

  String get label => switch (this) {
        TodoStatus.todo => 'To Do',
        TodoStatus.inProgress => 'In Progress',
        TodoStatus.done => 'Completed',
      };
}

class TodoTask {
  TodoTask({
    required this.id,
    required this.title,
    this.notes = '',
    this.priority = TaskPriority.medium,
    this.status = TodoStatus.todo,
    this.category = 'General',
    this.dueDate,
    DateTime? createdAt,
    DateTime? updatedAt,
  })  : createdAt = createdAt ?? DateTime.now(),
        updatedAt = updatedAt ?? DateTime.now();

  final String id;
  final String title;
  final String notes;
  final TaskPriority priority;
  final TodoStatus status;
  final String category;
  final String? dueDate; // yyyy-MM-dd
  final DateTime createdAt;
  final DateTime updatedAt;

  bool get isDone => status == TodoStatus.done;

  TodoTask copyWith({
    String? id,
    String? title,
    String? notes,
    TaskPriority? priority,
    TodoStatus? status,
    String? category,
    String? dueDate,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    return TodoTask(
      id: id ?? this.id,
      title: title ?? this.title,
      notes: notes ?? this.notes,
      priority: priority ?? this.priority,
      status: status ?? this.status,
      category: category ?? this.category,
      dueDate: dueDate ?? this.dueDate,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? DateTime.now(),
    );
  }

  Map<String, Object?> toMap() => {
        'id': id,
        'title': title,
        'notes': notes,
        'priority': priority.name,
        'status': status.name,
        'category': category,
        'due_date': dueDate,
        'created_at': createdAt.toIso8601String(),
        'updated_at': updatedAt.toIso8601String(),
      };

  factory TodoTask.fromMap(Map<String, Object?> m) => TodoTask(
        id: m['id'] as String,
        title: m['title'] as String,
        notes: (m['notes'] as String?) ?? '',
        priority: TaskPriority.values.firstWhere(
          (p) => p.name == m['priority'],
          orElse: () => TaskPriority.medium,
        ),
        status: TodoStatus.values.firstWhere(
          (s) => s.name == m['status'],
          orElse: () => TodoStatus.todo,
        ),
        category: (m['category'] as String?) ?? 'General',
        dueDate: m['due_date'] as String?,
        createdAt: DateTime.tryParse((m['created_at'] as String?) ?? '') ??
            DateTime.now(),
        updatedAt: DateTime.tryParse((m['updated_at'] as String?) ?? '') ??
            DateTime.now(),
      );
}

