"""Testes do cálculo de venda."""
from app.services.venda import calcular_venda, rendimento_padrao


def test_rendimento_padrao_por_tipo():
    assert rendimento_padrao("Vaca") == 0.48
    assert rendimento_padrao("Novilha") == 0.50
    assert rendimento_padrao("Boi") == 0.52
    # Tipo desconhecido cai no padrão de novilha.
    assert rendimento_padrao("Bezerro") == 0.50
    assert rendimento_padrao(None) == 0.50


def test_calcular_venda():
    # Boi de 500 kg, 52% de rendimento, @ a R$ 300.
    # carcaça = 260 kg -> 260/15 = 17,333 @ -> R$ 5.200,00 (arroba de carcaça = 15 kg)
    res = calcular_venda(peso=500, rendimento=0.52, preco_arroba=300)
    assert res["peso_carcaca"] == 260.0
    assert res["arroba_liquida"] == 17.33
    assert res["valor_recebido"] == 5200.0
