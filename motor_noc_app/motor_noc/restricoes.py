"""
Mapeamento das restrições do modelo (Seção 6.5 do TCC).

As restrições rígidas são verificadas de forma incremental por
``pode_alocar`` — usada por todos os estágios do pipeline para manter a busca
dentro do espaço factível — e de forma global por ``validar``, que produz o
laudo completo usado pelo estágio de CSP.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Set

from .dominio import (
    INTERJORNADA_MINIMA_HORAS,
    TETO_SEMANAL_HORAS,
    Analista,
    Instancia,
    Nivel,
    Turno,
)
from .escala import Escala


@dataclass(frozen=True)
class Violacao:
    """Registro de descumprimento de uma restrição rígida."""

    tipo: str
    descricao: str
    id_turno: Optional[str] = None
    id_analista: Optional[str] = None

    def __str__(self) -> str:  # pragma: no cover - conveniência
        return f"[{self.tipo}] {self.descricao}"


# ---------------------------------------------------------------------------
# Auxiliares de calendário (regra de folga cascata, Equação 6.6)
# ---------------------------------------------------------------------------


def sexta_anterior(dia_fds: date) -> date:
    """Sexta-feira que antecede o fim de semana do dia informado."""
    return dia_fds - timedelta(days=dia_fds.weekday() - 4)


def terca_seguinte(dia_fds: date) -> date:
    """Terça-feira subsequente ao fim de semana do dia informado."""
    return dia_fds + timedelta(days=8 - dia_fds.weekday())


def fds_apos_sexta(dia_sexta: date) -> List[date]:
    return [dia_sexta + timedelta(days=1), dia_sexta + timedelta(days=2)]


def fds_antes_terca(dia_terca: date) -> List[date]:
    return [dia_terca - timedelta(days=3), dia_terca - timedelta(days=2)]


# ---------------------------------------------------------------------------
# Verificação incremental
# ---------------------------------------------------------------------------


def pode_alocar(
    inst: Instancia,
    escala: Escala,
    a: Analista,
    t: Turno,
    exigir_repouso_semanal: bool = True,
) -> bool:
    """Retorna True se X_{a,t} = 1 preserva todas as restrições rígidas.

    A restrição de demanda mínima (Equação 6.3) não é verificada aqui: ela é
    do tipo ``>=`` e nunca pode ser violada por uma inclusão, apenas por uma
    remoção. Seu tratamento fica em ``validar`` e no estágio de CSP.
    """
    # Equação 6.2 — domínio implícito do turno fixo contratual.
    if a.turno_fixo is not t.tipo:
        return False

    # Subseção 6.5.1.6 — competência técnica obrigatória.
    if not t.competencias_requeridas <= a.competencias:
        return False

    # Subseção 6.5.1.4 — turno único por dia civil.
    if t.dia_civil in escala.dias_ocupados(a.id):
        return False

    if not _cascata_ok(inst, escala, a, t):
        return False
    if not _jornada_semanal_ok(inst, escala, a, t):
        return False
    if not _interjornada_ok(inst, escala, a, t):
        return False
    if exigir_repouso_semanal and not _repouso_semanal_ok(inst, escala, a, t):
        return False
    return True


def _dias_do_analista(escala: Escala, a: Analista, extra: Optional[date] = None) -> Set[date]:
    dias = set(escala.dias_ocupados(a.id))
    if extra is not None:
        dias.add(extra)
    return dias


def _cascata_ok(inst: Instancia, escala: Escala, a: Analista, t: Turno) -> bool:
    """Equação 6.6 — plantão de fim de semana implica folga na sexta anterior
    e na terça subsequente, dentro do turno fixo do analista."""
    ocupados = escala.dias_ocupados(a.id)
    d = t.dia_civil

    if t.eh_fim_de_semana:
        return sexta_anterior(d) not in ocupados and terca_seguinte(d) not in ocupados

    if d.weekday() == 4:  # sexta-feira
        return not any(dia in ocupados for dia in fds_apos_sexta(d))

    if d.weekday() == 1:  # terça-feira
        return not any(dia in ocupados for dia in fds_antes_terca(d))

    return True


def _jornada_semanal_ok(inst: Instancia, escala: Escala, a: Analista, t: Turno) -> bool:
    """Equação 6.4 — teto de 44 horas em qualquer janela de 7 dias.

    A verificação por janela deslizante é mais restritiva que a por semana
    civil e evita o artefato de concentrar jornadas no fim de uma semana e no
    início da seguinte sem violar formalmente o limite.
    """
    turnos = escala.turnos_ordenados_de(a.id) + [t]
    turnos.sort(key=lambda x: x.inicio)
    n = len(turnos)
    for i in range(n):
        limite = turnos[i].inicio + timedelta(days=7)
        soma = 0.0
        for j in range(i, n):
            if turnos[j].inicio >= limite:
                break
            soma += turnos[j].duracao_legal
        if soma > TETO_SEMANAL_HORAS + 1e-9:
            return False
    return True


def _interjornada_ok(inst: Instancia, escala: Escala, a: Analista, t: Turno) -> bool:
    """Equação 6.5 — 11 horas consecutivas entre turnos sucessivos."""
    turnos = escala.turnos_ordenados_de(a.id) + [t]
    turnos.sort(key=lambda x: x.inicio)
    for anterior, proximo in zip(turnos, turnos[1:]):
        folga = (proximo.inicio - anterior.fim).total_seconds() / 3600.0
        if folga < INTERJORNADA_MINIMA_HORAS - 1e-9:
            return False
    return True


def _repouso_semanal_ok(inst: Instancia, escala: Escala, a: Analista, t: Turno) -> bool:
    """Art. 67 da CLT — repouso semanal remunerado.

    Aproximado como a exigência de ao menos um dia civil livre em toda janela
    de 7 dias consecutivos integralmente contida no horizonte de planejamento.
    Sob a premissa de turnos fixos, um dia civil livre garante folga contínua
    superior a 24 horas.
    """
    dias = _dias_do_analista(escala, a, t.dia_civil)
    horizonte = inst.dias
    if not horizonte:
        return True
    primeiro, ultimo = horizonte[0], horizonte[-1]

    inicio_varredura = max(primeiro, t.dia_civil - timedelta(days=6))
    fim_varredura = min(t.dia_civil, ultimo - timedelta(days=6))

    dia = inicio_varredura
    while dia <= fim_varredura:
        janela = [dia + timedelta(days=k) for k in range(7)]
        if all(d in dias for d in janela):
            return False
        dia += timedelta(days=1)
    return True


# ---------------------------------------------------------------------------
# Verificação global
# ---------------------------------------------------------------------------


def validar(
    inst: Instancia, escala: Escala, exigir_repouso_semanal: bool = True
) -> List[Violacao]:
    """Laudo completo de restrições rígidas sobre uma escala já construída."""
    violacoes: List[Violacao] = []

    # Equação 6.3 — demanda mínima por senioridade.
    for t in inst.turnos:
        contagem = escala.contagem_niveis(t.id)
        for nivel, minimo in t.min_requerido.items():
            if contagem.get(nivel, 0) < minimo:
                violacoes.append(
                    Violacao(
                        "DEMANDA_MINIMA",
                        f"Turno {t.id} exige {minimo} analista(s) {nivel.value}, "
                        f"tem {contagem.get(nivel, 0)}.",
                        id_turno=t.id,
                    )
                )

    for a in inst.analistas:
        turnos = escala.turnos_ordenados_de(a.id)

        for t in turnos:
            if a.turno_fixo is not t.tipo:
                violacoes.append(
                    Violacao(
                        "TURNO_FIXO",
                        f"Analista {a.id} ({a.turno_fixo.value}) alocado em turno "
                        f"{t.tipo.value}.",
                        t.id,
                        a.id,
                    )
                )
            if not t.competencias_requeridas <= a.competencias:
                faltantes = sorted(t.competencias_requeridas - a.competencias)
                violacoes.append(
                    Violacao(
                        "COMPETENCIA",
                        f"Analista {a.id} não possui {faltantes} exigida(s) pelo "
                        f"turno {t.id}.",
                        t.id,
                        a.id,
                    )
                )

        # Turno único diário.
        vistos: Dict[date, str] = {}
        for t in turnos:
            if t.dia_civil in vistos:
                violacoes.append(
                    Violacao(
                        "TURNO_UNICO_DIARIO",
                        f"Analista {a.id} escalado em mais de um turno em "
                        f"{t.dia_civil:%d/%m/%Y}.",
                        t.id,
                        a.id,
                    )
                )
            else:
                vistos[t.dia_civil] = t.id

        # Interjornada.
        for anterior, proximo in zip(turnos, turnos[1:]):
            folga = (proximo.inicio - anterior.fim).total_seconds() / 3600.0
            if folga < INTERJORNADA_MINIMA_HORAS - 1e-9:
                violacoes.append(
                    Violacao(
                        "INTERJORNADA",
                        f"Analista {a.id} com apenas {folga:.1f}h entre {anterior.id} "
                        f"e {proximo.id} (mínimo {INTERJORNADA_MINIMA_HORAS:.0f}h).",
                        proximo.id,
                        a.id,
                    )
                )

        # Jornada semanal em janela deslizante.
        n = len(turnos)
        for i in range(n):
            limite = turnos[i].inicio + timedelta(days=7)
            soma = 0.0
            for j in range(i, n):
                if turnos[j].inicio >= limite:
                    break
                soma += turnos[j].duracao_legal
            if soma > TETO_SEMANAL_HORAS + 1e-9:
                violacoes.append(
                    Violacao(
                        "JORNADA_SEMANAL",
                        f"Analista {a.id} acumula {soma:.1f}h legais na janela "
                        f"iniciada em {turnos[i].inicio:%d/%m/%Y} (teto "
                        f"{TETO_SEMANAL_HORAS:.0f}h).",
                        turnos[i].id,
                        a.id,
                    )
                )
                break

        # Folga cascata.
        dias = escala.dias_ocupados(a.id)
        for t in turnos:
            if not t.eh_fim_de_semana:
                continue
            for dia_bloqueado, rotulo in (
                (sexta_anterior(t.dia_civil), "sexta anterior"),
                (terca_seguinte(t.dia_civil), "terça subsequente"),
            ):
                if dia_bloqueado in dias:
                    violacoes.append(
                        Violacao(
                            "FOLGA_CASCATA",
                            f"Analista {a.id} tem plantão em {t.dia_civil:%d/%m} e "
                            f"permanece escalado na {rotulo} "
                            f"({dia_bloqueado:%d/%m}).",
                            t.id,
                            a.id,
                        )
                    )

        # Repouso semanal.
        if exigir_repouso_semanal and dias:
            horizonte = inst.dias
            primeiro, ultimo = horizonte[0], horizonte[-1]
            dia = primeiro
            while dia <= ultimo - timedelta(days=6):
                janela = [dia + timedelta(days=k) for k in range(7)]
                if all(d in dias for d in janela):
                    violacoes.append(
                        Violacao(
                            "REPOUSO_SEMANAL",
                            f"Analista {a.id} sem dia de folga na janela iniciada "
                            f"em {dia:%d/%m/%Y}.",
                            None,
                            a.id,
                        )
                    )
                    break
                dia += timedelta(days=1)

    return violacoes


def eh_factivel(inst: Instancia, escala: Escala, **kwargs) -> bool:
    return not validar(inst, escala, **kwargs)


# ---------------------------------------------------------------------------
# Restrições flexíveis (Subseção 6.5.2) — métrica 5.1(b)
# ---------------------------------------------------------------------------


def violacoes_flexiveis(
    inst: Instancia, escala: Escala, tolerancia_relativa: float = 0.10
) -> Dict[str, float]:
    """Quantifica o descumprimento das restrições flexíveis.

    - Equidade interna: analista cuja carga horária se afasta da média de sua
      equipe fixa além da tolerância relativa informada.
    - Superqualificação: cada alocação de N2/N3 em plantão de fim de semana
      que exige apenas N1.
    """
    desequilibrados = 0
    total_analistas = 0
    for tipo, equipe in inst.equipes.items():
        if not equipe:
            continue
        cargas = [escala.horas_reais[a.id] for a in equipe]
        media = sum(cargas) / len(cargas)
        total_analistas += len(equipe)
        limite = max(tolerancia_relativa * media, 1e-9)
        desequilibrados += sum(1 for h in cargas if abs(h - media) > limite)

    superqualificados = int(escala.f_senioridade)
    alocacoes_fds_n1 = sum(
        len(escala.analistas_em(t.id))
        for t in inst.turnos
        if t.eh_fim_de_semana and t.exige_apenas_n1
    )

    return {
        "analistas_desequilibrados": desequilibrados,
        "total_analistas": total_analistas,
        "taxa_desequilibrio": (
            desequilibrados / total_analistas if total_analistas else 0.0
        ),
        "alocacoes_superqualificadas": superqualificados,
        "alocacoes_fds_apenas_n1": alocacoes_fds_n1,
        "taxa_superqualificacao": (
            superqualificados / alocacoes_fds_n1 if alocacoes_fds_n1 else 0.0
        ),
    }
