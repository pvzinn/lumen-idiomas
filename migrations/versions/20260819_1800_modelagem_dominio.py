"""Modelagem do domínio: base de conhecimento, conversa e comercial

Cria as sete tabelas da seção 9 de `docs/comportamento.md`.

Nota sobre `vector(1536)`: a dimensão está escrita à mão aqui, e não importada
de `app.core.constants`. Migration é um registro do que aconteceu no banco numa
data; se ela lesse a constante, mudar o modelo de embedding amanhã reescreveria
retroativamente o que esta revisão fez, e um `upgrade` do zero produziria um
esquema diferente do que os bancos existentes têm.

Revision ID: 0002_modelagem_dominio
Revises: 0001_enable_pgvector
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0002_modelagem_dominio"
down_revision: str | None = "0001_enable_pgvector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Vocabulários fechados, criados como tipos `enum` do Postgres.
#
# Criados por `CREATE TYPE` explícito, e não deixados a cargo do
# `op.create_table`: o tipo `publico_documento` só aparece dentro de um array, e
# nesse caso o SQLAlchemy não emite a criação. Fazer todos pelo mesmo caminho
# evita a assimetria de um ser criado de um jeito e os outros de outro.
ENUMS: dict[str, tuple[str, ...]] = {
    "topico_documento": ("institucional", "academico", "operacional", "comercial"),
    "publico_documento": ("interessados", "alunos", "empresas"),
    "autor_mensagem": ("usuario", "bot"),
    "categoria_escalonamento": (
        "sem_resposta",
        "negociacao",
        "dado_individual",
        "agendamento",
        "reclamacao",
        "vaga",
        "pedido_humano",
    ),
    "tipo_contato": ("whatsapp", "email"),
    "idioma_interesse": ("ingles", "espanhol", "ambos"),
    "para_quem": ("proprio", "dependente"),
    "modalidade_interesse": ("presencial", "online", "indiferente"),
}


def _enum(nome: str) -> postgresql.ENUM:
    """Referência a um tipo já criado por `_criar_tipos`."""
    return postgresql.ENUM(*ENUMS[nome], name=nome, create_type=False)


def _criar_tipos() -> None:
    for nome, valores in ENUMS.items():
        rotulos = ", ".join(f"'{v}'" for v in valores)
        op.execute(f"CREATE TYPE {nome} AS ENUM ({rotulos})")


# Os `CheckConstraint` abaixo levam nome curto ("ordem_nao_negativa") porque a
# convenção de `app.db.base` — que o Alembic herda via `target_metadata` — já
# antepõe `ck_<tabela>_`. Passar o nome completo aqui produziria
# `ck_trechos_ck_trechos_ordem_nao_negativa`.
def upgrade() -> None:
    _criar_tipos()

    # --- Base de conhecimento -------------------------------------------------
    op.create_table(
        "documentos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("identificador", sa.String(length=64), nullable=False),
        sa.Column("arquivo", sa.String(length=255), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("topico", _enum("topico_documento"), nullable=False),
        sa.Column("publico", postgresql.ARRAY(_enum("publico_documento")), nullable=False),
        sa.Column("indexar", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("atualizado_em", sa.Date(), nullable=False),
        sa.Column("hash_conteudo", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_documentos"),
        sa.UniqueConstraint("identificador", name="uq_documentos_identificador"),
        sa.UniqueConstraint("arquivo", name="uq_documentos_arquivo"),
    )

    op.create_table(
        "trechos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("documento_id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=200), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("ordem", sa.SmallInteger(), nullable=False),
        # Sem índice HNSW nem IVFFlat. São 83 trechos: nesse volume a varredura
        # sequencial responde em milissegundos e é *exata*, enquanto todo índice
        # de vetor é aproximado — hoje o índice trocaria precisão por um ganho
        # de tempo imperceptível, e ainda exigiria escolher `m` e
        # `ef_construction` no escuro.
        #
        # Rever quando a base passar de alguns milhares de trechos ou quando a
        # latência medida da busca incomodar. O índice entra em migration
        # própria, com nome começando em `ix_vector_` — o `include_object` do
        # `migrations/env.py` já protege esse prefixo do autogenerate.
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.ForeignKeyConstraint(
            ["documento_id"],
            ["documentos.id"],
            name="fk_trechos_documento_id_documentos",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trechos"),
        sa.UniqueConstraint("documento_id", "ordem", name="uq_trechos_documento_id_ordem"),
        sa.CheckConstraint("ordem >= 0", name="ordem_nao_negativa"),
    )
    op.create_index("ix_trechos_documento_id", "trechos", ["documento_id"])

    # --- Conversa -------------------------------------------------------------
    op.create_table(
        "conversas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "iniciada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("encerrada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canal", sa.String(length=32), nullable=False),
        sa.Column("desfecho", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_conversas"),
    )
    op.create_index("ix_conversas_iniciada_em", "conversas", ["iniciada_em"])
    op.create_index("ix_conversas_canal", "conversas", ["canal"])

    op.create_table(
        "mensagens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversa_id", sa.Integer(), nullable=False),
        sa.Column("autor", _enum("autor_mensagem"), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column(
            "criada_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversa_id"],
            ["conversas.id"],
            name="fk_mensagens_conversa_id_conversas",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mensagens"),
    )
    op.create_index("ix_mensagens_conversa_id", "mensagens", ["conversa_id"])

    op.create_table(
        "mensagem_trechos",
        sa.Column("mensagem_id", sa.Integer(), nullable=False),
        sa.Column("trecho_id", sa.Integer(), nullable=False),
        sa.Column("similaridade", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["mensagem_id"],
            ["mensagens.id"],
            name="fk_mensagem_trechos_mensagem_id_mensagens",
            ondelete="CASCADE",
        ),
        # RESTRICT: registro de auditoria que a reindexação apaga não é
        # auditoria. Trecho já usado numa resposta não pode ser removido; um
        # documento que já respondeu algo sai da busca com `indexar = false`,
        # não com DELETE.
        sa.ForeignKeyConstraint(
            ["trecho_id"],
            ["trechos.id"],
            name="fk_mensagem_trechos_trecho_id_trechos",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("mensagem_id", "trecho_id", name="pk_mensagem_trechos"),
        sa.CheckConstraint(
            "similaridade >= 0 AND similaridade <= 1",
            name="similaridade_entre_0_e_1",
        ),
    )

    # --- Comercial ------------------------------------------------------------
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversa_id", sa.Integer(), nullable=False),
        # Anuláveis de propósito, inclusive os que a seção 5.3 marca como
        # obrigatórios: a seção 5.2 manda registrar o que já foi informado
        # quando a coleta é abandonada no meio. "Lead parcial é lead."
        sa.Column("nome", sa.String(length=120), nullable=True),
        sa.Column("contato", sa.String(length=120), nullable=True),
        sa.Column("tipo_contato", _enum("tipo_contato"), nullable=True),
        sa.Column("idioma_interesse", _enum("idioma_interesse"), nullable=True),
        sa.Column("para_quem", _enum("para_quem"), nullable=True),
        sa.Column("idade_aluno", sa.SmallInteger(), nullable=True),
        sa.Column("modalidade_interesse", _enum("modalidade_interesse"), nullable=True),
        sa.Column("unidade_interesse", sa.String(length=80), nullable=True),
        sa.Column("disponibilidade", sa.Text(), nullable=True),
        sa.Column("objetivo", sa.Text(), nullable=True),
        sa.Column("consentimento", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversa_id"],
            ["conversas.id"],
            name="fk_leads_conversa_id_conversas",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_leads"),
        sa.UniqueConstraint("conversa_id", name="uq_leads_conversa_id"),
        sa.CheckConstraint("idade_aluno IS NULL OR idade_aluno > 0", name="idade_aluno_positiva"),
    )

    op.create_table(
        "escalonamentos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversa_id", sa.Integer(), nullable=False),
        sa.Column("mensagem_id", sa.Integer(), nullable=False),
        # Tabela única para os sete motivos. Não existe `nao_respondidas`:
        # "sem resposta na base" é o sétimo valor desta coluna, e o relatório de
        # lacunas da base é um filtro por ela.
        sa.Column("categoria", _enum("categoria_escalonamento"), nullable=False),
        sa.Column("pergunta", sa.Text(), nullable=False),
        sa.Column("lead_id", sa.Integer(), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolvido", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversa_id"],
            ["conversas.id"],
            name="fk_escalonamentos_conversa_id_conversas",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mensagem_id"],
            ["mensagens.id"],
            name="fk_escalonamentos_mensagem_id_mensagens",
            ondelete="CASCADE",
        ),
        # SET NULL: apagar o lead a pedido do titular não pode apagar o registro
        # de que a pergunta ficou sem resposta.
        sa.ForeignKeyConstraint(
            ["lead_id"],
            ["leads.id"],
            name="fk_escalonamentos_lead_id_leads",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_escalonamentos"),
    )
    op.create_index("ix_escalonamentos_conversa_id", "escalonamentos", ["conversa_id"])
    op.create_index("ix_escalonamentos_mensagem_id", "escalonamentos", ["mensagem_id"])
    op.create_index("ix_escalonamentos_categoria", "escalonamentos", ["categoria"])
    op.create_index("ix_escalonamentos_criado_em", "escalonamentos", ["criado_em"])


def downgrade() -> None:
    # Ordem inversa da criação: quem tem FK cai antes de quem é referenciado.
    op.drop_table("escalonamentos")
    op.drop_table("leads")
    op.drop_table("mensagem_trechos")
    op.drop_table("mensagens")
    op.drop_table("conversas")
    op.drop_table("trechos")
    op.drop_table("documentos")

    # Os tipos não caem junto com as tabelas: `DROP TABLE` não remove o tipo.
    for nome in ENUMS:
        op.execute(f"DROP TYPE {nome}")
