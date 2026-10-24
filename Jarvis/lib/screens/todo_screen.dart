import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../models/todo_task.dart';
import '../services/todo_db.dart';

class TodoScreen extends StatefulWidget {
  const TodoScreen({super.key, required this.todoDb});

  final TodoDb todoDb;

  @override
  State<TodoScreen> createState() => _TodoScreenState();
}

class _TodoScreenState extends State<TodoScreen> {
  static const _red = Color(0xFFE74848);
  static const _teal = Color(0xFF00E5C9);
  static const _amber = Color(0xFFFFB347);
  static const _surface = Color(0xFF18101A);

  List<TodoTask> _tasks = [];
  bool _loading = true;
  String _searchQuery = '';
  TaskPriority? _selectedPriority;
  String _selectedStatus = 'all'; // 'all', 'active', 'done'
  String _selectedCategory = 'all';
  List<String> _categories = ['all'];

  final TextEditingController _quickTitleController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _quickTitleController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final tasks = await widget.todoDb.allTasks();
      final cats = await widget.todoDb.categories();
      if (!mounted) return;
      setState(() {
        _tasks = tasks;
        _categories = ['all', ...cats.where((c) => c.toLowerCase() != 'all')];
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  List<TodoTask> get _filteredTasks {
    return _tasks.where((t) {
      if (_selectedPriority != null && t.priority != _selectedPriority) {
        return false;
      }
      if (_selectedStatus == 'active' && t.isDone) return false;
      if (_selectedStatus == 'done' && !t.isDone) return false;
      if (_selectedCategory != 'all' && t.category != _selectedCategory) {
        return false;
      }
      if (_searchQuery.isNotEmpty) {
        final q = _searchQuery.toLowerCase();
        final matchTitle = t.title.toLowerCase().contains(q);
        final matchNotes = t.notes.toLowerCase().contains(q);
        final matchCat = t.category.toLowerCase().contains(q);
        if (!matchTitle && !matchNotes && !matchCat) return false;
      }
      return true;
    }).toList();
  }

  Future<void> _toggleDone(TodoTask task) async {
    await HapticFeedback.lightImpact();
    await widget.todoDb.toggleDone(task.id);
    await _load();
  }

  Future<void> _quickAdd() async {
    final title = _quickTitleController.text.trim();
    if (title.isEmpty) return;

    final newTask = TodoTask(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      title: title,
      priority: _selectedPriority ?? TaskPriority.medium,
      category: _selectedCategory == 'all' ? 'General' : _selectedCategory,
    );

    _quickTitleController.clear();
    await widget.todoDb.saveTask(newTask);
    await _load();
  }

  void _openEditor([TodoTask? task]) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => _TaskEditorSheet(
        task: task,
        categories: _categories.where((c) => c != 'all').toList(),
        onSave: (saved) async {
          await widget.todoDb.saveTask(saved);
          await _load();
        },
        onDelete: task == null
            ? null
            : () async {
                await widget.todoDb.deleteTask(task.id);
                await _load();
              },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator(color: _red));
    }

    final filtered = _filteredTasks;
    final totalPending = _tasks.where((t) => !t.isDone).length;
    final urgentCount =
        _tasks.where((t) => !t.isDone && t.priority == TaskPriority.urgent).length;

    return Scaffold(
      backgroundColor: Colors.transparent,
      body: SafeArea(
        child: Column(
          children: [
            _topBar(totalPending, urgentCount),
            _quickAddRow(),
            _filterRow(),
            Expanded(
              child: filtered.isEmpty
                  ? _emptyView()
                  : RefreshIndicator(
                      color: _red,
                      backgroundColor: _surface,
                      onRefresh: _load,
                      child: ListView.builder(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 80),
                        itemCount: filtered.length,
                        itemBuilder: (ctx, i) => _taskCard(filtered[i]),
                      ),
                    ),
            ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton(
        backgroundColor: _red,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        onPressed: () => _openEditor(),
        child: const Icon(Icons.add, size: 28),
      ),
    );
  }

  Widget _topBar(int pending, int urgent) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'PRIORITY & NOTES',
                    style: TextStyle(
                      fontSize: 18,
                      letterSpacing: 3.5,
                      fontWeight: FontWeight.w700,
                      color: _red,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    urgent > 0
                        ? '$pending pending · $urgent URGENT'
                        : '$pending tasks to do',
                    style: TextStyle(
                      color: urgent > 0 ? _amber : Colors.white60,
                      fontSize: 12,
                      fontWeight: urgent > 0 ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                ],
              ),
              const Spacer(),
              IconButton(
                icon: const Icon(Icons.add_task, color: _teal),
                tooltip: 'New Task & Note',
                onPressed: () => _openEditor(),
              ),
            ],
          ),
          const SizedBox(height: 10),
          // Search box
          Container(
            height: 42,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            decoration: BoxDecoration(
              color: _surface,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
            ),
            child: Row(
              children: [
                Icon(Icons.search, color: Colors.white.withValues(alpha: 0.4), size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    style: const TextStyle(color: Colors.white, fontSize: 13.5),
                    decoration: InputDecoration(
                      hintText: 'Search tasks, notes or tags...',
                      hintStyle: TextStyle(
                          color: Colors.white.withValues(alpha: 0.35), fontSize: 13),
                      border: InputBorder.none,
                      isDense: true,
                    ),
                    onChanged: (v) => setState(() => _searchQuery = v.trim()),
                  ),
                ),
                if (_searchQuery.isNotEmpty)
                  GestureDetector(
                    onTap: () => setState(() => _searchQuery = ''),
                    child: Icon(Icons.close,
                        color: Colors.white.withValues(alpha: 0.4), size: 18),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _quickAddRow() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
        decoration: BoxDecoration(
          color: _surface.withValues(alpha: 0.8),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: Colors.white.withValues(alpha: 0.07)),
        ),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _quickTitleController,
                style: const TextStyle(color: Colors.white, fontSize: 13.5),
                decoration: const InputDecoration(
                  hintText: 'Quick add a task...',
                  hintStyle: TextStyle(color: Colors.white38, fontSize: 13),
                  border: InputBorder.none,
                ),
                onSubmitted: (_) => _quickAdd(),
              ),
            ),
            IconButton(
              icon: const Icon(Icons.arrow_upward_rounded, color: _red, size: 20),
              onPressed: _quickAdd,
              tooltip: 'Add',
            ),
          ],
        ),
      ),
    );
  }

  Widget _filterRow() {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 6),
      child: Row(
        children: [
          // Status filters
          _statusPill('All', 'all'),
          const SizedBox(width: 6),
          _statusPill('Active', 'active'),
          const SizedBox(width: 6),
          _statusPill('Done', 'done'),
          const SizedBox(width: 14),
          // Priority filters
          _priorityPill('All Pri', null),
          const SizedBox(width: 6),
          _priorityPill('P1 Urgent', TaskPriority.urgent),
          const SizedBox(width: 6),
          _priorityPill('P2 High', TaskPriority.high),
          const SizedBox(width: 6),
          _priorityPill('P3 Med', TaskPriority.medium),
          const SizedBox(width: 6),
          _priorityPill('P4 Low', TaskPriority.low),
        ],
      ),
    );
  }

  Widget _statusPill(String label, String key) {
    final selected = _selectedStatus == key;
    return GestureDetector(
      onTap: () => setState(() => _selectedStatus = key),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: selected ? _red.withValues(alpha: 0.2) : Colors.white.withValues(alpha: 0.05),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: selected ? _red : Colors.white.withValues(alpha: 0.1),
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? Colors.white : Colors.white60,
            fontSize: 11,
            fontWeight: selected ? FontWeight.w700 : FontWeight.w400,
          ),
        ),
      ),
    );
  }

  Widget _priorityPill(String label, TaskPriority? p) {
    final selected = _selectedPriority == p;
    final color = p?.color ?? _teal;
    return GestureDetector(
      onTap: () => setState(() => _selectedPriority = p),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: selected ? color.withValues(alpha: 0.22) : Colors.white.withValues(alpha: 0.04),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: selected ? color : Colors.white.withValues(alpha: 0.08),
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? color : Colors.white54,
            fontSize: 11,
            fontWeight: selected ? FontWeight.w700 : FontWeight.w400,
          ),
        ),
      ),
    );
  }

  Widget _taskCard(TodoTask task) {
    final hasNotes = task.notes.trim().isNotEmpty;

    return Dismissible(
      key: ValueKey(task.id),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 20),
        color: _red.withValues(alpha: 0.4),
        child: const Icon(Icons.delete_outline, color: Colors.white),
      ),
      onDismissed: (_) {
        widget.todoDb.deleteTask(task.id);
        _tasks.removeWhere((t) => t.id == task.id);
      },
      child: GestureDetector(
        onTap: () => _openEditor(task),
        child: Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: _surface.withValues(alpha: 0.9),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
              color: task.priority == TaskPriority.urgent && !task.isDone
                  ? _red.withValues(alpha: 0.5)
                  : Colors.white.withValues(alpha: 0.08),
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Checkbox
              Padding(
                padding: const EdgeInsets.only(top: 2, right: 10),
                child: GestureDetector(
                  onTap: () => _toggleDone(task),
                  child: Container(
                    width: 22,
                    height: 22,
                    decoration: BoxDecoration(
                      color: task.isDone
                          ? _teal.withValues(alpha: 0.25)
                          : Colors.transparent,
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(
                        color: task.isDone
                            ? _teal
                            : task.priority.color.withValues(alpha: 0.7),
                        width: 1.8,
                      ),
                    ),
                    child: task.isDone
                        ? const Icon(Icons.check, size: 15, color: _teal)
                        : null,
                  ),
                ),
              ),
              // Content
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        // Priority Badge
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: task.priority.color.withValues(alpha: 0.16),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(
                            task.priority.tag,
                            style: TextStyle(
                              color: task.priority.color,
                              fontSize: 10,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                        const SizedBox(width: 6),
                        if (task.category.isNotEmpty && task.category != 'General') ...[
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.06),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              '#${task.category}',
                              style: const TextStyle(
                                color: Colors.white54,
                                fontSize: 10,
                              ),
                            ),
                          ),
                          const SizedBox(width: 6),
                        ],
                        if (task.dueDate != null) ...[
                          Icon(Icons.calendar_today,
                              size: 11, color: Colors.white.withValues(alpha: 0.4)),
                          const SizedBox(width: 4),
                          Text(
                            task.dueDate!,
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.45),
                              fontSize: 10.5,
                            ),
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 6),
                    Text(
                      task.title,
                      style: TextStyle(
                        color: task.isDone ? Colors.white38 : Colors.white,
                        fontSize: 14.5,
                        fontWeight: FontWeight.w600,
                        decoration: task.isDone
                            ? TextDecoration.lineThrough
                            : TextDecoration.none,
                      ),
                    ),
                    if (hasNotes) ...[
                      const SizedBox(height: 6),
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.03),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Icon(Icons.notes,
                                size: 13,
                                color: _teal.withValues(alpha: 0.8)),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                task.notes,
                                maxLines: 3,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  color: Colors.white.withValues(alpha: 0.65),
                                  fontSize: 12,
                                  height: 1.3,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.more_vert, size: 18, color: Colors.white38),
                onPressed: () => _openEditor(task),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _emptyView() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 64,
              height: 64,
              decoration: BoxDecoration(
                color: _red.withValues(alpha: 0.12),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.checklist_rtl_rounded, color: _red, size: 32),
            ),
            const SizedBox(height: 16),
            const Text(
              'No tasks found',
              style: TextStyle(
                  color: Colors.white, fontSize: 16, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 6),
            Text(
              _searchQuery.isNotEmpty
                  ? 'No task matches "$_searchQuery"'
                  : 'Capture tasks, set priorities, and write notes like Notion.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.white.withValues(alpha: 0.5), fontSize: 12.5),
            ),
          ],
        ),
      ),
    );
  }
}

class _TaskEditorSheet extends StatefulWidget {
  const _TaskEditorSheet({
    this.task,
    required this.categories,
    required this.onSave,
    this.onDelete,
  });

  final TodoTask? task;
  final List<String> categories;
  final ValueChanged<TodoTask> onSave;
  final VoidCallback? onDelete;

  @override
  State<_TaskEditorSheet> createState() => _TaskEditorSheetState();
}

class _TaskEditorSheetState extends State<_TaskEditorSheet> {
  static const _red = Color(0xFFE74848);
  static const _teal = Color(0xFF00E5C9);
  static const _surface = Color(0xFF18101A);

  late TextEditingController _titleCtrl;
  late TextEditingController _notesCtrl;
  late TextEditingController _catCtrl;
  late TaskPriority _priority;
  late TodoStatus _status;
  String? _dueDate;

  @override
  void initState() {
    super.initState();
    final t = widget.task;
    _titleCtrl = TextEditingController(text: t?.title ?? '');
    _notesCtrl = TextEditingController(text: t?.notes ?? '');
    _catCtrl = TextEditingController(text: t?.category ?? 'General');
    _priority = t?.priority ?? TaskPriority.medium;
    _status = t?.status ?? TodoStatus.todo;
    _dueDate = t?.dueDate;
  }

  @override
  void dispose() {
    _titleCtrl.dispose();
    _notesCtrl.dispose();
    _catCtrl.dispose();
    super.dispose();
  }

  void _save() {
    final title = _titleCtrl.text.trim();
    if (title.isEmpty) return;

    final cat = _catCtrl.text.trim().isEmpty ? 'General' : _catCtrl.text.trim();
    final saved = (widget.task ??
            TodoTask(
              id: DateTime.now().millisecondsSinceEpoch.toString(),
              title: title,
            ))
        .copyWith(
      title: title,
      notes: _notesCtrl.text.trim(),
      priority: _priority,
      status: _status,
      category: cat,
      dueDate: _dueDate,
    );

    widget.onSave(saved);
    Navigator.of(context).pop();
  }

  Future<void> _pickDate() async {
    final initial = _dueDate != null
        ? (DateTime.tryParse(_dueDate!) ?? DateTime.now())
        : DateTime.now();

    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime.now().subtract(const Duration(days: 365)),
      lastDate: DateTime.now().add(const Duration(days: 365 * 5)),
      builder: (ctx, child) => Theme(
        data: ThemeData.dark().copyWith(
          colorScheme: const ColorScheme.dark(
            primary: _red,
            surface: _surface,
          ),
        ),
        child: child!,
      ),
    );

    if (picked != null) {
      setState(() {
        _dueDate =
            '${picked.year}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final isNew = widget.task == null;

    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Container(
        decoration: const BoxDecoration(
          color: _surface,
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        ),
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Handle
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.white24,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Text(
                    isNew ? 'NEW TASK & NOTE' : 'EDIT TASK',
                    style: const TextStyle(
                      color: _red,
                      fontSize: 13,
                      letterSpacing: 2,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const Spacer(),
                  if (!isNew && widget.onDelete != null)
                    IconButton(
                      icon: const Icon(Icons.delete_outline,
                          color: Colors.redAccent, size: 20),
                      onPressed: () {
                        widget.onDelete!();
                        Navigator.of(context).pop();
                      },
                    ),
                  TextButton(
                    onPressed: _save,
                    child: const Text('Save',
                        style: TextStyle(color: _teal, fontWeight: FontWeight.w700)),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              // Title
              TextField(
                controller: _titleCtrl,
                style: const TextStyle(
                    color: Colors.white, fontSize: 17, fontWeight: FontWeight.w600),
                decoration: const InputDecoration(
                  hintText: 'Task Title...',
                  hintStyle: TextStyle(color: Colors.white38),
                  border: InputBorder.none,
                ),
                autofocus: isNew,
              ),
              const Divider(color: Colors.white12),
              const SizedBox(height: 8),

              // Priority Selector
              const Text('PRIORITY',
                  style: TextStyle(
                      color: Colors.white54,
                      fontSize: 10.5,
                      letterSpacing: 1.5,
                      fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                children: TaskPriority.values.map((p) {
                  final active = _priority == p;
                  return ChoiceChip(
                    label: Text('${p.tag} ${p.label}'),
                    selected: active,
                    selectedColor: p.color.withValues(alpha: 0.3),
                    backgroundColor: Colors.white.withValues(alpha: 0.04),
                    labelStyle: TextStyle(
                      color: active ? p.color : Colors.white60,
                      fontWeight: active ? FontWeight.w700 : FontWeight.w500,
                      fontSize: 12,
                    ),
                    side: BorderSide(
                      color: active ? p.color : Colors.white.withValues(alpha: 0.08),
                    ),
                    onSelected: (_) => setState(() => _priority = p),
                  );
                }).toList(),
              ),

              const SizedBox(height: 14),

              // Status Selector
              const Text('STATUS',
                  style: TextStyle(
                      color: Colors.white54,
                      fontSize: 10.5,
                      letterSpacing: 1.5,
                      fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                children: TodoStatus.values.map((s) {
                  final active = _status == s;
                  return ChoiceChip(
                    label: Text(s.label),
                    selected: active,
                    selectedColor: _teal.withValues(alpha: 0.25),
                    backgroundColor: Colors.white.withValues(alpha: 0.04),
                    labelStyle: TextStyle(
                      color: active ? _teal : Colors.white60,
                      fontWeight: active ? FontWeight.w700 : FontWeight.w500,
                      fontSize: 12,
                    ),
                    side: BorderSide(
                      color: active ? _teal : Colors.white.withValues(alpha: 0.08),
                    ),
                    onSelected: (_) => setState(() => _status = s),
                  );
                }).toList(),
              ),

              const SizedBox(height: 14),

              // Due Date & Category
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('DUE DATE',
                            style: TextStyle(
                                color: Colors.white54,
                                fontSize: 10.5,
                                letterSpacing: 1.5,
                                fontWeight: FontWeight.w700)),
                        const SizedBox(height: 6),
                        GestureDetector(
                          onTap: _pickDate,
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 10, vertical: 8),
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.04),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: Colors.white12),
                            ),
                            child: Row(
                              children: [
                                const Icon(Icons.calendar_today,
                                    size: 14, color: _teal),
                                const SizedBox(width: 8),
                                Text(
                                  _dueDate ?? 'Set Date',
                                  style: TextStyle(
                                    color: _dueDate != null
                                        ? Colors.white
                                        : Colors.white38,
                                    fontSize: 12,
                                  ),
                                ),
                                if (_dueDate != null) ...[
                                  const Spacer(),
                                  GestureDetector(
                                    onTap: () => setState(() => _dueDate = null),
                                    child: const Icon(Icons.close,
                                        size: 14, color: Colors.white38),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('CATEGORY',
                            style: TextStyle(
                                color: Colors.white54,
                                fontSize: 10.5,
                                letterSpacing: 1.5,
                                fontWeight: FontWeight.w700)),
                        const SizedBox(height: 6),
                        TextField(
                          controller: _catCtrl,
                          style: const TextStyle(color: Colors.white, fontSize: 12.5),
                          decoration: InputDecoration(
                            isDense: true,
                            contentPadding: const EdgeInsets.symmetric(
                                horizontal: 10, vertical: 8),
                            filled: true,
                            fillColor: Colors.white.withValues(alpha: 0.04),
                            hintText: 'e.g. Work, Ideas',
                            hintStyle: const TextStyle(color: Colors.white38),
                            enabledBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                              borderSide: const BorderSide(color: Colors.white12),
                            ),
                            focusedBorder: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                              borderSide: const BorderSide(color: _teal),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 16),

              // Notes
              const Text('NOTES (NOTION-STYLE)',
                  style: TextStyle(
                      color: Colors.white54,
                      fontSize: 10.5,
                      letterSpacing: 1.5,
                      fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              Container(
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.04),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.white12),
                ),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                child: TextField(
                  controller: _notesCtrl,
                  maxLines: 6,
                  style: const TextStyle(
                      color: Colors.white, fontSize: 13, height: 1.4),
                  decoration: const InputDecoration(
                    hintText:
                        'Write notes, detailed checklists, links or thoughts here...',
                    hintStyle: TextStyle(color: Colors.white30, fontSize: 13),
                    border: InputBorder.none,
                  ),
                ),
              ),
              const SizedBox(height: 18),
              SizedBox(
                width: double.infinity,
                height: 44,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: _teal,
                    foregroundColor: Colors.black,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12)),
                  ),
                  onPressed: _save,
                  child: const Text('Save Task & Notes',
                      style: TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
