"""Lógica de aplicação, independente de HTTP.

O que está aqui recebe uma sessão do banco e devolve dados; não conhece
requisição, resposta nem código de status. É o que permite a um script
(avaliação, tarefa 3.4) chamar a mesma função que a rota chama.
"""
