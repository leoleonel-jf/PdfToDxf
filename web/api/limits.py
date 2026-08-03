"""Tetos técnicos do serviço, num lugar só.

Estes valores valem para todo mundo. Os limites por plano de usuário — 20 MB
sem conta, 100 MB com conta — são da etapa 4 e moram em outro lugar.
"""

from __future__ import annotations

TETO_PDF_BYTES = 100 * 1024 * 1024      # 100 MB
TETO_ENTIDADES = 3_000_000              # por página
EXTRACOES_SIMULTANEAS = 4               # de 8 vCPU
PRAZO_SEGUNDOS = 4 * 60 * 60            # 4 horas
COTA_DISCO_BYTES = 40 * 1024 * 1024 * 1024   # 40 GB

# limites aplicados ao processo que extrai (só POSIX; ver jobs.py)
TETO_MEMORIA_WORKER_BYTES = 6 * 1024 * 1024 * 1024   # 6 GB
TETO_CPU_WORKER_SEGUNDOS = 300
