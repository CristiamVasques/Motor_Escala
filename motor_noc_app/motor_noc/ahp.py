"""
Calibração dos pesos estruturais α, δ, λ pelo Analytic Hierarchy Process
(Subseção 6.6.5), conforme SAATY e VARGAS (2012).

Converte julgamentos qualitativos pareados da gerência do NOC em pesos
quantitativos normalizados, verificando a razão de consistência antes de
aceitar a priorização informada.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from .objetivo import Pesos

CRITERIOS = ("equidade", "senioridade", "cobertura")

#: Índice Randômico de Saaty por ordem da matriz.
INDICE_RANDOMICO: Dict[int, float] = {
    1: 0.00,
    2: 0.00,
    3: 0.58,
    4: 0.90,
    5: 1.12,
    6: 1.24,
    7: 1.32,
    8: 1.41,
    9: 1.45,
}

#: Escala fundamental de importância (Saaty).
ESCALA_FUNDAMENTAL: Dict[int, str] = {
    1: "Importância igual",
    3: "Importância moderada",
    5: "Importância forte",
    7: "Importância muito forte",
    9: "Importância extrema",
}


@dataclass
class ResultadoAHP:
    pesos: Pesos
    vetor_prioridade: Dict[str, float]
    lambda_max: float
    indice_consistencia: float
    razao_consistencia: float

    @property
    def consistente(self) -> bool:
        """Julgamentos são aceitos quando CR <= 0,10 (Saaty)."""
        return self.razao_consistencia <= 0.10

    def resumo(self) -> Dict[str, object]:
        return {
            "pesos": self.pesos.como_dict(),
            "vetor_prioridade": self.vetor_prioridade,
            "lambda_max": self.lambda_max,
            "indice_consistencia": self.indice_consistencia,
            "razao_consistencia": self.razao_consistencia,
            "consistente": self.consistente,
        }


def matriz_a_partir_de_julgamentos(
    equidade_vs_senioridade: float,
    equidade_vs_cobertura: float,
    senioridade_vs_cobertura: float,
) -> List[List[float]]:
    """Monta a matriz recíproca 3x3 a partir de três comparações pareadas.

    Cada valor segue a escala fundamental de Saaty: quanto o primeiro critério
    é mais importante que o segundo. Valores menores que 1 indicam a relação
    inversa.
    """
    a, b, c = (
        equidade_vs_senioridade,
        equidade_vs_cobertura,
        senioridade_vs_cobertura,
    )
    for valor in (a, b, c):
        if valor <= 0:
            raise ValueError("Julgamentos devem ser estritamente positivos.")
    return [
        [1.0, a, b],
        [1.0 / a, 1.0, c],
        [1.0 / b, 1.0 / c, 1.0],
    ]


def _autovetor_principal(
    matriz: Sequence[Sequence[float]], iteracoes: int = 200, tol: float = 1e-12
) -> Tuple[List[float], float]:
    """Método das potências para o autovetor e o autovalor principais."""
    n = len(matriz)
    v = [1.0 / n] * n
    lambda_max = 0.0
    for _ in range(iteracoes):
        w = [sum(matriz[i][j] * v[j] for j in range(n)) for i in range(n)]
        soma = sum(w)
        if soma == 0:
            break
        novo = [x / soma for x in w]
        if max(abs(novo[i] - v[i]) for i in range(n)) < tol:
            v = novo
            break
        v = novo

    # λ_max = média das razões (Av)_i / v_i
    av = [sum(matriz[i][j] * v[j] for j in range(n)) for i in range(n)]
    lambda_max = sum(av[i] / v[i] for i in range(n) if v[i] > 0) / n
    return v, lambda_max


def calibrar(matriz: Sequence[Sequence[float]]) -> ResultadoAHP:
    """Deriva α, δ, λ e a razão de consistência da matriz de julgamentos."""
    n = len(matriz)
    if n != 3 or any(len(linha) != 3 for linha in matriz):
        raise ValueError("A matriz de julgamentos deve ser 3x3.")

    vetor, lambda_max = _autovetor_principal(matriz)
    ic = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    ir = INDICE_RANDOMICO.get(n, 1.49)
    cr = ic / ir if ir > 0 else 0.0

    return ResultadoAHP(
        pesos=Pesos(alpha=vetor[0], delta=vetor[1], lam=vetor[2]),
        vetor_prioridade=dict(zip(CRITERIOS, vetor)),
        lambda_max=lambda_max,
        indice_consistencia=ic,
        razao_consistencia=cr,
    )


def calibrar_por_julgamentos(
    equidade_vs_senioridade: float,
    equidade_vs_cobertura: float,
    senioridade_vs_cobertura: float,
) -> ResultadoAHP:
    return calibrar(
        matriz_a_partir_de_julgamentos(
            equidade_vs_senioridade, equidade_vs_cobertura, senioridade_vs_cobertura
        )
    )
