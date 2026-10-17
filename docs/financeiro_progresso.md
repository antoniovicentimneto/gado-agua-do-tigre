# Financeiro — progresso da implementação

Usado pela tarefa agendada "Continuar Financeiro" para retomar o trabalho se a sessão
parar no meio (ex.: acabaram os créditos). Marque [x] ao concluir cada item e faça commit.
Pedido do Antonio (16/10/2026): fazer todas as fases; o CPF/CNPJ é digitado numa tela
(não fixo), cada um com seu certificado. Decisões em `financeiro_consipa_engenharia_reversa.md` §5.

## Backend
- [x] Modelos, serviços, rotas `/api/fin/*` (só dono), testes (commit 41246b2)

## Frontend (backend/static/financeiro.js + index.html + style.css)
- [ ] Aba "Financeiro" (só dono) com sub-abas: Lançar · Notas · Resultado · Lançamentos · Revisar · Recorrentes · Extrato · Cadastros
- [ ] Lançar: formulário rápido (fornecedor com autocompletar e sugestão, valor, parcelas, conta, fazenda), "repetir último"
- [ ] Resultado por mês: árvore × meses, filtros, clique no número abre os lançamentos, clique abre a edição
- [ ] Lançamentos: tabela ordenável e filtrável, quem lançou/quando, editar/excluir (inativar)
- [ ] Revisar: sem categoria em vermelho, a confirmar (recorrentes), possíveis duplicados
- [ ] Notas: importar XML/ZIP, caixa de entrada com sugestão, dividir por item, lançar/ignorar, "buscar na SEFAZ"
- [ ] Cadastros: CPF/CNPJ (digitar + enviar certificado .pfx + senha), plano de contas, fornecedores (juntar), contas, fazendas, importar CONSIPA
- [ ] Recorrentes e Extrato (OFX + conciliação)
- [ ] Cache-busting: subir ?v= no index.html e service-worker.js (lista + nome do CACHE)

## Verificação e entrega
- [ ] Testar no navegador com banco isolado (`gado-teste`, porta 8078) importando a CONSIPA — nunca no Supabase
- [ ] Testar na largura de celular
- [ ] Atualizar CLAUDE.md (seção Financeiro) e README
- [ ] Commit final. NÃO dar push (push = deploy em produção) sem o Antonio autorizar.
