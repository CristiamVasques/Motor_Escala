"""Suíte de testes do motor de escalonamento (biblioteca padrão: unittest)."""
from __future__ import annotations

import random
import statistics
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor_noc import ahp
from motor_noc.algoritmos import csp, guloso, hill_climbing, pipeline
from motor_noc.algoritmos import simulated_annealing as sa
from motor_noc.baseline import construir_escala_manual
from motor_noc.dominio import (
    FATOR_HORA_NOTURNA,
    Analista,
    Instancia,
    Nivel,
    TipoTurno,
    Turno,
)
from motor_noc.escala import Escala
from motor_noc.gerador import gerar_instancia, gerar_instancia_reduzida
from motor_noc.metricas import gap_otimalidade
from motor_noc.objetivo import FuncaoObjetivo, Normalizador, Pesos
from motor_noc.restricoes import (
    pode_alocar,
    sexta_anterior,
    terca_seguinte,
    validar,
)


def _analista(id_: str, nivel: Nivel, tipo: TipoTurno) -> Analista:
    return Analista(
        id=id_,
        nome=id_,
        nivel=nivel,
        turno_fixo=tipo,
        competencias=frozenset({"ZABBIX", "LINUX"}),
        capacidade_atendimento=12,
    )


def _turno(
    id_: str,
    dia: date,
    hora: int,
    tipo: TipoTurno = TipoTurno.MATUTINO,
    minimo=None,
    volume: int = 10,
    duracao: float = 8.0,
) -> Turno:
    return Turno(
        id=id_,
        tipo=tipo,
        inicio=datetime(dia.year, dia.month, dia.day, hora),
        duracao_horas=duracao,
        min_requerido=minimo or {Nivel.N1: 1},
        competencias_requeridas=frozenset({"ZABBIX"}),
        volume_alertas=volume,
    )


class TestCalendario(unittest.TestCase):
    def test_sexta_anterior_e_terca_seguinte(self):
        sabado = date(2026, 3, 7)
        domingo = date(2026, 3, 8)
        self.assertEqual(sexta_anterior(sabado), date(2026, 3, 6))
        self.assertEqual(sexta_anterior(domingo), date(2026, 3, 6))
        self.assertEqual(terca_seguinte(sabado), date(2026, 3, 10))
        self.assertEqual(terca_seguinte(domingo), date(2026, 3, 10))


class TestRestricoesRigidas(unittest.TestCase):
    def test_turno_unico_diario(self):
        a = _analista("A1", Nivel.N1, TipoTurno.MATUTINO)
        dia = date(2026, 3, 2)
        t1 = _turno("T1", dia, 6)
        t2 = _turno("T2", dia, 6)
        inst = Instancia([a], [t1, t2])
        escala = Escala(inst)
        escala.alocar("A1", "T1")
        self.assertFalse(pode_alocar(inst, escala, a, t2))

    def test_interjornada_minima(self):
        a = _analista("A1", Nivel.N1, TipoTurno.MATUTINO)
        t1 = _turno("T1", date(2026, 3, 2), 14)  # termina às 22h
        t2 = _turno("T2", date(2026, 3, 3), 6)  # início 8h depois
        t3 = _turno("T3", date(2026, 3, 3), 9)  # início 11h depois
        inst = Instancia([a], [t1, t2, t3])
        escala = Escala(inst)
        escala.alocar("A1", "T1")
        self.assertFalse(pode_alocar(inst, escala, a, t2))
        self.assertTrue(pode_alocar(inst, escala, a, t3))

    def test_teto_semanal_de_44_horas(self):
        a = _analista("A1", Nivel.N1, TipoTurno.MATUTINO)
        inicio = date(2026, 3, 2)
        turnos = [
            _turno(f"T{i}", inicio + timedelta(days=i), 6) for i in range(7)
        ]
        inst = Instancia([a], turnos)
        escala = Escala(inst)
        for i in range(5):  # 40 horas acumuladas
            escala.alocar("A1", f"T{i}")
        # O sexto turno levaria a 48h na mesma janela de 7 dias.
        self.assertFalse(
            pode_alocar(inst, escala, a, inst.turno("T5"), exigir_repouso_semanal=False)
        )

    def test_hora_noturna_reduzida(self):
        t = _turno(
            "TN", date(2026, 3, 2), 22, tipo=TipoTurno.NOTURNO, duracao=8.0
        )
        self.assertAlmostEqual(t.duracao_horas, 8.0)
        self.assertAlmostEqual(t.duracao_legal, 8.0 * FATOR_HORA_NOTURNA)
        self.assertGreater(t.duracao_legal, t.duracao_horas)

    def test_folga_cascata_bloqueia_sexta_e_terca(self):
        a = _analista("A1", Nivel.N1, TipoTurno.MATUTINO)
        sabado = date(2026, 3, 7)
        t_sab = _turno("TSAB", sabado, 6)
        t_sex = _turno("TSEX", date(2026, 3, 6), 6)
        t_ter = _turno("TTER", date(2026, 3, 10), 6)
        t_qua = _turno("TQUA", date(2026, 3, 11), 6)
        inst = Instancia([a], [t_sex, t_sab, t_ter, t_qua])
        escala = Escala(inst)
        escala.alocar("A1", "TSAB")
        self.assertFalse(pode_alocar(inst, escala, a, t_sex))
        self.assertFalse(pode_alocar(inst, escala, a, t_ter))
        self.assertTrue(pode_alocar(inst, escala, a, t_qua))

    def test_folga_cascata_no_sentido_inverso(self):
        """Alocar a sexta primeiro deve impedir o plantão de sábado."""
        a = _analista("A1", Nivel.N1, TipoTurno.MATUTINO)
        t_sex = _turno("TSEX", date(2026, 3, 6), 6)
        t_sab = _turno("TSAB", date(2026, 3, 7), 6)
        inst = Instancia([a], [t_sex, t_sab])
        escala = Escala(inst)
        escala.alocar("A1", "TSEX")
        self.assertFalse(pode_alocar(inst, escala, a, t_sab))

    def test_competencia_tecnica_obrigatoria(self):
        a = Analista("A1", "A1", Nivel.N1, TipoTurno.NOTURNO, frozenset({"ZABBIX"}), 12)
        t = Turno(
            "T1",
            TipoTurno.NOTURNO,
            datetime(2026, 3, 2, 22),
            8.0,
            {Nivel.N1: 1},
            frozenset({"ZABBIX", "AVAYA"}),
            10,
        )
        inst = Instancia([a], [t])
        self.assertFalse(pode_alocar(inst, Escala(inst), a, t))

    def test_turno_fixo_contratual(self):
        a = _analista("A1", Nivel.N1, TipoTurno.MATUTINO)
        t = _turno("T1", date(2026, 3, 2), 22, tipo=TipoTurno.NOTURNO)
        inst = Instancia([a], [t])
        self.assertFalse(pode_alocar(inst, Escala(inst), a, t))


class TestEscalaIncremental(unittest.TestCase):
    """As estatísticas mantidas em O(1) devem coincidir com o cálculo direto."""

    def setUp(self):
        self.inst = gerar_instancia(dias=7, seed=3)
        self.escala, _ = guloso.construir(self.inst, random.Random(3))

    def _f_bal_forca_bruta(self) -> float:
        total = 0.0
        for equipe in self.inst.equipes.values():
            if not equipe:
                continue
            cargas = [self.escala.horas_reais[a.id] for a in equipe]
            media = sum(cargas) / len(cargas)
            total += sum((h - media) ** 2 for h in cargas) / len(cargas)
        return total

    def _f_aten_forca_bruta(self) -> float:
        total = 0.0
        for t in self.inst.turnos:
            capacidade = sum(
                self.inst.analista(i).capacidade_atendimento
                for i in self.escala.analistas_em(t.id)
            )
            total += abs(t.volume_alertas - capacidade)
        return total

    def test_componentes_incrementais_coincidem(self):
        self.assertAlmostEqual(
            self.escala.f_balanceamento, self._f_bal_forca_bruta(), places=6
        )
        self.assertAlmostEqual(
            self.escala.f_atendimento, self._f_aten_forca_bruta(), places=6
        )

    def test_alocar_e_desalocar_sao_reversiveis(self):
        antes = self.escala.componentes()
        turnos = [t for t in self.inst.turnos if inst_livre(self.inst, self.escala, t)]
        if not turnos:
            self.skipTest("sem turno com candidato livre nesta instância")
        t = turnos[0]
        livre = next(
            a for a in self.inst.candidatos[t.id]
            if a.id not in self.escala.analistas_em(t.id)
        )
        self.escala.alocar(livre.id, t.id)
        self.escala.desalocar(livre.id, t.id)
        depois = self.escala.componentes()
        for chave in antes:
            self.assertAlmostEqual(antes[chave], depois[chave], places=6)


def inst_livre(inst, escala, t) -> bool:
    return any(
        a.id not in escala.analistas_em(t.id) for a in inst.candidatos[t.id]
    )


class TestNormalizador(unittest.TestCase):
    def test_truncamento_em_zero_um(self):
        n = Normalizador()
        n.observar({"balanceamento": 100.0, "senioridade": 4.0, "atendimento": 200.0})
        n.congelar()
        fora = n.normalizar(
            {"balanceamento": 500.0, "senioridade": -1.0, "atendimento": 0.0}
        )
        self.assertEqual(fora["balanceamento"], 1.0)
        self.assertEqual(fora["senioridade"], 0.0)
        self.assertEqual(fora["atendimento"], 0.0)

    def test_componente_constante_e_anulada(self):
        n = Normalizador()
        n.observar({"balanceamento": 0.0, "senioridade": 0.0, "atendimento": 0.0})
        n.congelar()
        saida = n.normalizar(
            {"balanceamento": 0.0, "senioridade": 0.0, "atendimento": 0.0}
        )
        self.assertEqual(saida["senioridade"], 0.0)  # sem indeterminação numérica

    def test_limites_permanecem_congelados(self):
        n = Normalizador()
        n.observar({"balanceamento": 10.0, "senioridade": 1.0, "atendimento": 10.0})
        n.congelar()
        n.observar({"balanceamento": 999.0, "senioridade": 99.0, "atendimento": 999.0})
        self.assertEqual(n.maximos["balanceamento"], 10.0)


class TestPesos(unittest.TestCase):
    def test_soma_unitaria_e_normalizada(self):
        p = Pesos(2, 2, 4)
        self.assertAlmostEqual(p.alpha + p.delta + p.lam, 1.0)
        self.assertAlmostEqual(p.lam, 0.5)

    def test_pesos_invalidos(self):
        with self.assertRaises(ValueError):
            Pesos(0, 0, 0)


class TestAHP(unittest.TestCase):
    def test_matriz_consistente(self):
        # Julgamentos perfeitamente consistentes: RC deve ser ~0.
        matriz = [[1, 2, 4], [0.5, 1, 2], [0.25, 0.5, 1]]
        r = ahp.calibrar(matriz)
        self.assertLess(r.razao_consistencia, 1e-6)
        self.assertTrue(r.consistente)
        self.assertAlmostEqual(r.pesos.alpha, 4 / 7, places=4)

    def test_matriz_inconsistente_detectada(self):
        matriz = [[1, 9, 1 / 9], [1 / 9, 1, 9], [9, 1 / 9, 1]]
        r = ahp.calibrar(matriz)
        self.assertFalse(r.consistente)

    def test_julgamentos_pareados(self):
        r = ahp.calibrar_por_julgamentos(3, 5, 2)
        self.assertAlmostEqual(
            r.pesos.alpha + r.pesos.delta + r.pesos.lam, 1.0, places=6
        )
        self.assertGreater(r.pesos.alpha, r.pesos.lam)


class TestPipeline(unittest.TestCase):
    def test_escala_final_e_valida(self):
        inst = gerar_instancia(dias=14, seed=42)
        resultado = pipeline.executar(inst, seed=42)
        self.assertTrue(
            resultado.valida,
            msg=f"violações: {resultado.relatorio_csp.violacoes_finais[:5]}",
        )
        self.assertEqual(len(validar(inst, resultado.escala)), 0)

    def test_custo_nao_aumenta_nos_estagios_heuristicos(self):
        inst = gerar_instancia(dias=14, seed=11)
        resultado = pipeline.executar(inst, seed=11)
        custos = [e.custo for e in resultado.estagios]
        self.assertLessEqual(custos[1], custos[0] + 1e-9)  # Hill Climbing
        self.assertLessEqual(custos[2], custos[1] + 1e-9)  # Simulated Annealing

    def test_determinismo_com_mesma_semente(self):
        inst = gerar_instancia(dias=7, seed=5)
        r1 = pipeline.executar(inst, seed=5)
        r2 = pipeline.executar(inst, seed=5)
        self.assertEqual(r1.escala.distancia_hamming(r2.escala), 0)

    def test_motor_responde_a_repriorizacao(self):
        inst = gerar_instancia(dias=14, seed=42)
        so_equidade = pipeline.executar(inst, Pesos(1, 0, 0), seed=42)
        so_senioridade = pipeline.executar(inst, Pesos(0, 1, 0), seed=42)
        self.assertLess(
            so_equidade.escala.f_balanceamento,
            so_senioridade.escala.f_balanceamento,
        )

    def test_supera_a_escala_manual(self):
        inst = gerar_instancia(dias=14, seed=42)
        resultado = pipeline.executar(inst, seed=42)
        manual = construir_escala_manual(inst)
        self.assertLessEqual(
            resultado.fo.custo(resultado.escala), resultado.fo.custo(manual)
        )


class TestCSP(unittest.TestCase):
    def test_reparo_de_escala_corrompida(self):
        """Injeta violações deliberadas e verifica a atuação do Backtracking."""
        inst = gerar_instancia(dias=14, seed=9)
        escala, _ = guloso.construir(inst, random.Random(9))
        self.assertEqual(len(validar(inst, escala)), 0)

        # Corrompe: remove analistas de três turnos, gerando déficit.
        alvos = [t for t in inst.turnos if escala.analistas_em(t.id)][:3]
        for t in alvos:
            for id_a in list(escala.analistas_em(t.id)):
                escala.desalocar(id_a, t.id)
        self.assertGreater(len(validar(inst, escala)), 0)

        rel = csp.validar_e_reparar(inst, escala)
        self.assertGreater(len(rel.violacoes_iniciais), 0)
        self.assertTrue(rel.escala_valida, msg=str(rel.violacoes_finais[:5]))

    def test_remove_alocacao_que_viola_restricao_individual(self):
        a = _analista("A1", Nivel.N1, TipoTurno.MATUTINO)
        t1 = _turno("T1", date(2026, 3, 2), 6, minimo={Nivel.N1: 0})
        t2 = _turno("T2", date(2026, 3, 2), 6, minimo={Nivel.N1: 0})
        inst = Instancia([a], [t1, t2])
        escala = Escala(inst)
        # Dupla alocação no mesmo dia civil, inserida à revelia das verificações.
        escala.alocar("A1", "T1")
        escala._por_turno["T2"].add("A1")
        escala._por_analista["A1"].add("T2")
        escala._niveis["T2"][Nivel.N1] += 1
        self.assertGreater(len(validar(inst, escala)), 0)

        rel = csp.validar_e_reparar(inst, escala)
        self.assertTrue(rel.escala_valida)


class TestMetricas(unittest.TestCase):
    def test_gap_de_otimalidade_nao_negativo(self):
        inst = gerar_instancia_reduzida(seed=7)
        params = sa.ParametrosSA(
            iteracoes=2_000, iteracoes_aquecimento=300, max_iteracoes_sem_melhoria=800
        )
        resultado = pipeline.executar(inst, seed=7, params_sa=params)
        relatorio = gap_otimalidade(inst, resultado, extras_max=1, limite=50_000)
        self.assertNotIn("erro", relatorio)
        self.assertGreaterEqual(relatorio["gap_absoluto"], -1e-9)
        self.assertGreater(relatorio["solucoes_enumeradas"], 0)

    def test_escala_manual_e_factivel(self):
        inst = gerar_instancia(dias=14, seed=42)
        manual = construir_escala_manual(inst)
        violacoes = [v for v in validar(inst, manual) if v.tipo != "DEMANDA_MINIMA"]
        self.assertEqual(violacoes, [], msg=str(violacoes[:3]))



class TestHoraNoturnaReduzida(unittest.TestCase):
    """Art. 73, § 1º da CLT e Súmula 60, II, do TST — Tabela 4 do TCC."""

    def _turno(self, hora, minuto, presenca_h, tipo, intervalo=1.0):
        return Turno(
            id="T",
            tipo=tipo,
            inicio=datetime(2026, 3, 2, hora, minuto),
            duracao_horas=presenca_h,
            min_requerido={Nivel.N1: 1},
            competencias_requeridas=frozenset(),
            volume_alertas=10,
            intervalo_horas=intervalo,
        )

    def test_reproduz_a_tabela_de_turnos_do_tcc(self):
        casos = [
            (TipoTurno.MATUTINO, 5, 40, 9.8, 8.8),
            (TipoTurno.COMERCIAL, 8, 0, 9.8, 8.8),
            (TipoTurno.VESPERTINO, 12, 12, 9.8, 8.8),
            (TipoTurno.NOTURNO, 21, 40, 8 + 20 / 60, 8 + 20 / 60),
        ]
        for tipo, hora, minuto, presenca, esperado in casos:
            with self.subTest(tipo=tipo):
                t = self._turno(hora, minuto, presenca, tipo)
                self.assertAlmostEqual(t.duracao_legal, esperado, places=4)

    def test_fator_incide_so_sobre_a_parcela_noturna(self):
        """O turno inicia às 21h40: os 20 minutos iniciais são diurnos."""
        t = self._turno(21, 40, 8 + 20 / 60, TipoTurno.NOTURNO, intervalo=0.0)
        noturnas, diurnas = t._particao_noturna()
        self.assertAlmostEqual(diurnas, 20 / 60, places=4)
        self.assertAlmostEqual(noturnas, 8.0, places=4)
        # Aplicar o fator ao turno inteiro daria um valor maior e incorreto.
        self.assertLess(t.duracao_legal, t.duracao_horas * FATOR_HORA_NOTURNA)

    def test_turno_encerrado_as_22h_nao_tem_parcela_noturna(self):
        t = self._turno(12, 12, 9.8, TipoTurno.VESPERTINO, intervalo=0.0)
        noturnas, _ = t._particao_noturna()
        self.assertAlmostEqual(noturnas, 0.0, places=6)

    def test_prorrogacao_apos_as_5h_e_computada_como_noturna(self):
        """Súmula 60, II do TST: a prorrogação da jornada noturna é reduzida."""
        t = self._turno(22, 0, 8.0, TipoTurno.NOTURNO, intervalo=0.0)
        noturnas, diurnas = t._particao_noturna()
        self.assertAlmostEqual(noturnas, 8.0, places=4)
        self.assertAlmostEqual(diurnas, 0.0, places=6)

    def test_jornada_trabalhada_desconta_o_intervalo(self):
        t = self._turno(5, 40, 9.8, TipoTurno.MATUTINO, intervalo=1.0)
        self.assertAlmostEqual(t.duracao_trabalhada, 8.8, places=4)
        self.assertAlmostEqual(t.duracao_horas, 9.8, places=4)


class TestHonestidadeDoGap(unittest.TestCase):
    """A métrica 5.1(c) não deve afirmar otimalidade sem lastro."""

    def setUp(self):
        self.inst = gerar_instancia_reduzida()
        self.resultado = pipeline.executar(
            self.inst, seed=42, cardinalidade_fixa=True
        )

    def test_enumeracao_truncada_nao_afirma_otimalidade(self):
        rel = gap_otimalidade(self.inst, self.resultado, extras_max=1, limite=500)
        self.assertTrue(rel["limite_atingido"])
        self.assertFalse(rel["enumeracao_exaustiva"])
        self.assertIsNone(rel["motor_atingiu_otimo"])
        self.assertTrue(rel["ressalvas"])
        self.assertIn("truncada", rel["referencia"])

    def test_espacos_incompativeis_sao_sinalizados(self):
        rel = gap_otimalidade(self.inst, self.resultado, extras_max=1, limite=500_000)
        self.assertFalse(rel["espacos_compativeis"])
        self.assertIsNone(rel["motor_atingiu_otimo"])

    def test_enumeracao_exaustiva_permite_afirmar_otimalidade(self):
        rel = gap_otimalidade(self.inst, self.resultado, extras_max=0, limite=500_000)
        self.assertTrue(rel["enumeracao_exaustiva"])
        self.assertTrue(rel["espacos_compativeis"])
        self.assertEqual(rel["ressalvas"], [])
        self.assertIsInstance(rel["motor_atingiu_otimo"], bool)
        self.assertIn("ótimo global", rel["referencia"])

    def test_motor_e_enumeracao_com_a_mesma_cardinalidade(self):
        rel = gap_otimalidade(self.inst, self.resultado, extras_max=0, limite=500_000)
        self.assertEqual(
            rel["cardinalidade_enumerada_min"], rel["cardinalidade_enumerada_max"]
        )
        self.assertEqual(rel["cardinalidade_motor"], rel["cardinalidade_enumerada_min"])


if __name__ == "__main__":
    unittest.main(verbosity=2)