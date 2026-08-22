"""
Modelo de domínio do problema de escalonamento de analistas em NOC.

Implementa os conjuntos, parâmetros e variáveis de decisão descritos na
Seção 6.4 do TCC (Modelagem das Variáveis de Decisão e Estrutura Fixa).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from functools import lru_cache
from typing import Dict, FrozenSet, Iterable, List, Optional

# ---------------------------------------------------------------------------
# Enumerações
# ---------------------------------------------------------------------------


class Nivel(str, Enum):
    """Nível de senioridade do analista."""

    N1 = "N1"
    N2 = "N2"
    N3 = "N3"


ORDEM_NIVEL: Dict[Nivel, int] = {Nivel.N1: 1, Nivel.N2: 2, Nivel.N3: 3}


class TipoTurno(str, Enum):
    """Turnos fixos invariáveis (premissa da Seção 6.4)."""

    MATUTINO = "MATUTINO"
    COMERCIAL = "COMERCIAL"
    VESPERTINO = "VESPERTINO"
    NOTURNO = "NOTURNO"


# ---------------------------------------------------------------------------
# Parâmetros legais (Consolidação das Leis do Trabalho)
# ---------------------------------------------------------------------------

#: Teto da jornada semanal — art. 7º, XIII da CF/88, regulamentado pelos
#: arts. 58 e 59 da CLT.
TETO_SEMANAL_HORAS = 44.0

#: Intervalo mínimo entre jornadas — art. 66 da CLT.
INTERJORNADA_MINIMA_HORAS = 11.0

#: Repouso semanal remunerado — art. 67 da CLT.
REPOUSO_SEMANAL_HORAS = 24.0

#: Hora noturna reduzida (52min30s) — art. 73, § 1º da CLT.
#: Uma hora de relógio no turno noturno equivale a 60/52,5 horas legais.
FATOR_HORA_NOTURNA = 60.0 / 52.5

#: Janela do período noturno — art. 73, § 2º da CLT: das 22h de um dia às 5h
#: do dia seguinte.
HORA_INICIO_NOTURNO = 22
HORA_FIM_NOTURNO = 5


# ---------------------------------------------------------------------------
# Cálculo do período noturno
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4096)
def _particao_noturna(
    hora_inicio: int, minuto_inicio: int, duracao_horas: float
) -> tuple:
    """Separa a presença de um turno em parcelas noturna e diurna, em horas.

    O período noturno vai das 22h às 5h (art. 73, § 2º da CLT). A parcela
    trabalhada após as 5h, em prorrogação de jornada iniciada no período
    noturno, também é computada como noturna, conforme a Súmula 60, II, do
    Tribunal Superior do Trabalho.

    O resultado é memoizado: a função é chamada a cada alocação e desalocação
    do motor, mas depende apenas do horário de início e da duração do turno,
    que formam um conjunto pequeno de combinações distintas.
    """
    passo_h = 1.0 / 60.0
    total_minutos = int(round(duracao_horas * 60))
    minuto_corrente = hora_inicio * 60 + minuto_inicio
    noturnas = 0.0
    prorrogando = False
    for _ in range(total_minutos):
        hora = (minuto_corrente // 60) % 24
        if hora >= HORA_INICIO_NOTURNO or hora < HORA_FIM_NOTURNO:
            prorrogando = True
            noturnas += passo_h
        elif prorrogando:
            noturnas += passo_h  # prorrogação da jornada noturna
        minuto_corrente += 1
    return noturnas, max(0.0, duracao_horas - noturnas)


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Analista:
    """Elemento do conjunto A (Equação 6.1)."""

    id: str
    nome: str
    nivel: Nivel
    turno_fixo: TipoTurno
    competencias: FrozenSet[str]
    capacidade_atendimento: int

    def __repr__(self) -> str:  # pragma: no cover - conveniência
        return f"<Analista {self.id} {self.nivel.value} {self.turno_fixo.value}>"


@dataclass(frozen=True, eq=False)
class Turno:
    """Elemento do conjunto T. Representa uma janela operacional concreta."""

    id: str
    tipo: TipoTurno
    inicio: datetime
    #: Duração de PRESENÇA do turno, do início ao término (inclui o intervalo).
    duracao_horas: float
    min_requerido: Dict[Nivel, int]
    competencias_requeridas: FrozenSet[str]
    volume_alertas: int
    #: Intervalo intrajornada, em horas. Zero mantém o comportamento anterior,
    #: em que presença e jornada trabalhada coincidem.
    intervalo_horas: float = 0.0

    # -- propriedades derivadas -------------------------------------------

    @property
    def fim(self) -> datetime:
        return self.inicio + timedelta(hours=self.duracao_horas)

    @property
    def dia_civil(self) -> date:
        """Dia civil de início — base da restrição de turno único diário."""
        return self.inicio.date()

    @property
    def eh_fim_de_semana(self) -> bool:
        return self.inicio.weekday() >= 5  # 5 = sábado, 6 = domingo

    @property
    def duracao_trabalhada(self) -> float:
        """Horas efetivamente trabalhadas: presença menos intervalo."""
        return max(0.0, self.duracao_horas - self.intervalo_horas)

    def _particao_noturna(self) -> tuple:
        """Parcelas noturna e diurna da presença do turno, em horas."""
        return _particao_noturna(
            self.inicio.hour, self.inicio.minute, self.duracao_horas
        )

    @property
    def duracao_legal(self) -> float:
        """Duração computada para o teto semanal, com hora noturna reduzida.

        O fator de redução incide apenas sobre as horas efetivamente cumpridas
        no período noturno, e não sobre o turno inteiro: um turno que se inicia
        antes das 22h tem sua parcela inicial computada em horas de relógio.

        O intervalo intrajornada é descontado prioritariamente da parcela
        noturna, que é a hipótese usual em turnos que atravessam a madrugada.
        """
        noturnas, diurnas = self._particao_noturna()
        desconto_noturno = min(self.intervalo_horas, noturnas)
        noturnas -= desconto_noturno
        diurnas = max(0.0, diurnas - (self.intervalo_horas - desconto_noturno))
        return diurnas + noturnas * FATOR_HORA_NOTURNA

    @property
    def exige_apenas_n1(self) -> bool:
        """Conjunto T^{N1}_{FDS} da Equação 6.12 (quando em fim de semana)."""
        return (
            self.min_requerido.get(Nivel.N2, 0) == 0
            and self.min_requerido.get(Nivel.N3, 0) == 0
        )

    @property
    def demanda_total(self) -> int:
        return sum(self.min_requerido.values())

    def __repr__(self) -> str:  # pragma: no cover - conveniência
        return f"<Turno {self.id} {self.inicio:%d/%m %H:%M} {self.tipo.value}>"


class Instancia:
    """Agrega analistas, turnos e índices auxiliares de acesso rápido."""

    def __init__(self, analistas: Iterable[Analista], turnos: Iterable[Turno]):
        self.analistas: List[Analista] = list(analistas)
        self.turnos: List[Turno] = sorted(turnos, key=lambda t: t.inicio)

        self._analistas_por_id = {a.id: a for a in self.analistas}
        self._turnos_por_id = {t.id: t for t in self.turnos}

        self.equipes: Dict[TipoTurno, List[Analista]] = {tt: [] for tt in TipoTurno}
        for a in self.analistas:
            self.equipes[a.turno_fixo].append(a)

        self.turnos_por_tipo: Dict[TipoTurno, List[Turno]] = {tt: [] for tt in TipoTurno}
        for t in self.turnos:
            self.turnos_por_tipo[t.tipo].append(t)

        self.turnos_por_dia: Dict[date, List[Turno]] = {}
        for t in self.turnos:
            self.turnos_por_dia.setdefault(t.dia_civil, []).append(t)

        # Candidatos elegíveis por turno: mesma equipe fixa (Equação 6.2) e
        # competência técnica compatível (Subseção 6.5.1.6).
        self.candidatos: Dict[str, List[Analista]] = {
            t.id: [
                a
                for a in self.equipes[t.tipo]
                if t.competencias_requeridas <= a.competencias
            ]
            for t in self.turnos
        }

    # -- acesso ------------------------------------------------------------

    def analista(self, id_: str) -> Analista:
        return self._analistas_por_id[id_]

    def turno(self, id_: str) -> Turno:
        return self._turnos_por_id[id_]

    @property
    def dias(self) -> List[date]:
        return sorted(self.turnos_por_dia)

    def turnos_no_dia(self, dia: date) -> List[Turno]:
        return self.turnos_por_dia.get(dia, [])

    def resumo(self) -> Dict[str, object]:
        return {
            "analistas": len(self.analistas),
            "turnos": len(self.turnos),
            "dias": len(self.turnos_por_dia),
            "equipes": {tt.value: len(v) for tt, v in self.equipes.items()},
            "demanda_total_slots": sum(t.demanda_total for t in self.turnos),
            "volume_alertas_total": sum(t.volume_alertas for t in self.turnos),
        }
