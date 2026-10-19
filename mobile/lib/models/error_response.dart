class FieldError {
  final String field;
  final String type;
  final String message;

  FieldError({required this.field, required this.type, required this.message});

  factory FieldError.fromJson(Map<String, dynamic> json) {
    return FieldError(
      field: json['field'] as String? ?? '',
      type: json['type'] as String? ?? '',
      message: json['message'] as String? ?? '',
    );
  }
}

class ErrorBody {
  final String code;
  final String message;
  final List<FieldError>? details;

  ErrorBody({required this.code, required this.message, this.details});

  factory ErrorBody.fromJson(Map<String, dynamic> json) {
    final rawDetails = json['details'];
    return ErrorBody(
      code: json['code'] as String,
      message: json['message'] as String,
      details: rawDetails is List
          ? rawDetails.whereType<Map<String, dynamic>>().map(FieldError.fromJson).toList()
          : null,
    );
  }
}
