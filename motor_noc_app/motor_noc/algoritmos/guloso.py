"""
Estágio 1 do pipeline — construção gulosa (Subseção 6.1.1).

O algoritmo guloso não otimiza a escala em definitivo: sua função é abrir o
pipeline com uma primeira solução factível, respeitando as restrições
operacionais mais imediatas, sobre a qual os estágios seguintes atuam.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Tuple

from ..dominio import Analista, Instancia, Nivel, Turno
from ..escala import Escala
from ..restricoes import pode_alocar


def _ordem_de_atendimento(inst: Instancia) -> List[Turno]:
    """Turnos de fim de semana primeiro, depois por demanda e cronologia.

    A ordem não é indiferente: um plantão de fim de semana bloqueia a sexta
    anterior e a terça subsequente do analista (Equação 6.6). Preencher
    primeiro os turnos mais restritos reduz a chance de o guloso chegar aos
    plantões sem candidatos disponíveis.
    """
    return sorted(
        inst.turnos,
        key=lambda t: (0 if t.eh_fim_de_semana else 1, -t.demanda_total, t.inicio),
    )


def _escolher(
    inst: Instancia,
    escala: Escala,
    t: Turno,
    nivel: Nivel,
    rng: random.Random,
    exigir_repouso_semanal: bool,
) -> Optional[Analista]:
    """Seleciona o analista de menor carga acumulada apto ao slot."""
    escalados = escala.analistas_em(t.id)
    aptos = [
        a
        for a in inst.candidatos[t.id]
        if a.nivel is nivel
        and a.id not in escalados
        and pode_alocar(inst, escala, a, t, exigir_repouso_semanal)
    ]
    if not aptos:
        return None
    # Critério guloso: menor carga horária acumulada (favorece a equidade
    # interna já na construção), com desempate determinístico pelo id.
    aptos.sort(key=lambda a: (escala.horas_reais[a.id], a.id))
    return aptos[0]


def _completar_capacidade(
    inst: Instancia,
    escala: Escala,
    t: Turno,
    rng: random.Random,
    exigir_repouso_semanal: bool,
) -> None:
    """Ajusta a vazão do turno ao volume de alertas previsto (Equação 6.14)."""
    escalados = escala.analistas_em(t.id)
    capacidade = sum(inst.analista(a).capacidade_atendimento for a in escalados)
    while capacidade < t.volume_alertas:
        aptos = [
            a
            for a in inst.candidatos[t.id]
            if a.id not in escala.analistas_em(t.id)
            and pode_alocar(inst, escala, a, t, exigir_repouso_semanal)
        ]
        if not aptos:
            return
        # Preferência por nível mais baixo suficiente, preservando o recurso
        # sênior para a janela comercial (Subseção 6.5.2.2).
        penaliza = t.eh_fim_de_semana and t.exige_apenas_n1
        aptos.sort(
            key=lambda a: (
                1 if (penaliza and a.nivel is not Nivel.N1) else 0,
                escala.horas_reais[a.id],
                a.id,
            )
        )
        escolhido = aptos[0]
        folga_atual = abs(t.volume_alertas - capacidade)
        folga_nova = abs(
            t.volume_alertas - (capacidade + escolhido.capacidade_atendimento)
        )
        if folga_nova >= folga_atual:
            return
        escala.alocar(escolhido.id, t.id)
        capacidade += escolhido.capacidade_atendimento


def construir(
    inst: Instancia,
    rng: Optional[random.Random] = None,
    ajustar_capacidade: bool = True,
    exigir_repouso_semanal: bool = True,
) -> Tuple[Escala, List[str]]:
    """Constrói a escala inicial factível.

    Retorna a escala e a lista de déficits de demanda que o guloso não
    conseguiu preencher — insumo direto para o estágio de CSP.
    """
    rng = rng or random.Random(0)
    escala = Escala(inst)
    deficits: List[str] = []

    # Passe 1 — demanda mínima obrigatória de todos os turnos.
    #
    # A separação em dois passes não é cosmética: se o ajuste de capacidade
    # fosse feito turno a turno junto com a demanda mínima, as inclusões
    # discricionárias dos primeiros turnos consumiriam a disponibilidade dos
    # analistas (turno único diário, repouso semanal) e inviabilizariam
    # slots obrigatórios de turnos posteriores.
    for t in _ordem_de_atendimento(inst):
        for nivel in (Nivel.N3, Nivel.N2, Nivel.N1):
            faltam = t.min_requerido.get(nivel, 0)
            while escala.contagem_niveis(t.id)[nivel] < faltam:
                escolhido = _escolher(inst, escala, t, nivel, rng, exigir_repouso_semanal)
                if escolhido is None:
                    deficits.append(
                        f"Turno {t.id} ({t.inicio:%d/%m %H:%M}): sem candidato "
                        f"{nivel.value} disponível."
                    )
                    break
                escala.alocar(escolhido.id, t.id)

    # Passe 2 — ajuste discricionário da vazão ao volume de alertas.
    if ajustar_capacidade:
        for t in sorted(
            inst.turnos, key=lambda x: (-x.volume_alertas, x.inicio)
        ):
            _completar_capacidade(inst, escala, t, rng, exigir_repouso_semanal)

    return escala, deficits
