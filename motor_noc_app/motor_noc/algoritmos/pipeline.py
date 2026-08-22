"""
Arquitetura híbrida de otimização (Subseção 6.1.8).

Encadeia os quatro estágios do motor e registra, ao final de cada um, o custo,
as componentes brutas e as violações remanescentes — insumo direto para a
métrica 5.1(b), que quantifica o ganho incremental de qualidade proporcionado
por cada etapa do pipeline.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..dominio import Instancia
from ..escala import Escala
from ..objetivo import FuncaoObjetivo, Normalizador, Pesos
from ..restricoes import validar, violacoes_flexiveis
from . import csp, guloso, hill_climbing, simulated_annealing
from .simulated_annealing import ParametrosSA


@dataclass
class EstagioInfo:
    """Fotografia do estado da solução ao término de um estágio."""

    nome: str
    tempo_s: float
    alocacoes: int
    componentes_brutos: Dict[str, float] = field(default_factory=dict)
    custo: float = 0.0
    violacoes_rigidas: int = 0
    flexiveis: Dict[str, float] = field(default_factory=dict)
    escala: Optional[Escala] = None


@dataclass
class ResultadoPipeline:
    escala: Escala
    fo: FuncaoObjetivo
    estagios: List[EstagioInfo] = field(default_factory=list)
    deficits_guloso: List[str] = field(default_factory=list)
    relatorio_hc: Optional[hill_climbing.RelatorioHillClimbing] = None
    relatorio_sa: Optional[simulated_annealing.RelatorioSA] = None
    relatorio_csp: Optional[csp.RelatorioCSP] = None
    tempo_total_s: float = 0.0

    @property
    def valida(self) -> bool:
        return bool(self.relatorio_csp and self.relatorio_csp.escala_valida)

    def custo_final(self) -> float:
        return self.fo.custo(self.escala)


def _fotografar(
    nome: str,
    inst: Instancia,
    escala: Escala,
    fo: FuncaoObjetivo,
    tempo_s: float,
    exigir_repouso_semanal: bool,
) -> EstagioInfo:
    return EstagioInfo(
        nome=nome,
        tempo_s=tempo_s,
        alocacoes=escala.total_alocacoes(),
        componentes_brutos=escala.componentes(),
        custo=fo.custo(escala),
        violacoes_rigidas=len(validar(inst, escala, exigir_repouso_semanal)),
        flexiveis=violacoes_flexiveis(inst, escala),
        escala=escala.copiar(),
    )


def executar(
    inst: Instancia,
    pesos: Optional[Pesos] = None,
    seed: int = 42,
    params_sa: Optional[ParametrosSA] = None,
    max_iteracoes_hc: int = 200,
    tamanho_vizinhanca: int = 240,
    exigir_repouso_semanal: bool = True,
    max_nos_csp: int = 200_000,
    cardinalidade_fixa: bool = False,
) -> ResultadoPipeline:
    """Executa Greedy → Hill Climbing → Simulated Annealing → CSP.

    Em modo de cardinalidade fixa o motor não inclui analistas além da
    demanda mínima, de modo que seu espaço de busca coincida com o espaço
    percorrido pela busca exaustiva na métrica 5.1(c).
    """
    pesos = pesos or Pesos()
    params_sa = params_sa or ParametrosSA()
    rng = random.Random(seed)
    fo = FuncaoObjetivo(pesos, Normalizador())

    t0 = time.perf_counter()
    estagios: List[EstagioInfo] = []

    # -- Estágio 1: construção gulosa -------------------------------------
    marco = time.perf_counter()
    escala, deficits = guloso.construir(
        inst,
        rng,
        ajustar_capacidade=not cardinalidade_fixa,
        exigir_repouso_semanal=exigir_repouso_semanal,
    )
    tempo_guloso = time.perf_counter() - marco

    # -- Aquecimento: calibra e congela os limites de normalização --------
    # Executado sobre a solução gulosa, antes dos estágios de refinamento,
    # para que todos compartilhem a mesma escala de custo e as comparações
    # entre etapas sejam legítimas.
    marco = time.perf_counter()
    simulated_annealing.aquecer(
        inst,
        escala,
        fo,
        random.Random(seed + 1),
        params_sa.iteracoes_aquecimento,
        exigir_repouso_semanal,
        cardinalidade_fixa,
    )
    tempo_aquecimento = time.perf_counter() - marco

    estagios.append(
        _fotografar(
            "1. Construção Gulosa",
            inst,
            escala,
            fo,
            tempo_guloso + tempo_aquecimento,
            exigir_repouso_semanal,
        )
    )

    # -- Estágio 2: Hill Climbing -----------------------------------------
    marco = time.perf_counter()
    rel_hc = hill_climbing.otimizar(
        inst,
        escala,
        fo,
        rng,
        max_iteracoes=max_iteracoes_hc,
        tamanho_vizinhanca=tamanho_vizinhanca,
        exigir_repouso_semanal=exigir_repouso_semanal,
        cardinalidade_fixa=cardinalidade_fixa,
    )
    estagios.append(
        _fotografar(
            "2. Hill Climbing",
            inst,
            escala,
            fo,
            time.perf_counter() - marco,
            exigir_repouso_semanal,
        )
    )

    # -- Estágio 3: Simulated Annealing -----------------------------------
    marco = time.perf_counter()
    escala, rel_sa = simulated_annealing.otimizar(
        inst, escala, fo, rng, params_sa, exigir_repouso_semanal, cardinalidade_fixa
    )
    estagios.append(
        _fotografar(
            "3. Simulated Annealing",
            inst,
            escala,
            fo,
            time.perf_counter() - marco,
            exigir_repouso_semanal,
        )
    )

    # -- Estágio 4: CSP com Backtracking ----------------------------------
    marco = time.perf_counter()
    rel_csp = csp.validar_e_reparar(
        inst, escala, max_nos_csp, exigir_repouso_semanal
    )
    estagios.append(
        _fotografar(
            "4. CSP com Backtracking",
            inst,
            escala,
            fo,
            time.perf_counter() - marco,
            exigir_repouso_semanal,
        )
    )

    return ResultadoPipeline(
        escala=escala,
        fo=fo,
        estagios=estagios,
        deficits_guloso=deficits,
        relatorio_hc=rel_hc,
        relatorio_sa=rel_sa,
        relatorio_csp=rel_csp,
        tempo_total_s=time.perf_counter() - t0,
    )
