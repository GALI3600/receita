import 'package:flutter/material.dart';

/// Campo de senha com botão de olho para mostrar/ocultar o texto digitado.
class PasswordField extends StatefulWidget {
  final TextEditingController controller;
  final String label;
  final List<String>? autofillHints;
  final ValueChanged<String>? onFieldSubmitted;
  final String? Function(String?)? validator;

  const PasswordField({
    super.key,
    required this.controller,
    required this.label,
    this.autofillHints,
    this.onFieldSubmitted,
    this.validator,
  });

  @override
  State<PasswordField> createState() => _PasswordFieldState();
}

class _PasswordFieldState extends State<PasswordField> {
  bool _obscure = true;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: widget.controller,
      obscureText: _obscure,
      autofillHints: widget.autofillHints,
      validator: widget.validator,
      onFieldSubmitted: widget.onFieldSubmitted,
      decoration: InputDecoration(
        labelText: widget.label,
        suffixIcon: IconButton(
          icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
          tooltip: _obscure ? 'Mostrar senha' : 'Ocultar senha',
          onPressed: () => setState(() => _obscure = !_obscure),
        ),
      ),
    );
  }
}
