"""
Métricas de avaliação da solução (Seção 5.1 do TCC).

  (a) comparação com a escala manual histórica;
  (b) taxa de violação de restrições flexíveis por estágio do pipeline;
  (c) gap de otimalidade em instâncias reduzidas;
  (d) curva de convergência do Simulated Annealing;
  (e) sensibilidade aos pesos estruturais α, δ, λ.

Acrescenta ainda o benchmark de desempenho computacional previsto no objetivo
específico (d): tempo de processamento e consumo de memória sob carga.
"""
from __future__ import annotations

import itertools
import random
import statistics
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .algoritmos.pipeline import ResultadoPipeline, executar
from .algoritmos.simulated_annealing import ParametrosSA, RelatorioSA
from .baseline import construir_escala_manual
from .dominio import Instancia, Nivel, Turno
from .escala import Escala
from .objetivo import FuncaoObjetivo, Normalizador, Pesos
from .restricoes import pode_alocar, validar, violacoes_flexiveis


# ---------------------------------------------------------------------------
# (a) Comparação com a escala manual
# ---------------------------------------------------------------------------


def _estatisticas_de_carga(inst: Instancia, escala: Escala) -> Dict[str, float]:
    desvios: List[float] = []
    amplitudes: List[float] = []
    for equipe in inst.equipes.values():
        if len(equipe) < 2:
            continue
        cargas = [escala.horas_reais[a.id] for a in equipe]
        desvios.append(statistics.pstdev(cargas))
        amplitudes.append(max(cargas) - min(cargas))
    todas = [escala.horas_reais[a.id] for a in inst.analistas]
    return {
        "desvio_padrao_medio_por_equipe": statistics.fmean(desvios) if desvios else 0.0,
        "amplitude_media_por_equipe": statistics.fmean(amplitudes) if amplitudes else 0.0,
        "carga_media_h": statistics.fmean(todas) if todas else 0.0,
        "carga_maxima_h": max(todas) if todas else 0.0,
        "carga_minima_h": min(todas) if todas else 0.0,
    }


def comparar_com_manual(
    inst: Instancia,
    escala_motor: Escala,
    escala_manual: Escala,
    fo: FuncaoObjetivo,
) -> Dict[str, Dict[str, float]]:
    """Métrica 5.1(a) — motor versus escala montada por rodízio manual."""
    linhas: Dict[str, Dict[str, float]] = {}
    for rotulo, escala in (("manual", escala_manual), ("motor", escala_motor)):
        flex = violacoes_flexiveis(inst, escala)
        linhas[rotulo] = {
            **_estatisticas_de_carga(inst, escala),
            "custo_F": fo.custo(escala),
            "f_balanceamento": escala.f_balanceamento,
            "f_senioridade": escala.f_senioridade,
            "f_atendimento": escala.f_atendimento,
            "alocacoes_superqualificadas": flex["alocacoes_superqualificadas"],
            "violacoes_rigidas": float(len(validar(inst, escala))),
            "alocacoes": float(escala.total_alocacoes()),
        }

    manual, motor = linhas["manual"], linhas["motor"]
    linhas["variacao_percentual"] = {
        chave: (
            100.0 * (motor[chave] - manual[chave]) / manual[chave]
            if manual[chave]
            else 0.0
        )
        for chave in manual
    }
    return linhas


# ---------------------------------------------------------------------------
# (b) Ganho incremental por estágio
# ---------------------------------------------------------------------------


def ganho_por_estagio(resultado: ResultadoPipeline) -> List[Dict[str, object]]:
    """Métrica 5.1(b) — evolução do custo e das violações a cada estágio."""
    linhas: List[Dict[str, object]] = []
    custo_anterior: Optional[float] = None
    for estagio in resultado.estagios:
        ganho = (
            0.0 if custo_anterior is None else custo_anterior - estagio.custo
        )
        linhas.append(
            {
                "estagio": estagio.nome,
                "tempo_s": round(estagio.tempo_s, 4),
                "alocacoes": estagio.alocacoes,
                "custo_F": estagio.custo,
                "ganho_absoluto": ganho,
                "ganho_percentual": (
                    100.0 * ganho / custo_anterior
                    if custo_anterior not in (None, 0)
                    else 0.0
                ),
                "violacoes_rigidas": estagio.violacoes_rigidas,
                "taxa_desequilibrio": estagio.flexiveis["taxa_desequilibrio"],
                "taxa_superqualificacao": estagio.flexiveis["taxa_superqualificacao"],
                **{f"bruto_{k}": v for k, v in estagio.componentes_brutos.items()},
            }
        )
        custo_anterior = estagio.custo
    return linhas


# ---------------------------------------------------------------------------
# (c) Gap de otimalidade em instância reduzida
# ---------------------------------------------------------------------------


def _grupos_viaveis(
    inst: Instancia, t: Turno, extras_max: int
) -> List[Tuple[str, ...]]:
    """Conjuntos de analistas que satisfazem a demanda mínima do turno."""
    por_nivel: Dict[Nivel, List[str]] = {}
    for a in inst.candidatos[t.id]:
        por_nivel.setdefault(a.nivel, []).append(a.id)

    obrigatorios: List[List[Tuple[str, ...]]] = []
    for nivel, minimo in t.min_requerido.items():
        if minimo <= 0:
            continue
        disponiveis = sorted(por_nivel.get(nivel, []))
        if len(disponiveis) < minimo:
            return []
        obrigatorios.append(list(itertools.combinations(disponiveis, minimo)))

    grupos: List[Tuple[str, ...]] = []
    for combinacao in itertools.product(*obrigatorios) if obrigatorios else [()]:
        base = tuple(sorted(itertools.chain.from_iterable(combinacao)))
        grupos.append(base)
        restantes = sorted(
            a.id for a in inst.candidatos[t.id] if a.id not in set(base)
        )
        for k in range(1, extras_max + 1):
            for extra in itertools.combinations(restantes, k):
                grupos.append(tuple(sorted(base + extra)))
    return grupos


def enumerar_solucoes(
    inst: Instancia,
    extras_max: int = 0,
    limite: int = 200_000,
    exigir_repouso_semanal: bool = True,
) -> Tuple[List[Tuple[Dict[str, float], Tuple[Tuple[str, str], ...]]], bool]:
    """Busca exaustiva sobre o espaço de soluções factíveis (instâncias pequenas)."""
    escala = Escala(inst)
    solucoes: List[Tuple[Dict[str, float], Tuple[Tuple[str, str], ...]]] = []
    grupos_por_turno = {
        t.id: _grupos_viaveis(inst, t, extras_max) for t in inst.turnos
    }
    estourou = False

    def dfs(indice: int) -> None:
        nonlocal estourou
        if estourou:
            return
        if len(solucoes) >= limite:
            estourou = True
            return
        if indice == len(inst.turnos):
            solucoes.append(
                (escala.componentes(), tuple(sorted(escala.itens())))
            )
            return
        t = inst.turnos[indice]
        for grupo in grupos_por_turno[t.id]:
            aplicados: List[str] = []
            viavel = True
            for id_a in grupo:
                a = inst.analista(id_a)
                if pode_alocar(inst, escala, a, t, exigir_repouso_semanal):
                    escala.alocar(id_a, t.id)
                    aplicados.append(id_a)
                else:
                    viavel = False
                    break
            if viavel:
                dfs(indice + 1)
            for id_a in aplicados:
                escala.desalocar(id_a, t.id)

    dfs(0)
    return solucoes, estourou


def gap_otimalidade(
    inst: Instancia,
    resultado: ResultadoPipeline,
    extras_max: int = 0,
    limite: int = 200_000,
    exigir_repouso_semanal: bool = True,
) -> Dict[str, object]:
    """Métrica 5.1(c) — afastamento entre a solução heurística e a referência.

    Ambas as soluções são avaliadas sob um mesmo normalizador, construído sobre
    o conjunto enumerado acrescido da solução do motor: comparar custos
    normalizados por escalas distintas não teria significado.

    Duas ressalvas condicionam a leitura do resultado e são devolvidas de forma
    explícita no relatório, em vez de ficarem implícitas:

    1. **Exaustividade.** A enumeração interrompe ao atingir ``limite``. Quando
       isso ocorre, a referência deixa de ser o ótimo global e passa a ser
       apenas a melhor solução encontrada em um prefixo da árvore de busca.
       Como o ótimo verdadeiro é menor ou igual a essa referência, o gap
       calculado é um **limite inferior** do gap real — isto é, o número
       subestima o afastamento. Nesse caso nenhuma afirmação de otimalidade é
       emitida.

    2. **Compatibilidade dos espaços.** O gap só mede qualidade de busca se o
       motor puder, em princípio, alcançar qualquer solução enumerada. Com
       ``extras_max`` acima de zero a enumeração admite alocações excedentes que
       o motor em cardinalidade fixa não consegue produzir, e a comparação
       passa a medir uma diferença estrutural. O relatório informa as
       cardinalidades de ambos os lados para que a incompatibilidade seja
       visível.
    """
    solucoes, estourou = enumerar_solucoes(
        inst, extras_max, limite, exigir_repouso_semanal
    )
    if not solucoes:
        return {"erro": "nenhuma solução factível enumerada", "limite_atingido": estourou}

    normalizador = Normalizador()
    for componentes, _ in solucoes:
        normalizador.observar(componentes)
    componentes_motor = resultado.escala.componentes()
    normalizador.observar(componentes_motor)
    normalizador.congelar()

    fo = FuncaoObjetivo(resultado.fo.pesos, normalizador)

    custos = []
    for componentes, alocacoes in solucoes:
        n = normalizador.normalizar(componentes)
        custo = (
            fo.pesos.alpha * n["balanceamento"]
            + fo.pesos.delta * n["senioridade"]
            + fo.pesos.lam * n["atendimento"]
        )
        custos.append((custo, alocacoes))

    custo_otimo, _ = min(custos, key=lambda x: x[0])
    n_motor = normalizador.normalizar(componentes_motor)
    custo_motor = (
        fo.pesos.alpha * n_motor["balanceamento"]
        + fo.pesos.delta * n_motor["senioridade"]
        + fo.pesos.lam * n_motor["atendimento"]
    )

    gap_abs = custo_motor - custo_otimo
    gap_rel = (gap_abs / custo_otimo * 100.0) if custo_otimo > 0 else float("inf")

    exaustiva = not estourou

    cardinalidade_motor = resultado.escala.total_alocacoes()
    cardinalidades = [len(alocacoes) for _, alocacoes in solucoes]
    espacos_compativeis = (
        min(cardinalidades) <= cardinalidade_motor <= max(cardinalidades)
        and extras_max == 0
    )

    ressalvas: List[str] = []
    if not exaustiva:
        ressalvas.append(
            f"Enumeração truncada em {limite} soluções: a referência é a melhor "
            "solução conhecida, não o ótimo global. O gap informado é limite "
            "INFERIOR do gap real."
        )
    if not espacos_compativeis:
        ressalvas.append(
            f"Espaços de busca distintos: o motor produziu {cardinalidade_motor} "
            f"alocações e a enumeração percorre de {min(cardinalidades)} a "
            f"{max(cardinalidades)}. Parte do gap pode ser estrutural, e não "
            "deficiência da heurística. Use extras_max=0 para igualá-los."
        )

    relatorio: Dict[str, object] = {
        "solucoes_enumeradas": len(solucoes),
        "enumeracao_exaustiva": exaustiva,
        "limite_atingido": estourou,
        "referencia": (
            "ótimo global (enumeração exaustiva)"
            if exaustiva
            else "melhor solução conhecida (enumeração truncada)"
        ),
        "custo_referencia": custo_otimo,
        "custo_motor": custo_motor,
        "gap_absoluto": gap_abs,
        "gap_percentual": gap_rel,
        "cardinalidade_motor": cardinalidade_motor,
        "cardinalidade_enumerada_min": min(cardinalidades),
        "cardinalidade_enumerada_max": max(cardinalidades),
        "espacos_compativeis": espacos_compativeis,
        "ressalvas": ressalvas,
    }

    # A afirmação de otimalidade só é emitida quando há lastro para ela.
    if exaustiva and espacos_compativeis:
        relatorio["motor_atingiu_otimo"] = gap_abs <= 1e-9
    else:
        relatorio["motor_atingiu_otimo"] = None

    # Mantido por compatibilidade com consumidores anteriores do relatório.
    relatorio["custo_otimo"] = custo_otimo

    return relatorio


# ---------------------------------------------------------------------------
# (d) Curva de convergência
# ---------------------------------------------------------------------------


def curva_convergencia(rel: RelatorioSA) -> List[Dict[str, float]]:
    """Métrica 5.1(d) — evolução de F(X) ao longo das iterações do SA."""
    return [
        {
            "iteracao": r.iteracao,
            "temperatura": r.temperatura,
            "custo_atual": r.custo_atual,
            "custo_melhor": r.custo_melhor,
            "aceitos_acumulados": r.aceitos,
            "aceitos_piores_acumulados": r.aceitos_piores,
        }
        for r in rel.curva
    ]


# ---------------------------------------------------------------------------
# (e) Sensibilidade aos pesos estruturais
# ---------------------------------------------------------------------------


def grade_de_pesos(passo: float = 0.1) -> List[Pesos]:
    """Malha sobre o simplex α + δ + λ = 1."""
    n = int(round(1.0 / passo))
    combinacoes: List[Pesos] = []
    for i in range(n + 1):
        for j in range(n + 1 - i):
            k = n - i - j
            combinacoes.append(Pesos(i / n, j / n, k / n))
    return combinacoes


def analise_sensibilidade(
    inst: Instancia,
    passo: float = 0.25,
    seed: int = 42,
    params_sa: Optional[ParametrosSA] = None,
    referencia: Optional[Pesos] = None,
) -> List[Dict[str, object]]:
    """Métrica 5.1(e) — robustez da solução frente à repriorização gerencial."""
    params_sa = params_sa or ParametrosSA(
        iteracoes=4_000, iteracoes_aquecimento=600, max_iteracoes_sem_melhoria=1_500
    )
    referencia = referencia or Pesos()
    base = executar(inst, referencia, seed=seed, params_sa=params_sa)

    linhas: List[Dict[str, object]] = []
    for pesos in grade_de_pesos(passo):
        resultado = executar(inst, pesos, seed=seed, params_sa=params_sa)
        flex = violacoes_flexiveis(inst, resultado.escala)
        linhas.append(
            {
                "alpha": round(pesos.alpha, 4),
                "delta": round(pesos.delta, 4),
                "lambda": round(pesos.lam, 4),
                "custo_F": resultado.custo_final(),
                "f_balanceamento": resultado.escala.f_balanceamento,
                "f_senioridade": resultado.escala.f_senioridade,
                "f_atendimento": resultado.escala.f_atendimento,
                "taxa_desequilibrio": flex["taxa_desequilibrio"],
                "taxa_superqualificacao": flex["taxa_superqualificacao"],
                "violacoes_rigidas": len(validar(inst, resultado.escala)),
                "distancia_hamming_ref": resultado.escala.distancia_hamming(base.escala),
                "tempo_s": round(resultado.tempo_total_s, 3),
            }
        )
    return linhas


# ---------------------------------------------------------------------------
# Desempenho computacional (objetivo específico "d")
# ---------------------------------------------------------------------------


@dataclass
class MedicaoDesempenho:
    dias: int
    analistas: int
    turnos: int
    tempo_s: float
    memoria_pico_mb: float
    custo_final: float
    violacoes_rigidas: int


def benchmark(
    tamanhos_em_dias: Sequence[int] = (7, 14, 28, 56),
    seed: int = 42,
    params_sa: Optional[ParametrosSA] = None,
    fator_volume: float = 1.0,
) -> List[MedicaoDesempenho]:
    """Simulação de estresse com cargas crescentes de dados."""
    from .gerador import gerar_instancia

    params_sa = params_sa or ParametrosSA(
        iteracoes=8_000, iteracoes_aquecimento=800, max_iteracoes_sem_melhoria=3_000
    )
    medicoes: List[MedicaoDesempenho] = []
    for dias in tamanhos_em_dias:
        inst = gerar_instancia(dias=dias, seed=seed, fator_volume=fator_volume)
        tracemalloc.start()
        inicio = time.perf_counter()
        resultado = executar(inst, seed=seed, params_sa=params_sa)
        tempo = time.perf_counter() - inicio
        _, pico = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        medicoes.append(
            MedicaoDesempenho(
                dias=dias,
                analistas=len(inst.analistas),
                turnos=len(inst.turnos),
                tempo_s=tempo,
                memoria_pico_mb=pico / (1024 * 1024),
                custo_final=resultado.custo_final(),
                violacoes_rigidas=len(validar(inst, resultado.escala)),
            )
        )
    return medicoes
