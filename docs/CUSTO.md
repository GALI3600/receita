# Receita: plano de custo do Claude

Este plano mostra como reduzir o custo de cada receita gerada sem perder qualidade. Hoje, cada vídeo novo faz **uma chamada** ao `claude-opus-5-5` (`recipe_llm.generate_recipe`). A receita fica guardada por vídeo e é copiada para os outros usuários sem chamada nova. A ordem segue o guia de otimização de custo da Anthropic ([CO]): primeiro vêm os ganhos grátis, depois as trocas de qualidade por custo, e estas só depois de passar no eval. Os preços vêm das páginas oficiais consultadas em 2026-10-14 (lista em **Fontes**, no fim).

**Resumo**
- **Custo medido:** cerca de US$ 0,086 por receita no prompt `2026-10-14.2`. A saída é **70%** da conta, e o thinking sozinho é 23%.
- **Corrigir a contabilidade antes de tudo** (§ 3; feito na fase 0). O `quotas.py` não aplica o desconto de batch, não tem preço para Sonnet nem para Haiku e cobra pouco por modelos fora da tabela. Sem essa correção, nenhuma das mudanças abaixo pode ser medida.
- **Maiores tetos de economia:**
  - **Modelo:** o Haiku 5.5 sai ~97% mais barato e o Sonnet 5.5, ~50%. As duas trocas precisam de eval. O Haiku 5.5 não tem fallback no servidor (§ 5.6).
  - **Batch:** 50% de desconto em evals, imports adiados e backfill depois de um bump de prompt. É grátis.
  - **Effort:** passar para `low` economiza até ~23%. Precisa de eval.
- **Cache:** no eval, o teto é −7,7% sobre os US$ 0,086 medidos. Em produção, com chamadas espalhadas, a base é outra: o custo modelado de "5 min sempre", de US$ 0,10 a 0,108. Contra essa base, a política certa economiza de −5,5% (pouco volume, sem marcador) a −19% (50 imports/dia, TTL de 1 h). Como o volume real é desconhecido, nada muda antes de medir (§ 5.1).
- **Os ganhos de entrada e saída** ficam entre 1% e 8% cada. Só valem um ciclo de eval se o modelo continuar sendo o Opus.
- **Orçamento de medição:** ≈ US$ 6 na fase 2. O total vai de ≈ US$ 17 a ≈ US$ 32 via batch, conforme o modelo vencedor (§ 9). A nota da rubrica é dada por agentes do Claude Code, fora da API.

---

## 1. Escopo, barra de qualidade e linha de base

| Item | Valor |
|---|---|
| Escopo | Uma única chamada: `pipeline.generate` → `recipe_llm.generate_recipe`. Classes de tráfego: **import interativo** (o usuário espera de 20 a 80 s), **import adiado** (cron das 00:05 UTC), **regeneração depois de um bump de `PROMPT_VERSION`** (hoje é preguiçosa e só acontece no próximo import) e **eval/CLI**. |
| Plataforma | API da Anthropic (first-party). Todas as alavancas abaixo estão disponíveis nela. |
| Requisição | `claude-opus-5-5`, `messages.parse` com `output_format=RecipeLLM`, effort `medium` (o padrão), thinking adaptativo sempre ligado, `system` com `cache_control` de 5 min, `fallbacks="default"` e `max_tokens=16000`. |
| Barra de qualidade | Rubrica de 7 critérios, de 1 a 5, mais uma nota geral. Só a v1 e a v2 têm nota (`results.json`): a média geral subiu de 4,10 para 4,60. Na v2, 3 avaliadores usaram escala /10. **A 14.2 (v3) não tem nota de rubrica**, apenas a checagem dirigida de timestamps. O ruído do juiz não foi medido. Também **não existe runner automatizado** (§ 7). |
| Linha de base | **US$ 0,086/receita** (17 chamadas, US$ 1,464; `llm_calls` = `llm_usage` dos JSONs). Na v1 era US$ 0,071 e na v2, US$ 0,080. |
| Unidade dos tetos | % da conta, calculado a partir dos logs de uso do próprio app. Os valores em US$ aparecem só como apoio, entre parênteses. |
| Páginas consultadas (2026-10-14) | [P] Pricing, [CO] Cost optimization, [PC] Prompt caching, [B] Batch e [E] Effort, além de [SO] Structured outputs, [RF] Refusals and fallback, [FC] Fallback credit, [T] Thinking e [MO] Models overview. A página Preserved thinking **não se aplica**: é uma chamada de turno único, sem histórico de thinking, mesmo quando o 2c edita o `system` ou o modelo muda. Nenhuma chamada paga foi feita; as contagens vêm do `count_tokens`. |

---

## 2. Perfil atual (medido)

### 2.1 Para onde vai o dinheiro (`2026-10-14.2`, 17 chamadas)

| Componente | Tokens | % da conta |
|---|---|---|
| Saída visível (JSON compacto) | 34.968 | 47,8% |
| Thinking (`output_tokens_details.thinking_tokens`) | 16.547 | 22,6% |
| Entrada sem cache (transcrição, descrição e metadados) | 75.381 | 20,6% |
| Escrita no cache de 5 min (4 escritas em 17 chamadas) | 23.396 | 8,0% |
| Leitura do cache | 76.037 | 1,0% |

Preços [P]: o Opus 5.5 custa US$ 4 por MTok de entrada e US$ 20 de saída. A escrita no cache custa 1,25× a entrada (5 min) ou 2× (1 h). A leitura custa 0,05× (US$ 0,20).

- **O custo acompanha o tamanho da receita, não a duração do vídeo.** A correlação entre custo e saída é r = 0,95; entre custo e entrada, 0,69. A saída visível segue ≈ 21 + 52·ingredientes + 74·passos + 43·dicas (R² 0,98), e o thinking fica em ≈ 0,46 × a saída visível.
- **A cauda pesa.** Os 10% mais caros são 24,9% do gasto. Só o OWLnnv4tsFQ (3 marmitas, 72 ingredientes, 10.138 tokens de saída) é 16,3% da rodada, cerca de 3× a mediana. A maior saída observada usa 63% do `max_tokens`.
- **Por que o custo subiu de v1 para v3** (US$ 0,071 → 0,086):
  - o thinking médio passou de 531 para 973 tokens (+US$ 0,009);
  - a saída visível cresceu (+US$ 0,004);
  - houve escritas concorrentes no cache por causa da rajada do eval (+US$ 0,0035).

### 2.2 Prefixo cacheado (5.849 tokens, igual ao `cache_creation_input_tokens`)

| Parte | Tokens |
|---|---|
| `SYSTEM_PROMPT` | ~3.638 |
| Schema `RecipeLLM` renderizado pela saída estruturada | ~2.209 (38% do prefixo) |
| — dos quais, `description` dos campos (repetem em boa parte as regras 3–10) | ~765 |

Nada dinâmico fica acima do breakpoint. Estes eventos **quebram o cache**:
- trocar de modelo ou de effort;
- editar o `SYSTEM_PROMPT`;
- editar a `description` ou o tipo de um campo Pydantic, o que muda o prefixo mesmo sem bump;
- mudar `fallbacks` ou `betas`;
- atualizar o SDK, se a atualização mudar o `transform_schema`.

O prefixo mínimo cacheável é de 512 tokens no Opus, no Sonnet e no Haiku 5.5, e de 4.096 tokens no Haiku 4.5 [PC].

### 2.3 Taxa de acerto do cache em produção (modelo)

O eval roda em rajada, com 76–94% de acerto, então não representa produção. Se toda chamada for fria, o custo sobe para **~US$ 0,108/receita (+25%)**. O modelo abaixo usa chegadas Poisson ao longo de 14 h ativas por dia e conta como fria a primeira chamada de cada dia. O volume de produção é desconhecido, porque os dados são de dev.

Custo do prefixo por chamada [P], conforme o tipo de cobrança: sem cache, US$ 0,0234; escrita de 5 min, US$ 0,0292; escrita de 1 h, US$ 0,0468; leitura, US$ 0,0012. O cache só compensa acima de **20,8% de acerto (5 min) e 51,3% (1 h)**.

| imports/dia | acerto 5 min | acerto 1 h | mais barato | vs "5 min sempre" no mesmo volume (modelado) |
|---|---|---|---|---|
| 1 | 0% | 0% | sem marcador | −5,5% (0,1017 vs 0,1076) |
| 3 | 1% | 13% | sem marcador | −5,1% |
| 10 | 5% | 46% | sem marcador | −4,1% |
| 20 | 11% | 72% | 1 h | −11,9% (0,0922 vs 0,1046) |
| 50 | 25% | 95% | 1 h | −18,7% (0,0817 vs 0,1005) |
| 200 | 69% | 99,5% | 1 h | −9,5% |
| 1000 | 99,6% | 99,9% | 1 h ≈ 5 min | 0% |

Com 100% de acerto, o teto do cache é −21,8% contra não cachear e −7,7% contra os US$ 0,086 medidos.

### 2.4 Reuso entre usuários (já existe e é a maior economia estrutural)

A receita canônica é copiada sem chamada nova (`find_ready_video`, `complete_from_existing`). O veredito "não é receita" também é reaproveitado, e uma trava por vídeo garante uma única chamada mesmo quando vários imports chegam juntos. Se *r* é a fração de imports servidos por cópia, o custo por import é (1 − *r*) × o custo de uma receita nova:

| *r* | 0 | 0,3 | 0,5 | 0,8 |
|---|---|---|---|---|
| custo por import | US$ 0,086 | US$ 0,060 | US$ 0,043 | US$ 0,017 |

**O ponto fraco é o bump de `PROMPT_VERSION`.** Depois dele, `is_ready` volta a falso em todo o catálogo. Cada re-import de um vídeo popular paga então uma chamada síncrona fria, de ~US$ 0,10 a 0,108, com o usuário esperando. Esse re-import ainda gasta 1 das 10 receitas diárias do usuário (`charged=generated`, `worker.py:149`). O valor de *r* ainda não é medido (§ 8).

---

## 3. Corrigir a contabilidade primeiro (`backend/app/services/quotas.py` e afins)

| # | Problema | Efeito | Correção |
|---|---|---|---|
| 1 | `MODEL_PRICES` só tem Opus 5.5, Opus 5 e Opus 4.8. Para modelos fora da tabela, `_FALLBACK_PRICE` usa o mais caro **da tabela** (US$ 25 de saída). | O roteamento de fallback não é publicado [RF]. Um Fable 5.1 (US$ 10 / US$ 50 [P]) seria cobrado pela metade. Sonnet e Haiku saem caros demais, o que impede medir uma troca de modelo. | Cadastrar `claude-sonnet-5-5` (2 / 10 / leitura 0,10), `claude-haiku-5-5` (0,10 / 0,50 / 0,01, mais a faixa >100k), `claude-haiku-4-5` (1 / 5 / 0,10) e os Fable [P]. Para modelos fora da tabela, usar o maior preço publicado. |
| 2 | Não aplica o desconto de batch. | Adiados, backfill e evals em batch seriam contados em dobro. | Multiplicar por 0,5 quando `usage.service_tier == "batch"`. O SDK já tipa o campo como `Literal["standard","priority","batch"]`. |
| 3 | Chamada cobrada mas não registrada quando o timeout dispara depois da geração (`asyncio.timeout` de 900 s ou timeout de leitura do cliente). | `llm_usage` fica `None` e nada entra em `llm_calls` (`pipeline.py:158-164`). O retry transitório paga de novo, e o orçamento fica abaixo do real. | Gravar a chamada com `request_id` e o erro. Avaliar streaming para não perder o `usage`. |
| 4 | O orçamento não reserva o custo das chamadas em andamento. | Com `max_jobs=10` e até ~US$ 0,24 por chamada, o gasto pode passar ~24% do teto padrão de US$ 10. | Reservar uma estimativa antes de chamar (`count_tokens`, que é grátis, mais a saída média). Acertar o valor quando a chamada termina. |
| 5 | Eval e produção dividem o mesmo orçamento e a mesma tabela. | As 3 rodadas de hoje gastaram ~US$ 3,9 dos US$ 10 do dia. | Criar a coluna `purpose`, com orçamento separado para eval, e usar chave ou workspace separado. |
| 6 | Falta o multiplicador de 1,1× para `inference_geo == "us"` [P]. | Sem efeito hoje, porque o valor é `global`. | Aplicar o multiplicador por precaução. |
| 7 | Toda tentativa recusada é cobrada, mas só as categorias `bio`, `frontier_llm` e `reasoning_extraction` são faturadas [RF]. | Cobra a mais, do lado seguro. As `iterations` não trazem a categoria. | Documentar. Não há como corrigir. |

**Fase 0 (feito):** itens 1 a 6 corrigidos (preços por modelo com a faixa >100k do Haiku 5.5, batch e geo "us", reserva com `llm_in_progress`/`llm_timeout`, `purpose` com `EVAL_DAILY_LLM_BUDGET_USD`); item 7 documentado no `quotas.llm_cost_usd`. Desvios do que a tabela propõe:
- item 3: sem `request_id` (um timeout não traz resposta) e sem streaming; a chamada interrompida fica com o custo estimado;
- item 4: estimativa local (caracteres ÷ 1,4) e saída reservada de 12k (`LLM_RESERVED_OUTPUT_TOKENS`), não `count_tokens` + saída média: sem chamada de rede antes do import, determinística, e a cauda da saída (10.138 tokens no OWLnnv4tsFQ) passaria da média;
- item 5: orçamento separado, mas sem chave ou workspace separado. Isso continua pendente, junto com o limite de gasto no Console (aprovação 2 do § 9, passo manual).

**Barreiras de custo que já existem** (`config.py:71–87`): `daily_import_limit` = 10 receitas novas por usuário por dia; `daily_failed_import_limit` = 20; `rate_limit_imports` = 30/h; `DAILY_LLM_BUDGET_USD` = 10; vídeo de no máximo 60 min. Duas lacunas:
- falta um **limite de gasto do workspace no Console**, como última barreira;
- o eval pela CLI passa por fora dos limites por usuário. Por isso ele precisa de orçamento próprio e da confirmação `--yes` (§ 7).

---

## 4. Lista curta

*Ordenada pelo teto de economia, não pela ordem de aplicação.*

| Alavanca | Tipo | Teto (% da conta) | Fonte |
|---|---|---|---|
| Modelo: Haiku 5.5 | troca | ~97% (US$ 0,0022/receita) | logs de uso × [P] |
| Batch para evals, adiados e backfill | grátis | 50% do tráfego elegível (hoje, 100% do gasto de dev é eval) | logs de uso + [B]/[P] |
| Modelo: Sonnet 5.5 | troca | ~50% (US$ 0,043), antes do efeito do effort `high`, que é o padrão | logs de uso × [P] |
| Bump compatível + backfill (§ 5.4, 4c) | (i) decisão de produto ou troca; (ii) e (iii) grátis | até 100% da regeneração síncrona pós-bump | código |
| Effort `low` | troca | ≤ 22,6% (todo o thinking) | logs de uso |
| Política de cache | grátis | pendente de medição: de −5,5% (pouco volume) a −19% (50/dia), contra o modelo de "5 min sempre" (§ 2.3), não contra os US$ 0,086 | modelo Poisson |
| Schema de saída enxuto | grátis com risco | ~5–8%, a confirmar (§ 5.3) | `count_tokens` |
| Escritas redundantes na rajada do cron | grátis | −23% nas chamadas da rajada (~6% de uma rodada); some com o batch | logs de uso |
| Agrupar a transcrição em trechos de 15 s | grátis com risco | 3,4% | `count_tokens` |
| Auditoria das descrições do schema | grátis com risco | ~3% em chamada fria; ≈ 0,2% com cache quente | `count_tokens` (765 tokens) |

- **Os tetos não se somam.**
  - As opções de modelo excluem umas às outras.
  - Batch, effort e modelo se multiplicam. Exemplos: Opus via batch sai a US$ 0,043; Haiku 5.5 via batch, a ≈ US$ 0,0011.
  - A política de cache e a auditoria disputam os mesmos tokens do prefixo.
- **Se o eval aprovar o Haiku 5.5 ou o Sonnet 5.5**, as linhas de 3% a 8% passam a valer frações de centavo. Elas são reavaliadas depois da fase 2 (§ 9).

---

## 5. Mudanças, na ordem de aplicação

Cada mudança vira **um diff próprio** e é medida contra a última configuração mantida. Há uma exceção na medição: a matriz modelo × effort roda **cedo**. O resultado dela decide se as alavancas de entrada e de saída ainda pagam o próprio ciclo de eval.

### 5.1 Prompt caching (*medir antes de mudar*; validado só por custo, porque não muda a saída)

A recomendação padrão é deixar o cache sempre ligado. Este plano só se afasta disso se o § 2.3 se confirmar em produção. Como a saída não muda, o risco é só de custo.

- **Fase 0:** gravar `started_at` em `llm_calls` e simular o TTL (5 min e 1 h) sobre o tráfego real. Manter o "5 min sempre" e trocar a constante por um config `LLM_CACHE_TTL = "5m" | "1h"`. Feito: `started_at`, `LLM_CACHE_TTL` e `python -m app.cli llm-cache-sim` existem.
- **Decidir com os dados do TTL walk:**
  - acerto de 1 h ≥ ~51% (≈ 11–12 ou mais imports/dia espalhados) → **1 h sempre** (de −12% a −19% contra hoje, com 20 a 50 por dia);
  - volume baixo → desligar o marcador ou passar a marcar por demanda. O ganho absoluto é pequeno: ≤ US$ 0,006 por chamada fria, menos de US$ 2/mês com 1 a 10 imports/dia. Só vale se o desenho abaixo for barato de manter.
- **Desenho opcional da marcação por demanda:**
  - `use_cache = receita:llm:cache_warm_until existe OR demanda ≥ 1`;
  - a chave recebe `SET … PX=TTL−30s` no início de cada requisição com marcador, porque o TTL conta desde o início da requisição [PC];
  - "demanda" são outros imports em `pending`, `fetching` ou `generating`, sem contar os que esperam o whisper;
  - registrar `cache_marker` em `llm_calls`.
  
  Isso **não** é a regra "olhar para trás" descartada no § 6: a chave só é gravada por chamadas com marcador, então ela indica cache realmente quente. Enquanto a chave existir, o marcador é obrigatório.
- **Keep-alive: descartado.** O `max_tokens: 0` é rejeitado junto com `output_config.format` e também dentro de Batches [CO], [PC].

**1b. Rajada do cron das 00:05** (paliativo até o 4b)
- Hoje, até 10 chamadas frias escrevem o mesmo prefixo ao mesmo tempo.
- Correção: o cron enfileira o primeiro import, espera ele terminar e só então solta o resto. Com isso, o prefixo de cada chamada cai de 1,25× para ~0,17× (K = 10), −23% por chamada (0,1075 → 0,0823).
- A entrada do cache já fica legível quando a primeira resposta *começa* [PC]. Mas, sem streaming, esperar o fim é o caminho mais simples.

### 5.2 Higiene de entrada

| | Mudança | Teto | Tag | Risco e checagem |
|---|---|---|---|---|
| 2a | Juntar segmentos consecutivos da transcrição em trechos de **15 s**, com um marcador `[Ns]` por trecho | 3,4% (16% da mensagem do usuário; de −2% a −26% conforme o vídeo) | *precisa de eval* | `video_timestamp_s` passa a ser o início do trecho, e o salto pode cair até 15 s antes da ação. A variação natural entre rodadas já chega a 9 s (ZU_wbPigVRI: 508 → 517). Por isso, um limite fixo de Δ ≤ 15 s daria falso alarme e não pegaria viés. **Checagem:** o novo timestamp tem de ser o início do trecho que contém o timestamp da 14.2 (± 1 trecho), com o Δ médio reportado com sinal. O ZU_wbPigVRI entra em todo trial. Se "até 15 s antes" é aceitável, quem decide é o produto. Um marcador mais curto (`[398]`) pode ser medido no `count_tokens`, mas o `s` faz parte da correção da 14.2, então mudar o marcador também exige eval. Trechos de 30 s foram descartados (§ 6). |
| 2c | Auditoria do prompt: tirar das `description` do schema as regras que já estão no `SYSTEM_PROMPT` | ~3% em chamada fria, ≈ 0,2% com cache quente (765 tokens; cortes no prompt só depois de medir com `count_tokens`) | *precisa de eval* | Só compensa se a política de cache deixar muitas chamadas frias. Exige bump de `PROMPT_VERSION`. **Descrições protegidas** (correções da v2): `tips` "não fala das fontes" (32 → 0 na regex), `note` "sem parênteses" e `video_timestamp_s`. Cortar só duplicatas de formato. **Checagens:** regex das fontes = 0, os 6 detalhes recuperados na v2 (ex.: pré-aquecimento no nAWH) e o teste de timestamp do 2a. |

A duplicação na transcrição foi descartada: são 22 palavras sobrepostas em 21.904.

### 5.3 Saída

| | Mudança | Teto | Tag | Observações |
|---|---|---|---|---|
| 3a | Schema enxuto: (1) remover `Step.order`, que o `normalize_recipe` já renumera (≈ 66 tokens por receita, 1,5%); (2) içar `group` (ingredientes como `[{group, items}]`); (3) parar de emitir campos nulos e vazios | ~5–8% juntos, a confirmar | *precisa de eval* | Os ~4,7% do (2) podem já incluir o `order`. Medir (2) sozinho com `count_tokens`, sobre as 17 saídas reserializadas, antes de somar. As chaves e a estrutura são 32% da saída visível. **Riscos do (3):** cada campo opcional dobra parte da gramática; o limite é de 24 opcionais e de 16 tipos união (`X \| None`) por requisição [SO]; e propriedades obrigatórias saem antes das opcionais [SO], então tornar `quantity`, `unit`, `group` ou `video_timestamp_s` opcionais muda a ordem em que o modelo escreve. Aplicar (1) e (2) primeiro, e (3) só se ainda valer. Trocar o schema invalida o cache e paga uma compilação única da gramática [SO]. |
| 3b | `max_tokens` de 16000 para **20000** e **nenhum retry no mesmo teto** depois de `stop_reason: max_tokens` (subir o teto ou usar streaming) | 0% por token; evita falhas pagas | *proposta* | A maior saída já usou 63% do teto. Hoje, um corte vira `LLM_INVALID_OUTPUT` pago, e há 2 tentativas no mesmo teto. Só os tokens gerados são cobrados. Acima de ~21k, o SDK exige streaming ou `timeout` explícito. Rechecar p95/teto por modelo depois do eval: com o Sonnet em `high`, a saída pode crescer. |

**3b feito na fase 0:** `MAX_TOKENS=20000`, `llm_output_too_long` sem nova tentativa no mesmo teto; streaming só acima de 21.333.

O thinking (22,6%) só se controla pelo effort (5.5): no Opus 5.5, `thinking: disabled` retorna 400 [E].

### 5.4 Batch (−50% em todos os tokens, inclusive cache [CO], [P])

| Caminho | Batch? | Observações |
|---|---|---|
| Import interativo | Não | O usuário está esperando. |
| **4a. Evals e varreduras** | **Sim, primeiro** | Corta pela metade o orçamento de medição do § 9. |
| **4b. Imports adiados** (00:05) | Sim | A maioria dos lotes termina em menos de 1 h. O prazo máximo é de 24 h, e itens expirados não são cobrados [B]. Substitui o 1b. |
| **4c. Backfill depois de bump** | Sim | Ver abaixo. |

**Restrições**
- `fallbacks` não é aceito em batch, e o item volta como erro [RF]. Os itens vão sem `fallbacks` e sem `betas`.
- Uma recusa no batch **não conta** para o limite `LLM_REFUSED = 1`. O item é refeito de forma síncrona, com fallbacks, depois de checar o orçamento; só esse retry conta para o limite.
- O acerto de cache dentro de um lote é por melhor esforço, tipicamente de 30% a 98% [B]. Os itens usam TTL de 1 h.
- Aquecer o cache antes do lote custa uma geração real, porque `max_tokens: 0` não funciona aqui. O primeiro item roda síncrono, sem `fallbacks` nem `betas`, com o mesmo `output_config` e TTL de 1 h; o resto vai no lote [PC].
- Saída estruturada via `output_config.format` + `RecipeLLM.model_validate_json`.

**Desenho**
1. **Separar `generate_recipe`** em `build_params(video, config)` e `interpret(body, video)`. A segunda parte concentra recusa, `max_tokens`, parse, `normalize_recipe` e `_without_method`. Os caminhos síncrono e batch passam a enviar o mesmo `system`, `messages` e `output_config`. Como o batch tira `fallbacks` e `betas`, é preciso confirmar no `usage` se os dois caminhos compartilham a entrada de cache.
2. **Tabelas novas.**
   - `llm_batches`: `anthropic_batch_id`, kind, prompt_version, model, status.
   - `llm_batch_items`: status, attempts, `prompt_version` numa coluna própria, e UNIQUE (vídeo, versão) enquanto o item não terminar.
   - O **`custom_id` é o id do item** em `llm_batch_items`. A API exige `^[a-zA-Z0-9_-]{1,64}$`, então `video_id:2026-10-14.2` seria rejeitado.
3. **Envio** por cron ou CLI:
   - selecionar os vídeos elegíveis;
   - reservar o orçamento ao preço de batch;
   - gravar os itens antes de chamar `batches.create`.

   Um cron de reconciliação cobre falhas entre a criação do lote e a gravação do id. O cron roda com `run_at_startup=True` (`worker.py:410`) e por isso envia a cada deploy; a UNIQUE impede itens duplicados.
4. **Polling** por cron arq, a cada 5–10 min. Cada item é travado e só é aplicado se ainda estiver `pending`, numa transação; é isso que garante a idempotência. Os resultados ficam disponíveis por 29 dias [B].
   - `succeeded` → `interpret` + `LLMCall` com `batch_id`. O resultado só vai para o `Video` se a versão ainda for a atual.
   - `errored` com `invalid_request` → `failed`.
   - Outros erros e `expired` → reenviar, com limite de tentativas.
5. **Adiados e imports concorrentes.** Ao aplicar o resultado, chamar `copy_recipe` + `mark_done` em todos os imports que esperam o vídeo. Se chegar um import novo de um vídeo com item `pending`, `create_import` e `process_import` o deixam `deferred`, esperando esse item, em vez de abrir uma chamada síncrona.
6. **Orçamento.** O `llm_spend_today` soma por `created_at`, que é a hora da aplicação. Por isso, reservar ao preço de batch no envio, acertar na aplicação e liberar a reserva se o item expirar ou for cancelado. Também definir um teto para a fração do orçamento diário que os lotes podem usar, para o lote das 00:05 não travar os imports interativos. Depende do item 2 do § 3.
7. **Bump com lote em andamento.** Chamar `batches.cancel`, porque itens não processados não são cobrados. A outra opção é deixar o lote terminar e aplicar o resultado via 4c(ii).

**4c. Bump compatível + backfill**
- **(i) Separar "versão atual" de "versão mínima aceita para reuso"** (ex.: `PROMPT_VERSION` + `REGENERATE_BEFORE`). Um bump que não muda a receita de forma relevante deixa de invalidar o catálogo. É **decisão de produto e troca de qualidade**, porque o usuário recebe a receita do prompt antigo.
- **(ii) Grátis.** Enquanto o backfill estiver pendente, `is_ready` e `find_ready_video` aceitam a versão anterior (`is_recipe=true`). O usuário recebe a cópia na hora, sem chamada síncrona, e **não perde cota** (`charged=false`).
- **(iii) Grátis.** O backfill cobre só os vídeos com demanda (≥ 2 cópias ou import nos últimos N dias), em ordem de número de cópias. Hoje, um bump custa *V* × ~US$ 0,10–0,108 em chamadas síncronas frias, sendo *V* o número de vídeos re-importados. Com batch, cai para cerca de metade; com (i), para zero.

**Chamadas evitáveis já cobertas:** limite de duração; vídeo ao vivo ou não incorporável; vídeo sem fala e com descrição de menos de 15 palavras; normalização de URL com `youtube_id` UNIQUE; trava por vídeo; limites de falhas pagas por versão.

### 5.5 Effort (*precisa de eval*)

- **`low` contra `medium` no Opus 5.5.** O teto é o thinking inteiro, 22,6%. Na 14.2, 3 das 17 chamadas já geraram zero thinking em `medium`.
- **Curvas publicadas para o Opus 5.5** [CO], nenhuma de extração. Em `low` contra `medium`:
  - SWE-bench Pro: ~48% mais barato por tarefa, com −5,4 pts;
  - HLE: −3,4 pts;
  - DRACO: −13,3 pts;
  - Física: −14,0 pts.
- **Risco:** a cauda. O OWLnnv4tsFQ usou 3.277 tokens de thinking para extrair as 3 marmitas. Também correm risco os timestamps e pequenas invenções (P4 da v1).
- **Cada effort cria sua própria entrada de cache.** Em batch, o acerto de cache varia por lote. Por isso, as células são comparadas pela saída (visível + thinking) e pela entrada sem cache, e as métricas de cache são analisadas à parte.
- **Rodar em `low` e refazer só as falhas em `medium`.** Só vale testar se a curva vier mista. O caso publicado [CO] chega a ~97% de resolução por ~US$ 0,17, contra US$ 0,29 com tudo em `high`. Aqui, porém, o sinal automático de falha é fraco: erro de schema, receita sem passos, `max_tokens`, timestamps fora de ordem, menos receitas do que a descrição indica. Falhas de qualidade não seriam detectadas.

### 5.6 Modelo (*precisa de eval*; último na aplicação, cedo na medição)

Os tokens medidos foram re-precificados pelas tabelas [P]. É só uma indicação, porque comportamento e tokenizador mudam as contagens.

| Modelo | US$/receita | vs hoje | Observações |
|---|---|---|---|
| Opus 5.5 `medium` (hoje) | 0,086 | — | |
| Opus 5.5 via batch | 0,043 | −50% | Só para tráfego fora do interativo. |
| Sonnet 5.5 | 0,043 | −50% | O effort padrão é `high`, então o thinking tende a crescer. Testar `high` e `medium` [E]. |
| **Haiku 5.5** | **0,0022** | **−97%** | Indicado para extração em alto volume [MO]. Effort de `low` a `high`, com thinking desligável [E]. Prompts de 6–18k ficam longe do degrau de >100k [P]. GPQA: 85% contra 91% do Opus, a ~1/20 do custo por acerto [CO]. **Não tem fallback no servidor** [RF]: com `fallbacks="default"`, uma recusa continua recusa, e uma lista de modelos dá 400. A recusa não gera fallback credit [FC], e o `LLM_REFUSED = 1` a tornaria definitiva. |
| Haiku 4.5 | 0,022 | −75% | Fora da matriz. É de geração anterior, 10× mais caro que o Haiku 5.5 e sem effort. O tokenizador antigo deu −21% de tokens (4.632 contra 5.847 medidos), o que deixa só ~12% de folga sobre o mínimo de cache. |

- **Ordem da matriz:**
  1. Haiku 5.5 em `medium`, `low` e `high` (o `high` é o recomendado [E] para seguir instruções estritas, e o prompt tem 10 regras); cada célula custa centavos;
  2. se não passar, Sonnet 5.5 em `high` e em `medium`.
- **Comparar pela cauda e pelos casos de risco, não pela mediana:**
  - cauda: OWLnnv4tsFQ, HOaJ6ak8hrA, ZU_wbPigVRI, 0QmeCM2x9Mo e BiiPDwCbzbM;
  - idioma e transcrição: wyuec0PPz68 (inglês, oz → g), uc8Pwe7alJ8 (espanhol), _T6jkRvhlkk (italiano), 8uYzXzUHvYY (whisper), KXcP15SaB_s (coreano e inglês, só música) e bXHUoszxL6A (não é receita).
- **Pré-requisitos:**
  - preços cadastrados (§ 3, item 1);
  - taxa de recusa medida por célula;
  - p95/teto da saída checado de novo (3b);
  - cache mínimo checado de novo;
  - no interativo, manter `fallbacks="default"` no Opus e no Sonnet. No Haiku 5.5, usar fallback no cliente (middleware do SDK ou retry manual) e incluir no custo do candidato o retry sem crédito, que paga a escrita completa do cache no outro modelo.

---

## 6. Alavancas descartadas

| Alavanca | Por quê |
|---|---|
| Keep-alive com `max_tokens: 0` | Rejeitado junto com saída estruturada e em Batches [CO], [PC]. |
| Cache condicional "olhando para trás" (marcar se a chamada anterior foi há menos de um TTL) | O custo esperado sempre fica entre "desligado" e "sempre ligado". |
| Limpeza da descrição (remover URLs, hashtags, redes, patrocínio) | ≤ 0,8% (≈ US$ 0,0007 por receita), medido removendo a linha inteira. Removendo só a URL, o ganho é ainda menor. Não paga o teste nem o diff. |
| Pré-classificador barato (receita ou não) | Valor esperado negativo. Não-receita já sai barato (bXHUoszxL6A: US$ 0,0099), e o veredito é reaproveitado. |
| Deduplicar re-uploads da mesma receita | Detecção cara para um ganho raro. As formas de URL já são unificadas. |
| Desligar o thinking no Opus 5.5 | Retorna 400 [E]. |
| Encurtar os nomes das chaves JSON | Teto ≤ 3–6%, com risco de o modelo entender pior os campos. Mexer na estrutura (3a) vem antes. |
| Remover duplicações, como a lista bilíngue do KXcP15SaB_s | < 0,1% e não é seguro fazer automaticamente. |
| Trechos de 30 s na transcrição | Só +0,3 p.p. sobre 15 s, com o dobro de imprecisão. |
| Haiku 4.5 | Dominado pelo Haiku 5.5 (§ 5.6). |
| Tool search, context editing, compaction, subagentes, Files API, redução de imagem | Não há tools, loop, mídia nem histórico. |
| Cache automático no topo da requisição | O turno do usuário é único por vídeo, e o breakpoint no `system` já cobre o prefixo. |
| Fast mode e `inference_geo: "us"` | Custam acima do preço padrão (US$ 8/40 e 1,1× [P]). |
| Advisor ou orquestrador com dois modelos | Não há trabalho volumoso a delegar nem loop. |
| Task budgets | São feitos para loops agênticos. Aqui, o thinking se controla pelo effort. |
| Escalonar chamadas frias concorrentes no interativo | Exige streaming, e o ganho é baixo no tráfego atual (o cron já é coberto por 1b e 4b). |
| Usage/Cost Admin API | Indisponível em contas individuais. O `llm_calls` já fornece o perfil. |

---

## 7. Eval runner

É pré-requisito de toda troca: nenhuma vai para produção sem ele.

**Fase 0 (feito):** runner em `python -m app.cli llm-eval` (sem `--batch`, que é da fase 1), conjunto em `backend/evals/ids.txt`; `--from-db` avalia as receitas gravadas sem chamar o Claude (a linha de base da 14.2). A rubrica continua fora do runner.

- **`LLMConfig(model, effort, max_tokens, fallbacks, cache_ttl)`** congelado, com os padrões de produção. `generate_recipe(video, *, client=None, config=DEFAULT)` monta a requisição a partir dele.
- **CLI:** `python -m app.cli llm-eval --ids FILE --model M --effort E [--max-tokens N] [--no-fallbacks] [--batch] [--repeat K] --out DIR`
  - Lê as linhas de `Video` congeladas, sem yt-dlp nem whisper, então a entrada é idêntica byte a byte entre as células.
  - **Nunca escreve em `Video`.** Grava em `llm_calls` com `purpose='eval'`, em orçamento separado.
  - Roda em ordem estável e sequencial, ou com `--batch`.
  - Antes de rodar, imprime a estimativa de custo e exige `--yes`, porque passa por fora dos limites por usuário.
- **Saída:**
  - `DIR/<id>.json`: receita, `usage`, `llm_cost_usd`, `stop_reason`, `request_id`, latência e config;
  - `DIR/summary.csv`: custo por receita, custo de saída e de entrada sem cache, acerto de cache, % de thinking, p95 da saída, taxa de recusa e checagens.
- **Conjunto:** os 17 vídeos da v1 à v3 (`eval/v3/ids.txt`), com `expected_is_recipe`. Na fase 4, ~50 vídeos.
- **Referência (primeiro passo da fase 2):**
  - dar nota de rubrica às saídas da 14.2, às cegas: o juiz não sabe a configuração;
  - avaliar duas vezes as mesmas saídas, para medir o ruído do juiz;
  - definir o limite de aceitação a partir desse ruído.
- **Checagens automáticas (grátis):**
  - `is_recipe` igual ao esperado (inclusive no bXHU);
  - regex de "dica que fala das fontes" = 0;
  - timestamp no início do trecho que contém o timestamp da 14.2 (± 1 trecho), com o Δ médio com sinal;
  - nenhum `stop_reason: max_tokens`;
  - 3 receitas no OWLnnv4tsFQ;
  - número de ingredientes e de passos contra a referência;
  - texto em pt-BR, sem passos em inglês ou espanhol;
  - unidades imperiais convertidas, com o original na `note`.
- **Rubrica (escala única de 1 a 5):** `ingredients_complete`, `quantities_correct`, `steps_faithful`, `timestamps_accurate`, `no_hallucination`, `tips_useful`, `title_summary_tags` e `overall`. Quem avalia são agentes do Claude Code, fora da API, como na v1 e na v2. Um juiz pela API custaria ~1 geração Opus por saída avaliada: ≈ US$ 26 síncrono na fase 2 e ≈ US$ 43 na fase 4. Se for usado, precisa de aprovação própria.
- **Critério para manter uma mudança:**
  - `overall` médio ≥ referência − o ruído medido do juiz;
  - nenhuma queda ≥ 1 ponto em `timestamps_accurate` ou em `no_hallucination` que se repita em ≥ 2 trials;
  - nenhum problema novo de severidade alta.

  A variação num único vídeo não decide nada.

---

## 8. Monitoramento

**Fase 0 (feito):** colunas criadas; `llm-spend --by version`.

**Colunas novas em `llm_calls`:** `started_at`, `latency_ms`, `purpose` (`import`/`deferred`/`backfill`/`eval`/`cli`), `batch_id`, `effort`, `max_tokens`, `stop_reason`, `request_id`, `cache_marker` e `cost_usd` (custo calculado na hora da gravação, incluindo as `iterations` de fallback).

| Métrica (por `prompt_version` × `model` × `purpose`) | Para quê |
|---|---|
| Custo por **receita concluída** (gasto total, incluindo falhas pagas, ÷ receitas ok) | É a unidade da otimização. |
| Acerto de cache e simulação do TTL sobre `started_at` (5 min e 1 h) | Decidir a política de cache (§ 5.1). |
| % de thinking e p95 da saída ÷ `max_tokens` | Acompanhar o effort e o risco de corte. |
| Taxa de reuso *r* | Medir a maior economia estrutural (§ 2.4). |
| Gasto por `purpose`, fração em batch e taxa de recusa | Medir o teto real do batch e o risco de fallback. |

- **`llm-spend --by version`** no CLI. O custo vem de `sum(cost_usd)`. O `usage` do topo não inclui as `iterations` de fallback, então, até a coluna existir, a consulta abaixo subconta essas chamadas:
  ```sql
  SELECT prompt_version, model, count(*) calls,
    count(*) FILTER (WHERE error_code IS NULL) ok,
    sum(coalesce((usage->>'output_tokens')::int,0)) output,
    sum(coalesce((usage->'output_tokens_details'->>'thinking_tokens')::int,0)) thinking,
    round(avg((coalesce((usage->>'cache_read_input_tokens')::int,0) > 0)::int),2) hit_rate,
    percentile_disc(0.95) WITHIN GROUP (ORDER BY coalesce((usage->>'output_tokens')::int,0)) p95_out
  FROM llm_calls GROUP BY 1,2 ORDER BY min(created_at);
  ```
- **Alertas:**
  - custo por receita ≥ +20% contra a versão anterior, depois de um deploy;
  - queda do acerto de cache com tráfego estável (algo quebrou o cache);
  - qualquer `stop_reason: max_tokens`.
- **Conferência externa:** com chave ou workspace dedicado, comparar com o Console e definir lá o limite de gasto do workspace.

---

## 9. Próximos passos, orçamento de medição e aprovações

| Fase | O quê | Custo de geração (batch) |
|---|---|---|
| 0 | **Entregue.** Correções do § 3 e barreiras de custo; colunas e `purpose` (§ 8); eval runner (§ 7); `started_at` + simulação do TTL, mantendo "5 min sempre" (5.1); 3b | US$ 0 (`count_tokens` é grátis) |
| 1 | Batch para evals e adiados (4a, 4b); desenho do 4c | US$ 0 de eval; validado só por custo |
| 2 | Nota de rubrica da 14.2 e ruído do juiz; matriz modelo × effort com 17 vídeos | **≈ US$ 6** (≈ US$ 12 síncrono) |
| 3 | Só se o modelo vencedor ainda for o Opus: 2a, 3a e 2c, com 2 trials cada | ≤ US$ 4,4 |
| 4 | Corte do vencedor para produção: ~50 vídeos × **5 trials**, baseline (Opus) e candidato | baseline US$ 10,75 + candidato (Opus ≤ US$ 10,75; Sonnet ≈ US$ 5,5; Haiku 5.5 ≈ US$ 0,3) |

A fase 4 precisa de ~33 transcrições novas. Elas vêm só da etapa de transcrição, sem chamar o Claude, o que exige uma flag nova no CLI.

**Detalhe da fase 2** (uma célula = 17 vídeos):

| Célula | Trials | Custo por célula | Subtotal |
|---|---|---|---|
| Opus 5.5 `medium` (baseline 14.2; 1 trial já existe) | 2 | US$ 0,73 | US$ 1,46 |
| Opus 5.5 `low` | 3 | ≤ US$ 0,73 | ≤ US$ 2,20 |
| Haiku 5.5 `medium` / `low` / `high` | 3 + 3 + 3 | ~US$ 0,02 | ~US$ 0,17 |
| Sonnet 5.5 `high` / `medium` | 2 + 2 | ~US$ 0,37–0,50 | ~US$ 1,5–2,0 |

**Total por cenário (geração via batch; o dobro se for síncrono; avaliação por agentes, fora da API):**

| Cenário | Fases | Total |
|---|---|---|
| Opus continua vencendo | 6 + 4,4 + 10,75 + 10,75 | ≈ US$ 32 |
| Sonnet 5.5 vence | 6 + 10,75 + 5,5 | ≈ US$ 22 |
| Haiku 5.5 vence | 6 + 10,75 + 0,3 | ≈ US$ 17 |

**Aprovações necessárias**
1. **Orçamento de medição:** ≈ US$ 6 para a fase 2. As fases 3 e 4, de até ≈ US$ 26, só são aprovadas depois do resultado da fase 2. Um juiz pela API teria custo à parte (§ 7).
2. **Chave ou workspace separado** (ou orçamento próprio para `purpose='eval'`) e um limite de gasto do workspace no Console.
3. **Decisão de produto do 4c(i):** separar a versão atual da versão mínima aceita para reuso.
4. **Troca de modelo ou de effort:** só depois do eval da fase 4. No Haiku 5.5, com o fallback no cliente já implementado. Um shadow run em produção dobra o gasto enquanto roda e precisa de aprovação própria.
5. **Mudança da política de cache:** para 1 h, quando a simulação do TTL em produção mostrar acerto ≥ ~51% em 1 h; para desligado ou por demanda, se o volume for baixo. Nos dois casos, registrando por escrito o desvio do "cache sempre ligado".

---

## Fontes (consultadas em 2026-10-14)

- [P] Pricing: https://platform.claude.com/docs/en/about-claude/pricing
- [CO] Optimizing for cost and intelligence: https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence
- [PC] Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- [B] Batch processing: https://platform.claude.com/docs/en/build-with-claude/batch-processing (e `custom_id` em https://platform.claude.com/docs/en/api/messages/batches/create)
- [E] Effort: https://platform.claude.com/docs/en/build-with-claude/effort
- [SO] Structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- [RF] Refusals and fallback: https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback
- [FC] Fallback credit: https://platform.claude.com/docs/en/build-with-claude/fallback-credit
- [T] Thinking: https://platform.claude.com/docs/en/build-with-claude/thinking
- [MO] Models overview: https://platform.claude.com/docs/en/about-claude/models/overview
- Dados: tabela `llm_calls` de dev (50 linhas; versões 2026-10-13.1, 2026-10-14.1 e 2026-10-14.2), JSONs do eval v1/v2/v3, `results.json` da v1 e da v2, e `count_tokens`.
