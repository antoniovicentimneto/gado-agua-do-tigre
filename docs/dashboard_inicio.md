# Tela inicial: estudo, crítica e decisão (out/2026)

Pergunta: o que o dono precisa ver ao abrir o app? O estudo partiu dos dados reais do banco
em 30/10/2026: 390 animais ativos, 5.568 pesagens, 2.985 lançamentos financeiros.

## O que a crítica derrubou

| Candidato | Veredito | Motivo |
|---|---|---|
| Total de animais, nº de pesagens | Fora | Só sobe. Não leva a nenhuma decisão. |
| GMD médio antigo (média dos GMDs individuais) | Trocado | Animal com 10 dias pesa igual a quem tem 1 ano, e mistura o histórico inteiro. |
| Comparar com o período anterior | Trocado | O ganho vai de ~0,2 a ~0,8 kg/dia conforme a época. Só vale comparar com o mesmo período do ano anterior. |
| Resultado da fazenda inteira | Rebaixado | Em 2025 o setor Sede teve R$ 2,6 mi de arrendamento e o Pessoal, R$ 0,8 mi de saída. Esse número não diz nada sobre o gado. |
| Lucro = receita − despesa | Separado | Comprar gado aparece como despesa (R$ 1,4 mi em 2025), mas o gado continua na fazenda. A compra aparece à parte. |
| Lotação histórica (UA/ha) | Em espera | Só 2 ocupações registradas e 5 de 6 lotes sem piquete. Daria um número baixo falso. |
| Produção por hectare (@/ha) | Em espera | 200 dos 381 ha são de inverno, e não dá para saber onde cada lote esteve. |
| Valor de compra (tabela Compra) | Fora | 544 registros somam só R$ 72 mil: incompleto. O custo vem do Financeiro. |
| Natalidade, intervalo entre partos | Em espera | Só 12 animais têm mãe registrada. |
| Sal e sanidade | Em espera | Nenhum registro ainda. A tela já avisa carência quando houver. |

## O que ficou

1. **Rebanho hoje:** cabeças, @ em pé, UA e valor estimado (dono). Peso estimado até hoje, marcado com "~".
2. **Pede atenção:** a lista do que fazer, cada linha leva até o lugar certo.
3. **Rebanho por categoria:** cada linha abre os animais.
4. **Desempenho do gado:** GMD, @ produzidas, mortalidade e "em dia na balança", com período próprio.
5. **Resultado da pecuária (dono):** saldo, custo da @ produzida, sobra por @ e próximos 30 dias, com período próprio.
6. **Lotes:** tabela ordenável; a linha abre os animais do lote.

"Em dia na balança" fica entre os indicadores principais porque diz quanto dá para confiar nos outros.

## Contas

- **GMD do rebanho** = kg ganhos ÷ animal-dias entre pesagens seguidas de todos os animais,
  inclusive os já vendidos. Intervalo que atravessa o período conta só a parte de dentro.
- **Fora da conta:** pesagens com menos de 7 dias de intervalo e ganho fora de −1,5 a 3 kg/dia
  (repesagem ou erro de digitação).
- **@ produzidas** = kg ganhos × rendimento do tipo ÷ 15 kg de carcaça.
- **Mortalidade** = (mortos + perdidos) ÷ rebanho médio do período. Sem anualizar.
- **Custeio** = despesas do setor Pecuária, menos Aquisição de rebanho, Investimentos, Captação
  de crédito e Retirada de lucro.
- **Custo da @ produzida** = custeio ÷ @ produzidas. Não inclui rateio de Sede e Máquinas, então
  o custo real é maior.
- **Sobra por @** = preço médio da @ vendida − custo da @ produzida. É uma aproximação: compara
  o que foi vendido com o que foi produzido no período.
- **Financeiro:** só o realizado, com a mesma regra da aba Resultado (venceu = realizado).

## Achados nos dados (para o Antonio decidir)

- **GMD de referência corrigido em 30/10/2026, a pedido do Antonio.** Era águas (out–mar) 0,5 e seca
  (abr–set) 0,2. Passou a Inverno (jul–set) 0,67 e Resto do ano (out–jun) 0,33, média medida na balança
  de jul/2024 a out/2026. O valor antigo está no log de alterações. Vale só para lote sem GMD próprio.
- **Ganho caiu:** 0,367 kg/dia nos últimos 12 meses contra 0,526 nos 12 anteriores. A base do ano
  anterior tem menos animais pesados até mai/2025, então a queda pode estar exagerada.
- **Mortalidade acima do limite:** 3,3% nos últimos 12 meses (13 mortos, 1 perdido). O limite de 2%
  é um valor de partida, editável em Config › Alertas.
- **Pecuária sem receita desde jun/2026 no Financeiro,** embora tenha havido vendas no manejo. Enquanto
  as vendas não forem fechadas, saldo e sobra por @ ficam incompletos. A tela mostra quantas faltam.
