"""Base de conhecimento indexada: documentos e seus trechos.

Espelha `knowledge-base/*.md`. O arquivo continua sendo a fonte da verdade — o
banco é uma projeção dele, reconstruível a qualquer momento pela reindexação.
"""

from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import EMBEDDING_DIM
from app.db.base import Base
from app.models.enums import PublicoDocumento, TopicoDocumento, pg_enum


class Documento(Base):
    """Um registro por arquivo `.md` da base de conhecimento."""

    __tablename__ = "documentos"

    id: Mapped[int] = mapped_column(primary_key=True)

    # O campo `id` do cabeçalho YAML (`a-escola`, `valores-e-pagamento`). É
    # chave natural e estável, mas não é a chave primária: se um dia for
    # renomeado, renomear a PK arrastaria as FKs de trechos e de auditoria.
    # Fica como UNIQUE, que dá a garantia sem o custo.
    identificador: Mapped[str] = mapped_column(String(64), unique=True)

    # Nome do arquivo de origem. UNIQUE porque dois registros apontando para o
    # mesmo arquivo significam indexação duplicada, não dois documentos.
    arquivo: Mapped[str] = mapped_column(String(255), unique=True)

    titulo: Mapped[str] = mapped_column(String(200))
    topico: Mapped[TopicoDocumento] = mapped_column(pg_enum(TopicoDocumento, "topico_documento"))

    # `publico` é lista no YAML (`[interessados, alunos]`). Array de enum em vez
    # de tabela de associação: são três valores fixos, sem atributos próprios e
    # sem vida fora do documento — uma tabela de ligação aqui seria cerimônia.
    publico: Mapped[list[PublicoDocumento]] = mapped_column(
        ARRAY(pg_enum(PublicoDocumento, "publico_documento"))
    )

    # Filtro de recuperação, não decoração: a busca só considera trechos de
    # documentos com `indexar` verdadeiro. Default no servidor para que uma
    # inserção que omita a coluna não deixe o documento fora da busca por
    # engano — o default seguro é participar.
    indexar: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    # Data editorial do cabeçalho YAML: quando o *conteúdo* foi revisado por uma
    # pessoa. Não é carimbo de linha, por isso é `date` e não `timestamptz` — o
    # YAML traz `YYYY-MM-DD` e guardar hora seria inventar precisão.
    atualizado_em: Mapped[date] = mapped_column(Date)

    # SHA-256 do arquivo no momento da indexação, em hexadecimal (64 chars).
    # É o que responde "este arquivo mudou desde a última vez?" sem reler e
    # reprocessar os 83 trechos — e sem depender do mtime do sistema de
    # arquivos, que muda em todo `git checkout`.
    hash_conteudo: Mapped[str] = mapped_column(String(64))

    trechos: Mapped[list["Trecho"]] = relationship(
        back_populates="documento",
        cascade="all, delete-orphan",
        # O `ON DELETE CASCADE` está no banco; `passive_deletes` impede o
        # SQLAlchemy de carregar os filhos só para apagá-los um a um.
        passive_deletes=True,
        order_by="Trecho.ordem",
    )


class Trecho(Base):
    """Um registro por seção `##` de um documento. É a unidade de recuperação."""

    __tablename__ = "trechos"
    __table_args__ = (
        # A ordem identifica a seção dentro do documento; repetida, a
        # reindexação estaria gravando a mesma seção duas vezes.
        UniqueConstraint("documento_id", "ordem"),
        CheckConstraint("ordem >= 0", name="ordem_nao_negativa"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # CASCADE: um trecho não existe sem o documento que o originou. Apagar o
    # documento apaga seus trechos — que é exatamente o que a reindexação faz.
    documento_id: Mapped[int] = mapped_column(
        ForeignKey("documentos.id", ondelete="CASCADE"),
        index=True,
    )

    # Título da seção `##`, sem o `##`. Entra no texto embeddado junto com o
    # conteúdo: "Quanto custa a mensalidade" carrega sinal que o corpo não tem.
    titulo: Mapped[str] = mapped_column(String(200))

    conteudo: Mapped[str] = mapped_column(Text)

    # Posição da seção no arquivo, base 0. `smallint` porque o maior documento
    # tem 9 seções; a base inteira tem 83 trechos.
    ordem: Mapped[int] = mapped_column(SmallInteger)

    # Nulo entre inserir o trecho e calcular o embedding. A indexação grava o
    # texto primeiro e preenche os vetores depois, em lote; exigir NOT NULL aqui
    # obrigaria a manter tudo em memória até a API de embedding responder.
    # `Vector(n)` carrega a dimensão no tipo: ver `app.core.constants`.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)

    documento: Mapped["Documento"] = relationship(back_populates="trechos")


# Sem índice HNSW nem IVFFlat, por ora.
#
# São 83 trechos. Nesse tamanho o Postgres varre a tabela inteira em alguns
# milissegundos e a busca sequencial é *exata* — índice de vetor é aproximado
# por construção, então adotá-lo agora trocaria precisão por um ganho de tempo
# que ninguém percebe. O filtro `ix_vector_*` do `migrations/env.py` continua
# valendo para quando o índice existir.
#
# Rever quando a base passar de alguns milhares de trechos, ou quando a latência
# medida da busca justificar. Aí o índice entra em migration própria, com
# `lists`/`m`/`ef_construction` escolhidos sobre o volume real.
__all__ = ["Documento", "Trecho"]
