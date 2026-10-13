// Escala de porções: acha os números de um texto de quantidade ("2", "1/2", "1 e 1/2", "1,5",
// "2-3", "200 g") e multiplica, mantendo o resto do texto. O que não tem número ("a gosto",
// "uma pitada") fica como está.

const UNICODE_FRACTIONS: Record<string, number> = {
  '½': 1 / 2,
  '⅓': 1 / 3,
  '⅔': 2 / 3,
  '¼': 1 / 4,
  '¾': 3 / 4,
  '⅕': 1 / 5,
  '⅖': 2 / 5,
  '⅗': 3 / 5,
  '⅘': 4 / 5,
  '⅙': 1 / 6,
  '⅚': 5 / 6,
  '⅛': 1 / 8,
  '⅜': 3 / 8,
  '⅝': 5 / 8,
  '⅞': 7 / 8,
}
const UNI = Object.keys(UNICODE_FRACTIONS).join('')

// Um número: misto ("1 1/2", "1 e 1/2", "1½"), fração ("1/2", "½") ou decimal/inteiro
// ("1,5", "1.5", "200", "1.000"). A ordem das alternativas importa: a mais longa primeiro.
const SINGLE = [
  String.raw`\d+\s+(?:e\s+)?\d+\s*\/\s*\d+`,
  String.raw`\d+\s*(?:e\s+)?[${UNI}]`,
  String.raw`\d+\s*\/\s*\d+`,
  `[${UNI}]`,
  String.raw`\d+(?:[.,]\d+)?`,
].join('|')

// Uma quantidade, que pode ser uma faixa ("2-3", "2 a 3", "2 ou 3"). Não começa colado em letra
// nem em outro número ("x2", "1/2" já consumido) e não termina no meio de um número.
const AMOUNT_RE = new RegExp(
  String.raw`(?<![\p{L}\d.,\/])(${SINGLE})(?:(\s*[-–—]\s*|\s+(?:a|até|ou)\s+)(${SINGLE}))?(?![\d\/])`,
  'gu',
)

type NumberStyle = 'integer' | 'decimal' | 'fraction'

interface ParsedNumber {
  value: number
  style: NumberStyle
}

/** Lê um número isolado (uma das alternativas de SINGLE); null se não for válido. */
export function parseNumber(raw: string): ParsedNumber | null {
  const text = raw.trim()
  let match = /^(\d+)\s+(?:e\s+)?(\d+)\s*\/\s*(\d+)$/.exec(text)
  if (match) {
    const den = Number(match[3])
    if (den === 0) return null
    return { value: Number(match[1]) + Number(match[2]) / den, style: 'fraction' }
  }
  match = new RegExp(`^(\\d+)\\s*(?:e\\s+)?([${UNI}])$`, 'u').exec(text)
  if (match) {
    return { value: Number(match[1]) + UNICODE_FRACTIONS[match[2]], style: 'fraction' }
  }
  match = /^(\d+)\s*\/\s*(\d+)$/.exec(text)
  if (match) {
    const den = Number(match[2])
    if (den === 0) return null
    return { value: Number(match[1]) / den, style: 'fraction' }
  }
  if (text in UNICODE_FRACTIONS) return { value: UNICODE_FRACTIONS[text], style: 'fraction' }
  // "1.000" e "12.500" são milhares (como se escreve no Brasil); "1.5" e "1,5" são decimais.
  if (/^\d{1,3}(?:\.\d{3})+$/.test(text)) {
    return { value: Number(text.replace(/\./g, '')), style: 'integer' }
  }
  if (/^\d+$/.test(text)) return { value: Number(text), style: 'integer' }
  if (/^\d+[.,]\d+$/.test(text)) {
    return { value: Number(text.replace(',', '.')), style: 'decimal' }
  }
  return null
}

const integerFormat = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })
const decimalFormat = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 2 })
const oneDecimalFormat = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 })

// Frações de cozinha: oitavos, quartos, terços e meios.
const KITCHEN_FRACTIONS: Array<[number, string]> = [
  [0, ''],
  [1 / 8, '1/8'],
  [1 / 4, '1/4'],
  [1 / 3, '1/3'],
  [3 / 8, '3/8'],
  [1 / 2, '1/2'],
  [5 / 8, '5/8'],
  [2 / 3, '2/3'],
  [3 / 4, '3/4'],
  [7 / 8, '7/8'],
  [1, ''],
]
const FRACTION_TOLERANCE = 0.035
// Abaixo disto (sem parte inteira) nem o oitavo serve: fica o decimal ("0,06").
const SMALLEST_FRACTION = 1 / 8 - FRACTION_TOLERANCE

function formatDecimal(value: number): string {
  return (value >= 10 ? oneDecimalFormat : decimalFormat).format(value)
}

/**
 * Número em formato de receita. Estilo "fraction" (padrão): frações amigáveis (0,5 → "1/2",
 * 1,5 → "1 1/2", 0,333 → "1/3"); o que não bate com nenhuma vai para a fração de cozinha mais
 * próxima (1,17 → "1 1/8", 0,58 → "5/8"), e só o que é pequeno demais até para um oitavo fica
 * decimal ("0,06"). De 10 em diante só inteiros e meios e, de 100 em diante, só inteiros
 * ("133", "1.000"). Estilo "decimal": vírgula, até duas casas ("2,25").
 */
export function formatAmount(value: number, style: NumberStyle = 'fraction'): string {
  if (!Number.isFinite(value) || value < 0) return ''
  if (style === 'decimal') {
    const rounded = Math.round(value * 100) / 100
    return Number.isInteger(rounded) ? integerFormat.format(rounded) : formatDecimal(rounded)
  }
  if (value >= 100) return integerFormat.format(Math.round(value))
  if (value >= 10) {
    // Meio só quando está perto (10,4 → "10 1/2"); senão, inteiro (83,3 → "83").
    const halves = Math.round(value * 2) / 2
    if (Number.isInteger(halves) || Math.abs(value - halves) > 0.1 + 1e-9) {
      return integerFormat.format(Math.round(value))
    }
    return `${Math.floor(halves)} 1/2`
  }
  const whole = Math.floor(value)
  const rest = value - whole
  let best = KITCHEN_FRACTIONS[0]
  for (const candidate of KITCHEN_FRACTIONS) {
    if (Math.abs(rest - candidate[0]) < Math.abs(rest - best[0])) best = candidate
  }
  if (whole === 0 && rest < SMALLEST_FRACTION) return formatDecimal(value)
  const wholePart = whole + (best[0] === 1 ? 1 : 0)
  const fraction = best[0] === 1 ? '' : best[1]
  if (wholePart === 0 && !fraction) {
    // Pequeno demais para uma fração (ex.: 0,02): mostra o decimal em vez de "0".
    return value === 0 ? '0' : formatDecimal(value)
  }
  if (wholePart === 0) return fraction
  return fraction ? `${wholePart} ${fraction}` : String(wholePart)
}

interface AmountMatch {
  start: number
  end: number
  /** Um valor, ou dois numa faixa. */
  values: number[]
  styles: NumberStyle[]
  separator: string | null
}

function findAmounts(text: string): AmountMatch[] {
  const found: AmountMatch[] = []
  for (const match of text.matchAll(AMOUNT_RE)) {
    const first = parseNumber(match[1])
    if (!first) continue
    const second = match[3] ? parseNumber(match[3]) : null
    const start = match.index
    if (match[3] && !second) {
      // "2-x/0": vale só o primeiro número.
      found.push({
        start,
        end: start + match[1].length,
        values: [first.value],
        styles: [first.style],
        separator: null,
      })
      continue
    }
    found.push({
      start,
      end: start + match[0].length,
      values: second ? [first.value, second.value] : [first.value],
      styles: second ? [first.style, second.style] : [first.style],
      separator: second ? match[2] : null,
    })
  }
  return found
}

/**
 * Quantidade escalada. Em unidades métricas (g, kg, ml, l), um número inteiro escalado vira
 * decimal ("1 kg" → "1,17 kg"), não fração de cozinha; de 10 em diante, inteiro ("233 g").
 */
function formatScaled(match: AmountMatch, factor: number, metric = false): string {
  const parts = match.values.map((value, i) => {
    const scaled = value * factor
    if (metric && match.styles[i] === 'integer') {
      return formatAmount(scaled >= 10 ? Math.round(scaled) : scaled, 'decimal')
    }
    return formatAmount(scaled, match.styles[i])
  })
  return match.separator === null ? parts[0] : `${parts[0]}${match.separator}${parts[1]}`
}

/** O maior valor da quantidade (o fim da faixa), para decidir singular/plural. */
function amountForAgreement(match: AmountMatch): number {
  return Math.max(...match.values)
}

/** Primeiro número do texto (o começo da faixa), ou null se não houver. */
export function firstAmount(text: string | null | undefined): number | null {
  if (!text) return null
  const match = findAmounts(text)[0]
  return match ? match.values[0] : null
}

/** O texto tem algum número que dá para escalar? */
export function hasAmount(text: string | null | undefined): boolean {
  return firstAmount(text) !== null
}

export interface ScaledText {
  text: string
  /** O primeiro número antes e depois de escalar (para concordar a unidade). */
  before: number | null
  after: number | null
}

/**
 * Multiplica os números de `text` por `factor`, mantendo o resto. Com `firstOnly`, só a primeira
 * quantidade muda (no rendimento, "1 forma de 20 cm" não vira "2 formas de 40 cm").
 */
export function scaleText(
  text: string,
  factor: number,
  { firstOnly = false, metric = false }: { firstOnly?: boolean; metric?: boolean } = {},
): ScaledText {
  const matches = findAmounts(text)
  if (matches.length === 0) return { text, before: null, after: null }
  const first = matches[0]
  const before = amountForAgreement(first)
  if (factor === 1) return { text, before, after: before }
  const targets = firstOnly ? [first] : matches
  let result = ''
  let cursor = 0
  for (const match of targets) {
    result += text.slice(cursor, match.start) + formatScaled(match, factor, metric)
    cursor = match.end
  }
  result += text.slice(cursor)
  return { text: result, before, after: before * factor }
}

// --- Singular e plural da unidade --------------------------------------------------------------

/** Em português, 1 e 1/2 xícara ainda é singular; o plural começa em 2. */
function isPlural(value: number): boolean {
  return value >= 2 - 1e-9
}

const WORD_RE = /^(\p{L}+)/u

// Palavras em "-ão" cujo plural não é "-ões".
const PLURAL_AO: Record<string, string> = {
  pão: 'pães',
  mão: 'mãos',
  grão: 'grãos',
  cão: 'cães',
}

function pluralize(word: string): string {
  const lower = word.toLowerCase()
  // Mantém a primeira letra como veio ("Pão" → "Pães").
  if (PLURAL_AO[lower]) return word[0] + PLURAL_AO[lower].slice(1)
  if (/ão$/.test(word)) return word.replace(/ão$/, 'ões')
  if (/[aeiouáéíóúâêô]$/i.test(word)) return `${word}s`
  if (/[rz]$/i.test(word)) return `${word}es`
  return word
}

function singularize(word: string): string {
  if (/ões$/.test(word)) return word.replace(/ões$/, 'ão')
  if (/ães$/.test(word)) return word.replace(/ães$/, 'ão')
  if (/[rz]es$/i.test(word)) return word.slice(0, -2)
  if (/[aeiouáéíóúâêô]s$/i.test(word)) return word.slice(0, -1)
  return word
}

/**
 * Concorda a primeira palavra de uma unidade com a quantidade nova ("xícara" → "xícaras",
 * "colheres de sopa" → "colher de sopa", "pão" → "pães"). Abreviações ("g", "ml", "kg") ficam
 * como estão; só muda quando a quantidade passou de singular para plural ou o contrário.
 */
export function agreeUnit(unit: string, before: number | null, after: number | null): string {
  if (before === null || after === null) return unit
  const wasPlural = isPlural(before)
  const willBePlural = isPlural(after)
  if (wasPlural === willBePlural) return unit
  const match = WORD_RE.exec(unit)
  if (!match || match[1].length < 3) return unit
  const word = match[1]
  const changed = willBePlural ? pluralize(word) : singularize(word)
  return changed + unit.slice(word.length)
}

// --- Ingredientes e rendimento ---------------------------------------------------------------

export interface ScalableIngredient {
  quantity: string | null
  unit: string | null
}

const METRIC_UNIT_RE =
  /^(?:k?g|mg|m?l|gramas?|quilos?|quilogramas?|mililitros?|litros?)(?![\p{L}])/iu

/** Quantidade e unidade escaladas; sem número na quantidade, tudo fica igual. */
export function scaleIngredient<T extends ScalableIngredient>(ingredient: T, factor: number): T {
  if (factor === 1 || !ingredient.quantity) return ingredient
  const metric = METRIC_UNIT_RE.test(ingredient.unit?.trim() ?? '')
  const scaled = scaleText(ingredient.quantity, factor, { metric })
  if (scaled.before === null) return ingredient
  const unit = ingredient.unit ? agreeUnit(ingredient.unit, scaled.before, scaled.after) : null
  return { ...ingredient, quantity: scaled.text, unit }
}

/** Quantas porções o rendimento indica ("6 unidades" → 6, "4 a 6 porções" → 4), ou null. */
export function parseServings(servings: string | null | undefined): number | null {
  const value = firstAmount(servings)
  return value !== null && value > 0 ? value : null
}

/**
 * Rendimento para `count` porções a partir do original: "6 unidades" com 12 → "12 unidades";
 * "4 a 6 porções" com 8 → "8 a 12 porções"; "1 bolo" com 2 → "2 bolos".
 */
export function scaleServings(servings: string, count: number): string {
  const base = parseServings(servings)
  if (base === null || count === base) return servings
  const factor = count / base
  const scaled = scaleText(servings, factor, { firstOnly: true })
  const match = findAmounts(servings)[0]
  // A palavra logo depois do número concorda com ele ("1 bolo" → "2 bolos").
  const scaledEnd = match.start + formatScaled(match, factor).length
  const head = scaled.text.slice(0, scaledEnd)
  const tail = scaled.text.slice(scaledEnd)
  const spacing = /^\s+/.exec(tail)?.[0] ?? ''
  if (!spacing) return scaled.text
  const after = amountForAgreement(match) * factor
  return head + spacing + agreeUnit(tail.slice(spacing.length), amountForAgreement(match), after)
}
