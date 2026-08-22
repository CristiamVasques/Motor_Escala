"""
Estágio 2 do pipeline — busca local por Hill Climbing (Subseção 6.1.3).

Estratégia de melhor melhora (best improvement): a cada iteração toda a
vizinhança amostrada é avaliada e aplica-se o movimento de maior redução da
função objetivo. O caráter determinístico do método é preservado: fixados a
solução inicial e o seed do gerador, o resultado é sempre o mesmo.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..dominio import Instancia
from ..escala import Escala
from ..objetivo import FuncaoObjetivo
from ..vizinhanca import (
    Movimento,
    aplicar_se_factivel,
    gerar_vizinhanca,
    reverter,
)


@dataclass
class RelatorioHillClimbing:
    iteracoes: int = 0
    movimentos_aplicados: int = 0
    custo_inicial: float = 0.0
    custo_final: float = 0.0
    movimentos_por_tipo: Dict[str, int] = field(default_factory=dict)

    @property
    def ganho(self) -> float:
        return self.custo_inicial - self.custo_final


def otimizar(
    inst: Instancia,
    escala: Escala,
    fo: FuncaoObjetivo,
    rng: Optional[random.Random] = None,
    max_iteracoes: int = 200,
    tamanho_vizinhanca: int = 240,
    epsilon: float = 1e-9,
    exigir_repouso_semanal: bool = True,
    cardinalidade_fixa: bool = False,
) -> RelatorioHillClimbing:
    """Refina a escala in loco até atingir um ponto de estabilidade local."""
    rng = rng or random.Random(0)
    rel = RelatorioHillClimbing(custo_inicial=fo.custo(escala))
    custo_atual = rel.custo_inicial

    for _ in range(max_iteracoes):
        rel.iteracoes += 1
        vizinhos = gerar_vizinhanca(
            inst, escala, rng, tamanho_vizinhanca, cardinalidade_fixa
        )

        melhor_mov: Optional[Movimento] = None
        melhor_custo = custo_atual

        for mov in vizinhos:
            if not aplicar_se_factivel(inst, escala, mov, exigir_repouso_semanal):
                continue
            candidato = fo.custo(escala)
            reverter(escala, mov)
            if candidato < melhor_custo - epsilon:
                melhor_custo = candidato
                melhor_mov = mov

        if melhor_mov is None:
            break  # ótimo local: nenhum vizinho representa melhoria

        aplicar_se_factivel(inst, escala, melhor_mov, exigir_repouso_semanal)
        custo_atual = melhor_custo
        rel.movimentos_aplicados += 1
        rel.movimentos_por_tipo[melhor_mov.tipo] = (
            rel.movimentos_por_tipo.get(melhor_mov.tipo, 0) + 1
        )

    rel.custo_final = custo_atual
    return rel
