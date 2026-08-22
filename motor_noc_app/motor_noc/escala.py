"""
Representação da matriz de decisão X_{a,t} e manutenção incremental dos
componentes brutos da função de custo (Seções 6.6.2 a 6.6.4).

A escolha por atualização incremental é deliberada: o Simulated Annealing
executa dezenas de milhares de iterações, e recalcular as três componentes do
zero a cada movimento tornaria o motor inviável em Python. Aqui, todo
movimento custa O(1) na avaliação do custo.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, Iterator, List, Set, Tuple

from .dominio import Analista, Instancia, Nivel, TipoTurno, Turno


class Escala:
    """Matriz binária X_{a,t} com estatísticas de custo mantidas em linha."""

    def __init__(self, instancia: Instancia):
        self.inst = instancia

        self._por_turno: Dict[str, Set[str]] = {t.id: set() for t in instancia.turnos}
        self._por_analista: Dict[str, Set[str]] = {
            a.id: set() for a in instancia.analistas
        }

        # Cargas horárias individuais (Equação 6.9).
        self.horas_reais: Dict[str, float] = {a.id: 0.0 for a in instancia.analistas}
        self.horas_legais: Dict[str, float] = {a.id: 0.0 for a in instancia.analistas}

        # Somatórios por equipe fixa, para variância em O(1) (Equação 6.11).
        self._soma_h: Dict[TipoTurno, float] = {tt: 0.0 for tt in TipoTurno}
        self._soma_h2: Dict[TipoTurno, float] = {tt: 0.0 for tt in TipoTurno}

        # Capacidade de vazão escalada por turno (Equação 6.14).
        self._capacidade: Dict[str, int] = {t.id: 0 for t in instancia.turnos}
        self._f_atendimento: float = float(
            sum(t.volume_alertas for t in instancia.turnos)
        )

        # Penalização de superqualificação (Equação 6.13).
        self._f_senioridade: float = 0.0

        # Contagem por nível em cada turno, para checar a demanda mínima.
        self._niveis: Dict[str, Dict[Nivel, int]] = {
            t.id: {Nivel.N1: 0, Nivel.N2: 0, Nivel.N3: 0} for t in instancia.turnos
        }

        # Dia civil ocupado por analista (restrição de turno único diário).
        self._dias_ocupados: Dict[str, Set[date]] = {
            a.id: set() for a in instancia.analistas
        }

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------

    def esta_alocado(self, id_analista: str, id_turno: str) -> bool:
        return id_analista in self._por_turno[id_turno]

    def analistas_em(self, id_turno: str) -> Set[str]:
        return self._por_turno[id_turno]

    def turnos_de(self, id_analista: str) -> Set[str]:
        return self._por_analista[id_analista]

    def turnos_ordenados_de(self, id_analista: str) -> List[Turno]:
        return sorted(
            (self.inst.turno(t) for t in self._por_analista[id_analista]),
            key=lambda t: t.inicio,
        )

    def dias_ocupados(self, id_analista: str) -> Set[date]:
        return self._dias_ocupados[id_analista]

    def contagem_niveis(self, id_turno: str) -> Dict[Nivel, int]:
        return self._niveis[id_turno]

    def total_alocacoes(self) -> int:
        return sum(len(v) for v in self._por_turno.values())

    def itens(self) -> Iterator[Tuple[str, str]]:
        for id_turno, analistas in self._por_turno.items():
            for id_analista in analistas:
                yield id_analista, id_turno

    # ------------------------------------------------------------------
    # Componentes brutos da função de custo
    # ------------------------------------------------------------------

    @property
    def f_balanceamento(self) -> float:
        """f_balanceamento_interno(X) — Equação 6.11.

        Variância das cargas horárias dentro de cada equipe fixa, normalizada
        pela cardinalidade do subconjunto para que equipes maiores não pesem
        mais apenas por seu tamanho.
        """
        total = 0.0
        for tipo, equipe in self.inst.equipes.items():
            n = len(equipe)
            if n == 0:
                continue
            media = self._soma_h[tipo] / n
            total += self._soma_h2[tipo] / n - media * media
        return max(0.0, total)  # protege contra ruído numérico

    @property
    def f_senioridade(self) -> float:
        """f_senioridade(X) — Equação 6.13."""
        return self._f_senioridade

    @property
    def f_atendimento(self) -> float:
        """f_atendimento(X) — Equação 6.14."""
        return self._f_atendimento

    def componentes(self) -> Dict[str, float]:
        return {
            "balanceamento": self.f_balanceamento,
            "senioridade": self.f_senioridade,
            "atendimento": self.f_atendimento,
        }

    # ------------------------------------------------------------------
    # Mutação
    # ------------------------------------------------------------------

    def alocar(self, id_analista: str, id_turno: str) -> None:
        """Faz X_{a,t} = 1 e atualiza todas as estatísticas derivadas."""
        if id_analista in self._por_turno[id_turno]:
            return
        a = self.inst.analista(id_analista)
        t = self.inst.turno(id_turno)

        self._por_turno[id_turno].add(id_analista)
        self._por_analista[id_analista].add(id_turno)
        self._dias_ocupados[id_analista].add(t.dia_civil)
        self._niveis[id_turno][a.nivel] += 1

        self._atualizar_carga(a, +t.duracao_trabalhada, +t.duracao_legal)
        self._atualizar_capacidade(t, +a.capacidade_atendimento)

        if t.eh_fim_de_semana and t.exige_apenas_n1 and a.nivel is not Nivel.N1:
            self._f_senioridade += 1.0

    def desalocar(self, id_analista: str, id_turno: str) -> None:
        """Faz X_{a,t} = 0 e reverte as estatísticas derivadas."""
        if id_analista not in self._por_turno[id_turno]:
            return
        a = self.inst.analista(id_analista)
        t = self.inst.turno(id_turno)

        self._por_turno[id_turno].discard(id_analista)
        self._por_analista[id_analista].discard(id_turno)
        self._niveis[id_turno][a.nivel] -= 1

        # O dia civil só é liberado se o analista não tiver outro turno nele.
        if not any(
            self.inst.turno(tid).dia_civil == t.dia_civil
            for tid in self._por_analista[id_analista]
        ):
            self._dias_ocupados[id_analista].discard(t.dia_civil)

        self._atualizar_carga(a, -t.duracao_trabalhada, -t.duracao_legal)
        self._atualizar_capacidade(t, -a.capacidade_atendimento)

        if t.eh_fim_de_semana and t.exige_apenas_n1 and a.nivel is not Nivel.N1:
            self._f_senioridade -= 1.0

    # -- auxiliares internos ------------------------------------------------

    def _atualizar_carga(self, a: Analista, delta_real: float, delta_legal: float) -> None:
        tipo = a.turno_fixo
        antiga = self.horas_reais[a.id]
        nova = antiga + delta_real
        self.horas_reais[a.id] = nova
        self.horas_legais[a.id] += delta_legal
        self._soma_h[tipo] += nova - antiga
        self._soma_h2[tipo] += nova * nova - antiga * antiga

    def _atualizar_capacidade(self, t: Turno, delta: int) -> None:
        antiga = self._capacidade[t.id]
        nova = antiga + delta
        self._capacidade[t.id] = nova
        self._f_atendimento += abs(t.volume_alertas - nova) - abs(
            t.volume_alertas - antiga
        )

    # ------------------------------------------------------------------
    # Cópia
    # ------------------------------------------------------------------

    def copiar(self) -> "Escala":
        nova = Escala.__new__(Escala)
        nova.inst = self.inst
        nova._por_turno = {k: set(v) for k, v in self._por_turno.items()}
        nova._por_analista = {k: set(v) for k, v in self._por_analista.items()}
        nova.horas_reais = dict(self.horas_reais)
        nova.horas_legais = dict(self.horas_legais)
        nova._soma_h = dict(self._soma_h)
        nova._soma_h2 = dict(self._soma_h2)
        nova._capacidade = dict(self._capacidade)
        nova._f_atendimento = self._f_atendimento
        nova._f_senioridade = self._f_senioridade
        nova._niveis = {k: dict(v) for k, v in self._niveis.items()}
        nova._dias_ocupados = {k: set(v) for k, v in self._dias_ocupados.items()}
        return nova

    def distancia_hamming(self, outra: "Escala") -> int:
        """Número de posições em que duas matrizes X diferem."""
        d = 0
        for id_turno, analistas in self._por_turno.items():
            d += len(analistas.symmetric_difference(outra._por_turno[id_turno]))
        return d
