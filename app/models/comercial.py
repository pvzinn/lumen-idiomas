"""O que a escola recebe da conversa: leads e escalonamentos."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.conversa import Conversa
from app.models.enums import (
    CategoriaEscalonamento,
    IdiomaInteresse,
    ModalidadeInteresse,
    ParaQuem,
    TipoContato,
    pg_enum,
)


class Lead(Base):
    """Contato coletado na conversa, com os campos da seção 5.3.

    Quase tudo é anulável, inclusive o que a seção 5.3 marca como obrigatório.
    Não é descuido: a seção 5.2 diz que se o interessado abandonar no meio da
    coleta, o que já foi informado é registrado — "lead parcial é lead". A
    obrigatoriedade é regra de conversa (o bot pergunta até obter), não invariante
    de linha. NOT NULL aqui produziria o oposto do pedido: o lead incompleto não
    caberia na tabela e se perderia inteiro.
    """

    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(
            "idade_aluno IS NULL OR idade_aluno > 0",
            name="idade_aluno_positiva",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # UNIQUE: um lead por conversa. Um segundo conjunto de dados na mesma
    # conversa é correção do primeiro — a mesma pessoa se corrigindo —, não um
    # segundo interessado. Se um dia a escola quiser registrar dois alunos numa
    # conversa só (dois filhos, por exemplo), isto vira índice não único.
    conversa_id: Mapped[int] = mapped_column(
        ForeignKey("conversas.id", ondelete="CASCADE"),
        unique=True,
    )

    nome: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # WhatsApp ou e-mail em uma coluna só, com o tipo ao lado: a seção 5.3 pede
    # "o que a pessoa preferir", e duas colunas exclusivas entre si exigiriam um
    # check para garantir que exatamente uma esteja preenchida — mais estrutura
    # para o mesmo fato.
    contato: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tipo_contato: Mapped[TipoContato | None] = mapped_column(
        pg_enum(TipoContato, "tipo_contato"), nullable=True
    )

    idioma_interesse: Mapped[IdiomaInteresse | None] = mapped_column(
        pg_enum(IdiomaInteresse, "idioma_interesse"), nullable=True
    )
    para_quem: Mapped[ParaQuem | None] = mapped_column(
        pg_enum(ParaQuem, "para_quem"), nullable=True
    )

    # Só faz sentido quando `para_quem = dependente`, mas não há check cruzando
    # os dois: numa coleta interrompida os campos chegam fora de ordem e
    # incompletos, e um check assim recusaria justamente o lead parcial.
    idade_aluno: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    modalidade_interesse: Mapped[ModalidadeInteresse | None] = mapped_column(
        pg_enum(ModalidadeInteresse, "modalidade_interesse"), nullable=True
    )

    # Texto e não enum: unidade é dado da escola, que abre e fecha endereço sem
    # pedir licença ao esquema. Enum transformaria "abrimos uma unidade" em
    # migration.
    unidade_interesse: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Texto livre por definição na seção 5.3 — "turno e dias possíveis".
    disponibilidade: Mapped[str | None] = mapped_column(Text, nullable=True)

    # O campo que a seção 5.3 diz ser o que mais ajuda a secretaria a preparar o
    # contato. Livre, e sem limite de tamanho por isso.
    objetivo: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Único campo da seção 5.3 que é NOT NULL, porque é o que autoriza a escola
    # a ligar. Default `false` no servidor: na dúvida, não houve consentimento.
    # Um lead com `consentimento = false` é lead abandonado antes da
    # autorização — fica registrado, e não vai para a secretaria.
    consentimento: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversa: Mapped["Conversa"] = relationship()
    escalonamentos: Mapped[list["Escalonamento"]] = relationship(back_populates="lead")


class Escalonamento(Base):
    """Pergunta que o bot não respondeu e encaminhou para uma pessoa.

    Tabela única: as seis categorias da seção 4 e mais `sem_resposta` convivem
    aqui. O relatório de perguntas sem cobertura na base — descrito na seção 9
    como o entregável de maior valor comercial — é
    `WHERE categoria = 'sem_resposta'`, não um UNION entre duas tabelas quase
    iguais. A diferença de ciclo de vida (a secretaria fecha um escalonamento;
    uma lacuna de conteúdo talvez nunca "feche") é filtro no painel, não
    estrutura.
    """

    __tablename__ = "escalonamentos"

    id: Mapped[int] = mapped_column(primary_key=True)

    conversa_id: Mapped[int] = mapped_column(
        ForeignKey("conversas.id", ondelete="CASCADE"),
        index=True,
    )

    # A mensagem do interessado que disparou o escalonamento. CASCADE pelo mesmo
    # motivo da conversa: apagada a conversa, apaga-se o que dela derivou.
    mensagem_id: Mapped[int] = mapped_column(
        ForeignKey("mensagens.id", ondelete="CASCADE"),
        index=True,
    )

    categoria: Mapped[CategoriaEscalonamento] = mapped_column(
        pg_enum(CategoriaEscalonamento, "categoria_escalonamento"),
        index=True,
    )

    # Cópia deliberada do texto da mensagem. O painel lista perguntas; fazê-lo
    # reconstruir o texto pela conversa a cada consulta é caro e frágil, e a
    # pergunta registrada precisa ser a que de fato escalou, mesmo que a
    # conversa siga e a mensagem seja reinterpretada depois. Numa pergunta que
    # mistura assunto respondível e escalável (seção 4), aqui entra só a parte
    # que escalou — que não é o conteúdo integral da mensagem.
    pergunta: Mapped[str] = mapped_column(Text)

    # Opcional: nem todo escalonamento coleta contato, e a seção 5.2 proíbe
    # insistir depois de uma recusa. SET NULL, não CASCADE — apagar o lead a
    # pedido do titular não pode apagar o fato de que a pergunta ficou sem
    # resposta, que é informação da escola sobre o próprio material.
    lead_id: Mapped[int | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"),
        nullable=True,
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Marcado pela secretaria quando o retorno aconteceu. `false` no servidor
    # para que a fila de pendências seja o default de quem esquecer a coluna.
    resolvido: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    lead: Mapped["Lead | None"] = relationship(back_populates="escalonamentos")


__all__ = ["Escalonamento", "Lead"]
