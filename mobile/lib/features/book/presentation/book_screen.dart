import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../widgets/error_banner.dart';
import '../application/recipe_list_providers.dart';
import 'widgets/recipe_card.dart';

class BookScreen extends ConsumerStatefulWidget {
  const BookScreen({super.key});

  @override
  ConsumerState<BookScreen> createState() => _BookScreenState();
}

class _BookScreenState extends ConsumerState<BookScreen> {
  final _searchController = TextEditingController();
  final _scrollController = ScrollController();
  Timer? _debounce;
  RecipeListFilters _filters = const RecipeListFilters();

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchController.dispose();
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >
        _scrollController.position.maxScrollExtent - 300) {
      ref.read(recipeListProvider(_filters).notifier).loadMore();
    }
  }

  void _onSearchChanged(String value) {
    // Reconstrói na hora para o botão de limpar (×) aparecer/desaparecer junto da digitação,
    // sem esperar o debounce do filtro em si.
    setState(() {});
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 400), () {
      final trimmed = value.trim();
      setState(() => _filters = _filters.copyWith(q: trimmed, clearQuery: trimmed.isEmpty));
    });
  }

  void _clearSearch() {
    _debounce?.cancel();
    _searchController.clear();
    setState(() => _filters = _filters.copyWith(clearQuery: true));
  }

  void _toggleFavoriteFilter() {
    setState(() {
      _filters = _filters.favorite == true
          ? _filters.copyWith(clearFavorite: true)
          : _filters.copyWith(favorite: true);
    });
  }

  @override
  Widget build(BuildContext context) {
    final listState = ref.watch(recipeListProvider(_filters));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Meu livro de receitas'),
        actions: [
          IconButton(
            icon: const Icon(Icons.person_outline),
            tooltip: 'Conta',
            onPressed: () => context.push('/conta'),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/nova'),
        icon: const Icon(Icons.add),
        label: const Text('Importar vídeo'),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: TextField(
              controller: _searchController,
              onChanged: _onSearchChanged,
              decoration: InputDecoration(
                hintText: 'Buscar receitas…',
                prefixIcon: const Icon(Icons.search),
                border: const OutlineInputBorder(),
                isDense: true,
                suffixIcon: _searchController.text.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.clear),
                        tooltip: 'Limpar busca',
                        onPressed: _clearSearch,
                      ),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Align(
              alignment: Alignment.centerLeft,
              child: FilterChip(
                label: const Text('Favoritas'),
                avatar: const Icon(Icons.favorite, size: 16),
                selected: _filters.favorite == true,
                onSelected: (_) => _toggleFavoriteFilter(),
              ),
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: listState.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: ErrorBanner(error: error),
                ),
              ),
              data: (state) {
                if (state.items.isEmpty) {
                  return const Center(child: Text('Nenhuma receita encontrada.'));
                }
                return RefreshIndicator(
                  onRefresh: () => ref.read(recipeListProvider(_filters).notifier).refresh(),
                  child: ListView.builder(
                    controller: _scrollController,
                    padding: const EdgeInsets.only(bottom: 96),
                    itemCount: state.items.length + (state.isLoadingMore ? 1 : 0),
                    itemBuilder: (context, index) {
                      if (index >= state.items.length) {
                        return const Padding(
                          padding: EdgeInsets.all(16),
                          child: Center(child: CircularProgressIndicator()),
                        );
                      }
                      return RecipeCard(recipe: state.items[index]);
                    },
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
