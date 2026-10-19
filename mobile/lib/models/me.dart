/// Espelha `QuotaOut` em `backend/app/schemas/auth.py`.
class Quota {
  final int used;
  final int limit;
  final int remaining;
  final DateTime resetsAt;

  Quota({
    required this.used,
    required this.limit,
    required this.remaining,
    required this.resetsAt,
  });

  factory Quota.fromJson(Map<String, dynamic> json) {
    return Quota(
      used: json['used'] as int,
      limit: json['limit'] as int,
      remaining: json['remaining'] as int,
      resetsAt: DateTime.parse(json['resets_at'] as String),
    );
  }
}

/// Espelha `MeOut` em `backend/app/schemas/auth.py`.
class Me {
  final String id;
  final String name;
  final String email;
  final bool emailVerified;
  final String plan;
  final DateTime createdAt;
  final Quota quota;

  Me({
    required this.id,
    required this.name,
    required this.email,
    required this.emailVerified,
    required this.plan,
    required this.createdAt,
    required this.quota,
  });

  factory Me.fromJson(Map<String, dynamic> json) {
    return Me(
      id: json['id'] as String,
      name: json['name'] as String,
      email: json['email'] as String,
      emailVerified: json['email_verified'] as bool,
      plan: json['plan'] as String,
      createdAt: DateTime.parse(json['created_at'] as String),
      quota: Quota.fromJson((json['quota'] as Map).cast<String, dynamic>()),
    );
  }
}
