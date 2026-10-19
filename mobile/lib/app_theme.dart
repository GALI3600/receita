import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Paleta espelhando a web: fundo creme, texto marrom escuro, destaque terracota
/// (`#faf6ee`/`#3b2a20`/`#a8472a` em `frontend/src/index.css`), títulos serifados
/// (Fraunces) e corpo em sans (Source Sans 3) — as mesmas famílias usadas na web
/// (`@fontsource-variable/fraunces`, `@fontsource-variable/source-sans-3`), buscadas via
/// `google_fonts` em vez de vendorizar os arquivos de fonte.
const Color _cream = Color(0xFFFAF6EE);
const Color _ink = Color(0xFF3B2A20);
const Color _terracotta = Color(0xFFA8472A);

ThemeData buildAppTheme() {
  final colorScheme = ColorScheme.fromSeed(
    seedColor: _terracotta,
    brightness: Brightness.light,
    surface: _cream,
    onSurface: _ink,
  );

  final baseTextTheme = GoogleFonts.sourceSans3TextTheme().apply(
    bodyColor: _ink,
    displayColor: _ink,
  );
  final headingStyle = GoogleFonts.fraunces(color: _ink, fontWeight: FontWeight.w600);

  return ThemeData(
    useMaterial3: true,
    colorScheme: colorScheme,
    scaffoldBackgroundColor: _cream,
    textTheme: baseTextTheme.copyWith(
      headlineLarge: headingStyle.copyWith(fontSize: baseTextTheme.headlineLarge?.fontSize),
      headlineMedium: headingStyle.copyWith(fontSize: baseTextTheme.headlineMedium?.fontSize),
      titleLarge: headingStyle.copyWith(fontSize: baseTextTheme.titleLarge?.fontSize),
      titleMedium: headingStyle.copyWith(fontSize: baseTextTheme.titleMedium?.fontSize),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: _cream,
      foregroundColor: _ink,
      elevation: 0,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(backgroundColor: _terracotta, foregroundColor: Colors.white),
    ),
    inputDecorationTheme: const InputDecorationTheme(border: OutlineInputBorder()),
  );
}
