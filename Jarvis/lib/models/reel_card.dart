import 'dart:convert';

/// What a saved reel became: either something to do, or something to know.
enum CardKind { task, fact }

/// How long a task takes, which is what decides the bucket it lands in.
enum Horizon { today, shortTerm, longTerm }

/// Where a task currently sits. `active` only applies to long-term work that
/// has been started but can't be finished in a sitting.
enum TaskStatus { backlog, active, done, snoozed }

Horizon horizonFrom(String? s) => switch (s) {
      'today' => Horizon.today,
      'long_term' => Horizon.longTerm,
      _ => Horizon.shortTerm,
    };

String horizonKey(Horizon h) => switch (h) {
      Horizon.today => 'today',
      Horizon.shortTerm => 'short_term',
      Horizon.longTerm => 'long_term',
    };

String horizonLabel(Horizon h) => switch (h) {
      Horizon.today => 'Today',
      Horizon.shortTerm => 'Short term',
      Horizon.longTerm => 'Long term',
    };

TaskStatus statusFrom(String? s) => switch (s) {
      'active' => TaskStatus.active,
      'done' => TaskStatus.done,
      'snoozed' => TaskStatus.snoozed,
      _ => TaskStatus.backlog,
    };

String statusKey(TaskStatus s) => s.name;

class ReelCard {
  final String id;
  final CardKind kind;
  final String title;
  final String summary;
  final String domain;
  final List<String> tags;
  final String url;
  final String owner;
  final String collection;
  final String evidence;
  final String confidence;

  /// Asset path for the reel's cover image, or empty when we couldn't fetch one.
  final String thumb;

  // task-only
  final List<String> steps;
  final String effort;
  final Horizon horizon;
  final String recurrence;

  // fact-only
  final String claim;
  final String why;
  final String applicability;

  // mutable state, joined in from task_state
  final TaskStatus status;
  final int progress;

  const ReelCard({
    required this.id,
    required this.kind,
    required this.title,
    required this.summary,
    required this.domain,
    required this.tags,
    required this.url,
    required this.owner,
    required this.collection,
    required this.evidence,
    required this.confidence,
    this.thumb = '',
    this.steps = const [],
    this.effort = '',
    this.horizon = Horizon.shortTerm,
    this.recurrence = 'once',
    this.claim = '',
    this.why = '',
    this.applicability = '',
    this.status = TaskStatus.backlog,
    this.progress = 0,
  });

  bool get isTask => kind == CardKind.task;
  bool get isDone => status == TaskStatus.done;

  /// Long-term work is never "finished today" -- it gets nudged along instead,
  /// so the UI offers progress rather than a tick.
  bool get tracksProgress => isTask && horizon == Horizon.longTerm;

  /// Built by `reelflow/pack.py`; keys match the KEEP list there.
  factory ReelCard.fromPack(Map<String, dynamic> j) => ReelCard(
        id: j['id'] as String,
        kind: j['kind'] == 'fact' ? CardKind.fact : CardKind.task,
        title: (j['title'] ?? '') as String,
        summary: (j['summary'] ?? '') as String,
        domain: (j['domain'] ?? 'other') as String,
        tags: ((j['tags'] ?? const []) as List).cast<String>(),
        url: (j['url'] ?? '') as String,
        owner: (j['owner_user'] ?? '') as String,
        collection: (j['collection'] ?? '') as String,
        evidence: (j['evidence'] ?? '') as String,
        confidence: (j['confidence'] ?? '') as String,
        thumb: (j['thumb'] ?? '') as String,
        steps: ((j['steps'] ?? const []) as List).cast<String>(),
        effort: (j['effort'] ?? '') as String,
        horizon: horizonFrom(j['horizon'] as String?),
        recurrence: (j['recurrence'] ?? 'once') as String,
        claim: (j['claim'] ?? '') as String,
        why: (j['why'] ?? '') as String,
        applicability: (j['applicability'] ?? '') as String,
      );

  Map<String, Object?> toRow() => {
        'id': id,
        'kind': kind.name,
        'title': title,
        'summary': summary,
        'domain': domain,
        'tags': jsonEncode(tags),
        'url': url,
        'owner': owner,
        'collection': collection,
        'evidence': evidence,
        'confidence': confidence,
        'thumb': thumb,
        'steps': jsonEncode(steps),
        'effort': effort,
        'horizon': horizonKey(horizon),
        'recurrence': recurrence,
        'claim': claim,
        'why': why,
        'applicability': applicability,
      };

  factory ReelCard.fromRow(Map<String, Object?> r) => ReelCard(
        id: r['id'] as String,
        kind: r['kind'] == 'fact' ? CardKind.fact : CardKind.task,
        title: (r['title'] ?? '') as String,
        summary: (r['summary'] ?? '') as String,
        domain: (r['domain'] ?? 'other') as String,
        tags: (jsonDecode((r['tags'] ?? '[]') as String) as List).cast<String>(),
        url: (r['url'] ?? '') as String,
        owner: (r['owner'] ?? '') as String,
        collection: (r['collection'] ?? '') as String,
        evidence: (r['evidence'] ?? '') as String,
        confidence: (r['confidence'] ?? '') as String,
        thumb: (r['thumb'] ?? '') as String,
        steps: (jsonDecode((r['steps'] ?? '[]') as String) as List).cast<String>(),
        effort: (r['effort'] ?? '') as String,
        horizon: horizonFrom(r['horizon'] as String?),
        recurrence: (r['recurrence'] ?? 'once') as String,
        claim: (r['claim'] ?? '') as String,
        why: (r['why'] ?? '') as String,
        applicability: (r['applicability'] ?? '') as String,
        status: statusFrom(r['status'] as String?),
        progress: (r['progress'] as int?) ?? 0,
      );

  ReelCard copyWith({TaskStatus? status, int? progress}) => ReelCard(
        id: id,
        kind: kind,
        title: title,
        summary: summary,
        domain: domain,
        tags: tags,
        url: url,
        owner: owner,
        collection: collection,
        evidence: evidence,
        confidence: confidence,
        thumb: thumb,
        steps: steps,
        effort: effort,
        horizon: horizon,
        recurrence: recurrence,
        claim: claim,
        why: why,
        applicability: applicability,
        status: status ?? this.status,
        progress: progress ?? this.progress,
      );
}
