"""Constantes de domínio. Não são configuráveis por ambiente.

O que está aqui não muda entre local, staging e produção. Um valor que
diferisse por ambiente quebraria o banco: ver `EMBEDDING_DIM`.
"""

# Dimensão do vetor de embedding.
#
# Deixou de ser variável de ambiente porque nunca foi configuração de verdade:
# a dimensão faz parte do tipo da coluna (`vector(1536)`), então mudá-la é uma
# migration, não um redeploy. Como variável de ambiente ela criava a ilusão do
# contrário — bastava um ambiente subir com valor diferente do que está no banco
# para toda inserção de trecho falhar, e o erro apareceria longe da causa.
#
# Para trocar de modelo de embedding: altere aqui, gere a migration que altera
# o tipo da coluna (o `compare_type=True` do `env.py` a detecta) e reindexe a
# base inteira — vetores de dimensões diferentes não são comparáveis.
EMBEDDING_DIM = 1536
