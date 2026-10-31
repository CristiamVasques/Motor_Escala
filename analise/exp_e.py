"""Experimento E — verifica se a dominância sobre a escala manual se sustenta.

Em lambda = 0,9 a execução de semente 42 produziu cobertura igual a da escala
manual com desequilibrio menor. Este experimento repete a configuracao em
trinta instancias para medir com que frequencia a dominancia se sustenta.
"""
import json
import os
from multiprocessing import Pool

from motor_noc.gerador import gerar_instancia
from motor_noc.baseline import construir_escala_manual
from motor_noc.objetivo import Pesos, FuncaoObjetivo
from motor_noc.algoritmos import pipeline
from motor_noc import metricas

SAIDA = os.path.dirname(os.path.abspath(__file__))
LAMBDAS = [0.85, 0.9, 0.95]


def _uma(seed):
    inst = gerar_instancia(dias=28, seed=seed)
    manual = construir_escala_manual(inst)
    saida = {"seed": seed}
    for lam in LAMBDAS:
        pesos = Pesos(round(1 - lam, 2), 0.0, lam)
        res = pipeline.executar(inst, pesos, seed=seed)
        fo = FuncaoObjetivo(pesos, res.fo.normalizador)
        comp = metricas.comparar_com_manual(inst, res.escala, manual, fo)
        saida[str(lam)] = {"motor": comp["motor"], "manual": comp["manual"]}
    return saida


if __name__ == "__main__":
    with Pool(2) as pool:
        linhas = pool.map(_uma, range(1, 31))
    with open(f"{SAIDA}/exp_e_dominancia.json", "w") as fh:
        json.dump(linhas, fh, indent=1)
    print(f"E: {len(linhas)} sementes")
