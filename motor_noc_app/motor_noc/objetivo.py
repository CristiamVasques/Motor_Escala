"""
Função objetivo F(X) e normalização min-max das componentes de custo
(Seções 6.6 e 6.6.1 do TCC).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Tuple

from .escala import Escala

COMPONENTES = ("balanceamento", "senioridade", "atendimento")


class Normalizador:
    """Normalização min-max com limites congelados ao fim do aquecimento.

    O congelamento (Subseção 6.6.1) é condição para a convergência do
    Simulated Annealing: se os limites fossem atualizados a cada nova solução
    visitada, a paisagem de custo se alteraria durante a busca e o ΔF usado no
    critério probabilístico de aceitação deixaria de ser comparável entre
    iterações distintas.

    Sobre ``usar_minimo_teorico``: as três componentes têm zero como ínfimo
    matemático — variância nula (equidade perfeita), nenhuma alocação
    superqualificada e aderência exata entre capacidade e volume de alertas.
    Adotar f_min = 0 em vez do menor valor observado no aquecimento evita um
    efeito colateral severo do truncamento da Equação 6.8: se f_min for
    estimado empiricamente e a busca alcançar valores inferiores, todos eles
    são truncados em 0 e a componente deixa de discriminar soluções, anulando
    o gradiente justamente na região de maior qualidade. Mantém-se a estimativa
    empírica apenas para f_max, onde não há limite superior natural.
    """

    def __init__(self, usar_minimo_teorico: bool = True) -> None:
        self.usar_minimo_teorico = usar_minimo_teorico
        self.minimos: Dict[str, float] = (
            {c: 0.0 for c in COMPONENTES} if usar_minimo_teorico else {}
        )
        self.maximos: Dict[str, float] = {}
        self.congelado = False
        self.amostras = 0

    def observar(self, componentes: Dict[str, float]) -> None:
        if self.congelado:
            return
        for chave in COMPONENTES:
            valor = componentes[chave]
            if not self.usar_minimo_teorico:
                if chave not in self.minimos or valor < self.minimos[chave]:
                    self.minimos[chave] = valor
            if chave not in self.maximos or valor > self.maximos[chave]:
                self.maximos[chave] = valor
        self.amostras += 1

    def congelar(self) -> None:
        for chave in COMPONENTES:
            self.minimos.setdefault(chave, 0.0)
            self.maximos.setdefault(chave, 0.0)
        self.congelado = True

    def normalizar(self, componentes: Dict[str, float]) -> Dict[str, float]:
        """Equação 6.8, com truncamento em [0, 1]."""
        saida: Dict[str, float] = {}
        for chave in COMPONENTES:
            f_min = self.minimos.get(chave, 0.0)
            f_max = self.maximos.get(chave, 0.0)
            if f_max <= f_min:
                # Componente constante durante o aquecimento: retirada da
                # composição do custo em vez de gerar indeterminação numérica.
                saida[chave] = 0.0
            else:
                bruto = (componentes[chave] - f_min) / (f_max - f_min)
                saida[chave] = min(1.0, max(0.0, bruto))
        return saida

    def limites(self) -> Dict[str, Tuple[float, float]]:
        return {c: (self.minimos.get(c, 0.0), self.maximos.get(c, 0.0)) for c in COMPONENTES}


@dataclass
class Pesos:
    """Pesos estruturais α, δ, λ, sujeitos a α + δ + λ = 1."""

    alpha: float = 1 / 3
    delta: float = 1 / 3
    lam: float = 1 / 3

    def __post_init__(self) -> None:
        soma = self.alpha + self.delta + self.lam
        if soma <= 0:
            raise ValueError("A soma dos pesos deve ser positiva.")
        if abs(soma - 1.0) > 1e-9:
            self.alpha /= soma
            self.delta /= soma
            self.lam /= soma
        for nome, valor in (("alpha", self.alpha), ("delta", self.delta), ("lam", self.lam)):
            if valor < -1e-12 or valor > 1 + 1e-12:
                raise ValueError(f"Peso {nome} fora do intervalo [0, 1]: {valor}")

    def como_dict(self) -> Dict[str, float]:
        return {"alpha": self.alpha, "delta": self.delta, "lambda": self.lam}


class FuncaoObjetivo:
    """F(X) = α·f̂_bal + δ·f̂_sen + λ·f̂_atend (Equação 6.7)."""

    def __init__(self, pesos: Pesos, normalizador: Normalizador | None = None):
        self.pesos = pesos
        self.normalizador = normalizador or Normalizador()

    def componentes_brutos(self, escala: Escala) -> Dict[str, float]:
        return escala.componentes()

    def componentes_normalizados(self, escala: Escala) -> Dict[str, float]:
        return self.normalizador.normalizar(escala.componentes())

    def custo(self, escala: Escala) -> float:
        n = self.componentes_normalizados(escala)
        return (
            self.pesos.alpha * n["balanceamento"]
            + self.pesos.delta * n["senioridade"]
            + self.pesos.lam * n["atendimento"]
        )

    def detalhar(self, escala: Escala) -> Dict[str, object]:
        brutos = self.componentes_brutos(escala)
        normalizados = self.componentes_normalizados(escala)
        return {
            "custo": self.custo(escala),
            "brutos": brutos,
            "normalizados": normalizados,
            "pesos": self.pesos.como_dict(),
            "limites_normalizacao": self.normalizador.limites(),
        }
