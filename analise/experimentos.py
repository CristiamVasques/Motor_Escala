"""Experimentos complementares para o capítulo de Resultados Obtidos."""
import json
import os
import statistics
import sys
import time
import tracemalloc
from multiprocessing import Pool

from motor_noc.gerador import gerar_instancia
from motor_noc.baseline import construir_escala_manual
from motor_noc.objetivo import Pesos, FuncaoObjetivo, Normalizador
from motor_noc.algoritmos import pipeline
from motor_noc import metricas

SAIDA = os.path.dirname(os.path.abspath(__file__))
DIAS = 28
CONFIGS = {
    "identicos": Pesos(1 / 3, 1 / 3, 1 / 3),
    "lambda08": Pesos(0.2, 0.0, 0.8),
}


def _uma_semente(seed):
    inst = gerar_instancia(dias=DIAS, seed=seed)
    manual = construir_escala_manual(inst)
    linha = {"seed": seed}
    for nome, pesos in CONFIGS.items():
        t0 = time.perf_counter()
        res = pipeline.executar(inst, pesos, seed=seed)
        tempo = time.perf_counter() - t0
        fo = FuncaoObjetivo(pesos, res.fo.normalizador)
        comp = metricas.comparar_com_manual(inst, res.escala, manual, fo)
        linha[nome] = {
            "motor": comp["motor"],
            "manual": comp["manual"],
            "tempo_s": tempo,
            "valida": res.valida,
        }
    return linha


def experimento_a(n_sementes=30):
    with Pool(2) as pool:
        linhas = pool.map(_uma_semente, range(1, n_sementes + 1))
    with open(f"{SAIDA}/exp_a_multisemente.json", "w") as fh:
        json.dump(linhas, fh, indent=1)
    print(f"A: {len(linhas)} sementes gravadas")


def _um_lambda(lam):
    inst = gerar_instancia(dias=DIAS, seed=42)
    pesos = Pesos(round(1.0 - lam, 2), 0.0, round(lam, 2))
    res = pipeline.executar(inst, pesos, seed=42)
    manual = construir_escala_manual(inst)
    fo = FuncaoObjetivo(pesos, res.fo.normalizador)
    comp = metricas.comparar_com_manual(inst, res.escala, manual, fo)
    return {"lam": lam, "alpha": round(1.0 - lam, 2), **comp["motor"]}


def experimento_b():
    lams = [round(0.1 * i, 1) for i in range(11)]
    with Pool(2) as pool:
        pontos = pool.map(_um_lambda, lams)
    inst = gerar_instancia(dias=DIAS, seed=42)
    manual = construir_escala_manual(inst)
    fo = FuncaoObjetivo(Pesos(), Normalizador())
    est = metricas._estatisticas_de_carga(inst, manual)
    ponto_manual = {
        "f_balanceamento": manual.f_balanceamento,
        "f_atendimento": manual.f_atendimento,
        "alocacoes": float(manual.total_alocacoes()),
        **est,
    }
    with open(f"{SAIDA}/exp_b_fronteira.json", "w") as fh:
        json.dump({"motor": pontos, "manual": ponto_manual}, fh, indent=1)
    print(f"B: {len(pontos)} pontos de fronteira")


def experimento_c():
    """Convergência do SA, estágios e cargas individuais (semente 42)."""
    inst = gerar_instancia(dias=DIAS, seed=42)
    manual = construir_escala_manual(inst)
    dados = {}
    for nome, pesos in CONFIGS.items():
        res = pipeline.executar(inst, pesos, seed=42)
        dados[nome] = {
            "estagios": metricas.ganho_por_estagio(res),
            "convergencia": metricas.curva_convergencia(res.relatorio_sa),
            "cargas": {a.id: res.escala.horas_reais[a.id] for a in inst.analistas},
            "sa": {
                "iteracoes": res.relatorio_sa.iteracoes_executadas,
                "avaliados": res.relatorio_sa.movimentos_avaliados,
                "aceitos": res.relatorio_sa.movimentos_aceitos,
                "piores_aceitos": res.relatorio_sa.movimentos_piores_aceitos,
                "aceitacao": res.relatorio_sa.taxa_aceitacao,
                "t0": res.relatorio_sa.temperatura_inicial,
                "custo_inicial": res.relatorio_sa.custo_inicial,
                "custo_final": res.relatorio_sa.custo_final,
                "limites": res.relatorio_sa.limites_normalizacao,
            },
        }
    dados["manual"] = {
        "cargas": {a.id: manual.horas_reais[a.id] for a in inst.analistas}
    }
    dados["equipes"] = {
        tipo.value: [a.id for a in equipe] for tipo, equipe in inst.equipes.items()
    }
    with open(f"{SAIDA}/exp_c_convergencia.json", "w") as fh:
        json.dump(dados, fh, indent=1, default=str)
    print("C: convergência, estágios e cargas gravados")


def experimento_d():
    horizontes = [7, 14, 21, 28, 42, 56, 70, 84]
    linhas = []
    for dias in horizontes:
        inst = gerar_instancia(dias=dias, seed=42)
        tracemalloc.start()
        t0 = time.perf_counter()
        res = pipeline.executar(inst, Pesos(), seed=42)
        tempo = time.perf_counter() - t0
        _, pico = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        linhas.append(
            {
                "dias": dias,
                "turnos": len(inst.turnos),
                "tempo_s": tempo,
                "memoria_mb": pico / (1024 * 1024),
                "valida": res.valida,
                "alocacoes": res.escala.total_alocacoes(),
            }
        )
        print(f"  {dias} dias: {tempo:.2f}s", flush=True)
    with open(f"{SAIDA}/exp_d_escalabilidade.json", "w") as fh:
        json.dump(linhas, fh, indent=1)
    print("D: escalabilidade gravada")


if __name__ == "__main__":
    {"a": experimento_a, "b": experimento_b, "c": experimento_c, "d": experimento_d}[
        sys.argv[1]
    ]()
