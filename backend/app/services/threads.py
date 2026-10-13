"""Trabalho bloqueante em thread que respeita o cancelamento da tarefa asyncio.

`asyncio.to_thread` não interrompe a thread quando a tarefa é cancelada (timeout do job,
shutdown): ela continua baixando ou transcrevendo, e quem limpa os arquivos logo depois apaga
o diretório debaixo dela. Aqui a função recebe um `threading.Event` que é marcado no
cancelamento e precisa consultá-lo para parar; o cancelamento só se propaga depois que a
thread terminou.
"""

import asyncio
import threading
from collections.abc import Callable


async def run_cancellable[T](func: Callable[[threading.Event], T]) -> T:
    cancel = threading.Event()
    task = asyncio.ensure_future(asyncio.to_thread(func, cancel))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        cancel.set()
        await asyncio.wait({task})
        if not task.cancelled():
            # Marca como lido o erro de ter sido interrompida; o resultado não interessa mais.
            task.exception()
        raise
