"""
Motor algorítmico para escalonamento de analistas em Centros de Operações de
Rede — protótipo funcional do TCC de Pós-Graduação em Tecnologias e Sistemas
de Informação (UFABC).

Arquitetura híbrida sequencial:
    Greedy → Hill Climbing → Simulated Annealing → CSP com Backtracking

Implementado exclusivamente com a biblioteca padrão do Python 3.10+.
"""

from .dominio import Analista, Instancia, Nivel, TipoTurno, Turno
from .escala import Escala
from .objetivo import FuncaoObjetivo, Normalizador, Pesos

__version__ = "1.0.0"

__all__ = [
    "Analista",
    "Turno",
    "Instancia",
    "Nivel",
    "TipoTurno",
    "Escala",
    "Pesos",
    "Normalizador",
    "FuncaoObjetivo",
]
