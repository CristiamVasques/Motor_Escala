"""
Estrutura de vizinhança do espaço de busca.

Os movimentos definidos aqui são compartilhados pelo Hill Climbing
(Subseção 6.1.3) e pelo Simulated Annealing (Subseção 6.1.4). Todos preservam
o particionamento por turno fixo (Equação 6.2): trocas e realocações só
ocorrem entre analistas da mesma equipe contratual.

A aplicação é sempre tentativa: o movimento é executado, as restrições rígidas
afetadas são verificadas e, em caso de inviabilidade, a escala é restaurada ao
estado anterior. Com isso a busca permanece integralmente dentro do espaço
factível, e o estágio de CSP atua como verificação final e mecanismo de reparo.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .dominio import Instancia, Nivel, TipoTurno
from .escala import Escala
from .restricoes import pode_alocar

Par = Tuple[str, str]  # (id_analista, id_turno)


@dataclass
class Movimento:
    """Perturbação elementar sobre a matriz X."""

    tipo: str
    remocoes: List[Par] = field(default_factory=list)
    adicoes: List[Par] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - conveniência
        rem = ", ".join(f"-{a}@{t}" for a, t in self.remocoes)
        ad = ", ".join(f"+{a}@{t}" for a, t in self.adicoes)
        return f"{self.tipo}({rem}{'; ' if rem and ad else ''}{ad})"


def aplicar(escala: Escala, mov: Movimento) -> None:
    for a, t in mov.remocoes:
        escala.desalocar(a, t)
    for a, t in mov.adicoes:
        escala.alocar(a, t)


def reverter(escala: Escala, mov: Movimento) -> None:
    for a, t in mov.adicoes:
        escala.desalocar(a, t)
    for a, t in mov.remocoes:
        escala.alocar(a, t)


def demanda_atendida(inst: Instancia, escala: Escala, id_turno: str) -> bool:
    t = inst.turno(id_turno)
    contagem = escala.contagem_niveis(id_turno)
    return all(contagem.get(n, 0) >= m for n, m in t.min_requerido.items())


def aplicar_se_factivel(
    inst: Instancia,
    escala: Escala,
    mov: Movimento,
    exigir_repouso_semanal: bool = True,
) -> bool:
    """Aplica o movimento apenas se a escala resultante continuar factível."""
    for a, t in mov.remocoes:
        escala.desalocar(a, t)

    aplicadas: List[Par] = []
    for id_a, id_t in mov.adicoes:
        a = inst.analista(id_a)
        t = inst.turno(id_t)
        if not pode_alocar(inst, escala, a, t, exigir_repouso_semanal):
            for ia, it in aplicadas:
                escala.desalocar(ia, it)
            for ia, it in mov.remocoes:
                escala.alocar(ia, it)
            return False
        escala.alocar(id_a, id_t)
        aplicadas.append((id_a, id_t))

    afetados = {t for _, t in mov.remocoes} | {t for _, t in mov.adicoes}
    if not all(demanda_atendida(inst, escala, t) for t in afetados):
        reverter(escala, mov)
        return False
    return True


# ---------------------------------------------------------------------------
# Geração de movimentos
# ---------------------------------------------------------------------------


def _turnos_com_alocacao(inst: Instancia, escala: Escala) -> List[str]:
    return [t.id for t in inst.turnos if escala.analistas_em(t.id)]


def gerar_movimento(
    inst: Instancia,
    escala: Escala,
    rng: random.Random,
    cardinalidade_fixa: bool = False,
) -> Optional[Movimento]:
    """Sorteia um movimento candidato (usado pelo Simulated Annealing).

    Em modo de cardinalidade fixa, inclusões e exclusões são suprimidas e o
    número total de alocações permanece constante. O modo é usado no cálculo
    do gap de otimalidade (métrica 5.1c), onde motor e busca exaustiva
    precisam percorrer exatamente o mesmo espaço de soluções para que a
    comparação tenha significado.
    """
    estrategia = rng.random()
    if cardinalidade_fixa:
        if estrategia < 0.40:
            return _troca(inst, escala, rng)
        if estrategia < 0.75:
            return _realocacao(inst, escala, rng)
        return _substituicao(inst, escala, rng)
    if estrategia < 0.35:
        return _troca(inst, escala, rng)
    if estrategia < 0.65:
        return _realocacao(inst, escala, rng)
    if estrategia < 0.85:
        return _substituicao(inst, escala, rng)
    if estrategia < 0.93:
        return _inclusao(inst, escala, rng)
    return _exclusao(inst, escala, rng)


def _troca(inst: Instancia, escala: Escala, rng: random.Random) -> Optional[Movimento]:
    ocupados = _turnos_com_alocacao(inst, escala)
    if len(ocupados) < 2:
        return None
    for _ in range(12):
        id_t1, id_t2 = rng.sample(ocupados, 2)
        t1, t2 = inst.turno(id_t1), inst.turno(id_t2)
        if t1.tipo is not t2.tipo:
            continue
        a1 = rng.choice(sorted(escala.analistas_em(id_t1)))
        a2 = rng.choice(sorted(escala.analistas_em(id_t2)))
        if a1 == a2:
            continue
        if escala.esta_alocado(a1, id_t2) or escala.esta_alocado(a2, id_t1):
            continue
        return Movimento(
            "TROCA",
            remocoes=[(a1, id_t1), (a2, id_t2)],
            adicoes=[(a2, id_t1), (a1, id_t2)],
        )
    return None


def _realocacao(
    inst: Instancia, escala: Escala, rng: random.Random
) -> Optional[Movimento]:
    ocupados = _turnos_com_alocacao(inst, escala)
    if not ocupados:
        return None
    for _ in range(12):
        id_origem = rng.choice(ocupados)
        origem = inst.turno(id_origem)
        candidatos_destino = inst.turnos_por_tipo[origem.tipo]
        if len(candidatos_destino) < 2:
            continue
        destino = rng.choice(candidatos_destino)
        if destino.id == id_origem:
            continue
        a = rng.choice(sorted(escala.analistas_em(id_origem)))
        if escala.esta_alocado(a, destino.id):
            continue
        if inst.analista(a) not in inst.candidatos[destino.id]:
            continue
        return Movimento(
            "REALOCACAO", remocoes=[(a, id_origem)], adicoes=[(a, destino.id)]
        )
    return None


def _substituicao(
    inst: Instancia, escala: Escala, rng: random.Random
) -> Optional[Movimento]:
    ocupados = _turnos_com_alocacao(inst, escala)
    if not ocupados:
        return None
    for _ in range(12):
        id_t = rng.choice(ocupados)
        escalados = escala.analistas_em(id_t)
        disponiveis = [a for a in inst.candidatos[id_t] if a.id not in escalados]
        if not disponiveis:
            continue
        a_out = rng.choice(sorted(escalados))
        a_in = rng.choice(disponiveis)
        return Movimento(
            "SUBSTITUICAO", remocoes=[(a_out, id_t)], adicoes=[(a_in.id, id_t)]
        )
    return None


def _inclusao(
    inst: Instancia, escala: Escala, rng: random.Random
) -> Optional[Movimento]:
    for _ in range(12):
        t = rng.choice(inst.turnos)
        escalados = escala.analistas_em(t.id)
        disponiveis = [a for a in inst.candidatos[t.id] if a.id not in escalados]
        if not disponiveis:
            continue
        return Movimento("INCLUSAO", adicoes=[(rng.choice(disponiveis).id, t.id)])
    return None


def _exclusao(
    inst: Instancia, escala: Escala, rng: random.Random
) -> Optional[Movimento]:
    ocupados = _turnos_com_alocacao(inst, escala)
    if not ocupados:
        return None
    for _ in range(12):
        id_t = rng.choice(ocupados)
        a = rng.choice(sorted(escala.analistas_em(id_t)))
        return Movimento("EXCLUSAO", remocoes=[(a, id_t)])
    return None


def gerar_vizinhanca(
    inst: Instancia,
    escala: Escala,
    rng: random.Random,
    limite: int = 240,
    cardinalidade_fixa: bool = False,
) -> List[Movimento]:
    """Amostra determinística (dado o seed) da vizinhança da solução corrente.

    O limite existe porque a vizinhança completa cresce com |A|²·|T|²: uma
    vizinhança ampla demais eleva o custo de avaliar cada movimento sem ganho
    proporcional de qualidade.
    """
    movimentos: List[Movimento] = []
    tentativas = 0
    geradores = (
        (_troca, _realocacao, _substituicao)
        if cardinalidade_fixa
        else (_troca, _realocacao, _substituicao, _inclusao, _exclusao)
    )
    while len(movimentos) < limite and tentativas < limite * 4:
        gerador = geradores[tentativas % len(geradores)]
        mov = gerador(inst, escala, rng)
        if mov is not None:
            movimentos.append(mov)
        tentativas += 1
    return movimentos
