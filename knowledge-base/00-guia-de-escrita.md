---
id: guia-de-escrita
titulo: Guia de escrita da base de conhecimento
tipo: interno
indexar: false
atualizado_em: 2026-08-11
---

# Guia de escrita da base de conhecimento — Lumen Idiomas

Documento interno. **Não deve ser indexado** junto com a base: ele fala sobre a base, não sobre a escola, e se for recuperado vai poluir as respostas.

---

## 1. Por que a estrutura importa

O sistema não entrega o documento inteiro ao modelo. Ele quebra cada arquivo em trechos, guarda a representação numérica de cada trecho e, na hora da pergunta, recupera apenas os 3 a 5 trechos mais parecidos com a dúvida do usuário.

O modelo recebe esses trechos soltos, sem o arquivo em volta.

Consequência prática: **um trecho que só faz sentido dentro do documento é um trecho que vai gerar resposta errada.** A maior parte do trabalho de qualidade em recuperação não está no código; está aqui.

A quebra será feita por título de seção (`##`). Ou seja: **cada `##` deste projeto é, na prática, uma unidade de resposta.** Escreva pensando nisso.

---

## 2. Regras de escrita

### R1 — Cada seção se sustenta sozinha

A primeira frase da seção deve responder à pergunta central dela sem depender de nada anterior.

- Ruim: `Ele também pode ser feito online.`
- Bom: `O curso de inglês para adultos da Lumen também pode ser cursado na modalidade online ao vivo.`

### R2 — Nenhuma referência para fora da seção

Elimine "como dito acima", "veja a seção de valores", "além disso", "esse curso", "essa modalidade" quando o antecedente estiver em outra seção.

- Ruim: `Os descontos citados anteriormente não se aplicam a esse caso.`
- Bom: `O desconto de familiar não se aplica às aulas particulares da Lumen.`

### R3 — Repita o sujeito e o nome da escola

Parece redundante lendo o arquivo inteiro. Não é redundante quando o trecho aparece sozinho. Escreva "a Lumen Idiomas" ou "a Lumen" pelo menos uma vez em cada seção.

### R4 — Um fato mora em um lugar só

O valor da mensalidade existe apenas em `06-valores-e-pagamento.md`. Nenhum outro arquivo repete o número.

Se o mesmo fato aparecer em dois arquivos, um dia você atualiza um e esquece o outro — e a busca vai recuperar os dois trechos contraditórios ao mesmo tempo. O modelo então escolhe um, e você não controla qual.

Quando outro arquivo precisar tocar no assunto, cite sem o dado: `As aulas particulares da Lumen têm valor por hora-aula, diferente da mensalidade das turmas em grupo.`

### R5 — Use o vocabulário de quem pergunta

A busca é por significado, mas a proximidade de vocabulário ainda ajuda muito. Prefira as palavras do cliente e inclua as variações naturais dentro do texto.

- Ruim: `O investimento mensal para o programa regular é de R$ 389,00.`
- Bom: `A mensalidade das turmas em grupo presenciais da Lumen custa R$ 389,00 por mês.`

Termo interno ("programa regular", "módulo consolidado") só entra se você também explicar em linguagem comum na mesma seção.

### R6 — Seções entre 80 e 250 palavras

Seção curta demais vira um trecho pobre, sem contexto suficiente para o modelo responder. Seção longa demais mistura vários assuntos, e a busca passa a recuperar o trecho certo pelo motivo errado.

Passou de 250 palavras: quebre em duas seções com títulos próprios.

### R7 — Tabela sempre precedida de prosa

Tabela perde o cabeçalho e o sentido quando recuperada isolada. Só use para dados curtos e comparativos, e sempre coloque a informação principal em uma frase antes dela.

- Ruim: uma tabela de horários solta sob o título.
- Bom: `As turmas de inglês para adultos da Lumen acontecem em três horários: manhã, noite e sábado. A tabela abaixo detalha os dias e horários de cada uma.` seguido da tabela.

### R8 — Nada de tempo relativo

Proibido: "atualmente", "no próximo semestre", "a partir do mês que vem", "recentemente".

Use datas e períodos explícitos: "no semestre 2026/2", "a partir de 1º de fevereiro de 2026". O modelo não sabe quando o texto foi escrito, e o campo `atualizado_em` do cabeçalho existe justamente para isso.

### R9 — Declare os limites explicitamente

A base precisa conter as negativas mais perguntadas, escritas de forma afirmativa. Sem isso, o modelo não encontra nada, e um modelo que não encontra nada tende a inventar algo plausível.

- `A Lumen Idiomas oferece apenas inglês e espanhol. A escola não oferece cursos de francês, alemão, italiano ou japonês.`
- `A Lumen não emite certificados internacionais. A escola prepara para os exames, mas a certificação é emitida pela instituição examinadora.`

---

## 3. Cabeçalho obrigatório de cada arquivo

Todo arquivo da base começa com este bloco. Os campos viram metadados dos trechos no banco e permitem filtrar, auditar e mostrar a fonte da resposta no painel.

```yaml
---
id: valores-e-pagamento
titulo: Valores e pagamento
topico: comercial
publico: [interessados, alunos]
indexar: true
atualizado_em: 2026-08-11
---
```

- `id`: identificador estável, em minúsculas com hífen. Não mude depois de criado.
- `topico`: um entre `institucional`, `academico`, `comercial`, `operacional`.
- `publico`: para quem a informação serve.
- `indexar`: `false` apenas em documentos internos como este guia.
- `atualizado_em`: data real da última edição.

---

## 4. Estrutura de arquivos

| Arquivo | Cobre |
|---|---|
| `01-a-escola.md` | Quem é a Lumen, tempo de mercado, proposta, números gerais, canais de contato |
| `02-cursos-e-idiomas.md` | Idiomas oferecidos, faixas etárias, tipos de curso, o que a escola não oferece |
| `03-niveis-e-nivelamento.md` | Níveis A1–C1, como funciona o teste de nivelamento, duração e progressão |
| `04-modalidades-e-turmas.md` | Presencial, online ao vivo, particular, tamanho de turma, carga horária, horários |
| `05-calendario-e-matricula.md` | Datas de início, períodos de matrícula, documentos necessários, aula experimental |
| `06-valores-e-pagamento.md` | Mensalidade, matrícula, material, descontos, formas de pagamento, atraso, reajuste |
| `07-certificacoes-e-preparatorios.md` | Cursos preparatórios, exames atendidos, certificado interno da escola |
| `08-politicas.md` | Trancamento, cancelamento, reposição, transferência de turma, faltas, frequência mínima |
| `09-metodologia-e-professores.md` | Método de ensino, formação do corpo docente, avaliação, plataforma de apoio |
| `10-unidades-e-estrutura.md` | Endereços, horário de funcionamento, estacionamento, acessibilidade, salas |
| `11-particulares-e-empresas.md` | Aulas individuais, in-company, turmas fechadas, como funciona a contratação |

Ordem sugerida de escrita: comece por `02`, `04` e `06`. São os três que concentram a maioria das perguntas reais e vão te dar sinal cedo sobre a qualidade da recuperação.

---

## 5. O que não entra na base

Estes assuntos ficam **fora** de propósito. São exatamente os casos em que o bot deve dizer que não sabe e registrar a necessidade de atendimento humano:

- negociação de desconto fora da tabela;
- situação financeira de um aluno específico, segunda via de boleto, comprovante;
- reclamação sobre professor, turma ou atendimento;
- pedido de cancelamento com devolução de valores;
- agendamento efetivo de visita, aula experimental ou reunião;
- promessa de vaga em turma específica.

Se você colocar esses temas na base, o bot vai tentar respondê-los — e é justamente aí que ele erra de um jeito que custa dinheiro para a escola.

O comportamento de recusa é configurado no prompt do sistema, não aqui.

---

## 6. Checklist antes de dar um arquivo por pronto

- [ ] Cabeçalho preenchido, com `atualizado_em` real
- [ ] Toda seção começa com uma frase que responde à pergunta sozinha
- [ ] Nenhum pronome aponta para fora da seção
- [ ] "Lumen" aparece pelo menos uma vez por seção
- [ ] Nenhum "veja acima", "conforme citado", "além disso" com antecedente externo
- [ ] Nenhum dado numérico duplicado em outro arquivo da base
- [ ] Nenhuma seção passa de 250 palavras
- [ ] Toda tabela é precedida por uma frase com a informação principal
- [ ] Nenhuma expressão de tempo relativo
- [ ] As negativas mais comuns do tema estão escritas de forma afirmativa
