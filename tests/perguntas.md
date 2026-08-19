# Conjunto de perguntas de teste — chatbot Lumen Idiomas

Este arquivo é a especificação de comportamento do bot. Ele é escrito **antes** da implementação e vira teste automatizado na fase 6.

## Como preencher

| Coluna | O que colocar |
|---|---|
| `id` | Identificador estável. Não renumerar depois. |
| `pergunta` | Exatamente como uma pessoa real escreveria, com gírias e erros de digitação quando for o caso. |
| `esperado` | `responder`, `parcial` ou `recusar`. |
| `origem` | Arquivo onde mora a resposta. Vazio (`—`) quando `esperado` é `recusar`. |
| `nota` | O que essa pergunta está testando. |

### Os três resultados esperados

- **`responder`** — a base cobre a pergunta. O bot responde com base nela e não escala.
- **`parcial`** — a base cobre uma parte. O bot responde o que sabe, diz claramente o que não sabe e escala apenas a parte faltante.
- **`recusar`** — a base não cobre, ou o assunto está fora de escopo por decisão de projeto (negociação, dado individual, agendamento, reclamação). O bot não tenta responder, registra a pergunta e encaminha para atendimento humano.

### Distribuição atual

| Tipo | Quantidade |
|---|---|
| `responder` — diretas | 9 |
| `responder` — informais | 4 |
| `responder` — combinadas | 4 |
| `parcial` | 5 |
| `recusar` | 5 |
| **Total** | **27** |

---

## Perguntas

| id | pergunta | esperado | origem | nota |
|---|---|---|---|---|
| P01 | Quanto custa o curso de inglês? | responder | 06 | Direta. Ambígua quanto à modalidade: o bot deve dar os dois valores ou perguntar qual. |
| P02 | vcs tem aula pra crianca de 8 anos? | responder | 02 | Informal, sem acento. Testa se a busca aguenta escrita descuidada. |
| P03 | Quero fazer inglês à noite mas só posso terça e quinta. Tem turma e quanto sai? | responder | 04 + 06 | Combinada: horário está em 04, valor em 06. Dois trechos precisam ser recuperados. |
| P04 | O certificado de vocês serve pra eu fazer faculdade fora do Brasil? | responder | 07 | Direta e crítica. Resposta errada aqui gera reclamação real. |
| P05 | Vocês vão oferecer outros idiomas no futuro? | parcial | 02 | Base cobre o presente, não planos. O bot deve responder o que é hoje e não especular. |
| P06 | Consigo desconto se eu pagar o ano todo adiantado? | recusar | — | Negociação. A base tem desconto por semestre à vista, não por ano — o bot não pode extrapolar. |
| P07 | Quantos professores trabalham na Lumen? | responder | 01 | Direta. Fato numérico isolado, o caso mais fácil do conjunto. Serve de linha de base: se essa falhar, o problema é de infraestrutura, não de recuperação. |
| P08 | Entendi que a escola de vocês recomenda aulas particulares quando o aluno tem mais dificuldades. Como funciona isso? Qual o valor de uma aula particular? | responder | 09 + 11 + 06 | Combinada com três origens: a recomendação está em 09, o funcionamento em 11, o valor em 06. A mais exigente do conjunto para a recuperação. |
| P09 | O espanhol que vocês ensinam tem algum sotaque específico? Queria aprender o espanhol igual aos mexicanos. | parcial | 02 | A base diz "variante latino-americana", que não é o mesmo que "mexicano". O bot deve informar a variante e não confirmar a equivalência com o espanhol do México. |
| P10 | A realização das tarefas de casa contam para a aprovação do aluno? | responder | 03 + 09 | Direta, mas expõe uma duplicação: 03 e 09 afirmam o mesmo fato. Ver "Achados" no fim do arquivo. |
| P11 | Vocês passam avaliações também ou só tarefas? | responder | 03 | Direta. A composição da média está em uma única seção de 03. |
| P12 | Dá pra um aluno ser reprovado? | responder | 03 | Direta. O bot deve citar os dois critérios (nota e frequência) e a recuperação, sem omitir que a reprovação existe. |
| P13 | Posso ter uma aula experimental para cada idioma ou só uma aula por aluno? | parcial | 05 | A base diz que a aula experimental é única, mas não trata do caso de dois idiomas. Ver "Achados". |
| P14 | Com quantos anos um aluno ainda é considerado da turma Kids? | responder | 02 | Direta. Faixa etária explícita na base. |
| P15 | Meu filho tem 8 anos mas já fala inglês muito bem, ele poderia ser alocado em uma turma com outros alunos do mesmo nível dele ou só depende da idade? | responder | 02 + 03 | Combinada: a regra de faixa etária está em 02, o nivelamento em 03. O bot precisa responder que a idade define a faixa e o nivelamento define a etapa dentro dela. |
| P16 | Quero cancelar minha matrícula, posso fazer isso digitalmente ou só no presencial? | parcial | 08 | A base define a política (por escrito, 30 dias), mas não o canal. Além disso, o bot informa a regra e **não** executa o cancelamento. Distinção central: informação sim, ação não. |
| P17 | Posso entrar no meio de um semestre ou preciso esperar o próximo? | responder | 05 | Direta. A resposta é condicional (duas primeiras semanas, se houver vaga) e o bot não pode simplificar para um "sim" ou "não". |
| P18 | Tem algum desconto pra pagamento à vista? | responder | 06 | Direta. Par proposital com P06: aqui o desconto existe, lá não. Testa se o bot distingue as duas condições. |
| P19 | Meu filho tem 15 anos e já é praticamente fluente em inglês, mas quer melhorar na conversação. Posso matricular ele no curso de conversação? | responder | 02 | Direta com armadilha. A resposta é não, por idade mínima de 17 anos. Um bot ruim confirma a matrícula porque o curso existe. |
| P20 | Estou apertado esse mês e não vou conseguir pagar a mensalidade na data combinada. Será que meu filho pode continuar fazendo as aulas normalmente e no mês que vem eu acerto tudo? | parcial | 06 | A base cobre a regra geral (aula não é interrompida, há multa e juros), mas o caso é individual. O bot informa a regra, não autoriza o atraso e encaminha à secretaria. Tom importa: não pode soar como permissão concedida. |
| P21 | Meu boleto de agosto não chegou no e-mail, consegue reenviar pra mim? | recusar | — | Dado financeiro individual. O bot não tem e não deve ter acesso ao cadastro de nenhum aluno. |
| P22 | Queria marcar a aula experimental pra quinta às 19h, dá certo? | recusar | — | Agendamento. O bot explica que a aula experimental existe e precisa ser agendada pela secretaria, mas não marca nada. |
| P23 | A professora da turma do meu filho falta demais e não devolve as tarefas corrigidas. O que vocês vão fazer sobre isso? | recusar | — | Reclamação. Nenhuma resposta automática é adequada aqui. Escalar com prioridade e registrar. |
| P24 | Ainda tem vaga na turma de inglês B1 de terça e quinta à noite no Setor Bueno? Consegue segurar uma pra mim? | recusar | — | Promessa de vaga. A base descreve horários possíveis, não a grade real do semestre nem a ocupação. O bot não pode inferir disponibilidade. |
| P25 | vcs tem aula online msm? funciona igual a presencial? | responder | 04 | Informal. Testa se "msm" e a ausência de pontuação atrapalham a recuperação. |
| P26 | oq q eu preciso levar pra fazer a matricula | responder | 05 | Informal, sem acento e sem interrogação. Pergunta escrita como quem manda mensagem no fim da noite. |
| P27 | tem estacionamento ai no bueno? | responder | 10 | Informal, com referência abreviada à unidade. Testa se "bueno" recupera a seção da unidade Setor Bueno. |

---

## Achados desta etapa

Duas perguntas revelaram problemas na base de conhecimento, antes de existir qualquer código.

### P10 — duplicação entre `03` e `09`

O arquivo `03-niveis-e-nivelamento.md` afirma que a média final é composta por avaliação, tarefas e participação. O arquivo `09-metodologia-e-professores.md` afirma, separadamente, que as tarefas compõem parte da nota.

É uma violação branda da regra R4: o mesmo fato mora em dois lugares. O risco não é a resposta de hoje, e sim a divergência futura — se a composição da nota mudar e só um arquivo for atualizado, a busca passará a recuperar dois trechos contraditórios.

**Correção prevista:** `03` mantém a composição da média; `09` passa a dizer apenas que as tarefas são corrigidas com devolutiva, sem afirmar que compõem a nota.

### P13 — lacuna real em `05`

O arquivo `05-calendario-e-matricula.md` diz que a aula experimental é única e não se repete, mas não trata do caso de quem se interessa pelos dois idiomas. Não existe resposta na base.

Enquanto a lacuna existir, o comportamento correto é `parcial`. Depois de corrigida, esta linha passa a `responder`.

**Correção prevista:** acrescentar a `05` que a aula experimental é uma por pessoa, independentemente do número de idiomas de interesse.

As duas correções ficam para depois da fase 1, junto com a primeira rodada de avaliação da recuperação. Corrigir agora significaria alterar a base sem ter como medir se a alteração melhorou alguma coisa.

---

## Observação sobre o equilíbrio do conjunto

Este conjunto tem 17 perguntas `responder` para 5 `recusar`. A proporção reflete a realidade do atendimento, em que a maioria das perguntas tem resposta, mas subrepresenta o comportamento mais arriscado do sistema.

Ao medir os resultados, acompanhe as taxas separadamente por categoria. Uma taxa global de acerto de 85% pode esconder um bot que acerta quase tudo em `responder` e falha na metade das `recusar` — que é exatamente o modo de falha que causa prejuízo para a escola.
