# Financeiro — engenharia reversa da planilha CONSIPA e proposta de app

Arquivo analisado: `08 - SISTEMA CONSIPA 4.39_2804 - Atualizado.xlsm` (11,8 MB, out/2026).
Produtor no menu: Luiz Zanetti Jr · Fazenda Boa Vistinha · técnico Jean Mezzalira.

---

## 1. O que a planilha é, por dentro

É um "sistema" comercial (Consipa) feito em Excel: **63 abas, 11 tabelas, 12 tabelas
dinâmicas, 11 segmentações, 3 linhas do tempo, 12 gráficos e ~30 macros VBA**. Mas tudo gira
em torno de **uma tabela só**:

### 1.1 `CentralReal` (tabela `tblCentralReal`) — o livro de lançamentos

2.479 linhas (de 2020 a 2027, grosso em 2025–2026). Cada linha = **uma parcela**.
São 23 colunas digitadas + 35 colunas calculadas.

| Coluna digitada | Uso real |
|---|---|
| DATA CONTÁBIL | data da compra/competência |
| DATA FLUXO | data em que o dinheiro sai (vencimento da parcela) |
| STATUS | REALIZADO / PREVISTO (fórmula: data fluxo ≤ hoje → realizado) |
| SETOR | SEDE, PECUÁRIA DE CORTE, PESSOAL, MÁQUINAS, PECUÁRIA DE LEITE, AGRICULTURA, INVENTÁRIO, CONFIGURAÇÕES |
| ENTRADAS/SAÍDAS | 1. DESPESA (2.059), 2. RECEITA (44), 5. ATIVIDADE/6. TERRAS (inventário) |
| CENTRAL DE CUSTO | nível 2 do plano de contas (ex.: 1.01. RECURSOS HUMANOS) |
| CATEGORIA | nível 3 (ex.: 1.01.09. PRÓ LABORE) |
| ITEM / SUBITEM | níveis 4 e 5 — quase não usados (1.291 linhas com 0) |
| Nº NOTA FISCAL | preenchido em só ~44% das compras |
| FORNECEDOR | texto livre (381 nomes distintos) |
| DESCRIÇÃO | texto livre (1.589 distintas) |
| Nº DE PARCELAS, QUANTIDADE, VALOR UNITÁRIO | valor da compra |
| @/KG/L/SACA, UNIDADE, RENDIMENTO | só para compra/venda de gado e grãos |
| DESCONTO/ÁGIO, OBSERVAÇÃO | pouco usados |
| CONTA | Banco do Brasil, Santander, Sicoob, cartões BB/Santander/Sicoob, Itaú, Bradesco, Frísia |
| FAZENDA | **nunca usada** (0 linhas) |

Colunas calculadas que importam:
- **VALOR TOTAL** = (unitário − desconto) × qtde × @/kg ÷ nº de parcelas (já é o valor **da parcela**).
- **VALOR COM SINAL** = −valor para despesa, +valor para receita → é o que a tabela dinâmica soma.
- **MÊS/ANO FLUXO** e **MÊS/ANO CONTÁBIL** = 1º dia do mês das duas datas (as duas visões:
  caixa e competência).
- PESO KG/@, PREÇO POR KG/@ = para gado (arroba de 15 kg com rendimento padrão 50%).
- Colunas de estoque, talhão, "último item", animal adicionado/subtraído = para os módulos de
  estoque/rebanho (pouco ou nada usados aqui).

### 1.2 Como se lança hoje (as abas `Cad…`)

São 36 abas-formulário (`CadPesDesp`, `CadAgrDesp`, `CadPecCorDesp`, `CadMaqDesp`, ... uma por
setor × tipo). Todas iguais:

1. Preenche C2:C18 (real/projetado, data, nº de parcelas, tipo de parcela mensal/anual,
   central, categoria, item, NF, fornecedor, descrição, qtde, valor, conta...). Pode digitar as
   datas de pagamento à mão em F4:F15.
2. Fórmulas em I8:AB19 geram **uma linha por parcela** (data fluxo = data + n meses, ou as datas
   digitadas).
3. Macro `CadastrarCentral` copia essas linhas como valor para o fim da `CentralReal`, limpa o
   formulário e guarda o último lançamento em AH2:AH18 (botão "Carregar" repete o último).

Ou seja: **não há validação nenhuma**, não há edição (corrigir = mexer direto na tabela), e cada
parcela vira uma linha solta (se errar o valor, tem que corrigir em N linhas).

### 1.3 Plano de contas (`Listas`)

Hierarquia em 5 níveis, com chaves concatenadas para os menus suspensos dependentes:
`SETOR (8) › ENTRADAS/SAÍDAS (50) › CENTRAL DE CUSTO (225) › CATEGORIA (410) › ITEM (790) › SUBITEM (266)`.
Também: `tblAnimais` (13 categorias de gado), `tblUnidades`, `tblFazenda`.

Na prática a fazenda usa **3 níveis** (setor › central › categoria) e ~80 categorias.
Os mais usados: Infraestrutura, Encargos trabalhistas, Diárias, Cães e gatos, Bancos/tarifas,
Luz, Sanidade, Salário, Mercado, Escritório, Vale alimentação, ITR, IRPF, Aquisição de bovinos.

### 1.4 A tela que você gosta (`DashResultados`)

É a **tabela dinâmica "Tabela dinâmica5"** sobre a `tblCentralReal`:
- Linhas: Projeção/Real › Entradas/Saídas › Central de custo › Categoria › Descrição
  (abre e fecha com o +/−).
- Colunas: MÊS/ANO FLUXO (mês de pagamento).
- Valor: soma do VALOR COM SINAL.
- Filtros: linha do tempo de mês + segmentações de SETOR, STATUS, CENTRAL, CATEGORIA.
- **Duplo clique num número = o Excel abre uma aba nova com todos os lançamentos que formam
  aquele valor** (é recurso nativo da tabela dinâmica, "mostrar detalhes"). É isso que permite
  achar o lançamento errado.

### 1.5 As outras abas

| Grupo | Abas | Serve pra quê | Vale levar? |
|---|---|---|---|
| Dados | CentralReal | livro de lançamentos | **Sim — migrar tudo** |
| Plano de contas | Listas, ChaveItem | hierarquia e menus | **Sim**, simplificado a 3 níveis (+ item opcional) |
| Lançamento | 36 abas Cad… | formulários | Não — substituir por 1 tela de lançamento |
| Visões | DashResultados, DashDespMes (lista por mês), DashGeral (receita/despesa/custeio/investimento por mês e setor), DashComparacao (real × projetado, saldo acumulado) | relatórios | **Sim** — virar 2–3 telas do app |
| Saldos | Saldos (saldo por conta/mês) | está **vazia** (fórmulas sem saldo inicial) | Sim, mas como conciliação com extrato |
| Projeção | CentralProjecao, HistProj, RelatorioProjecao, DashDespMesProj + macros gerar/salvar/apagar projeção | orçamento = repete o ano anterior (+ IGPM, que está 0) | Depois — "previsto" já cobre boa parte |
| Rebanho/zootecnia | EvolucaoRebanho, Zootecnia, DashEvolRebanho, DashCorte, DashLeite, DashEstoque, Inventário | controle de animais por categoria | Não — o app do gado já faz isso melhor (por animal) |
| Agricultura | Talhoes, DashTalhao, CadAgr… | custo por talhão | Não usado (15 linhas) |
| TIR | DashTIR | retorno de investimento | Não usado |
| Cadastros | Clientes, Fornecedores (tabelas dinâmicas sobre a descrição), Cad… | listas | Fornecedor **sim**, como cadastro de verdade (CNPJ) |
| Sistema | Menu, Configuracoes, Dashboards | navegação, nome, mês inicial | Não |

Macros: `CadastrarCentral` (lançar), `Carregar`/`Duplicar` (repetir), `OrdenarTabelasLista`,
`gerar/salvar/apagar_projecao`, `pdf_*` (exportar PDF), `ConfigurarLayout`/`ReverterLayout`
(esconder faixa de opções, com senha), bloqueio de abas com senha, e um `Workbook_Open` que
**fecha a planilha sozinha se ela não estiver numa pasta com "Drive" no caminho** (trava de
cópia do fornecedor). Nada de integração com nota, banco ou internet.

---

## 2. Problemas encontrados nos dados (o que dificulta enxergar os números)

- **~400 lançamentos sem categoria** (categoria "0") — caem num balde genérico dentro da central.
- **Categorias trocadas de galho**: ex. "1.12 RETIRADA DE LUCRO › 1.04.02 LUZ ELÉTRICA",
  "RETIRADA › 1.13.04 INVESTIMENTO" — o menu deixa escolher categoria de outra central.
- **Fornecedor duplicado por grafia**: Frísia/Frisia, "Piscinas e CIA"/"Piscina e cia",
  BB/Banco do Brasil... (sem CNPJ, não tem como unificar).
- **Conta (banco/cartão) vazia em ~40% das compras** → saldo por conta não fecha.
- Pró-labore está em SEDE › Recursos humanos; Infraestrutura pessoal (obra?) em PESSOAL ›
  Investimentos com 187 linhas — vale revisar a árvore com a Letícia.
- Parcelas são linhas soltas: corrigir uma compra parcelada = corrigir N linhas.
- Volume: **~80 compras/mês** (≈1.700 compras em 2025–2026).

---

## 3. Busca automática de notas pelo CPF/CNPJ — dá pra fazer?

**Dá.** É o serviço oficial da Receita/SEFAZ chamado **NFeDistribuicaoDFe** (Ambiente Nacional):
você informa o CPF (produtor rural) ou CNPJ e ele devolve **todas as NF-e emitidas contra esse
documento** nos últimos ~90 dias, 50 por vez, em sequência (NSU). É o mesmo serviço que
Arquivei/Qive, SIEG, NFe.io etc. usam por baixo.

Como funciona:
1. O app consulta a SEFAZ com o **certificado digital A1 do destinatário** (e-CPF A1 do produtor,
   ou e-CNPJ se for empresa). **Sem certificado não tem como** — é exigência do governo.
2. Vem primeiro um **resumo** (emitente, CNPJ, valor, data, chave).
3. O app registra automaticamente a "**Ciência da Operação**" (manifestação do destinatário —
   não aceita nem recusa nada, só diz "estou ciente") e aí a SEFAZ libera o **XML completo**.
4. Do XML a gente puxa: fornecedor + CNPJ, data, número, **cada produto** (descrição, NCM,
   quantidade, valor), **duplicatas** (`<cobr><dup>`: nº, vencimento e valor de cada parcela) e
   **forma de pagamento** (`<pag>`: Pix, boleto, cartão, dinheiro...). Quando a nota não traz
   parcelas, o app deixa em aberto para a Letícia preencher.
5. Limite da SEFAZ: no máximo **1 consulta por hora** por CPF/CNPJ (passar disso bloqueia por 1 h).
   Pra uma fazenda é mais que suficiente.

Ferramentas prontas no GitHub (código aberto):
- **[PyNFe](https://github.com/TadaSoftware/PyNFe)** (Python, ~600★, ativo) — já tem
  `consulta_distribuicao(cpf=..., nsu=...)` **com suporte a CPF** e envio de evento
  (manifestação). Encaixa direto no nosso backend Python.
- **[BrazilFiscalReport](https://github.com/Engenere/BrazilFiscalReport)** (Python) — gera o
  PDF da DANFE a partir do XML (pra Letícia abrir a nota no app).
- Referências: [sped-nfe](https://github.com/nfephp-org/sped-nfe) (PHP, o mais usado no Brasil),
  [node-mde](https://github.com/lucashpmelo/node-mde) (Node), ACBr (Delphi).
- Alternativa paga (se não quiser lidar com certificado no servidor): APIs como NFe.io, Focus
  NFe, SIEG, Qive — cobram por CNPJ/mês e entregam o XML pronto.

### O que a busca automática **não** pega (importante!)

Pelos dados da planilha, só ~44% das compras têm número de nota, e elas somam ~25% do valor.
O resto não vem por esse caminho:

| Tipo de gasto | Exemplo na planilha | Vem pela SEFAZ? | Como resolver |
|---|---|---|---|
| NF-e modelo 55 contra o CPF/IE | Frísia, Olikampa, Matsuda, Mercado Livre, Valtra, Toyota | **Sim** | automático |
| Cupom de posto/mercado (NFC-e) | Trevo 4 (gasolina), compras sede | **Não** (NFC-e não entra na distribuição) | pedir NF-e no CPF+IE, ou lançar rápido / ler QR Code do cupom |
| Nota de serviço (NFS-e) | contabilidade, consultoria, internet | Não pelo mesmo serviço — existe a API nacional da NFS-e (ADN), também com certificado | fase 2 |
| Conta de luz | Copel | Não (é outro modelo de documento) | lançamento recorrente |
| Folha, diárias, pró-labore, vale | Erondilena, Gilberto, Romário, Nutricard | Não tem nota | **lançamentos recorrentes** (o app gera todo mês, ela só confirma) |
| Tarifa banco, IOF, anuidade, ITR, IRPF | BB, Santander, Sicoob | Não | recorrentes + (fase 3) importar extrato OFX do banco |
| Compra de gado | aquisição de bovinos | Às vezes (NF de produtor/GTA) | já existe "Compra" no app do gado → integrar |

**Ponto a confirmar:** em nome de quem as notas são emitidas — CPF do Antonio, do Luiz, da
Letícia? Com qual Inscrição Estadual? Cada CPF precisa do seu certificado A1 (~R$ 150–250/ano).

---

## 4. Proposta: módulo "Financeiro" dentro do app Água do Tigre

Mesmo login (Antonio e Letícia = dono; peão não vê nada do financeiro), mesmo servidor,
mesmo banco.

### 4.1 Telas

1. **Caixa de entrada de notas** — as notas que chegaram da SEFAZ (ou XML arrastado/enviado).
   Cada nota já vem com fornecedor, data, valor, itens e parcelas preenchidos e uma **sugestão
   de classificação**. A Letícia confere e toca **"Lançar"** (1 toque se a sugestão estiver
   certa). Se a nota tiver itens de classes diferentes (ex. Frísia: sal mineral + arame), ela
   pode dividir por item.
2. **Lançamento rápido** (celular) — para o que não tem nota: fornecedor com autocompletar,
   valor, categoria (sugerida pelo fornecedor), conta, parcelas. Botão "repetir último".
3. **Recorrentes** — salário, pró-labore, diárias fixas, Copel, Nutricard, tarifas, seguros:
   cadastra uma vez; todo mês aparecem como "previsto" e ela só confirma o valor real.
4. **Resultado por mês** (a tela da tabela dinâmica) — árvore Setor › Central › Categoria ›
   Descrição × meses, abre/fecha, filtros de período, setor, realizado/previsto, caixa ou
   competência. **Tocar em qualquer número abre a lista dos lançamentos daquele valor**, com
   edição direta (e mostra a nota/PDF se tiver).
5. **Conferência** — "lançados hoje / esta semana / por quem", alertas automáticos:
   possível duplicado (mesma chave de nota, ou mesmo fornecedor+valor+data), sem categoria,
   sem conta, nota que chegou e não foi lançada.
6. **Fornecedores** — cadastro com CNPJ/CPF (vem da nota), unifica grafias, e guarda a
   classificação padrão.

### 4.2 Como o app "aprende"

- **Fornecedor → classificação**: a última categoria/setor/conta usada para aquele CNPJ vira a
  sugestão da próxima nota. Frísia sempre ração? Vem pronto.
- **Produto → classificação**: para fornecedores que vendem de tudo (cooperativa, Mercado
  Livre), a sugestão é por **descrição/NCM do produto** (NCM 2309 = ração, 3002 = vacina,
  2710 = diesel...), aprendida a partir do que ela já classificou.
- Ela sempre pode trocar; a troca vira o novo aprendizado. Nada é lançado sem ela confirmar.

### 4.3 Modelo de dados (resumo)

- `Lancamento` (1 por compra/receita: data competência, setor, categoria, fornecedor, descrição,
  valor total, conta, chave da NF-e, origem: manual/nota/recorrente, quem lançou)
- `Parcela` (vencimento, valor, pago/previsto, conta) — corrigir a compra corrige as parcelas
- `PlanoConta` (setor › central › categoria › item, com código, ativo/inativo — inativar em
  vez de apagar)
- `Fornecedor` (CNPJ/CPF, nome, apelidos, classificação padrão)
- `NotaRecebida` (chave, XML, resumo, situação: nova/lançada/ignorada, NSU)
- `RegraClassificacao` (fornecedor e/ou NCM/palavra → categoria)
- `Recorrente` (modelo de lançamento mensal)

### 4.4 Fases sugeridas

1. **Base** — plano de contas, lançamento rápido, parcelas, recorrentes, **migração das 2.479
   linhas da CONSIPA** (com limpeza: sem categoria, fornecedores duplicados) e a tela
   **Resultado por mês com clique → lançamentos**. Já substitui a planilha.
2. **Notas por XML** — arrastar/enviar o XML (muitos fornecedores já mandam por e-mail) →
   caixa de entrada com sugestão. Não precisa de certificado.
3. **Busca automática na SEFAZ** — certificado A1, consulta de hora em hora, ciência
   automática, XML completo. (Precisa resolver: o Render grátis "dorme"; a consulta roda quando
   alguém abre o app ou por um agendador externo. O certificado fica em variável secreta do
   servidor, nunca no banco nem no git.)
4. **Extrato bancário (OFX)** — importar extrato de BB/Santander/Sicoob/cartões e casar com os
   lançamentos: mostra o que saiu do banco e não foi lançado. Fecha o ciclo "se salvou tudo".
5. Depois: NFS-e (serviços), orçamento/projeção, real × previsto.

---

## 5. Decisões do plano de contas (revisão com o Antonio, 16/10/2026)

1. **Lançamentos sem categoria (584 parcelas)**: entram no app marcados em **vermelho** numa
   fila "a revisar". Não classificar sozinho na migração — a Letícia revisa um por um.
2. **SEDE × PESSOAL**: a distinção existe e fica. **PESSOAL = tudo o que vai para a conta pessoal
   do sogro**; SEDE = despesa da fazenda. Antonio e Letícia vão revisar o que está em cada um
   (ex.: pró-labore/salário em SEDE; "infraestrutura" de 187 lançamentos em PESSOAL).
3. **Pecuária de leite NÃO é leite**: era o jeito de separar a **fazenda de Castro** (arrendada do
   sogro), porque a planilha não tinha opção de duas fazendas. → O app ganha o campo **Fazenda**
   (Água do Tigre, Castro) em todo lançamento, e os relatórios filtram/separam por fazenda.
   Na migração: setor "PECUÁRIA DE LEITE" vira setor de pecuária + fazenda = Castro (também os
   10 lançamentos com "Fazenda Castro" na observação). *A confirmar: as categorias de Castro
   seguem a mesma árvore da pecuária de corte.*
4. **Agricultura sai como setor**: o sogro não planta, só arrenda. Receita de arrendamento
   (soja etc.) passa para **SEDE › Receita › Arrendamento**. As 2 despesas de agricultura
   (cerca R$ 479 e retirada R$ 192 mil) serão revistas.
5. **3 categorias no galho errado** — corrigir na migração:
   - PESSOAL › 1.12 Retirada de lucro › 1.04.02 Luz elétrica
   - PESSOAL › 1.12 Retirada de lucro › 1.13.04 Investimento
   - PECUÁRIA DE CORTE › 2.01 Abate › 2.02.04 Novilha mais 2 anos
6. **Categorias com 1–2 lançamentos (46)**: por ora ficam como estão; lista abaixo para analisar
   depois e decidir se juntam em "Outros".
7. **Sem ITEM/SUBITEM**: o app terá só **Setor › Grupo (central de custo) › Categoria** +
   descrição livre. Menos opções = lançamento mais rápido e mais lançamentos feitos. Item só
   volta se aparecer algo muito específico.

Setores resultantes: **SEDE, PESSOAL, PECUÁRIA, MÁQUINAS E EQUIPAMENTOS** × Fazenda
(**Água do Tigre, Castro**).

### 5.1 Categorias com 1 ou 2 lançamentos (para analisar depois)

| Tipo | Setor | Central | Categoria | Lanç. | R$ | Fornecedor |
|---|---|---|---|---|---|---|
| Despesa | Agricultura | 1.04. MATERIAIS DE CONSUMO, OPERAÇÃO E MANUTENÇÃO | 1.04.05. CERCAS | 1 | 479,00 | Borges |
| Despesa | Máquinas E Equipamentos | 1.04. MATERIAIS DE CONSUMO, OPERAÇÃO E MANUTENÇÃO | 1.04.08. FERRAMENTAS | 1 | 340,00 | Carlos Gerson Breus |
| Despesa | Pecuária De Corte | 1.01. RECURSOS HUMANOS | 1.01.01. ADMISSÃO | 1 | 600,00 |  |
| Despesa | Pecuária De Corte | 1.01. RECURSOS HUMANOS | 1.01.06. FÉRIAS | 1 | 1.213,88 |  |
| Despesa | Pecuária De Corte | 1.01. RECURSOS HUMANOS | 1.01.08. OUTROS | 1 | 100,00 |  |
| Despesa | Pecuária De Corte | 1.02. ALIMENTOS | 1.02.02. ANUAIS DE VERÃO | 2 | 23.176,80 | Semeia sementes, Frísia |
| Despesa | Pecuária De Corte | 1.02. ALIMENTOS | 1.02.03. PERENES DE INVERNO | 1 | 7.089,00 | Adriano Renato Kiers |
| Despesa | Pecuária De Corte | 1.02. ALIMENTOS | 1.02.06. CAPINEIRAS | 1 | 715,95 | Cocari |
| Despesa | Pecuária De Corte | 1.02. ALIMENTOS | 1.02.15. CONCENTRADOS | 1 | 161,12 | Frísia |
| Despesa | Pecuária De Corte | 1.04. MATERIAIS DE CONSUMO, OPERAÇÃO E MANUTENÇÃO | 1.04.04. POÇO ARTESIANO | 1 | 82,41 | Frísia |
| Despesa | Pecuária De Corte | 1.04. MATERIAIS DE CONSUMO, OPERAÇÃO E MANUTENÇÃO | 1.04.07. INFRAESTRUTURA | 1 | 2.000,00 | Metais PG |
| Despesa | Pecuária De Corte | 1.05. IMPOSTOS E ENCARGOS | 1.05.01. BANCOS E CORRETORAS | 1 | 28,10 | BB |
| Despesa | Pecuária De Corte | 1.07. AQUISIÇÃO DE REBANHO | 1.07.08. DESPESAS EXTRAS | 1 | 854,71 | Frísia |
| Despesa | Pecuária De Corte | 1.08. GASTOS COM REBANHO | 1.08.05. OUTROS | 1 | 3.000,00 | Vinicius Garbuio |
| Despesa | Pecuária De Corte | 1.10. GASTOS GERAIS | 1.10.02. MERCADO - GASTOS DA FAZENDA | 1 | 181,40 | Restaurante Moinho |
| Despesa | Pecuária De Leite | 1.03. ARRENDAMENTO | 1.03.01. PASTAGEM DE INVERNO | 1 | 5.000,00 | André Trentini |
| Despesa | Pecuária De Leite | 1.04. MATERIAIS DE CONSUMO, OPERAÇÃO E MANUTENÇÃO | 1.04.01. BARRACÃO | 1 | 131,40 | Erondilena |
| Despesa | Pecuária De Leite | 1.04. MATERIAIS DE CONSUMO, OPERAÇÃO E MANUTENÇÃO | 1.04.06. CURRAL | 1 | 60,00 | Tintas Darka |
| Despesa | Pecuária De Leite | 1.04. MATERIAIS DE CONSUMO, OPERAÇÃO E MANUTENÇÃO | 1.04.07. INFRAESTRUTURA | 1 | 918,10 | Erondilena |
| Despesa | Pecuária De Leite | 1.04. MATERIAIS DE CONSUMO, OPERAÇÃO E MANUTENÇÃO | 1.04.08. FERRAMENTAS | 1 | 260,41 | Frísia |
| Despesa | Pecuária De Leite | 1.05. IMPOSTOS E ENCARGOS | 1.05.10. ITR - IMPOSTO TERRITORIAL RURAL | 1 | 4.860,72 |  |
| Despesa | Pecuária De Leite | 1.08. GASTOS COM REBANHO | 1.08.03. SANIDADE | 1 | 444,77 | Frísia |
| Despesa | Pecuária De Leite | 1.09. ADMINISTRATIVO | 1.09.01. CONSULTORIA E ASSESSORIA | 1 | 1.000,00 | Bruno Advogado |
| Despesa | Pessoal | 1.04. MATERIAIS DE CONSUMO, OPERAÇÃO E MANUTENÇÃO | 1.04.03. REDE ELÉTRICA | 1 | 2.300,00 | João Luis Staveski |
| Despesa | Pessoal | 1.06. INVESTIMENTOS | 1.06.01. INSTITUIÇÕES FINANCEIRAS | 1 | 100,00 | BB |
| Despesa | Pessoal | 1.09. ADMINISTRATIVO | 1.09.01. CONSULTORIA E ASSESSORIA | 2 | 16.650,00 | Allan Paisani, Bruno Advogado |
| Despesa | Pessoal | 1.10. GASTOS GERAIS | 1.10.02. MERCADO - GASTOS DA FAZENDA | 2 | 1.046,04 | Showroom da carne, Showroom da Carne |
| Despesa | Pessoal | 1.12. RETIRADA DE LUCRO | 1.04.02. LUZ ELÉTRICA | 1 | 143,82 | Celesc |
| Despesa | Pessoal | 1.12. RETIRADA DE LUCRO | 1.12.02. MERCADO - GASTOS PESSOAIS | 2 | 503,63 | B9 conveniência, Showroom da Carne |
| Despesa | Pessoal | 1.12. RETIRADA DE LUCRO | 1.12.04. CONSÓRCIO | 1 | 10.880,96 |  |
| Despesa | Pessoal | 1.12. RETIRADA DE LUCRO | 1.12.07. GASTOS EM GERAL | 2 | 1.866,89 |  |
| Despesa | Pessoal | 1.12. RETIRADA DE LUCRO | 1.12.09. OUTROS | 2 | 6.147,58 | Veloe |
| Despesa | Sede | 1.01. RECURSOS HUMANOS | 1.01.02. COMISSÃO E PREMIAÇÃO | 1 | 163,76 | Natura |
| Despesa | Sede | 1.04. MATERIAIS DE CONSUMO, OPERAÇÃO E MANUTENÇÃO | 1.04.01. BARRACÃO | 1 | 30,00 | Cristal Vidros |
| Despesa | Sede | 1.04. MATERIAIS DE CONSUMO, OPERAÇÃO E MANUTENÇÃO | 1.04.03. REDE ELÉTRICA | 1 | 700,00 | Rodrigo Bombardieri |
| Despesa | Sede | 1.04. MATERIAIS DE CONSUMO, OPERAÇÃO E MANUTENÇÃO | 1.04.09. BEBEDOUROS E AGUADA NATURAL | 1 | 35,10 | Frísia |
| Receita | Agricultura | 2.01. ARRENDAMENTO | 2.01.10. OUTROS | 1 | 1.920.401,04 | Cargill |
| Receita | Pecuária De Corte | 2.01. ABATE | 2.01.04. NOVILHA MAIS 2 ANOS | 2 | 243.151,79 | Boi Gordo, Cooperaliança |
| Receita | Pecuária De Corte | 2.01. ABATE | 2.01.08. VACA MATRIZ | 1 | 113.754,28 | Cooper Aliança |
| Receita | Pecuária De Corte | 2.01. ABATE | 2.01.10. BOI | 2 | 217.098,05 | Argus Frigorífico |
| Receita | Pecuária De Corte | 2.01. ABATE | 2.02.04. NOVILHA MAIS 2 ANOS | 1 | 121.293,45 | Cooperaliança |
| Receita | Pecuária De Corte | 2.02. VENDA DE ANIMAIS | 2.02.01. BEZERRA | 1 | 5.205,00 |  |
| Receita | Pecuária De Corte | 2.02. VENDA DE ANIMAIS | 2.02.02. BEZERRO | 1 | 1.510,00 |  |
| Receita | Pecuária De Corte | 2.02. VENDA DE ANIMAIS | 2.02.08. VACA MATRIZ | 2 | 225.051,61 | Argus |
| Receita | Pecuária De Corte | 2.02. VENDA DE ANIMAIS | 2.02.10. BOI | 1 | 225.472,86 | Frígorífico Argus |
| Receita | Sede | 2.02. VENDA DE GRÃOS E TUBÉRCULOS | 2.02.01. SOJA | 1 | 60.500,00 | Bunge |

---

## Fontes

- [PyNFe — TadaSoftware/PyNFe](https://github.com/TadaSoftware/PyNFe) (função `consulta_distribuicao` com CPF)
- [BrazilFiscalReport](https://github.com/Engenere/BrazilFiscalReport)
- [node-mde](https://github.com/lucashpmelo/node-mde)
- [NFeDistribuicaoDFe — tributos.io](https://tributos.io/blog/documentos-fiscais/nfedistribuicaodfe-consulta-e-distribuicao-de-documentos-fiscais-eletronicos-1)
- [Intervalo mínimo de consulta DistDFe — Tek-System](https://teksystem.com.br/tekwiki/images/2/20/ProcessamentoDistrDFe.pdf)
- [ACBr — distribuição DF-e e erro 656](https://www.projetoacbr.com.br/forum/topic/78305-consulta-ao-m%C3%A9todo-nfedistribuicaodfe-da-sefaz/)
- [NF-e por CPF para produtor rural (NT 2018.001) — Senior](https://documentacao.senior.com.br/gestaoempresarialerp/5.10.3/manuais_processos/nota-fiscal/nfe-pessoa-fisica.htm)
- [Manual APIs ADN — NFS-e Nacional](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/manual-contribuintes-apis-adn-sistema-nacional-nfse.pdf)
- [NFe.io — distribuição inbound](https://nfe.io/docs/documentacao/distribuicao/dfe-inbound-documentacao-funcional-clientes/index.md)
- [Consulta NFC-e — Fazenda PR](https://www.fazenda.pr.gov.br/servicos/Empresa/Documentos-fiscais-eletronicos/Consultar-NFC-e-nota-fiscal-eletronica-gzNEE1NO)
