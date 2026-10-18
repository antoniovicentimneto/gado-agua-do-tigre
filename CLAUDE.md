# CLAUDE.md — Gado Água do Tigre

App de controle de peso de gado da fazenda **Água do Tigre**. Substitui a planilha
`2025_PLANILHA GADO BOAVISTINHA.xlsx`. Cada pesagem é um registro (data+peso); GMD é
sempre calculado, nunca digitado.

> Regras gerais do repositório (Python 3.11+, comentários/README em português,
> commits com prefixo semântico, modular) estão no `CLAUDE.md` da pasta pai.

## Como rodar / testar / deployar

```bash
# Rodar local (SQLite ou nuvem, conforme backend/.env)
cd gado_app/backend && python -m uvicorn app.main:app --port 8077

# Testes (46+; SQLite em memória, fixture em tests/conftest.py)
cd gado_app/backend && pytest -q

# Deploy: git push -> Render faz deploy automático do main
```

- **Produção:** https://gado-agua-do-tigre.onrender.com
- **Repo:** github.com/antoniovicentimneto/gado-agua-do-tigre (repo próprio, NÃO dentro
  do PROJETOS maior; identidade git local = Antonio Vicentim Neto).
- **Deploy:** Render (plano free, blueprint `render.yaml` na raiz, rootDir=backend).
  O free "dorme" após ~15 min sem uso e demora 30-60s pra acordar na 1ª abertura.
- **Banco:** Supabase Postgres, região **sa-east-1 (São Paulo)**. Conexão via
  **pooler IPv4**: `aws-1-sa-east-1.pooler.supabase.com:5432`, user
  `postgres.egpdgkmchellkcmdteae`, prefixo `postgresql+psycopg://`. A string completa
  (com senha) fica em `backend/.env` (gitignored) — **NUNCA** exibir/commitar a senha.
  A conexão "direct" (`db.*.supabase.co`) é IPv6-only e NÃO funciona.

## ⚠️ Gotcha de performance (o mais importante)

O backend roda no **Render (Oregon, EUA)** e o banco fica no **Supabase (São Paulo)** →
~180-200 ms de latência POR ida-e-volta ao banco. **Cada `SELECT` separado custa uma
viagem transatlântica.** Consultas N+1 (uma query por animal) ficam absurdamente lentas
(ex.: pesar 18 animais levava 20s porque `animais_a_pesar` carregava os 763 animais a
cada render). **Regra:** sempre usar `selectinload` e consultar só o necessário (ex.:
animais de um lote via `AnimalLote` com `data_fim IS NULL`, nunca varrer o rebanho todo).
Já corrigido em: `listar_animais`, `listar_lotes`, `dashboard`, `exportacao`, `juntar`,
`animais_a_pesar`, `manejos`. Se algo ficar lento, procurar N+1 primeiro.

## ⚠️ Segurança dos dados (o usuário tem MEDO de perder)

- **NUNCA** recriar o banco (`rm gado.db` + `importar.py`) com dados reais — apaga o que
  foi lançado pelo app. `importar.py` é só pra 1ª carga.
- Atualizar pela planilha original = `atualizar.py` (incremental, `importar_incremental`):
  só adiciona animais/pesagens que faltam, nunca apaga, faz backup antes.
- Recuperar tudo do zero = `restaurar.py` lê o **Excel exportado pelo próprio app**
  (Painel → Exportar; abas "Animais"+"Pesos") e recria num banco vazio. Pareia as abas
  por POSIÇÃO da linha, não por brinco (há 13 brincos duplicados na base).
- **Sempre perguntar antes de apagar qualquer arquivo de backup/teste**, mesmo que pareça
  temporário.
- Ao testar no navegador, usar banco isolado: config `gado-teste` no `.claude/launch.json`
  com `DATABASE_URL=sqlite:///./gado_teste.db` na porta 8078 (criar/remover conforme
  necessário; nunca criar contas/dados de teste no Supabase de produção sem autorização).

## ⚠️ Cache-busting (disciplina obrigatória)

Assets estáticos são versionados com `?v=N`. **A cada mudança em qualquer arquivo de
`static/`, incrementar N** no `index.html` E no `service-worker.js` (a lista ARQUIVOS e o
nome do CACHE `gado-agua-do-tigre-vX`). **Versão atual: v=63 / cache v55.** (Leaflet fica em `static/vendor/leaflet/`, sem versão no nome.)
O SW é network-first (online sempre pega o novo) e há auto-reload no `controllerchange`,
mas o navegador do usuário às vezes segura a versão antiga — se o usuário relatar que "não
mudou", verificar com `curl` que o deploy terminou e orientar Ctrl+Shift+R (PC) / fechar e
reabrir o app (celular).

Bug de CSS já resolvido, mas fica de alerta: `.escondido { display:none !important }` vence
qualquer `style.display="block"` inline. Não usar a classe `escondido` em containers cuja
visibilidade é alternada por `style.display` (foi o que deixou a aba Manejos invisível).

## Arquitetura

```
backend/
  app/
    main.py            # FastAPI, middleware no-store, serve o frontend, /sw.js
    config.py          # DATABASE_URL, rendimentos, auth_secret, token_dias
    database.py        # engine + SessaoLocal
    models.py          # Animal, Pesagem, Lote, AnimalLote, SessaoPesagem, Compra,
                       #   Venda, Denticao, Score, HistoricoBrinco, Usuario, OpcaoCadastro
    schemas.py         # Pydantic
    routers/
      api.py           # /api/* (animais, lotes, manejos, opcoes, venda, dashboard...)
      auth.py          # /api/auth/* (login, setup, usuarios)
      sessoes.py       # /api/sessoes/* (mangueira)
    services/
      sessao.py        # lógica da mangueira (criar/registrar/vincular/finalizar)
      manejos.py       # histórico de manejos (sessões + pesagens legado)
      consultas.py     # lote_atual, montar_resumo, pontos_pesagem
      gmd.py           # cálculos de GMD/uGMD/período
      venda.py         # cálculo de venda (arroba)
      opcoes.py        # listas de tipos/raças (config)
      exportacao.py / importacao.py / restauracao.py
  static/              # frontend vanilla JS: index.html, app.js, mangueira.js,
                       #   fila-offline.js, style.css, service-worker.js, manifest.json
  tests/               # pytest
  importar.py / atualizar.py / restaurar.py / migrar_para_nuvem.py
render.yaml            # blueprint do Render
```

Frontend: **vanilla JS, sem framework**. `app.js` = geral (abas, rebanho, ficha, config,
usuários, cache de animais). `mangueira.js` = tela de pesagem. Comunicação via objeto `api`
(get/post/put/delete) que injeta `Authorization: Bearer <token>` e trata 401.

## Login e perfis

- **DONO** (Antonio + esposa Leticia): acesso total.
- **PEÃO**: só lança peso e mexe em lotes durante a pesagem. NÃO edita/remove pesagens
  antigas, NÃO edita cadastro, NÃO exporta Excel, NÃO vê compra/venda.
- Token próprio (sem lib externa): base64(payload).base64(HMAC-SHA256), assinado com
  `config.auth_secret`. Senha via PBKDF2. `usuario_atual()` (login) e `requer_dono()`
  (dono) como dependências FastAPI. Endpoints sensíveis levam `_dono=Depends(requer_dono)`.
- Frontend esconde controles de dono pro peão; backend é a fonte da verdade (403).

## Offline-first (PWA) + cache local

- `manifest.json` + `service-worker.js` (registrado em `/sw.js` na raiz p/ escopo total) →
  instalável no celular, abre sem sinal.
- **Fila offline** (`fila-offline.js`): se a pesagem falhar por falta de rede, guarda no
  localStorage (`forcar:true`) e sincroniza sozinha quando volta (evento `online` + a cada
  20s). Mostra "📡 N pesagens aguardando envio".
- **Cache local de animais** (`/api/animais-cache`, carregado na abertura da sessão e no
  login): a consulta do brinco é LOCAL/instantânea (sem ir à rede a cada tecla, sem "puxar
  brinco errado" por resposta atrasada). Duplicados e cadastro de compra resolvidos a partir
  do cache. `cacheUpsertAnimal` mantém atualizado após cada pesagem.

- **Rede fraca** (`app.js`: `fetchComPrazo`, `redeBoa/marcarRedeRuim`): lançamento da mangueira
  tem prazo de 8 s; estourou, vai pra fila e a rede fica "ruim" por 45 s (os próximos entram
  na fila na hora). Cada lançamento leva uma `chave` (Pesagem.chave_cliente) — reenvio não
  duplica. A fila NUNCA descarta: 5xx/401/sem resposta mantém; 4xx ou resposta com `alerta`
  vai pra lista de "recusadas" (aviso vermelho, o usuário refaz na mão).
- **Sessão aberta sem sinal**: "Iniciar pesagem" sem rede (ou sem resposta em 8 s) abre a
  sessão no aparelho com id provisório `off-<chave>`; a abertura entra na fila (POST
  `/api/sessoes` com `chave` → `SessaoPesagem.chave_cliente`, servidor não duplica) e os
  lançamentos vão pra fila com o id provisório na URL. Quando a abertura é aceita,
  `filaTrocarSessao` troca o id pelo real no resto da fila e avisa a mangueira
  (`sessao-sincronizada`). Se a abertura for recusada, as pesagens dela vão pras recusadas.
  Finalizar/vincular esperam a sessão chegar e a fila dela esvaziar. Sessões abertas sem
  sinal aparecem em "retomar"; sessões do servidor podem ser retomadas sem rede pelo último
  estado guardado (`gat_cache_sessoes_estado`).
- **Ficha do animal**: um botão só ("Salvar modificações", `salvarFicha`) grava tudo o que
  mudou; fechar com mudança pendente pede confirmação.

## Regras de negócio (confirmadas pelo usuário)

- **GMD** = (último peso − primeiro peso) / dias totais.
- **uGMD** = GMD do último período (entre as DUAS últimas pesagens do animal). Média do
  lote = média simples dos uGMD individuais (o usuário sabe que os períodos podem diferir;
  em aberto se muda pra ponderada por dias ou período comum).
- **GMD por período** = escolhe intervalo de datas (comparar pastagens).
- **Arroba (@) = 15 kg de CARCAÇA** (NÃO 30). Arroba líquida = (peso vivo × rendimento)/15.
- **Rendimento padrão:** Vaca 48%, Novilha 50%, Boi 52% (editável por venda).
- **Venda:** "peso fazenda" (vivo × rendimento, na hora) ou "peso morto/gancho" (frigorífico
  manda rendimento+carcaça depois → fica pendente).
- **UA (unidade animal)** = 1 animal de **450 kg vivos**. UA do lote = soma dos pesos/450.
- **Status:** ATIVO, VENDIDO, PERDIDO, MORTO. Só ATIVO conta na fazenda; os outros são
  inativos (`STATUS_INATIVOS`) e saem das listas de pesagem.
- **Compra:** são animais NOVOS. Não pede lote de origem, só destino. Ao digitar brinco novo
  pede tipo+raça (lembra a última escolha e cadastra os próximos direto); se o brinco já
  existe, só avisa e cria outro animal mesmo assim.
- **Re-etiquetagem:** animal sem brinco/brinco novo é "vinculado" a um animal antigo faltante
  (herda histórico; usa `pesagens.append` p/ não apagar por cascade).
- **Brincos duplicados** existem (13): a pesagem mostra um seletor pra escolher qual animal.

## Mangueira (tela principal)

Sessão de pesagem com 3 colunas (a pesar · lançamento brinco+peso+enviar · pesados). Lote
ativo "grudado". Tipos: manejo/compra/venda_fazenda/venda_morto (compra/venda só dono).
"⚙ mais opções" (tipo/raça/dentes/obs) opcional, sem atrapalhar o fluxo rápido. Avisos:
fora do lote / já pesado / inexistente / ambíguo. Sublotes escolhidos de lista ou novo.
Coluna Pesados mostra peso total somado + uGMD médio. "Cancelar sessão" (só se vazia).
Fluxo básico intocável: **brinco + peso + enviar** (+ mudar lote quando quiser).

## Aba Manejos (Rebanho › Manejos)

Histórico de todos os manejos: sessões do app (com status/destino) + pesagens antigas da
planilha (sem sessão) agrupadas por data (tipo "legado"). Cartão abre detalhe com peso/GMD
de cada animal. Serviço: `app/services/manejos.py`.

## Cria (Rebanho › Cria) e venda no gancho

- **Cria** (`services/cria.py`, `routers/cria.py`, `static/cria.js`): `Animal.mae_id` liga o
  bezerro à mãe (pai não é registrado). Bezerro "ao pé" = cria ATIVA, tipo `Bez*`, sem
  `data_desmame`. Vaca **solteira** = sem bezerro ao pé. `Animal.prenhez` = prenhe (toque) /
  mojando (visual) / vazia; nascimento limpa. **Pode ir pro frigorífico** = solteira e não
  prenhe/mojando. Trocar o tipo de bezerro na mão grava `data_desmame` = hoje.
- Tela em formato de planilha com duas visões (**Vacas** / **Bezerros** — todos os bezerros,
  mãe e nascimento editáveis na linha), filtros, ordenação por coluna, "mostrar novilhas" e
  Excel do que está na tela (dono). **Peão lança** mãe, nascimento, prenhez, nascimento de
  bezerro e corrige brinco de bezerro; desmama é só dono.
- **Venda peso morto**: fechamento por animal (carcaça, rendimento, preço da @, acabamento)
  em `static/venda-gancho.js`, aberto pelo manejo de venda. Só dono.
- **Colunas novas** em tabela existente: acrescentar em `COLUNAS_NOVAS` (`database.py`) —
  `create_all` não adiciona coluna; a migração leve roda no start (só ADD COLUMN).
- Pendente: exportação/restauração Excel ainda NÃO leva mãe, desmame, prenhez nem venda.

## Pastos (aba Pastos) — fase 1 do plano em `docs/levantamento_apps_pecuaria.md`

- **Modelos:** `AreaPasto` (agrupamento: Sede, Castro/Rosa, azevém) → `Piquete` (geometria
  GeoJSON + hectares) ; `LotePiquete` = histórico de qual LOTE esteve em qual piquete
  (`data_saida` nula = está lá) ; `MovimentacaoPasto` = cada ação (mover/separar/juntar)
  com o JSON das linhas criadas/fechadas — é o que permite o **Desfazer** exato.
- **Serviços:** `services/pastos.py` (painel, mover, juntar, separar, desfazer, cadastro,
  importar) e `services/geo.py` (lê KML/KMZ/XML-KML/GeoJSON e calcula hectares em Python
  puro). Router: `routers/pastos.py` (`/api/pastos`). Peão move/separa/junta/desfaz;
  cadastrar/importar/remover piquete é só dono.
- **Painel em poucas consultas** (`_rebanho_por_lote`): cabeças e último peso por lote em 2
  queries — não usar `montar_resumo` por animal aqui (N+1 com o banco em SP).
- Lote que esvaziou por fora (venda, mangueira) continua com `LotePiquete` aberto; o painel
  trata como saída na data do último `AnimalLote.data_fim` daquele lote.
- **Frontend:** `static/pastos.js`. Toque no lote → "Levar para cá" (ou segurar e arrastar)
  → confirma; separar/juntar pela barra fixa do rodapé. Sem rede: vai pra fila offline com
  `chave` (servidor não duplica) e a tela é atualizada de forma otimista.
- **Cor e ícone do lote** (`Lote.cor`/`Lote.icone`): todo lote novo ganha cor automática
  (listener `before_insert` em models.py, cor menos usada de `PALETA_LOTES`); lote antigo sem
  cor usa `cor_do_lote()` (fixa pelo id). Mapa: um pino por lote no centro do piquete; de
  longe só os pinos, a partir do zoom 16 aparecem os nomes (`.pt-zoom-perto`). Toque no
  pino = ficha rápida (cabeças, kg médio, UA, uGMD médio, piquete, ações, cor/ícone).
- **Camadas do mapa** (`CamadaMapa`): divisa da fazenda (`tipo=divisa`) e áreas de outros
  usos (`tipo=uso`: lavoura, madeira, reserva, sede, outro). Só contexto visual — não recebem
  gado nem entram na lotação. Importadas pelo mesmo "Importar arquivo", escolhendo o destino.
- `#pt-mapa` tem `isolation: isolate`: sem isso as camadas do Leaflet (z-index 400+) ficam
  por cima da ficha/barra.
- **Datas:** usar `hojeLocal()` (app.js) — `toISOString()` é UTC e depois das 21h já é o dia
  seguinte. O painel recebe `?hoje=` do aparelho porque o servidor (Render) roda em UTC.

## Histórico dos piquetes e peso estimado — "o passado não muda"

- **Peso estimado** (`services/peso_estimado.py`): entre pesagens, peso = último peso + GMD ×
  dias (máx. 120 dias; passou disso = "estimativa velha"). GMD = média do uGMD do LOTE; sem
  GMD, GMD de referência por época (`ConfigValor` chave `gmd_referencia_epocas`, editável em
  Config; padrão águas out–mar 0,5 / seca abr–set 0,2). NUNCA vira pesagem; só cálculo.
  Pastos (UA, UA/ha, kg médio) usam o estimado e mostram "~"; `peso_medio_real` também vai.
- **Foto da ocupação** (`LotePiquete`): na entrada guarda cabeças, peso (real/estimado),
  `entrada_estimada` e os **hectares do piquete naquela data**; na saída, cabeças/peso/
  `saida_estimada`. Desfazer limpa a foto da saída. Ocupações antigas (antes disso) não têm foto.
- **Pasto por período** (`PastoPeriodo` em models_campo.py): substitui = troca/reforma (fecha o
  atual na véspera); `substitui=False` = sobressemeadura (azevém no Tifton). `Piquete.capim` é
  só o texto do pasto atual (sincronizado). Lista `pasto` nas opções. Migração do capim antigo
  roda no start (`migrar_capim_para_periodos`, idempotente).
- **Proteção do contorno**: mudar geometria/hectares de piquete que já teve gado exige
  `corrigir=True` (só pra desenho errado desde o início); reimportar arquivo não mexe nele
  (`protegidos`). Cerca nova = **Dividir** (`services/pastos_historico.dividir`): encerra o
  original (`ativo=False`, `encerrado_em`, renomeado "Nome (até dd/mm/aaaa)") com a área antiga,
  cria as partes (`origem_id`) herdando pasto e descanso, e leva o gado pra parte escolhida.
  Divisão não tem Desfazer. Remover piquete com histórico também renomeia (libera o nome).
- **Uso da área** (`Piquete.uso`): perene / inverno (lavoura no verão, gado no inverno) /
  verao. Lavoura pura não é piquete (vai como "Outras áreas"). **Grupo** = `AreaPasto` (só
  organiza a lista; guarda se a terra é própria ou arrendada). Na importação: 1) o que é o
  arquivo, 2) uso, 3) pastagem (padrão + por linha, lista `pasto` da Config), grupo opcional.
- Histórico do piquete: `GET /api/pastos/piquetes/{id}/historico` (ocupações com UA/ha da
  época, GMD do período, pasto da época, origem/partes) — botão 📜 na lista, mapa e edição.

## Campo: sal no cocho e sanidade

- **Modelos** em `app/models_campo.py` (importado no fim de models.py): `SalgaCocho` (lote,
  piquete e cabeças do momento, sal, kg, data/hora local do aparelho, quem) e
  `OcorrenciaSanitaria` (animal, lote do momento, problema, remédio, dose, carência →
  `carencia_ate`). Serviço `services/campo.py`, rotas `/api/sal` e `/api/sanidade`
  (`routers/campo.py`). Peão e dono lançam; apagar = dono, ou o próprio autor no mesmo dia.
- **Consumo de sal** = kg ÷ (cabeças × dias até a salga seguinte); média dos últimos 60 dias.
  A última salga ainda está no cocho e não entra.
- **Carência**: `/api/animais-cache` traz `carencia_ate`; mangueira, pesagem rápida e Sanidade
  mostram "⚠ EM CARÊNCIA até dd/mm" em vermelho (`emCarencia`/`textoCarencia` em app.js).
- Listas do campo em `OpcaoCadastro` (categorias `sal`, `medicamento`, `problema`, com
  valores iniciais em `opcoes.PADROES`); o peão pode criar opção nova na hora.
- Frontend `static/campo.js`: "🧂 Salgar cocho" na barra do lote e na ficha do lote (Pastos)
  e a aba Sanidade. Sem rede vai pra fila com `chave` (não duplica).
- Contexto: a fazenda trata só quem precisa (método SICOPA) — por isso sanidade é por animal,
  não calendário de vacinação do rebanho.

## Financeiro (aba Financeiro, só DONO) — substitui a planilha CONSIPA

- Análise da CONSIPA e decisões do Antonio: `docs/financeiro_consipa_engenharia_reversa.md`
  (§5). Progresso/retomada: `docs/financeiro_progresso.md` (tarefa agendada
  "continuar-financeiro-gado" lê esse arquivo; desativar quando tudo estiver [x]).
- **Modelos** em `app/models_financeiro.py` (importado no fim de models.py): FinLancamento
  (1 compra) + FinParcela (vencimentos), FinPlano (tipo › setor › grupo › categoria — só 3
  níveis, sem item/subitem), FinFornecedor (CNPJ/CPF + apelidos + classificação aprendida),
  FinRecorrente, FinRegra (aprendizado fornecedor/NCM → categoria), FinContribuinte (CPF/CNPJ
  digitado na tela + certificado A1 CRIPTOGRAFADO), FinNota (caixa de entrada de NF-e),
  FinMovimento (extrato OFX). Campo **fazenda** (Água do Tigre / Castro) em todo lançamento.
- **Serviços** `services/fin_*.py`; rotas `/api/fin/*` (`routers/financeiro.py`, router inteiro
  com `requer_dono`). Frontend `static/financeiro.js` (lançar, resultado, lançamentos, revisar,
  recorrentes) e `static/financeiro-notas.js` (notas, extrato, cadastros).
- Regras: sem categoria = `revisar=True` (vermelho, aba Revisar); excluir = `excluido=True`
  com motivo (nunca apaga); parcela `pago=None` = automático (venceu = realizado), `False` = a
  confirmar (recorrentes). Resultado: visão **caixa** (vencimento) ou **competência** (compra).
- **Horários** do Financeiro gravados em UTC (`agora_utc()`, saída com `Z` via `iso_utc()`); a
  tela converte pra hora local (`finLocal`). Não usar `datetime.now()` aqui.
- **SEFAZ** (`fin_sefaz.py`): NFeDistribuicaoDFe (distNSU/consChNFe) + evento Ciência da
  Operação 210210 assinado (XMLDSig RSA-SHA1/C14N com lxml). Exige e-CPF/e-CNPJ A1 do próprio
  documento. Limite da SEFAZ: 1 consulta/hora (cStat 137/656 → `pode_consultar_apos`). Só NF-e
  modelo 55; NFC-e e NFS-e não vêm. Testado só com SEFAZ simulada (`transporte` trocado nos
  testes) — o primeiro uso real precisa ser acompanhado. Chave de criptografia: `FIN_CHAVE` no
  .env (sem ela usa o AUTH_SECRET; trocar obriga a reenviar os certificados).
- Upload (certificado, planilha, XML, OFX) não vai pro log de auditoria (`(arquivo enviado)`).
- Importar CONSIPA: Cadastros › Importar CONSIPA (idempotente por `chave_origem`). Totais de
  2025 batem centavo a centavo com a planilha (despesa R$ 3.555.070,06 / receita R$ 4.266.963,84).

## Estado atual (jul/2026)

Tudo no ar e funcionando: login+perfis, offline/PWA, deploy Render+Supabase, config
tipos/raças, edição de ficha (brinco/tipo/raça/obs/excluir animal/excluir pesagem),
histórico de lotes, seletor de brinco duplicado, seletor de lote em todo lugar, cache local,
compra sem lote de origem, aba Manejos, indicadores por lote (GMD/uGMD/UA).
Pendências abertas: método do uGMD médio do lote (usuário vai decidir); possível banner de
"nova versão disponível" pra evitar recarregar na mão.
