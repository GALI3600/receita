/**
 * Quantos caracteres o backend conta: code points (len() do Python, max_length do Pydantic), não
 * unidades UTF-16 como `.length` do JavaScript. Um emoji conta 1, e não 2.
 */
export function charCount(text: string): number {
  return Array.from(text).length
}
