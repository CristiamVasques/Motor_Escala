"""
Escala de referência construída por rodízio simples.

Reproduz a prática usual de montagem manual da escala pela gerência do NOC:
percorre os turnos em ordem cronológica e preenche a demanda mínima por
rodízio cíclico entre os analistas da equipe, sem qualquer avaliação global de
equidade de carga, superqualificação ou aderência ao volume de alertas.

Serve como linha de base para a métrica 5.1(a) — comparação com a escala
manual histórica.
"""
from __future__ import annotations

from typing import Dict, List

from .dominio import Instancia, Nivel, TipoTurno
from .escala import Escala
from .restricoes import pode_alocar


def construir_escala_manual(
    inst: Instancia, exigir_repouso_semanal: bool = True
) -> Escala:
    """Monta a escala por rodízio cíclico, respeitando as restrições rígidas."""
    escala = Escala(inst)

    # Fila circular por (turno fixo, nível).
    filas: Dict[tuple, List[str]] = {}
    for tipo, equipe in inst.equipes.items():
        for nivel in (Nivel.N1, Nivel.N2, Nivel.N3):
            filas[(tipo, nivel)] = [a.id for a in equipe if a.nivel is nivel]

    ponteiros: Dict[tuple, int] = {chave: 0 for chave in filas}

    for t in inst.turnos:  # ordem cronológica, como na montagem manual
        for nivel, minimo in t.min_requerido.items():
            chave = (t.tipo, nivel)
            fila = filas.get(chave, [])
            if not fila:
                continue
            alocados = 0
            tentativas = 0
            while alocados < minimo and tentativas < len(fila) * 2:
                idx = ponteiros[chave] % len(fila)
                ponteiros[chave] += 1
                tentativas += 1
                id_a = fila[idx]
                a = inst.analista(id_a)
                if escala.esta_alocado(id_a, t.id):
                    continue
                if pode_alocar(inst, escala, a, t, exigir_repouso_semanal):
                    escala.alocar(id_a, t.id)
                    alocados += 1
    return escala
