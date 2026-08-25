"""Vocabulários fechados do domínio.

Só vira `enum` do Postgres o vocabulário que `docs/comportamento.md` enumera
explicitamente. O que o documento cita mas não enumera — `canal` e `desfecho`
da conversa — fica como texto curto, porque inventar valores agora fixaria no
esquema um vocabulário que ninguém definiu, e corrigir enum é migration.

Os valores gravados no banco são as próprias strings abaixo (`values_callable`
nas colunas), não os nomes dos membros Python. São iguais hoje; a explicitação
evita que renomear um membro altere silenciosamente o dado.
"""

from enum import Enum, StrEnum

from sqlalchemy import Enum as SAEnum


class TopicoDocumento(StrEnum):
    """Campo `topico` do cabeçalho YAML dos arquivos da base."""

    INSTITUCIONAL = "institucional"
    ACADEMICO = "academico"
    OPERACIONAL = "operacional"
    COMERCIAL = "comercial"


class PublicoDocumento(StrEnum):
    """Campo `publico` do cabeçalho YAML. É lista: a coluna é array deste tipo."""

    INTERESSADOS = "interessados"
    ALUNOS = "alunos"
    EMPRESAS = "empresas"


class AutorMensagem(StrEnum):
    INTERESSADO = "usuario"
    BOT = "bot"


class CategoriaEscalonamento(StrEnum):
    """As seis categorias da seção 4, mais `sem_resposta`.

    `sem_resposta` não é um evento de outra natureza: é o mesmo fato — o bot não
    respondeu e encaminhou — com outro motivo. Por isso mora aqui, e não numa
    tabela `nao_respondidas` paralela. O relatório de maior valor comercial
    ("as perguntas que seu material não responde") é um filtro por esta coluna.
    """

    SEM_RESPOSTA = "sem_resposta"
    NEGOCIACAO = "negociacao"
    DADO_INDIVIDUAL = "dado_individual"
    AGENDAMENTO = "agendamento"
    RECLAMACAO = "reclamacao"
    VAGA = "vaga"
    PEDIDO_HUMANO = "pedido_humano"


class TipoContato(StrEnum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class IdiomaInteresse(StrEnum):
    INGLES = "ingles"
    ESPANHOL = "espanhol"
    AMBOS = "ambos"


class ParaQuem(StrEnum):
    """Muda a faixa etária ofertada e quem assina o contrato (seção 5.3)."""

    PROPRIO = "proprio"
    DEPENDENTE = "dependente"


class ModalidadeInteresse(StrEnum):
    PRESENCIAL = "presencial"
    ONLINE = "online"
    INDIFERENTE = "indiferente"


def pg_enum(enum_cls: type[Enum], name: str) -> SAEnum:
    """Coluna `enum` nativa do Postgres a partir de um enum Python.

    `values_callable` faz o banco guardar o valor (`"sem_resposta"`) e não o
    nome do membro (`"SEM_RESPOSTA"`), que é o default do SQLAlchemy.
    """
    return SAEnum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])
