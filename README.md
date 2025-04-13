# Trabalho_Framework_Django
🧠 Aplicação Web para Processamento de Transcrições Longas com LLM

🎯 Objetivo do Projeto
Esta aplicação foi desenvolvida para resolver um problema prático do meu trabalho:

Corrigir ortograficamente transcrições longas de palestras sem que trechos sejam resumidos ou omitidos pela IA.

⚠️ Desafio
As transcrições são muito extensas.

Modelos de linguagem como o GPT possuem limite de tokens (janela de contexto).

Quando enviamos textos longos demais, a LLM ignora partes do conteúdo ou faz resumos.

🧩 Solução Implementada
A aplicação:

💾 Recebe um arquivo .txt com a transcrição original.

✂️ Divide automaticamente o texto em chunks, respeitando o limite de contexto.

📜 Para cada chunk:

Adiciona um prompt fixo (“Corrija o texto abaixo:”).

Envia para o modelo GPT da OpenAI.

Recebe o texto corrigido, sem alterações de conteúdo.

🗃️ Armazena os resultados em arquivos .txt e os associa ao original no banco de dados.

🌐 O usuário pode visualizar e baixar os textos corrigidos pela interface web.

⚙️ Tecnologias Utilizadas
Django + Bootstrap (backend e interface)
OpenAI GPT (via API)
