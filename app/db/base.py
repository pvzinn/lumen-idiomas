"""Base declarativa do SQLAlchemy.

Todo modelo herda de `Base`. O Alembic lê `Base.metadata` para descobrir o
esquema desejado e comparar com o banco real ao gerar migrations.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Convenção de nomes para constraints e índices.
#
# Sem ela, o Postgres batiza sozinho o que não tiver nome explícito
# (`documentos_identificador_key`, `trechos_documento_id_fkey`). Isso só
# incomoda no dia em que uma migration precisa remover uma constraint: o
# `op.drop_constraint` exige o nome, e o nome varia conforme quem criou a
# tabela — `create_all` num teste, migration em produção. Com a convenção o
# nome é derivado do esquema e é o mesmo nos dois caminhos.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
