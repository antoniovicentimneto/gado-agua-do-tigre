# Levantamento comparativo — apps de pecuária × Gado Água do Tigre

*Feito em 15/10/2026. Baseado em material público (lojas de apps, sites e
reportagens). Não foi usado código de nenhum app — só as funcionalidades que eles
divulgam. O objetivo é colher ideias e reprogramá-las do nosso jeito.*

## 1. Apps analisados

| App | Foco | Pontos que se destacam |
|---|---|---|
| **JetBov** (web + *JetBov de Pasto* no celular) | Gestão completa de corte, forte em pasto | Mapa da fazenda com satélite e piquetes; mover lote **no mapa**; escores livres (altura do pasto, escore corporal, cocho, **voltagem da cerca**); tarefas para a equipe com prazo; fichas de animal, lote e **área**; descanso de piquete; lotação, ganho/ha e lucro/ha; seleção de descarte; agenda sanitária, nutricional e reprodutiva; simulador de vendas; assistente por voz/texto ("JetBov Gestor") |
| **iRancho** | Gestão + rastreabilidade | "App do Peão" offline; vacinação, medicamentos e insumos; manejos personalizados por fazenda; brinco eletrônico e balança; rastreabilidade (blockchain); uso por voz para funcionário com dificuldade em tecnologia; fluxo de caixa |
| **Bovitech** (Ideagri) | Corte: financeiro + zootécnico | Custos de nutrição, compra, operação e **maquinário**; balança eletrônica ou digitação; rentabilidade na venda; fluxo de caixa futuro; offline com sincronização |
| **Aegro – Módulo Pecuária** | Lote integrado ao financeiro | Custos lançados no lote (suplemento, pasto, sanidade, mão de obra) → **custo da arroba produzida antes de vender**; compra e venda caem direto no caixa e no DRE. Limitações: só por lote (sem brinco) e só no computador |
| **BovPilot** (antigo BovControl) | Coleta de dados no campo | Foto da nota fiscal vira lançamento de custo; RFID, balança e sensores. Nota baixa na loja (3,0) |
| **Embrapa** (Capta Pasto e régua de manejo) | Técnica de pastagem, gratuita | Foto do celular estima cobertura, altura e biomassa do pasto; **régua com altura de entrada e saída por capim** |

## 2. O que o gado_app já tem (e faz bem)

- **Pesagem na mangueira**, com sessão, sublotes, ordem de pesagem, pesagem sem brinco e alertas (fora do lote, já pesado, não existe).
- **GMD, uGMD e GMD por período** por animal, sempre calculados.
- **Lotes com histórico** de entrada e saída, além de mover e juntar lotes, com
  indicadores por lote (GMD, uGMD e UA). Falta a UA por hectare, que depende de a área estar cadastrada.
- **Compra e venda**: preço por kg ou por @, rendimento por tipo, peso de carcaça, acabamento e venda pendente do frigorífico.
- **Cria**: nascimento, mãe, prenhez e desmama.
- **Dentição e score** por animal.
- **Perfis dono/peão** e log de auditoria das alterações.
- **Offline na mangueira**, com fila que não duplica.
- **Exportação e relatório Excel** e restauração completa.

Nesses pontos o app está **no nível dos comerciais ou acima**: pesagem individual por brinco
(o Aegro nem tem), venda com carcaça e acabamento, e auditoria.

## 3. Cruzamento — o que falta

| Funcionalidade | JetBov | iRancho | Bovitech | Aegro | **gado_app** |
|---|:-:|:-:|:-:|:-:|:-:|
| Pesagem individual + GMD | ✔ | ✔ | ✔ | só lote | ✔ |
| Lotes com histórico | ✔ | ✔ | ✔ | ✔ | ✔ |
| Compra/venda com @ e rendimento | ✔ | ✔ | ✔ | ✔ | ✔ |
| **Áreas/piquetes cadastrados** | ✔ | – | – | – | ✘ |
| **Mudança de piquete + tempo de ocupação** | ✔ | – | – | – | ✘ |
| **Descanso do piquete / altura entrada-saída** | ✔ | – | – | – | ✘ |
| **Mapa com satélite** | ✔ | – | – | – | ✘ |
| **Indicadores por hectare** (UA/ha, @/ha, lucro/ha) | ✔ | – | – | – | ✘ |
| **Custo por lote → custo da @ produzida** | ✔ | ✔ | ✔ | ✔ | ✘ |
| **Sanidade** (vacina, medicamento, carência) | ✔ | ✔ | – | – | ✘ |
| **Tarefas para o peão** | ✔ | – | – | – | ✘ |
| **Escores livres** (pasto, cocho, cerca) | ✔ | ✔ | – | – | parcial (1 score por animal) |
| Seleção de descarte por índice | ✔ | – | ✔ | – | parcial (dá pra ver GMD) |
| Offline completo (abrir manejo sem sinal) | ✔ | ✔ | ✔ | ✘ | parcial (só dentro de sessão aberta) |
| Voz / assistente IA | ✔ | ✔ | – | – | ✘ |
| Balança/brinco eletrônico | – | ✔ | ✔ | ✘ | ✘ |

*"–" = não encontrado no material público (pode existir).*

## 4. Ideias priorizadas para a Água do Tigre

A ordem leva em conta como a fazenda funciona: ~80 ha próprios no verão, azevém na
área arrendada no inverno, a área de Castro/Rosa tratada à parte e o **tempo de
pastejo que hoje não é medido**.

### Prioridade 1 — Pasto (o módulo que você pediu)
1. **Cadastro de áreas e piquetes**: nome, hectares, capim (Marandu, Mombaça, azevém…),
   tipo (próprio / arrendado / azevém de inverno) e área-mãe (ex.: Castro/Rosa).
2. **Mudança de piquete**: o lote entra e sai de um piquete com data. Segue a mesma
   lógica do "lotes com histórico" que já existe, então o caminho está pronto. Resolve
   o **tempo de pastejo**, que hoje não é medido.
3. **Avaliação de pasto**: altura na entrada e na saída, nota visual e foto. O app
   avisa quando bate a altura de saída do capim, usando as metas da régua da Embrapa,
   que você pode editar.
4. **Painel de descanso**: quantos dias cada piquete está vazio e quais estão prontos
   para receber gado.
5. **GMD por piquete/área**: o diferencial que nenhum concorrente tem tão fácil. As
   pesagens já existem, então cruzando com o piquete o app mostra **qual pasto engorda
   mais**.

### Prioridade 2 — Dinheiro e rotina
6. **Indicadores por hectare**: lotação (UA/ha), @ produzida/ha e, junto com o custo,
   lucro/ha. Isso depende do item 1 (área cadastrada).
7. **Custo por lote → custo da @ produzida**: suplemento, sal, sanidade, arrendamento
   (os R$ 5 mil/mês de Castro) e **horas de máquina**. Pode puxar do projeto
   `fazenda-gestao` em vez de lançar duas vezes.
8. **Sanidade**: vacinas e medicamentos por lote ou animal, com **carência**. O app
   bloqueia ou avisa na venda se o animal estiver em carência.
9. **Tarefas para o peão**: o dono cria a tarefa ("trocar lote 2 para o piquete 5",
   "ver cerca do piquete 3") e o peão vê e marca como feita no celular.

### Prioridade 3 — Refinamentos
10. **Mapa com satélite**: desenhar os piquetes sobre a imagem, com a área em hectares
    calculada sozinha, e mover o lote pelo mapa. Dá para fazer com mapa e satélite gratuitos.
11. **Escores livres**: transformar o "score" atual num cadastro aberto (escore corporal,
    altura do pasto, cocho, voltagem da cerca), registrado por animal, lote ou piquete.
12. **Lista de descarte**: ranking automático dos piores GMD do lote.
13. **Offline completo**: permitir abrir sessão e mudar piquete sem sinal.

### Prioridade 4 — Futuro
14. Lançamento por **voz/áudio** ("lote 2 foi pro piquete 5 hoje").
15. Pluviômetro (chuva por área), importante para explicar a variação do pasto.
16. Balança e brinco eletrônico por bluetooth, quando houver equipamento.

## 5. O que **não** vale copiar
- **Blockchain/rastreabilidade** (iRancho): só faz sentido para quem vende para
  programas de exportação ou certificação.
- **Gestão só por lote** (Aegro): seria um retrocesso, porque o app já controla cada animal por brinco.

## Fontes
- [JetBov de Pasto — App Store](https://apps.apple.com/app/id6447628321)
- [Apresentação aos investidores JetBov 2025](https://eqseed.com/system/files/oferta-presentation/apresentacao_aos_investidores_-_jetbov_2025.pdf)
- [AgFeed — JetBov Gestor](https://agfeed.com.br/?p=57918)
- [AgFeed — JetBov franquias e módulos](https://agfeed.com.br/agtech/jetbov-levanta-r-1-milhao-para-aumentar-sistema-de-franquias-do-sistema-de-rastreabilidade-bovina)
- [CNN Brasil — iRancho](https://www.cnnbrasil.com.br/agro/irancho-projeta-crescimento-de-48-e-aposta-em-ia-para-acelerar-expansao/)
- [Compre Rural — iRancho e Banco do Brasil](https://www.comprerural.com/banco-do-brasil-firma-parceria-com-a-startup-irancho-para-rastreabilidade-de-bovinos-no-pais/)
- [Diário do Comércio — Bovitech/Ideagri](https://diariodocomercio.com.br/agronegocio/ideagri-lanca-ferramenta-de-gestao-para-gado-de-corte/)
- [Aegro — Módulo Pecuária](https://aegro.com.br/suporte/pecuaria/modulo-pecuaria-gerencie-seu-rebanho-integrado-ao-financeiro-da-fazenda/)
- [BovPilot — App Store](https://apps.apple.com/br/app/id6444866422)
- [Compre Rural — BovControl](https://comprerural.com/empresa-brasileira-desenvolve-a-internet-das-vacas/)
- [Embrapa — Pastejo rotacionado](https://www.infoteca.cnptia.embrapa.br/infoteca/bitstream/doc/1072007/1/PastejoRotacionadoFINAL.pdf)
- [Embrapa — Aplicativo de monitoramento de pastagens](https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1140827/1/Desenvolvimento-aplicativo-monitoramento-pastagens.pdf)
- [Compre Rural — Pastagens e custos](https://www.comprerural.com/manejo-adequado-das-pastagens-pode-reduzir-25-dos-custos-na-pecuaria)

---

## 6. Decisões do Antonio (15/10/2026)

| # | Ideia | Decisão | Observação |
|---|---|---|---|
| 1 | Áreas e piquetes | **Entra** | Importar o arquivo das áreas (XML/KML que ele já tem) **ou** desenhar no mapa |
| 2 | Mudança de piquete | **Entra** | Mover o gado de uma área para outra pelo celular com facilidade; cuidar de juntar e separar lotes; botões grandes e fáceis de acertar |
| 3 | Altura de entrada e saída | **Opcional** | Hoje não conseguem medir. O campo existe, mas não é obrigatório |
| 4 | Painel de descanso | **Entra** | |
| 5 | GMD por fator | **Entra (ampliado)** | Por piquete, lote, fornecedor, raça e outros, mostrando **qual fator mais influencia** |
| 6 | Indicadores por hectare | **Entra** | |
| 7 | Custo da @ produzida | **Depois** | Junto com o módulo financeiro/administrativo |
| 8 | Sanidade | **Fora** | Usam pouco medicamento; só tratam quem precisa (metodologia SICOPA) |
| 9 | Tarefas do peão | **Entra** | Agenda: o que fazer, quando fazer, e o peão marca como feito |
| 10 | Mapa com satélite | **Entra** | Junto com os itens 1 e 2 |
| 11 | Escores livres | **Entra** | O dono cria os escores que quiser |
| 12 | Lista de descarte | **Entra** | |
| 13 | Offline completo | **Entra** | |
| 14 | Voz | **Fase posterior** | |
| 15 | Pluviômetro | **Opcional** | Campo disponível, não obrigatório |
| 16 | Balança/brinco eletrônico | **Fora por ora** | A tela de pesagem atual atende bem |

## 7. Fases de implementação

**Fase 1 — Mapa e pasto (o coração)**
- Áreas e piquetes: importar o arquivo (KML/KMZ/XML/GeoJSON) ou desenhar no mapa com satélite; a área em hectares é calculada sozinha (1, 10)
- Mudança de piquete no celular: toque no lote → toque no destino (arrastar como atalho), com resumo antes de confirmar e opção de **desfazer**; juntar e separar lotes no mesmo fluxo (2)
- Painel de descanso (4)
- Já nasce funcionando **sem sinal** (13), estendendo o offline também às sessões da mangueira

**Fase 2 — Análises**
- GMD por fator: piquete, lote, fornecedor, raça, tipo, capado e época, com ranking de "o que mais influencia" e o número de animais de cada grupo (5)
- Indicadores por hectare, com o hectare equivalente para o azevém de inverno, no formato Inttegra (6)
- Lista de descarte (12)
- Escores livres (11), incluindo a nota visual do pasto como alternativa mais fácil à altura (3, opcional) e a chuva (15, opcional)

**Fase 3 — Rotina**
- Agenda de tarefas do peão (9)
- Lançamento por voz (14)

**Depois** — módulo financeiro/administrativo, com o custo da @ produzida (7).
