"""
Estágio 3 do pipeline — Simulated Annealing (Subseção 6.1.4).

Inclui a fase de aquecimento (warm-up) prevista na Subseção 6.6.1: uma
amostra de soluções candidatas é percorrida antes do resfriamento efetivo,
com dois propósitos — estimar os limites f_min e f_max de cada componente
para a normalização min-max e calibrar a temperatura inicial a partir da
magnitude observada de ΔF.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..dominio import Instancia
from ..escala import Escala
from ..objetivo import FuncaoObjetivo
from ..vizinhanca import aplicar_se_factivel, gerar_movimento, reverter


@dataclass
class ParametrosSA:
    """Parametrização do recozimento simulado."""

    iteracoes: int = 20_000
    iteracoes_aquecimento: int = 1_500
    taxa_resfriamento: float = 0.95
    iteracoes_por_temperatura: int = 200
    temperatura_minima: float = 1e-6
    #: Alvo de aceitação inicial. Valores usuais na literatura (0,8) supõem o
    #: SA partindo de uma solução aleatória. Aqui ele recebe uma solução já
    #: refinada pelo Hill Climbing: uma temperatura inicial alta desfaria esse
    #: refinamento antes de resfriar, e a busca se degenera em caminhada
    #: aleatória. O valor reduzido posiciona o SA como estágio de
    #: intensificação em torno da solução herdada.
    aceitacao_inicial_alvo: float = 0.15
    intervalo_registro: int = 50
    max_iteracoes_sem_melhoria: int = 8_000
    #: Iterações sem melhoria após as quais a busca retorna à melhor solução
    #: conhecida, evitando que a caminhada se afaste indefinidamente.
    retornar_ao_melhor_apos: int = 1_200


@dataclass
class RegistroConvergencia:
    """Ponto da curva de convergência — métrica 5.1(d)."""

    iteracao: int
    temperatura: float
    custo_atual: float
    custo_melhor: float
    aceitos: int
    aceitos_piores: int


@dataclass
class RelatorioSA:
    custo_inicial: float = 0.0
    custo_final: float = 0.0
    temperatura_inicial: float = 0.0
    iteracoes_executadas: int = 0
    movimentos_avaliados: int = 0
    movimentos_aceitos: int = 0
    movimentos_piores_aceitos: int = 0
    parou_por: str = ""
    retornos_ao_melhor: int = 0
    curva: List[RegistroConvergencia] = field(default_factory=list)
    limites_normalizacao: Dict[str, Tuple[float, float]] = field(default_factory=dict)

    @property
    def ganho(self) -> float:
        return self.custo_inicial - self.custo_final

    @property
    def taxa_aceitacao(self) -> float:
        return (
            self.movimentos_aceitos / self.movimentos_avaliados
            if self.movimentos_avaliados
            else 0.0
        )


def aquecer(
    inst: Instancia,
    escala: Escala,
    fo: FuncaoObjetivo,
    rng: random.Random,
    iteracoes: int,
    exigir_repouso_semanal: bool = True,
    cardinalidade_fixa: bool = False,
) -> None:
    """Percorre uma amostra de soluções vizinhas e congela os limites min-max.

    A caminhada é feita sobre uma cópia da escala: as amostras servem apenas
    para estimar a faixa de variação de cada componente, e não devem
    degradar a solução herdada do Hill Climbing.
    """
    if fo.normalizador.congelado:
        return

    amostra = escala.copiar()
    fo.normalizador.observar(amostra.componentes())
    for _ in range(iteracoes):
        mov = gerar_movimento(inst, amostra, rng, cardinalidade_fixa)
        if mov is None:
            continue
        if aplicar_se_factivel(inst, amostra, mov, exigir_repouso_semanal):
            fo.normalizador.observar(amostra.componentes())

    fo.normalizador.observar(escala.componentes())
    fo.normalizador.congelar()


def _calibrar_temperatura(
    inst: Instancia,
    escala: Escala,
    fo: FuncaoObjetivo,
    rng: random.Random,
    alvo: float,
    amostras: int = 200,
    exigir_repouso_semanal: bool = True,
    cardinalidade_fixa: bool = False,
) -> float:
    """T0 tal que uma piora média seja aceita com probabilidade ``alvo``."""
    custo_base = fo.custo(escala)
    pioras: List[float] = []
    trabalho = escala.copiar()
    for _ in range(amostras):
        mov = gerar_movimento(inst, trabalho, rng, cardinalidade_fixa)
        if mov is None:
            continue
        if not aplicar_se_factivel(inst, trabalho, mov, exigir_repouso_semanal):
            continue
        delta = fo.custo(trabalho) - custo_base
        reverter(trabalho, mov)
        if delta > 0:
            pioras.append(delta)

    if not pioras:
        return 1e-3
    media = sum(pioras) / len(pioras)
    return max(-media / math.log(alvo), 1e-9)


def otimizar(
    inst: Instancia,
    escala: Escala,
    fo: FuncaoObjetivo,
    rng: Optional[random.Random] = None,
    params: Optional[ParametrosSA] = None,
    exigir_repouso_semanal: bool = True,
    cardinalidade_fixa: bool = False,
) -> Tuple[Escala, RelatorioSA]:
    """Executa o recozimento simulado e devolve a melhor escala encontrada."""
    rng = rng or random.Random(0)
    params = params or ParametrosSA()
    rel = RelatorioSA()

    aquecer(
        inst,
        escala,
        fo,
        rng,
        params.iteracoes_aquecimento,
        exigir_repouso_semanal,
        cardinalidade_fixa,
    )
    rel.limites_normalizacao = fo.normalizador.limites()

    temperatura = _calibrar_temperatura(
        inst,
        escala,
        fo,
        rng,
        params.aceitacao_inicial_alvo,
        exigir_repouso_semanal=exigir_repouso_semanal,
        cardinalidade_fixa=cardinalidade_fixa,
    )
    rel.temperatura_inicial = temperatura

    atual = escala
    custo_atual = fo.custo(atual)
    rel.custo_inicial = custo_atual

    melhor = atual.copiar()
    custo_melhor = custo_atual
    iteracoes_sem_melhoria = 0
    desde_ultimo_retorno = 0
    rel.retornos_ao_melhor = 0

    for i in range(1, params.iteracoes + 1):
        rel.iteracoes_executadas = i

        if (
            params.retornar_ao_melhor_apos
            and desde_ultimo_retorno >= params.retornar_ao_melhor_apos
        ):
            atual = melhor.copiar()
            custo_atual = custo_melhor
            desde_ultimo_retorno = 0
            rel.retornos_ao_melhor += 1

        if i % params.iteracoes_por_temperatura == 0:
            temperatura *= params.taxa_resfriamento

        if temperatura < params.temperatura_minima:
            rel.parou_por = "temperatura mínima atingida"
            break
        if iteracoes_sem_melhoria >= params.max_iteracoes_sem_melhoria:
            rel.parou_por = "estagnação da melhor solução"
            break

        mov = gerar_movimento(inst, atual, rng, cardinalidade_fixa)
        if mov is None:
            continue
        if not aplicar_se_factivel(inst, atual, mov, exigir_repouso_semanal):
            continue

        rel.movimentos_avaliados += 1
        custo_novo = fo.custo(atual)
        delta = custo_novo - custo_atual

        if delta <= 0:
            aceito = True
        else:
            aceito = rng.random() < math.exp(-delta / temperatura)
            if aceito:
                rel.movimentos_piores_aceitos += 1

        if aceito:
            custo_atual = custo_novo
            rel.movimentos_aceitos += 1
            if custo_atual < custo_melhor - 1e-12:
                custo_melhor = custo_atual
                melhor = atual.copiar()
                iteracoes_sem_melhoria = 0
                desde_ultimo_retorno = 0
            else:
                iteracoes_sem_melhoria += 1
                desde_ultimo_retorno += 1
        else:
            reverter(atual, mov)
            iteracoes_sem_melhoria += 1
            desde_ultimo_retorno += 1

        if i % params.intervalo_registro == 0:
            rel.curva.append(
                RegistroConvergencia(
                    iteracao=i,
                    temperatura=temperatura,
                    custo_atual=custo_atual,
                    custo_melhor=custo_melhor,
                    aceitos=rel.movimentos_aceitos,
                    aceitos_piores=rel.movimentos_piores_aceitos,
                )
            )

    if not rel.parou_por:
        rel.parou_por = "número máximo de iterações"
    rel.custo_final = custo_melhor
    return melhor, rel
