"""
Gerador de instâncias sintéticas de um NOC em regime 24x7.

Reproduz a estrutura de turnos fixos descrita na Seção 6.4: quatro
subconjuntos disjuntos de analistas (Matutino, Comercial, Vespertino e
Noturno), com o turno comercial operando apenas em dias úteis e os demais em
cobertura contínua, inclusive fins de semana.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, FrozenSet, List, Optional, Tuple

from .dominio import Analista, Instancia, Nivel, TipoTurno, Turno

COMPETENCIAS = ("ZABBIX", "AVAYA", "REDES", "LINUX", "WAZUH")

#: Estrutura de turnos da operação de referência, conforme a Tabela de turnos
#: da Seção 6.5.1.2 do TCC. Cada entrada traz hora e minuto de início, duração
#: de PRESENÇA em horas e intervalo intrajornada em horas.
#:
#: A escala é 5x2 com 8h48 de jornada trabalhada nas equipes diurnas. O turno
#: noturno tem presença menor (8h20) porque a redução da hora noturna do
#: art. 73, § 1º da CLT compensa a diferença: sua jornada computada é de 8h20,
#: e não as 7h20 de relógio.
#:
#: A cobertura é contínua: o turno noturno encerra às 06h00 e o matutino inicia
#: às 05h40, e as sobreposições entre turnos diurnos cobrem as transições.
JANELAS: Dict[TipoTurno, Tuple[int, int, float, float]] = {
    TipoTurno.MATUTINO: (5, 40, 9.8, 1.0),        # 05h40-15h28, computada 8h48
    TipoTurno.COMERCIAL: (8, 0, 9.8, 1.0),        # 08h00-17h48, computada 8h48
    TipoTurno.VESPERTINO: (12, 12, 9.8, 1.0),     # 12h12-22h00, computada 8h48
    TipoTurno.NOTURNO: (21, 40, 8 + 20 / 60, 1.0),  # 21h40-06h00, computada 8h20
}

#: Composição padrão de cada equipe fixa: quantidade por nível.
EQUIPE_PADRAO: Dict[TipoTurno, Dict[Nivel, int]] = {
    TipoTurno.MATUTINO: {Nivel.N1: 5, Nivel.N2: 2, Nivel.N3: 1},
    TipoTurno.COMERCIAL: {Nivel.N1: 3, Nivel.N2: 2, Nivel.N3: 2},
    TipoTurno.VESPERTINO: {Nivel.N1: 5, Nivel.N2: 2, Nivel.N3: 1},
    TipoTurno.NOTURNO: {Nivel.N1: 5, Nivel.N2: 2, Nivel.N3: 1},
}

#: Demanda mínima por senioridade em dia útil (parâmetro MinRequerido_{t,s}).
DEMANDA_DIA_UTIL: Dict[TipoTurno, Dict[Nivel, int]] = {
    TipoTurno.MATUTINO: {Nivel.N1: 2, Nivel.N2: 1, Nivel.N3: 0},
    TipoTurno.COMERCIAL: {Nivel.N1: 2, Nivel.N2: 1, Nivel.N3: 1},
    TipoTurno.VESPERTINO: {Nivel.N1: 2, Nivel.N2: 1, Nivel.N3: 0},
    TipoTurno.NOTURNO: {Nivel.N1: 2, Nivel.N2: 0, Nivel.N3: 0},
}

#: Demanda mínima em plantão de fim de semana — apenas N1, o que torna
#: aplicável a penalização de superqualificação (Subseção 6.5.2.2).
DEMANDA_FDS: Dict[TipoTurno, Dict[Nivel, int]] = {
    TipoTurno.MATUTINO: {Nivel.N1: 1, Nivel.N2: 0, Nivel.N3: 0},
    TipoTurno.VESPERTINO: {Nivel.N1: 1, Nivel.N2: 0, Nivel.N3: 0},
    TipoTurno.NOTURNO: {Nivel.N1: 1, Nivel.N2: 0, Nivel.N3: 0},
}

#: Volume médio de alertas por turno em dia útil.
VOLUME_BASE: Dict[TipoTurno, int] = {
    TipoTurno.MATUTINO: 30,
    TipoTurno.COMERCIAL: 45,
    TipoTurno.VESPERTINO: 34,
    TipoTurno.NOTURNO: 18,
}

#: Capacidade de triagem e resolução por turno, conforme o nível.
CAPACIDADE: Dict[Nivel, int] = {Nivel.N1: 12, Nivel.N2: 16, Nivel.N3: 20}

#: Competência técnica exigida por turno, quando houver.
COMPETENCIA_EXIGIDA: Dict[TipoTurno, FrozenSet[str]] = {
    TipoTurno.MATUTINO: frozenset({"ZABBIX"}),
    TipoTurno.COMERCIAL: frozenset({"ZABBIX", "AVAYA"}),
    TipoTurno.VESPERTINO: frozenset({"ZABBIX"}),
    TipoTurno.NOTURNO: frozenset({"ZABBIX", "LINUX"}),
}


def _competencias_do_analista(nivel: Nivel, rng: random.Random) -> FrozenSet[str]:
    """N1 domina o núcleo de monitoração; níveis superiores acumulam mais."""
    base = {"ZABBIX"}
    extras = {Nivel.N1: 1, Nivel.N2: 2, Nivel.N3: 3}[nivel]
    disponiveis = [c for c in COMPETENCIAS if c not in base]
    base.update(rng.sample(disponiveis, extras))
    return frozenset(base)


def gerar_analistas(
    composicao: Optional[Dict[TipoTurno, Dict[Nivel, int]]] = None,
    seed: int = 42,
) -> List[Analista]:
    composicao = composicao or EQUIPE_PADRAO
    rng = random.Random(seed)
    analistas: List[Analista] = []
    contador = 1
    for tipo, niveis in composicao.items():
        for nivel, quantidade in niveis.items():
            for _ in range(quantidade):
                # Garante que o turno noturno tenha LINUX e o comercial AVAYA,
                # de modo que a restrição de competência seja satisfatível.
                competencias = set(_competencias_do_analista(nivel, rng))
                competencias |= set(COMPETENCIA_EXIGIDA.get(tipo, frozenset()))
                analistas.append(
                    Analista(
                        id=f"A{contador:03d}",
                        nome=f"Analista {contador:03d} ({tipo.value.title()})",
                        nivel=nivel,
                        turno_fixo=tipo,
                        competencias=frozenset(competencias),
                        capacidade_atendimento=CAPACIDADE[nivel],
                    )
                )
                contador += 1
    return analistas


def gerar_turnos(
    data_inicio: date,
    dias: int,
    seed: int = 42,
    fator_volume: float = 1.0,
) -> List[Turno]:
    rng = random.Random(seed + 7)
    turnos: List[Turno] = []
    for d in range(dias):
        dia = data_inicio + timedelta(days=d)
        fim_de_semana = dia.weekday() >= 5
        for tipo, (hora, minuto, presenca, intervalo) in JANELAS.items():
            if tipo is TipoTurno.COMERCIAL and fim_de_semana:
                continue  # não há turno comercial em fim de semana

            demanda = (
                DEMANDA_FDS[tipo] if fim_de_semana else DEMANDA_DIA_UTIL[tipo]
            )
            base = VOLUME_BASE[tipo] * (0.55 if fim_de_semana else 1.0)
            volume = max(1, int(round(base * fator_volume * rng.uniform(0.75, 1.30))))

            turnos.append(
                Turno(
                    id=f"T{dia:%Y%m%d}-{tipo.value[:3]}",
                    tipo=tipo,
                    inicio=datetime(dia.year, dia.month, dia.day, hora, minuto),
                    duracao_horas=presenca,
                    min_requerido=dict(demanda),
                    competencias_requeridas=COMPETENCIA_EXIGIDA.get(tipo, frozenset()),
                    volume_alertas=volume,
                    intervalo_horas=intervalo,
                )
            )
    return turnos


def gerar_instancia(
    dias: int = 28,
    data_inicio: Optional[date] = None,
    seed: int = 42,
    composicao: Optional[Dict[TipoTurno, Dict[Nivel, int]]] = None,
    fator_volume: float = 1.0,
) -> Instancia:
    """Gera uma instância completa iniciando em uma segunda-feira."""
    if data_inicio is None:
        data_inicio = date(2026, 3, 2)  # segunda-feira
    return Instancia(
        gerar_analistas(composicao, seed),
        gerar_turnos(data_inicio, dias, seed, fator_volume),
    )


def gerar_instancia_reduzida(seed: int = 7) -> Instancia:
    """Instância mínima para o cálculo de gap por busca exaustiva (5.1c)."""
    composicao = {
        TipoTurno.MATUTINO: {Nivel.N1: 3, Nivel.N2: 1},
        TipoTurno.NOTURNO: {Nivel.N1: 3},
    }
    analistas = gerar_analistas(composicao, seed)
    data_inicio = date(2026, 3, 2)
    turnos: List[Turno] = []
    for d in range(4):
        dia = data_inicio + timedelta(days=d)
        for tipo in (TipoTurno.MATUTINO, TipoTurno.NOTURNO):
            hora, minuto, presenca, intervalo = JANELAS[tipo]
            turnos.append(
                Turno(
                    id=f"T{dia:%Y%m%d}-{tipo.value[:3]}",
                    tipo=tipo,
                    inicio=datetime(dia.year, dia.month, dia.day, hora, minuto),
                    duracao_horas=presenca,
                    min_requerido=(
                        {Nivel.N1: 1, Nivel.N2: 1}
                        if tipo is TipoTurno.MATUTINO
                        else {Nivel.N1: 1}
                    ),
                    competencias_requeridas=frozenset({"ZABBIX"}),
                    volume_alertas=14 if tipo is TipoTurno.MATUTINO else 10,
                    intervalo_horas=intervalo,
                )
            )
    return Instancia(analistas, turnos)
