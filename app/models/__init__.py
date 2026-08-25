"""Modelos ORM.

Todo modelo novo precisa ser importado aqui. O `env.py` do Alembic importa este
pacote para popular `Base.metadata`; um modelo que não aparece neste arquivo é
invisível para o autogenerate — e o efeito não é "não aparece na migration", é
*some do esquema* na migration seguinte, porque o autogenerate compara o banco
real com um metadata que não o contém e conclui que a tabela deve ser removida.

As tabelas saem da seção 9 de `docs/comportamento.md`.
"""

from app.db.base import Base
from app.models.comercial import Escalonamento, Lead
from app.models.conhecimento import Documento, Trecho
from app.models.conversa import Conversa, Mensagem, MensagemTrecho
from app.models.enums import (
    AutorMensagem,
    CategoriaEscalonamento,
    IdiomaInteresse,
    ModalidadeInteresse,
    ParaQuem,
    PublicoDocumento,
    TipoContato,
    TopicoDocumento,
)

__all__ = [
    "AutorMensagem",
    "Base",
    "CategoriaEscalonamento",
    "Conversa",
    "Documento",
    "Escalonamento",
    "IdiomaInteresse",
    "Lead",
    "Mensagem",
    "MensagemTrecho",
    "ModalidadeInteresse",
    "ParaQuem",
    "PublicoDocumento",
    "TipoContato",
    "TopicoDocumento",
    "Trecho",
]
