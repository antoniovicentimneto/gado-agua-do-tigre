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
nome do CACHE `gado-agua-do-tigre-vX`). **Versão atual: v=20 / cache v12.**
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

## Estado atual (jul/2026)

Tudo no ar e funcionando: login+perfis, offline/PWA, deploy Render+Supabase, config
tipos/raças, edição de ficha (brinco/tipo/raça/obs/excluir animal/excluir pesagem),
histórico de lotes, seletor de brinco duplicado, seletor de lote em todo lugar, cache local,
compra sem lote de origem, aba Manejos, indicadores por lote (GMD/uGMD/UA).
Pendências abertas: método do uGMD médio do lote (usuário vai decidir); possível banner de
"nova versão disponível" pra evitar recarregar na mão.
