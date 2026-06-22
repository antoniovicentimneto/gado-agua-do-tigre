# 🐂 Gado Água do Tigre

App de controle de peso do gado — substitui a planilha `2025_PLANILHA GADO BOAVISTINHA.xlsx`.

Em vez de uma coluna nova para cada data de pesagem (que crescia sem parar na
horizontal), cada pesagem vira um registro próprio. O GMD é sempre calculado, nunca
digitado.

## Funcionalidades

- **Mangueira** (tela principal do dia a dia): sessão de pesagem com 3 colunas
  (a pesar · lançamento · pesados). Tipos: manejo, compra, venda peso fazenda e
  venda peso morto. Separa em sublotes com "lote ativo grudado", mostra último
  peso/GMD ao digitar o brinco, numera a ordem de pesagem, conta por sublote.
  Avisa quando o brinco está fora do lote / já foi pesado / não existe
  (cadastro rápido). Permite pesar sem brinco e depois vincular a um animal que
  perdeu o brinco (herda o histórico). Finaliza com resumo e exporta CSV.
- **Rebanho**: lista de animais com último peso, GMD e uGMD; busca por brinco e filtro por status.
- **Ficha do animal**: histórico de pesagens, GMD total, último GMD (uGMD) e **GMD por período**
  (escolhe um intervalo para comparar pastagens/safras).
- **Pesagem rápida**: tela pensada para o curral — digita brinco → peso → Enter → próximo animal.
- **Lotes com histórico**: ao mudar o animal de lote, o vínculo anterior é fechado com data.
- **Venda**: puxa o rendimento padrão por tipo (Vaca 48%, Novilha 50%, Boi 52%), editável,
  e calcula a arroba líquida e o valor recebido pelo preço da @ líquida.
- **Painel**: total, ativos, vendidos, GMD médio do rebanho e total de pesagens.
- **Login com perfis**: dono/dona tem acesso completo; o peão só lança peso e
  mexe em lotes durante a pesagem — não edita/remove pesagens antigas, não
  exporta a planilha e não acessa compra/venda. O dono cadastra e remove
  usuários na aba **Usuários**.
- **Funciona sem internet**: dá pra lançar peso na mangueira mesmo sem sinal —
  fica guardado no celular e é enviado sozinho quando a conexão voltar (veja
  "Funciona sem internet" abaixo). Pode "instalar" o app na tela inicial do
  celular (PWA).

## Como funciona o GMD

- **GMD** = (último peso − primeiro peso) ÷ dias totais — índice principal.
- **uGMD** = GMD do último período (entre as duas últimas pesagens).
- **GMD por período** = GMD entre as pesagens dentro do intervalo escolhido.

## Tecnologia

- Python 3.11+ · FastAPI · SQLAlchemy
- Banco: PostgreSQL no Supabase (nuvem) em produção; SQLite local
  (`backend/gado.db`) para desenvolvimento/testes — basta trocar `DATABASE_URL`
  no `.env`.
- Frontend web responsivo (funciona no celular e no computador), com PWA
  (manifesto + service worker) e fila local de pesagens offline.
- Login com token assinado (sem serviço externo) e dois perfis: dono e peão.

## Login (primeiro acesso)

Na primeira vez que o app abrir sem nenhum usuário cadastrado, aparece a tela
"Primeiro acesso" para criar a conta do dono. Depois disso, todo acesso passa
pela tela de login. O dono cria as contas da esposa e do peão na aba
**Usuários**, escolhendo o perfil (dono ou peão).

## Funciona sem internet

Na mangueira, se a pesagem não conseguir falar com o servidor (sem sinal), o
peso fica guardado no aparelho (mostra "📡 N pesagens aguardando envio" no
topo) e é enviado automaticamente assim que a conexão voltar — não precisa
reabrir nada. Vale só para pesagens dentro de uma sessão já aberta com sinal;
abrir uma sessão nova exige conexão.

## Instalação

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Importar a planilha (primeira carga)

```bash
cd backend
python importar.py "C:\caminho\para\2025_PLANILHA GADO BOAVISTINHA.xlsx"
```

Lê a aba **DADOS**, cria os animais, normaliza as colunas-data em pesagens e
corrige datas digitadas com erro. ⚠️ **Recria o banco** — use só na primeira carga.

## Atualizar pela planilha SEM apagar nada (incremental)

```bash
cd backend
python atualizar.py "C:\caminho\para\PLANILHA.xlsx"
```

Só adiciona animais novos e pesagens de datas que ainda não existem. **Nunca
apaga** o que foi lançado no app e faz um backup automático antes
(`gado_backup_AAAAMMDD_HHMMSS.db`).

## Backup / Exportar

- No app, aba **Painel → Exportar planilha Excel**: baixa um `.xlsx` completo
  (abas *Animais* e *Pesos* em formato largo) — backup legível e de fácil acesso.
- O banco fica em `backend/gado.db`. Backups manuais: é só copiar esse arquivo.

## Rodar o app

```bash
cd backend
python -m uvicorn app.main:app --port 8077
```

Acesse: http://127.0.0.1:8077

## Rodar os testes

```bash
cd backend
pytest
```

## Nuvem (Supabase) e deploy

- O banco de produção já está no Supabase (Postgres); a `DATABASE_URL` fica no
  `backend/.env` (não versionado — guarda a senha do banco).
- O backend sobe no **Render** a partir do `render.yaml` na raiz do projeto
  (veja "Deploy no Render" abaixo) para acessar pelo celular fora da rede de
  casa.

## Deploy no Render

O `render.yaml` já descreve o serviço (`rootDir: backend`, instala
`requirements.txt`, roda `uvicorn` na porta que o Render define). Passos:

1. Subir este projeto (`gado_app/`) pra um repositório no GitHub.
2. Criar conta em [render.com](https://render.com) e conectar com o GitHub.
3. "New" → "Blueprint" → escolher o repositório → o Render lê o
   `render.yaml` automaticamente.
4. Preencher a variável `DATABASE_URL` com a mesma string de conexão do
   Supabase usada no `backend/.env` (a do **pooler**, não a "direct"). A
   `AUTH_SECRET` é gerada automaticamente pelo Render.
5. Deploy. O link público (`https://gado-agua-do-tigre.onrender.com`) já
   funciona no celular, com login e funcionamento offline.

No plano free o serviço "dorme" depois de ficar um tempo sem acesso e demora
uns segundos pra acordar na primeira abertura do dia — normal, não é erro.

## Estrutura

```
backend/
  app/
    main.py          # aplicação FastAPI + servir o frontend
    config.py        # configurações (DATABASE_URL, rendimentos padrão)
    database.py      # conexão com o banco
    models.py        # tabelas (animais, pesagens, lotes, dentições, scores, venda...)
    schemas.py       # validação da API
    routers/api.py   # endpoints
    services/        # regras de negócio (gmd, venda, importação, consultas)
  static/            # frontend (HTML, CSS, JS)
  tests/             # testes (pytest)
  importar.py        # importação da planilha
```
