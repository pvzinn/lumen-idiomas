"""Registro da conversa: o que foi dito, e o que sustentou cada resposta.

A seção 9 do comportamento é categórica: *toda* conversa gera registro,
independentemente do desfecho. Por isso nada aqui depende de a conversa ter
terminado bem, ou de ter terminado.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import AutorMensagem, pg_enum


class Conversa(Base):
    __tablename__ = "conversas"

    id: Mapped[int] = mapped_column(primary_key=True)

    iniciada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Nulo enquanto a conversa está aberta — e nulo para sempre quando o
    # interessado simplesmente some, que é o caso mais comum. NOT NULL aqui
    # obrigaria a inventar um fim para toda conversa abandonada.
    encerrada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # `canal` e `desfecho` são texto curto, não enum, porque o comportamento os
    # nomeia sem enumerar seus valores. Enum é constraint boa quando o
    # vocabulário está decidido; aqui ele fixaria no esquema um vocabulário
    # inventado por nós, e cada correção viraria migration. Viram enum quando a
    # lista existir.
    canal: Mapped[str] = mapped_column(String(32), index=True)
    desfecho: Mapped[str | None] = mapped_column(String(32), nullable=True)

    mensagens: Mapped[list["Mensagem"]] = relationship(
        back_populates="conversa",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Mensagem.criada_em",
    )


class Mensagem(Base):
    __tablename__ = "mensagens"

    id: Mapped[int] = mapped_column(primary_key=True)

    # CASCADE em toda a cadeia da conversa: apagar uma conversa é apagar o que
    # foi dito nela. É também o caminho de exclusão a pedido do titular — dado
    # pessoal não pode sobreviver órfão à conversa que o produziu.
    conversa_id: Mapped[int] = mapped_column(
        ForeignKey("conversas.id", ondelete="CASCADE"),
        index=True,
    )

    autor: Mapped[AutorMensagem] = mapped_column(pg_enum(AutorMensagem, "autor_mensagem"))
    conteudo: Mapped[str] = mapped_column(Text)
    criada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversa: Mapped["Conversa"] = relationship(back_populates="mensagens")
    trechos_usados: Mapped[list["MensagemTrecho"]] = relationship(
        back_populates="mensagem",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MensagemTrecho(Base):
    """Quais trechos alimentaram cada resposta do bot, e com que semelhança.

    É o registro de auditoria da seção 9: permite reconstruir, meses depois, com
    que base o bot afirmou o que afirmou.
    """

    __tablename__ = "mensagem_trechos"
    __table_args__ = (
        CheckConstraint(
            "similaridade >= 0 AND similaridade <= 1",
            name="similaridade_entre_0_e_1",
        ),
    )

    # Chave composta: o par (resposta, trecho) já identifica a linha, e a
    # composição impede o mesmo trecho ser registrado duas vezes na mesma
    # resposta. Não há id substituto porque não há nada que referencie esta
    # tabela.
    mensagem_id: Mapped[int] = mapped_column(
        ForeignKey("mensagens.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # RESTRICT, e não CASCADE: um trecho que já justificou uma resposta não pode
    # sumir sem deixar rastro — auditoria que a reindexação apaga não é
    # auditoria. Na prática isto impõe uma regra à indexação da fase 3: trecho
    # já usado não se apaga; e documento já usado não se apaga, tira-se da busca
    # com `indexar = false`. É o único ponto em que a estrutura decide uma regra
    # operacional, e é deliberado.
    trecho_id: Mapped[int] = mapped_column(
        ForeignKey("trechos.id", ondelete="RESTRICT"),
        primary_key=True,
    )

    # Semelhança entre a pergunta e o trecho, no momento da busca. `float`
    # (dupla precisão) e não `numeric`: é medida, não dinheiro — não se soma
    # nem se compara por igualdade exata. Fica gravada porque é irreprodutível:
    # reexecutar a busca hoje usaria outro índice, outro modelo e outra base.
    similaridade: Mapped[float] = mapped_column(Float)

    mensagem: Mapped["Mensagem"] = relationship(back_populates="trechos_usados")


__all__ = ["Conversa", "Mensagem", "MensagemTrecho"]
