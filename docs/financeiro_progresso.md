# Financeiro — progresso da implementação

Usado pela tarefa agendada "Continuar Financeiro" para retomar o trabalho se a sessão
parar no meio (ex.: acabaram os créditos). Marque [x] ao concluir cada item e faça commit.
Pedido do Antonio (16/10/2026): fazer todas as fases; o CPF/CNPJ é digitado numa tela
(não fixo), cada um com seu certificado. Decisões em `financeiro_consipa_engenharia_reversa.md` §5.

## Backend
- [x] Modelos, serviços, rotas `/api/fin/*` (só dono), testes (commit 41246b2)

## Frontend (backend/static/financeiro.js + index.html + style.css)
- [x] Aba "Financeiro" (só dono) com sub-abas: Lançar · Notas · Resultado · Lançamentos · Revisar · Recorrentes · Extrato · Cadastros
- [x] Lançar: formulário rápido (fornecedor com autocompletar e sugestão, valor, parcelas, conta, fazenda), "repetir último"
- [x] Resultado por mês: árvore × meses, filtros, clique no número abre os lançamentos, clique abre a edição
- [x] Lançamentos: tabela ordenável e filtrável, quem lançou/quando, editar/excluir (inativar)
- [x] Revisar: sem categoria em vermelho, a confirmar (recorrentes), possíveis duplicados
- [x] Notas: importar XML/ZIP, caixa de entrada com sugestão, dividir por item, lançar/ignorar, "buscar na SEFAZ"
- [x] Cadastros: CPF/CNPJ (digitar + enviar certificado .pfx + senha), plano de contas, fornecedores (juntar), contas, fazendas, importar CONSIPA
- [x] Recorrentes e Extrato (OFX + conciliação)
- [x] Cache-busting: subir ?v= no index.html e service-worker.js (lista + nome do CACHE)

## Verificação e entrega
- [x] Testar no navegador com banco isolado (`gado-teste`, porta 8078) importando a CONSIPA — nunca no Supabase
- [x] Testar na largura de celular
- [x] Atualizar CLAUDE.md (seção Financeiro) e README
- [x] Commit final (falta só o Antonio autorizar o push/deploy). NÃO dar push (push = deploy em produção) sem o Antonio autorizar.
