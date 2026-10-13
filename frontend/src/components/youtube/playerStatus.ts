export type PlayerStatus = 'loading' | 'ready' | 'unavailable' | 'error'

/** O vídeo não vai tocar aqui (removido, privado, sem embed ou a API não carregou). */
export function isPlayerUnavailable(status: PlayerStatus): boolean {
  return status === 'unavailable' || status === 'error'
}
