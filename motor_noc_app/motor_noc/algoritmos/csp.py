"""
Estágio 4 do pipeline — CSP com Backtracking (Subseções 6.1.5 e 6.1.6).

O paradigma CSP é aplicado aqui como garantia final de consistência: a escala
produzida pelos estágios heurísticos é varrida e, havendo violação de
restrição rígida, o Backtracking atua para restaurar a validade da solução.

O modelo é o triplo (X, D, C):
  X — slots em déficit de demanda mínima (turno, nível);
  D — analistas da equipe fixa correspondente, com competência compatível;
  C — o conjunto de restrições rígidas da Seção 6.5.

Aplicar o Backtracking apenas sobre uma solução já refinada, e não desde o
início do escalonamento, reduz drasticamente o esforço computacional: em vez
de varrer exaustivamente todo o espaço de soluções, o algoritmo age somente
onde há de fato uma inconsistência a corrigir.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ..dominio import Analista, Instancia, Nivel, Turno
from ..escala import Escala
from ..restricoes import Violacao, pode_alocar, validar

Slot = Tuple[str, Nivel]  # (id_turno, nível exigido)


@dataclass
class RelatorioCSP:
    violacoes_iniciais: List[str] = field(default_factory=list)
    violacoes_finais: List[str] = field(default_factory=list)
    alocacoes_removidas: List[str] = field(default_factory=list)
    slots_em_deficit: int = 0
    slots_preenchidos: int = 0
    nos_explorados: int = 0
    limite_atingido: bool = False

    @property
    def escala_valida(self) -> bool:
        return not self.violacoes_finais


def _sanear_restricoes_individuais(
    inst: Instancia,
    escala: Escala,
    rel: RelatorioCSP,
    exigir_repouso_semanal: bool,
) -> None:
    """Remove alocações que violem restrições rígidas de âmbito individual.

    Cada analista tem sua agenda reconstruída incrementalmente: as alocações
    são reinseridas em ordem de criticidade e aquelas que não passam na
    verificação são descartadas. Prioriza-se manter as alocações que sustentam
    a demanda mínima de seus turnos.
    """
    for a in inst.analistas:
        atuais = list(escala.turnos_ordenados_de(a.id))
        if not atuais:
            continue

        def criticidade(t: Turno) -> tuple:
            contagem = escala.contagem_niveis(t.id)
            apertado = contagem.get(a.nivel, 0) <= t.min_requerido.get(a.nivel, 0)
            return (0 if apertado else 1, t.inicio)

        ordenados = sorted(atuais, key=criticidade)

        for t in atuais:
            escala.desalocar(a.id, t.id)

        for t in ordenados:
            if pode_alocar(inst, escala, a, t, exigir_repouso_semanal):
                escala.alocar(a.id, t.id)
            else:
                rel.alocacoes_removidas.append(
                    f"{a.id} removido de {t.id} ({t.inicio:%d/%m %H:%M})"
                )


def _levantar_deficits(inst: Instancia, escala: Escala) -> List[Slot]:
    slots: List[Slot] = []
    for t in inst.turnos:
        contagem = escala.contagem_niveis(t.id)
        for nivel, minimo in t.min_requerido.items():
            faltam = minimo - contagem.get(nivel, 0)
            for _ in range(max(0, faltam)):
                slots.append((t.id, nivel))
    return slots


def _dominio(
    inst: Instancia,
    escala: Escala,
    slot: Slot,
    exigir_repouso_semanal: bool,
) -> List[Analista]:
    id_turno, nivel = slot
    t = inst.turno(id_turno)
    escalados = escala.analistas_em(id_turno)
    aptos = [
        a
        for a in inst.candidatos[id_turno]
        if a.nivel is nivel
        and a.id not in escalados
        and pode_alocar(inst, escala, a, t, exigir_repouso_semanal)
    ]
    # Heurística de valor: menor carga acumulada primeiro, favorecendo a
    # equidade interna já no reparo.
    aptos.sort(key=lambda a: (escala.horas_reais[a.id], a.id))
    return aptos


def _backtracking(
    inst: Instancia,
    escala: Escala,
    pendentes: List[Slot],
    rel: RelatorioCSP,
    max_nos: int,
    exigir_repouso_semanal: bool,
) -> bool:
    """Busca com retrocesso e heurística MRV (menor domínio restante)."""
    if not pendentes:
        return True
    if rel.nos_explorados >= max_nos:
        rel.limite_atingido = True
        return False

    # MRV: seleciona o slot com menor número de candidatos viáveis.
    dominios = {
        i: _dominio(inst, escala, slot, exigir_repouso_semanal)
        for i, slot in enumerate(pendentes)
    }
    indice = min(dominios, key=lambda i: len(dominios[i]))
    slot = pendentes[indice]
    candidatos = dominios[indice]

    if not candidatos:
        return False  # poda antecipada: ramo inviável

    restantes = pendentes[:indice] + pendentes[indice + 1 :]

    for a in candidatos:
        rel.nos_explorados += 1
        if rel.nos_explorados >= max_nos:
            rel.limite_atingido = True
            return False
        escala.alocar(a.id, slot[0])
        if _backtracking(
            inst, escala, restantes, rel, max_nos, exigir_repouso_semanal
        ):
            return True
        escala.desalocar(a.id, slot[0])  # retrocesso

    return False


def _tem_folga(inst: Instancia, escala: Escala, id_turno: str, nivel: Nivel) -> bool:
    """Indica se remover um analista do nível não descumpre a demanda mínima."""
    t = inst.turno(id_turno)
    return escala.contagem_niveis(id_turno).get(nivel, 0) > t.min_requerido.get(nivel, 0)


def _reparo_dirigido_por_conflito(
    inst: Instancia, escala: Escala, slot: Slot, exigir_repouso_semanal: bool
) -> bool:
    """Libera um candidato bloqueado, removendo alocação com folga.

    Quando o domínio de um slot está vazio, o impedimento em geral não é a
    ausência de pessoal, e sim o bloqueio de todos os candidatos por alocações
    já feitas — tipicamente pela folga cascata ou pelo turno único diário.
    Desfazer seletivamente uma alocação excedente de outro turno costuma ser
    suficiente para tornar o slot preenchível, sem comprometer aquele turno.
    """
    id_turno, nivel = slot
    t = inst.turno(id_turno)
    escalados = escala.analistas_em(id_turno)

    for a in inst.candidatos[id_turno]:
        if a.nivel is not nivel or a.id in escalados:
            continue
        conflitos = sorted(
            escala.turnos_de(a.id),
            key=lambda tid: inst.turno(tid).inicio,
        )
        for id_conflito in conflitos:
            if not _tem_folga(inst, escala, id_conflito, a.nivel):
                continue
            escala.desalocar(a.id, id_conflito)
            if pode_alocar(inst, escala, a, t, exigir_repouso_semanal):
                escala.alocar(a.id, id_turno)
                return True
            escala.alocar(a.id, id_conflito)  # restaura o estado anterior
    return False


def _preenchimento_parcial(
    inst: Instancia, escala: Escala, exigir_repouso_semanal: bool
) -> None:
    """Preenche gulosamente os déficits ainda resolvíveis, um a um."""
    progrediu = True
    while progrediu:
        progrediu = False
        for slot in _levantar_deficits(inst, escala):
            candidatos = _dominio(inst, escala, slot, exigir_repouso_semanal)
            if candidatos:
                escala.alocar(candidatos[0].id, slot[0])
                progrediu = True
            elif _reparo_dirigido_por_conflito(
                inst, escala, slot, exigir_repouso_semanal
            ):
                progrediu = True


def validar_e_reparar(
    inst: Instancia,
    escala: Escala,
    max_nos: int = 200_000,
    exigir_repouso_semanal: bool = True,
) -> RelatorioCSP:
    """Valida a escala e, se necessário, repara por Backtracking (in loco)."""
    rel = RelatorioCSP()
    rel.violacoes_iniciais = [str(v) for v in validar(inst, escala, exigir_repouso_semanal)]

    _sanear_restricoes_individuais(inst, escala, rel, exigir_repouso_semanal)

    pendentes = _levantar_deficits(inst, escala)
    rel.slots_em_deficit = len(pendentes)

    if pendentes:
        antes = escala.total_alocacoes()
        sucesso = _backtracking(
            inst, escala, pendentes, rel, max_nos, exigir_repouso_semanal
        )
        if not sucesso:
            # Nem sempre existe atribuição capaz de zerar o déficit: o quadro
            # de pessoal pode ser insuficiente para a demanda configurada.
            # Nesse caso preenche-se o máximo possível e o déficit residual é
            # reportado à gerência em vez de ser silenciado.
            _preenchimento_parcial(inst, escala, exigir_repouso_semanal)
        rel.slots_preenchidos = escala.total_alocacoes() - antes

    rel.violacoes_finais = [str(v) for v in validar(inst, escala, exigir_repouso_semanal)]
    return rel
