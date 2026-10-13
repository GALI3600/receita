import { useResendVerification } from '../api/queries'
import { describeError } from '../lib/errors'

/** Botão "reenviar link de confirmação" com o resultado logo abaixo (precisa estar logado). */
export function ResendVerification({ className = '' }: { className?: string }) {
  const resend = useResendVerification()
  return (
    <div className={className}>
      <button
        type="button"
        className="btn-secondary"
        onClick={() => resend.mutate()}
        disabled={resend.isPending || resend.isSuccess}
      >
        {resend.isPending ? 'Enviando…' : resend.isSuccess ? 'Link enviado' : 'Reenviar o link'}
      </button>
      <div aria-live="polite" className="mt-2 text-sm">
        {resend.isSuccess && <p className="text-sage">{resend.data.message}</p>}
        {resend.isError && (
          <p className="font-semibold text-danger">{describeError(resend.error)}</p>
        )}
      </div>
    </div>
  )
}
