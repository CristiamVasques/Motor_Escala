"""
Interface de linha de comando do motor de escalonamento.

Exemplos:
    python -m motor_noc.cli executar --dias 28 --saida saida/
    python -m motor_noc.cli comparar --dias 28
    python -m motor_noc.cli gap
    python -m motor_noc.cli sensibilidade --passo 0.25
    python -m motor_noc.cli benchmark --dias 7 14 28
    python -m motor_noc.cli ahp --eq-sen 3 --eq-cob 0.5 --sen-cob 0.25
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from . import ahp as modulo_ahp
from . import metricas, saida
from .algoritmos.pipeline import executar
from .algoritmos.simulated_annealing import ParametrosSA
from .baseline import construir_escala_manual
from .gerador import gerar_instancia, gerar_instancia_reduzida
from .objetivo import Pesos


def _params_sa(args) -> ParametrosSA:
    return ParametrosSA(
        iteracoes=args.iteracoes,
        iteracoes_aquecimento=args.aquecimento,
        taxa_resfriamento=args.resfriamento,
    )


def _pesos(args) -> Pesos:
    return Pesos(alpha=args.alpha, delta=args.delta, lam=args.lam)


# ---------------------------------------------------------------------------
# Subcomandos
# ---------------------------------------------------------------------------


def cmd_executar(args) -> int:
    inst = gerar_instancia(dias=args.dias, seed=args.seed, fator_volume=args.volume)
    resultado = executar(
        inst,
        pesos=_pesos(args),
        seed=args.seed,
        params_sa=_params_sa(args),
        exigir_repouso_semanal=not args.sem_repouso_semanal,
    )

    relatorio = saida.relatorio_texto(inst, resultado)
    print(relatorio)
    if args.grade:
        print()
        print(saida.grade_visual(inst, resultado.escala))

    if args.saida:
        destino = Path(args.saida)
        saida.exportar_csv(
            saida.escala_como_linhas(inst, resultado.escala), destino / "escala.csv"
        )
        saida.exportar_csv(
            saida.cargas_como_linhas(inst, resultado.escala), destino / "cargas.csv"
        )
        saida.exportar_csv(
            metricas.curva_convergencia(resultado.relatorio_sa),
            destino / "curva_convergencia.csv",
        )
        saida.exportar_csv(
            metricas.ganho_por_estagio(resultado), destino / "ganho_por_estagio.csv"
        )
        saida.exportar_texto(relatorio, destino / "relatorio.txt")
        saida.exportar_texto(
            saida.grade_visual(inst, resultado.escala), destino / "grade.txt"
        )
        saida.exportar_json(
            {
                "instancia": inst.resumo(),
                "pesos": resultado.fo.pesos.como_dict(),
                "custo_final": resultado.custo_final(),
                "escala_valida": resultado.valida,
                "tempo_total_s": resultado.tempo_total_s,
                "estagios": metricas.ganho_por_estagio(resultado),
                "deficits_guloso": resultado.deficits_guloso,
                "violacoes_finais": resultado.relatorio_csp.violacoes_finais,
            },
            destino / "resumo.json",
        )
        print(f"\nArtefatos gravados em: {destino.resolve()}")

    return 0 if resultado.valida else 1


def cmd_comparar(args) -> int:
    inst = gerar_instancia(dias=args.dias, seed=args.seed, fator_volume=args.volume)
    resultado = executar(
        inst, pesos=_pesos(args), seed=args.seed, params_sa=_params_sa(args)
    )
    manual = construir_escala_manual(inst)
    comparacao = metricas.comparar_com_manual(
        inst, resultado.escala, manual, resultado.fo
    )

    print("=" * 78)
    print("MÉTRICA 5.1(a) — MOTOR versus ESCALA MANUAL POR RODÍZIO")
    print("=" * 78)
    chaves = list(comparacao["manual"].keys())
    print(f"{'Indicador':<34}{'Manual':>13}{'Motor':>13}{'Δ %':>12}")
    for chave in chaves:
        print(
            f"{chave:<34}{comparacao['manual'][chave]:>13.3f}"
            f"{comparacao['motor'][chave]:>13.3f}"
            f"{comparacao['variacao_percentual'][chave]:>12.1f}"
        )

    if args.saida:
        destino = Path(args.saida)
        saida.exportar_json(comparacao, destino / "comparacao_manual.json")
        print(f"\nArtefatos gravados em: {destino.resolve()}")
    return 0


def cmd_gap(args) -> int:
    inst = gerar_instancia_reduzida(seed=args.seed)
    params = ParametrosSA(
        iteracoes=3_000, iteracoes_aquecimento=500, max_iteracoes_sem_melhoria=1_200
    )
    resultado = executar(
        inst,
        pesos=_pesos(args),
        seed=args.seed,
        params_sa=params,
        cardinalidade_fixa=True,
    )
    relatorio = metricas.gap_otimalidade(
        inst, resultado, extras_max=args.extras, limite=args.limite
    )

    print("=" * 78)
    print("MÉTRICA 5.1(c) — GAP DE OTIMALIDADE EM INSTÂNCIA REDUZIDA")
    print("=" * 78)
    print(f"Instância: {inst.resumo()}")
    for chave, valor in relatorio.items():
        print(f"{chave:<26}: {valor}")

    if args.saida:
        saida.exportar_json(relatorio, Path(args.saida) / "gap_otimalidade.json")
    return 0


def cmd_sensibilidade(args) -> int:
    inst = gerar_instancia(dias=args.dias, seed=args.seed, fator_volume=args.volume)
    linhas = metricas.analise_sensibilidade(inst, passo=args.passo, seed=args.seed)

    print("=" * 90)
    print("MÉTRICA 5.1(e) — SENSIBILIDADE AOS PESOS ESTRUTURAIS")
    print("=" * 90)
    print(
        f"{'α':>6}{'δ':>7}{'λ':>7}{'F(X)':>10}{'f_bal':>11}{'f_sen':>8}"
        f"{'f_aten':>9}{'dist.Ham':>10}{'viol':>6}"
    )
    for linha in linhas:
        print(
            f"{linha['alpha']:>6.2f}{linha['delta']:>7.2f}{linha['lambda']:>7.2f}"
            f"{linha['custo_F']:>10.4f}{linha['f_balanceamento']:>11.2f}"
            f"{linha['f_senioridade']:>8.0f}{linha['f_atendimento']:>9.0f}"
            f"{linha['distancia_hamming_ref']:>10d}{linha['violacoes_rigidas']:>6d}"
        )

    if args.saida:
        saida.exportar_csv(linhas, Path(args.saida) / "sensibilidade.csv")
    return 0


def cmd_benchmark(args) -> int:
    medicoes = metricas.benchmark(tuple(args.dias), seed=args.seed)
    print("=" * 78)
    print("SIMULAÇÃO DE ESTRESSE — TEMPO E CONSUMO DE MEMÓRIA")
    print("=" * 78)
    print(
        f"{'Dias':>6}{'Analistas':>11}{'Turnos':>9}{'Tempo(s)':>11}"
        f"{'Memória(MB)':>13}{'F(X)':>9}{'Viol.':>7}"
    )
    for m in medicoes:
        print(
            f"{m.dias:>6}{m.analistas:>11}{m.turnos:>9}{m.tempo_s:>11.3f}"
            f"{m.memoria_pico_mb:>13.2f}{m.custo_final:>9.4f}"
            f"{m.violacoes_rigidas:>7}"
        )
    if args.saida:
        saida.exportar_csv(
            [asdict(m) for m in medicoes], Path(args.saida) / "benchmark.csv"
        )
    return 0


def cmd_ahp(args) -> int:
    resultado = modulo_ahp.calibrar_por_julgamentos(
        args.eq_sen, args.eq_cob, args.sen_cob
    )
    print("=" * 78)
    print("CALIBRAÇÃO DOS PESOS ESTRUTURAIS POR AHP (Saaty & Vargas, 2012)")
    print("=" * 78)
    for criterio, valor in resultado.vetor_prioridade.items():
        print(f"{criterio:<14}: {valor:.4f}")
    print(f"λ_max            : {resultado.lambda_max:.4f}")
    print(f"IC               : {resultado.indice_consistencia:.4f}")
    print(f"RC               : {resultado.razao_consistencia:.4f}")
    print(
        "Julgamentos "
        + ("CONSISTENTES (RC ≤ 0,10)." if resultado.consistente else "INCONSISTENTES: revisar comparações.")
    )
    pesos = resultado.pesos
    print(f"\nα={pesos.alpha:.4f}  δ={pesos.delta:.4f}  λ={pesos.lam:.4f}")

    if args.saida:
        saida.exportar_json(resultado.resumo(), Path(args.saida) / "ahp.json")
    return 0 if resultado.consistente else 1


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="motor_noc",
        description=(
            "Motor algorítmico para escalonamento de analistas em Centros de "
            "Operações de Rede."
        ),
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    def comuns(p, com_dias=True):
        if com_dias:
            p.add_argument("--dias", type=int, default=28, help="horizonte em dias")
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--alpha", type=float, default=1 / 3, help="peso da equidade")
        p.add_argument("--delta", type=float, default=1 / 3, help="peso da senioridade")
        p.add_argument("--lam", type=float, default=1 / 3, help="peso da cobertura")
        p.add_argument("--volume", type=float, default=1.0, help="fator de volume de alertas")
        p.add_argument("--iteracoes", type=int, default=20_000)
        p.add_argument("--aquecimento", type=int, default=1_500)
        p.add_argument("--resfriamento", type=float, default=0.95)
        p.add_argument("--saida", type=str, default=None, help="diretório de saída")

    p_exec = sub.add_parser("executar", help="gera a escala otimizada")
    comuns(p_exec)
    p_exec.add_argument("--grade", action="store_true", help="imprime a grade visual")
    p_exec.add_argument(
        "--sem-repouso-semanal",
        action="store_true",
        help="desativa a verificação do repouso semanal (art. 67 da CLT)",
    )
    p_exec.set_defaults(func=cmd_executar)

    p_cmp = sub.add_parser("comparar", help="compara com a escala manual (5.1a)")
    comuns(p_cmp)
    p_cmp.set_defaults(func=cmd_comparar)

    p_gap = sub.add_parser("gap", help="gap de otimalidade em instância reduzida (5.1c)")
    comuns(p_gap, com_dias=False)
    p_gap.add_argument(
        "--extras",
        type=int,
        default=0,
        help="alocações excedentes permitidas por turno na enumeração",
    )
    p_gap.add_argument("--limite", type=int, default=500_000)
    p_gap.set_defaults(func=cmd_gap)

    p_sens = sub.add_parser("sensibilidade", help="análise de sensibilidade (5.1e)")
    comuns(p_sens)
    p_sens.add_argument("--passo", type=float, default=0.25)
    p_sens.set_defaults(func=cmd_sensibilidade)

    p_bench = sub.add_parser("benchmark", help="simulação de estresse")
    p_bench.add_argument("--dias", type=int, nargs="+", default=[7, 14, 28])
    p_bench.add_argument("--seed", type=int, default=42)
    p_bench.add_argument("--saida", type=str, default=None)
    p_bench.set_defaults(func=cmd_benchmark)

    p_ahp = sub.add_parser("ahp", help="calibra α, δ, λ por AHP (6.6.5)")
    p_ahp.add_argument("--eq-sen", type=float, required=True, dest="eq_sen")
    p_ahp.add_argument("--eq-cob", type=float, required=True, dest="eq_cob")
    p_ahp.add_argument("--sen-cob", type=float, required=True, dest="sen_cob")
    p_ahp.add_argument("--saida", type=str, default=None)
    p_ahp.set_defaults(func=cmd_ahp)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = construir_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
