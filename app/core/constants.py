"""Constantes de domínio. Não são configuráveis por ambiente.

O que está aqui não muda entre local, staging e produção. Um valor que
diferisse por ambiente quebraria o banco: ver `EMBEDDING_DIM`.
"""

# Dimensão do vetor de embedding.
#
# Deixou de ser variável de ambiente porque nunca foi configuração de verdade:
# a dimensão faz parte do tipo da coluna (`vector(n)`), então mudá-la é uma
# migration, não um redeploy. Como variável de ambiente ela criava a ilusão do
# contrário — bastava um ambiente subir com valor diferente do que está no banco
# para toda inserção de trecho falhar, e o erro apareceria longe da causa.
#
# Para trocar de modelo de embedding: altere aqui, gere a migration que altera
# o tipo da coluna (o `compare_type=True` do `env.py` a detecta) e reindexe a
# base inteira — vetores de dimensões diferentes não são comparáveis.
#
# 1024 porque é o valor default da família Voyage 4 (256/512/1024/2048
# disponíveis) mais próximo do 1536 anterior; a família não oferece 1536.
EMBEDDING_DIM = 1024

# Modelo usado para vetorizar os trechos da base de conhecimento (indexação).
MODELO_EMBEDDING_DOCUMENTOS = "voyage-4-lite"

# Modelo usado para vetorizar a pergunta do usuário, na busca (tarefa 3.3).
#
# Hoje tem o mesmo valor de `MODELO_EMBEDDING_DOCUMENTOS`, mas é uma constante
# separada de propósito: os modelos da família Voyage 4 compartilham espaço
# vetorial entre si, então a tarefa 3.4 vai testar recuperação assimétrica —
# indexar com um modelo maior (`voyage-4` ou `voyage-4-large`) e buscar com o
# lite, mais barato e mais rápido por ser chamado a cada pergunta. Trocar só
# esta constante troca só o lado da busca, sem reindexar a base.
MODELO_EMBEDDING_CONSULTAS = "voyage-4-lite"
