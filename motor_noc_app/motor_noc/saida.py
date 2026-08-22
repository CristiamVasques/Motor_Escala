"""Exportação de escalas, métricas e relatórios operacionais."""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from .algoritmos.pipeline import ResultadoPipeline
from .dominio import Instancia, Nivel, TipoTurno
from .escala import Escala
from .restricoes import validar, violacoes_flexiveis

SIGLAS = {
    TipoTurno.MATUTINO: "M",
    TipoTurno.COMERCIAL: "C",
    TipoTurno.VESPERTINO: "V",
    TipoTurno.NOTURNO: "N",
}


def _serializavel(obj):
    if is_dataclass(obj):
        return {k: _serializavel(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(_chave(k)): _serializavel(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_serializavel(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (Nivel, TipoTurno)):
        return obj.value
    return obj


def _chave(k):
    if isinstance(k, (Nivel, TipoTurno)):
        return k.value
    return k


def exportar_json(dados, caminho: Path) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(_serializavel(dados), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return caminho


def exportar_csv(linhas: Sequence[Dict], caminho: Path) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if not linhas:
        caminho.write_text("", encoding="utf-8")
        return caminho
    with caminho.open("w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        escritor.writeheader()
        for linha in linhas:
            escritor.writerow({k: _serializavel(v) for k, v in linha.items()})
    return caminho


def escala_como_linhas(inst: Instancia, escala: Escala) -> List[Dict]:
    linhas: List[Dict] = []
    for t in inst.turnos:
        for id_a in sorted(escala.analistas_em(t.id)):
            a = inst.analista(id_a)
            linhas.append(
                {
                    "data": t.inicio.strftime("%Y-%m-%d"),
                    "dia_semana": t.inicio.strftime("%a"),
                    "turno": t.tipo.value,
                    "inicio": t.inicio.strftime("%H:%M"),
                    "fim": t.fim.strftime("%H:%M"),
                    "id_turno": t.id,
                    "id_analista": a.id,
                    "analista": a.nome,
                    "nivel": a.nivel.value,
                    "capacidade": a.capacidade_atendimento,
                    "volume_alertas_turno": t.volume_alertas,
                }
            )
    return linhas


def cargas_como_linhas(inst: Instancia, escala: Escala) -> List[Dict]:
    return [
        {
            "id_analista": a.id,
            "analista": a.nome,
            "nivel": a.nivel.value,
            "equipe_fixa": a.turno_fixo.value,
            "turnos": len(escala.turnos_de(a.id)),
            "horas_reais": round(escala.horas_reais[a.id], 2),
            "horas_legais": round(escala.horas_legais[a.id], 2),
        }
        for a in inst.analistas
    ]


def grade_visual(inst: Instancia, escala: Escala) -> str:
    """Matriz analista × dia, no formato usual de conferência da gerência."""
    dias = inst.dias
    largura_nome = max(len(a.id) for a in inst.analistas) + 2
    cabecalho = " " * (largura_nome + 6) + " ".join(f"{d.day:02d}" for d in dias)
    linhas = [cabecalho]
    for tipo in TipoTurno:
        equipe = sorted(inst.equipes[tipo], key=lambda a: (a.nivel.value, a.id))
        if not equipe:
            continue
        linhas.append(f"-- {tipo.value} " + "-" * (len(cabecalho) - len(tipo.value) - 4))
        for a in equipe:
            marcas = []
            for d in dias:
                marcado = any(
                    inst.turno(tid).dia_civil == d for tid in escala.turnos_de(a.id)
                )
                marcas.append(SIGLAS[tipo] if marcado else " ·")
            linhas.append(
                f"{a.id:<{largura_nome}}{a.nivel.value:<6}" + " ".join(f"{m:>2}" for m in marcas)
            )
    return "\n".join(linhas)


def relatorio_texto(inst: Instancia, resultado: ResultadoPipeline) -> str:
    """Relatório analítico de desempenho, previsto no Objetivo Geral."""
    linhas: List[str] = []
    add = linhas.append

    add("=" * 78)
    add("MOTOR ALGORÍTMICO DE ESCALONAMENTO — RELATÓRIO DE EXECUÇÃO")
    add("=" * 78)
    resumo = inst.resumo()
    add(
        f"Instância: {resumo['analistas']} analistas | {resumo['turnos']} turnos | "
        f"{resumo['dias']} dias | {resumo['demanda_total_slots']} slots de demanda"
    )
    equipes = ", ".join(f"{k}={v}" for k, v in resumo["equipes"].items())
    add(f"Equipes fixas: {equipes}")
    pesos = resultado.fo.pesos
    add(
        f"Pesos estruturais: α={pesos.alpha:.3f}  δ={pesos.delta:.3f}  "
        f"λ={pesos.lam:.3f}"
    )
    add("")

    add("-" * 78)
    add("EVOLUÇÃO POR ESTÁGIO DO PIPELINE")
    add("-" * 78)
    add(
        f"{'Estágio':<26}{'F(X)':>10}{'Ganho':>10}{'Viol.':>8}"
        f"{'Aloc.':>8}{'Tempo(s)':>10}"
    )
    anterior = None
    for e in resultado.estagios:
        ganho = "—" if anterior is None else f"{anterior - e.custo:+.4f}"
        add(
            f"{e.nome:<26}{e.custo:>10.4f}{ganho:>10}{e.violacoes_rigidas:>8}"
            f"{e.alocacoes:>8}{e.tempo_s:>10.3f}"
        )
        anterior = e.custo
    add("")

    final = resultado.escala
    add("-" * 78)
    add("COMPONENTES DA FUNÇÃO OBJETIVO (solução final)")
    add("-" * 78)
    detalhe = resultado.fo.detalhar(final)
    for chave in ("balanceamento", "senioridade", "atendimento"):
        bruto = detalhe["brutos"][chave]
        norm = detalhe["normalizados"][chave]
        f_min, f_max = detalhe["limites_normalizacao"][chave]
        add(
            f"{chave:<18} bruto={bruto:>12.4f}  normalizado={norm:>7.4f}  "
            f"[min={f_min:.4f}; max={f_max:.4f}]"
        )
    add(f"{'F(X)':<18} {detalhe['custo']:.6f}")
    add("")

    sa = resultado.relatorio_sa
    if sa:
        add("-" * 78)
        add("SIMULATED ANNEALING")
        add("-" * 78)
        add(
            f"T0={sa.temperatura_inicial:.6f} | iterações={sa.iteracoes_executadas} | "
            f"aceitação={sa.taxa_aceitacao:.1%} | pioras aceitas="
            f"{sa.movimentos_piores_aceitos}"
        )
        add(f"Critério de parada: {sa.parou_por}")
        add("")

    hc = resultado.relatorio_hc
    if hc:
        add("-" * 78)
        add("HILL CLIMBING")
        add("-" * 78)
        add(
            f"iterações={hc.iteracoes} | movimentos aplicados="
            f"{hc.movimentos_aplicados} | ganho={hc.ganho:.6f}"
        )
        if hc.movimentos_por_tipo:
            add(
                "Movimentos: "
                + ", ".join(f"{k}={v}" for k, v in sorted(hc.movimentos_por_tipo.items()))
            )
        add("")

    csp_rel = resultado.relatorio_csp
    if csp_rel:
        add("-" * 78)
        add("CSP COM BACKTRACKING")
        add("-" * 78)
        add(
            f"violações na entrada={len(csp_rel.violacoes_iniciais)} | "
            f"alocações removidas={len(csp_rel.alocacoes_removidas)} | "
            f"slots em déficit={csp_rel.slots_em_deficit} | "
            f"nós explorados={csp_rel.nos_explorados}"
        )
        if csp_rel.violacoes_finais:
            add("ESCALA INVÁLIDA — violações remanescentes:")
            for v in csp_rel.violacoes_finais[:15]:
                add(f"  · {v}")
            if len(csp_rel.violacoes_finais) > 15:
                add(f"  ... e mais {len(csp_rel.violacoes_finais) - 15} violação(ões).")
        else:
            add("Escala válida: nenhuma restrição rígida violada.")
        add("")

    flex = violacoes_flexiveis(inst, final)
    add("-" * 78)
    add("RESTRIÇÕES FLEXÍVEIS")
    add("-" * 78)
    add(
        f"Analistas fora da faixa de equidade: "
        f"{int(flex['analistas_desequilibrados'])}/{int(flex['total_analistas'])} "
        f"({flex['taxa_desequilibrio']:.1%})"
    )
    add(
        f"Alocações superqualificadas em plantão N1: "
        f"{int(flex['alocacoes_superqualificadas'])}/"
        f"{int(flex['alocacoes_fds_apenas_n1'])} "
        f"({flex['taxa_superqualificacao']:.1%})"
    )
    add("")

    add("-" * 78)
    add("CARGA HORÁRIA POR EQUIPE FIXA")
    add("-" * 78)
    for tipo, equipe in inst.equipes.items():
        if not equipe:
            continue
        cargas = [final.horas_reais[a.id] for a in equipe]
        media = sum(cargas) / len(cargas)
        add(
            f"{tipo.value:<12} n={len(equipe):<3} média={media:6.1f}h  "
            f"mín={min(cargas):6.1f}h  máx={max(cargas):6.1f}h  "
            f"amplitude={max(cargas) - min(cargas):5.1f}h"
        )
    add("")
    add(f"Tempo total de execução: {resultado.tempo_total_s:.3f}s")
    add("=" * 78)
    return "\n".join(linhas)


def exportar_texto(conteudo: str, caminho: Path) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho
